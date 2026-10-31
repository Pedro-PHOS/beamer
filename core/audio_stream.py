"""Opt-in system audio on a separate, authenticated TCP channel.

48 kHz, stereo, signed little-endian PCM16, 20 ms blocks. Pairing secrets are
HKDF-domain-separated from the input protocol; raw frames use its authenticated framing.
No microphone is selected. One receive stream, or one send stream, per machine.
"""
from __future__ import annotations

import base64
import contextlib
import socket
import sys
import threading
import time

from core import protocol
from core.i18n import tr

PORT = 24822
RATE = 48000
CHANNELS = 2
FRAMES = 960
BLOCK_BYTES = FRAMES * CHANNELS * 2
MAX_FRAME = max(BLOCK_BYTES, 4096) + 64
FORMAT = {'version': 1, 'rate': RATE, 'channels': CHANNELS, 'format': 's16le', 'frames': FRAMES}


def audio_token(token):
    """Never reuse input-channel keys or key identifiers for audio."""
    if not isinstance(token, str) or not token:
        raise ValueError('missing pairing token')
    key = protocol.hkdf_sha256(token.encode('utf-8'), b'beamer-audio-v1', b'audio-pair')
    return base64.urlsafe_b64encode(key).decode('ascii').rstrip('=')


def eligible(peer):
    return (peer.get('platform') in ('windows', 'linux') and peer.get('id')
            and peer.get('token') and peer.get('in_use', True) and not peer.get('left_out', False))


def check_hello(message, own_id, peer_id):
    expected = dict(FORMAT, sender=peer_id, receiver=own_id)
    if message != {'type': 'audio_hello', 'data': expected}:
        raise ValueError('unsupported audio format or wrong peer identity')


def close_socket(sock):
    if sock is not None:
        with contextlib.suppress(OSError):
            sock.shutdown(socket.SHUT_RDWR)
        with contextlib.suppress(OSError):
            sock.close()


@contextlib.contextmanager
def backend_context(factory):
    # WASAPI needs a COM apartment on every worker, including after a reconnect.
    # SoundCard initializes COM during its first Windows import. Load it before
    # our per-worker initialization: otherwise its S_FALSE result is misreported
    # as Error 0x100000001 by SoundCard 0.4.5. The factory must not open devices.
    backend = factory()
    com = None
    if sys.platform == 'win32':
        import pythoncom
        pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
        com = pythoncom
    try:
        yield backend
    finally:
        if com is not None:
            com.CoUninitialize()


class SoundCardBackend:
    """Lazy import: disabled audio neither loads audio libraries nor opens devices."""
    def __init__(self):
        import numpy as np
        import soundcard as sc
        self.np, self.sc = np, sc

    @contextlib.contextmanager
    def capture(self):
        speaker = self.sc.default_speaker()
        if speaker is None:
            raise RuntimeError('No default output device')
        self.capture_device_id = speaker.id
        # Exact IDs only. Fuzzy microphone lookup could capture a real microphone.
        ids = {str(speaker.id), str(speaker.id) + '.monitor'}
        monitor = next((m for m in self.sc.all_microphones(include_loopback=True)
                        if m.isloopback and str(m.id) in ids), None)
        if monitor is None:
            raise RuntimeError('No loopback monitor for the default output device')
        with monitor.recorder(samplerate=RATE, channels=CHANNELS, blocksize=FRAMES) as recorder:
            yield recorder

    def mute_local(self):
        if sys.platform != 'win32':
            raise RuntimeError('Local audio mute is currently supported on Windows only')
        from core.audio_mute import muted_output
        return muted_output(self.capture_device_id)

    def record(self, recorder):
        data = recorder.record(numframes=FRAMES)
        data = self.np.nan_to_num(data, nan=0.0, posinf=1.0, neginf=-1.0)
        if data.shape != (FRAMES, CHANNELS):
            raise ValueError('Unexpected capture block shape')
        return (self.np.clip(data, -1, 1) * 32767).astype('<i2').tobytes()

    @contextlib.contextmanager
    def playback(self):
        speaker = self.sc.default_speaker()
        if speaker is None:
            raise RuntimeError('No default output device')
        with speaker.player(samplerate=RATE, channels=CHANNELS, blocksize=FRAMES) as player:
            yield player

    def play(self, player, block):
        data = self.np.frombuffer(block, dtype='<i2').reshape(FRAMES, CHANNELS)
        player.play(data.astype('float32') / 32768.0)


class AudioEngine:
    """An immutable configuration owns its sockets and threads until stop().

    Socket writes are bounded by a timeout and small OS buffers. No unbounded audio
    queue is kept, and no audio operation runs on the Qt/input threads.
    """
    def __init__(self, peers, own_id, *, target='', receive=False, backend=SoundCardBackend,
                 bind_host='0.0.0.0', port=PORT, mute_local=False):
        if target and receive:
            raise ValueError('Sending and receiving together can create an audio feedback loop')
        self.peers, self.own_id = peers, own_id
        self.target, self.receive = target, receive
        self.mute_local = mute_local
        self.backend_factory = backend
        self.bind_host, self.port = bind_host, port
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.sockets = set()
        self.thread = None
        self.status = tr('Audio is off.')
        self.error = ''
        self.bound_port = None

    def _status(self, status, error=''):
        with self.lock:
            self.status, self.error = status, str(error)[:240]

    def _register(self, sock):
        with self.lock:
            if self.stop_event.is_set():
                close_socket(sock)
                raise OSError('Audio stopped')
            self.sockets.add(sock)
        return sock

    def _close(self, sock):
        close_socket(sock)
        with self.lock:
            self.sockets.discard(sock)

    def start(self):
        if self.thread is not None or not (self.target or self.receive):
            return
        self.thread = threading.Thread(target=self._send if self.target else self._listen,
                                       name='Beamer-audio', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        with self.lock:
            sockets = list(self.sockets)
        for sock in sockets:
            close_socket(sock)
        self._status(tr('Audio is off.'))

    def _peer(self, ident):
        return next((p for p in self.peers() if eligible(p) and p['id'] == ident), None)

    def _send(self):
        while not self.stop_event.is_set():
            sock = None
            try:
                peer = self._peer(self.target)
                if not peer or not peer.get('host'):
                    raise ValueError('Selected destination is no longer paired or has no address')
                self._status(tr('Connecting audio to the selected computer…'))
                sock = self._register(socket.create_connection((peer['host'], self.port), timeout=2))
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 16384)
                session = protocol.LinkSession(audio_token(peer['token']), protocol.ROLE_INITIATOR)
                sock.sendall(session.preamble())
                deadline = time.monotonic() + 5
                session.accept_preamble(protocol.recv_link_preamble(sock, deadline))
                protocol.send_msg(sock, session, {'type': 'audio_hello',
                    'data': dict(FORMAT, sender=self.own_id, receiver=peer['id'])})
                reply = protocol.recv_msg(sock, session, limit=4096, deadline=deadline)
                if reply != {'type': 'audio_ready', 'data': FORMAT}:
                    raise ValueError('Destination did not enable audio reception or has an incompatible version')
                sock.settimeout(2)
                with backend_context(self.backend_factory) as backend, backend.capture() as capture, \
                        (backend.mute_local() if self.mute_local else contextlib.nullcontext()):
                    self._status(tr('Sending system audio to the selected computer.'))
                    next_check = 0
                    while not self.stop_event.is_set():
                        if time.monotonic() >= next_check:
                            current = self._peer(self.target)
                            if not current or current['token'] != peer['token'] or current.get('host') != peer['host']:
                                raise ValueError('Audio pairing or address changed')
                            next_check = time.monotonic() + 1
                        block = backend.record(capture)
                        if len(block) != BLOCK_BYTES:
                            raise ValueError('Unexpected audio block length')
                        if self.stop_event.is_set():
                            break
                        sock.sendall(session.seal_raw(block))
            except Exception as error:
                if not self.stop_event.is_set():
                    self._status(tr('Audio unavailable. Check the destination, reception and firewall.'), error)
            finally:
                if sock is not None:
                    self._close(sock)
            self.stop_event.wait(3)

    def _listen(self):
        listener = None
        try:
            listener = self._register(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((self.bind_host, self.port))
            listener.listen(2)
            listener.settimeout(0.25)
            self.bound_port = listener.getsockname()[1]
            self._status(tr('Ready to receive audio from a paired computer.'))
            while not self.stop_event.is_set():
                try:
                    connection, _ = listener.accept()
                except socket.timeout:
                    continue
                try:
                    self._register(connection)
                    self._receive(connection)
                except Exception as error:
                    if not self.stop_event.is_set():
                        self._status(tr('Ready to receive audio from a paired computer.'), error)
                finally:
                    self._close(connection)
        except Exception as error:
            if not self.stop_event.is_set():
                self._status(tr('Could not open the audio receiver.'), error)
        finally:
            if listener is not None:
                self._close(listener)

    def _receive(self, sock):
        sock.settimeout(2)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 16384)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        deadline = time.monotonic() + 5
        preamble = protocol.recv_link_preamble(sock, deadline)
        _, key_id, _ = protocol.split_preamble(preamble)
        peer = next((p for p in self.peers() if eligible(p)
                     and protocol.key_id(audio_token(p['token'])) == key_id), None)
        if peer is None:
            raise ValueError('Audio peer is not paired')
        session = protocol.LinkSession(audio_token(peer['token']), protocol.ROLE_RESPONDER)
        session.accept_preamble(preamble)
        sock.sendall(session.preamble())
        hello = protocol.recv_msg(sock, session, limit=4096, deadline=deadline)
        check_hello(hello, self.own_id, peer['id'])
        # Open hardware only after authentication. Failure means no readiness acknowledgment.
        with backend_context(self.backend_factory) as backend, backend.playback() as player:
            protocol.send_msg(sock, session, {'type': 'audio_ready', 'data': FORMAT})
            sock.settimeout(3)
            self._status(tr('Receiving audio. Sending is disabled to prevent feedback.'))
            next_check = 0
            while not self.stop_event.is_set():
                if time.monotonic() >= next_check:
                    current = self._peer(peer['id'])
                    if not current or current['token'] != peer['token']:
                        raise ValueError('Audio pairing was removed')
                    next_check = time.monotonic() + 1
                block = session.open_raw(protocol.recv_frame(sock, limit=MAX_FRAME,
                                                            deadline=time.monotonic() + 3))
                if len(block) != BLOCK_BYTES:
                    raise ValueError('Invalid audio frame size')
                if not self.stop_event.is_set():
                    backend.play(player, block)
