"""Audio transport tests use real TCP/encryption and synthetic audio devices."""
import base64
import contextlib
from dataclasses import replace
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core import audio_stream as audio, protocol
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'win_app'))
import app_config

A = protocol.id_text(b'a' * 16)
B = protocol.id_text(b'b' * 16)
TOKEN = base64.urlsafe_b64encode(bytes(range(32))).decode().rstrip('=')
BLOCK = b'\x10\x00\xf0\xff' * audio.FRAMES


def peer(ident, token=TOKEN):
    return dict(id=ident, token=token, platform='windows', host='127.0.0.1', in_use=True)


def until(predicate, seconds=4):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(.01)
    return False


class FakeBackend:
    def __init__(self):
        self.blocks = []
        self.captures = self.players = 0
        self.closed = 0
        self.muted = False
        self.mute_events = []

    @contextlib.contextmanager
    def capture(self):
        self.captures += 1
        try:
            yield self
        finally:
            self.closed += 1

    @contextlib.contextmanager
    def playback(self):
        self.players += 1
        try:
            yield self
        finally:
            self.closed += 1

    @contextlib.contextmanager
    def mute_local(self):
        self.muted = True
        self.mute_events.append('mute')
        try:
            yield
        finally:
            self.muted = False
            self.mute_events.append('restore')

    def record(self, capture):
        time.sleep(.02)
        return BLOCK

    def play(self, player, block):
        self.blocks.append(block)


class AudioTransportTests(unittest.TestCase):
    def start_receiver(self, peers=None):
        self.rx_backend = FakeBackend()
        self.allowed = peers if peers is not None else [peer(A)]
        self.rx = audio.AudioEngine(lambda: self.allowed, B, receive=True, port=0,
                                   bind_host='127.0.0.1', backend=lambda: self.rx_backend)
        self.rx.start()
        self.addCleanup(self.stop, self.rx)
        self.assertTrue(until(lambda: self.rx.bound_port is not None))
        return self.rx

    @staticmethod
    def stop(engine):
        engine.stop()
        if engine.thread:
            engine.thread.join(4)

    def start_sender(self, token=TOKEN, mute_local=False):
        self.tx_backend = FakeBackend()
        engine = audio.AudioEngine(lambda: [peer(B, token)], A, target=B,
            port=self.rx.bound_port, backend=lambda: self.tx_backend, mute_local=mute_local)
        engine.start()
        self.addCleanup(self.stop, engine)
        return engine

    def connect(self, token=TOKEN, sender=A):
        sock = socket.create_connection(('127.0.0.1', self.rx.bound_port), timeout=2)
        self.addCleanup(sock.close)
        session = protocol.LinkSession(audio.audio_token(token), protocol.ROLE_INITIATOR)
        sock.sendall(session.preamble())
        session.accept_preamble(protocol.recv_link_preamble(sock, time.monotonic()+2))
        protocol.send_msg(sock, session, {'type':'audio_hello',
             'data':dict(audio.FORMAT, sender=sender, receiver=B)})
        return sock, session

    def test_opt_in_mutes_only_while_streaming_and_restores_after_stop(self):
        self.start_receiver()
        tx = self.start_sender(mute_local=True)
        self.assertTrue(until(lambda: len(self.rx_backend.blocks) >= 2), tx.error)
        self.assertTrue(self.tx_backend.muted)
        self.assertFalse(self.rx_backend.muted)
        self.assertTrue(all(block == BLOCK for block in self.rx_backend.blocks))
        self.stop(tx)
        self.assertFalse(self.tx_backend.muted)
        self.assertEqual(self.tx_backend.mute_events, ['mute', 'restore'])

    def test_muted_sender_restores_after_receiver_disconnects(self):
        self.start_receiver()
        tx = self.start_sender(mute_local=True)
        self.assertTrue(until(lambda: len(self.rx_backend.blocks) >= 2), tx.error)
        self.stop(self.rx)
        self.assertTrue(until(lambda: self.tx_backend.mute_events == ['mute', 'restore']))
        self.assertFalse(self.tx_backend.muted)

    def test_disabled_audio_never_opens_devices_or_threads(self):
        backend = Mock(side_effect=AssertionError('must stay lazy'))
        engine = audio.AudioEngine(lambda: [], A, backend=backend)
        engine.start()
        self.assertIsNone(engine.thread)
        self.assertIsNone(engine.bound_port)
        backend.assert_not_called()

    def test_audio_key_is_domain_separated_from_input(self):
        token = audio.audio_token(TOKEN)
        self.assertNotEqual(protocol.key_id(TOKEN), protocol.key_id(token))
        self.assertEqual(token, audio.audio_token(TOKEN))
        self.assertNotEqual(token, audio.audio_token(TOKEN+'x'))

    def test_one_way_only_prevents_feedback(self):
        with self.assertRaises(ValueError):
            audio.AudioEngine(lambda: [], A, target=B, receive=True)

    def test_real_encrypted_stream_preserves_pcm_and_stops(self):
        self.start_receiver()
        tx = self.start_sender()
        self.assertTrue(until(lambda: len(self.rx_backend.blocks) >= 3), tx.error)
        self.assertTrue(all(x == BLOCK for x in self.rx_backend.blocks))
        self.assertEqual(self.tx_backend.captures, 1)
        tx.stop()
        self.assertTrue(until(lambda: not tx.thread.is_alive()))
        self.assertTrue(until(lambda: self.rx_backend.closed == 1))
        count = len(self.rx_backend.blocks)
        time.sleep(.08)
        self.assertEqual(len(self.rx_backend.blocks), count)

    def test_unknown_token_cannot_open_playback(self):
        self.start_receiver()
        self.start_sender(token='wrong-token')
        self.assertTrue(until(lambda: 'not paired' in self.rx.error))
        self.assertEqual(self.rx_backend.players, 0)

    def test_authenticated_wrong_identity_cannot_open_playback(self):
        self.start_receiver()
        sock, session = self.connect(sender=B)
        with self.assertRaises((OSError, protocol.ConnectionClosed)):
            protocol.recv_msg(sock, session, deadline=time.monotonic()+2)
        self.assertEqual(self.rx_backend.players, 0)

    def test_removing_pairing_stops_active_playback(self):
        self.start_receiver()
        self.start_sender()
        self.assertTrue(until(lambda: len(self.rx_backend.blocks) >= 2))
        self.allowed.clear()
        self.assertTrue(until(lambda: self.rx_backend.closed == 1, 3))

    def test_replayed_encrypted_frame_is_not_played_twice(self):
        self.start_receiver()
        sock, session = self.connect()
        protocol.recv_msg(sock, session, deadline=time.monotonic()+2)
        frame = session.seal_raw(BLOCK)
        sock.sendall(frame + frame)
        self.assertTrue(until(lambda: self.rx_backend.closed == 1))
        self.assertEqual(self.rx_backend.blocks, [BLOCK])

    def test_oversized_frame_is_rejected_before_allocation_or_playback(self):
        self.start_receiver()
        sock, session = self.connect()
        protocol.recv_msg(sock, session, deadline=time.monotonic()+2)
        sock.sendall(struct.pack('>I', audio.MAX_FRAME+1))
        self.assertTrue(until(lambda: self.rx_backend.closed == 1))
        self.assertEqual(self.rx_backend.blocks, [])

    def test_stop_receiver_closes_idle_stream(self):
        self.start_receiver()
        sock, session = self.connect()
        protocol.recv_msg(sock, session, deadline=time.monotonic()+2)
        self.rx.stop()
        self.assertTrue(until(lambda: not self.rx.thread.is_alive()))
        self.assertEqual(self.rx_backend.closed, 1)

    def test_pcm_size_and_format_are_fixed(self):
        self.start_receiver()
        sock, session = self.connect()
        protocol.recv_msg(sock, session, deadline=time.monotonic()+2)
        sock.sendall(session.seal_raw(b'short'))
        self.assertTrue(until(lambda: self.rx_backend.closed == 1))
        self.assertEqual(self.rx_backend.blocks, [])


class AudioDeviceTests(unittest.TestCase):
    def test_no_fallback_to_physical_microphone(self):
        backend = audio.SoundCardBackend.__new__(audio.SoundCardBackend)
        physical = SimpleNamespace(id='speaker', isloopback=False)
        backend.sc = SimpleNamespace(default_speaker=lambda: SimpleNamespace(id='speaker'),
                                     all_microphones=lambda **kw: [physical])
        with self.assertRaisesRegex(RuntimeError, 'loopback'):
            with backend.capture():
                self.fail('must not use a microphone')

    def test_capture_selects_only_exact_output_monitor(self):
        backend = audio.SoundCardBackend.__new__(audio.SoundCardBackend)
        recorder = object()
        physical = SimpleNamespace(id='speaker', isloopback=False)
        monitor = SimpleNamespace(id='speaker.monitor', isloopback=True,
                    recorder=lambda **kw: contextlib.nullcontext(recorder))
        backend.sc = SimpleNamespace(default_speaker=lambda: SimpleNamespace(id='speaker'),
                                     all_microphones=lambda **kw: [physical, monitor])
        with backend.capture() as captured:
            self.assertIs(captured, recorder)

    def test_pcm_conversion_sanitizes_non_finite_samples(self):
        import numpy as np
        backend = audio.SoundCardBackend.__new__(audio.SoundCardBackend)
        backend.np = np
        data = np.full((audio.FRAMES, audio.CHANNELS), np.nan)
        data[0] = [np.inf, -np.inf]
        block = backend.record(SimpleNamespace(record=lambda **kw: data))
        values = np.frombuffer(block, dtype='<i2')
        self.assertEqual(len(block), audio.BLOCK_BYTES)
        self.assertEqual(values[:4].tolist(), [32767, -32767, 0, 0])


class AudioSettingsTests(unittest.TestCase):
    def test_defaults_off_and_preferences_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'settings.json'
            cfg = app_config.load_config(path, unpaired_ok=True)
            self.assertFalse(cfg.audio_send)
            self.assertFalse(cfg.audio_receive)
            self.assertFalse(cfg.audio_mute_local)
            cfg = replace(cfg, audio_send=True, audio_target=B, audio_mute_local=True)
            app_config.save_config(path, cfg)
            loaded = app_config.load_config(path, unpaired_ok=True)
            self.assertTrue(loaded.audio_mute_local)
            self.assertEqual((loaded.audio_send, loaded.audio_receive, loaded.audio_target), (True, False, B))

    def test_invalid_or_duplex_preferences_are_refused(self):
        raw = app_config.config_to_dict(app_config.Config(host='', port=24820, auth_token=''))
        for values in ({'audio_mute_local':'yes'}, {'audio_send':'yes'}, {'audio_send':True, 'audio_receive':True},
                       {'audio_target':'not-an-id'}):
            with self.subTest(values=values), self.assertRaises(app_config.ConfigError):
                app_config.config_from_dict(dict(raw, **values))



class AudioWindowsCOMTests(unittest.TestCase):
    def test_first_library_import_precedes_worker_com_initialization(self):
        # SoundCard 0.4.5 rejects S_FALSE when COM is initialized before import.
        events = []
        com = SimpleNamespace(COINIT_MULTITHREADED=0,
            CoInitializeEx=lambda mode: events.append('initialize'),
            CoUninitialize=lambda: events.append('uninitialize'))
        backend = object()
        def factory():
            self.assertNotIn('initialize', events)
            events.append('import soundcard')
            return backend
        with patch.object(audio.sys, 'platform', 'win32'), patch.dict(sys.modules, pythoncom=com):
            with audio.backend_context(factory) as actual:
                self.assertIs(actual, backend)
                events.append('device access')
        self.assertEqual(events, ['import soundcard', 'initialize', 'device access', 'uninitialize'])

    def test_reconnect_initializes_each_worker_and_cleans_up_on_device_error(self):
        com = Mock(COINIT_MULTITHREADED=0)
        with patch.object(audio.sys, 'platform', 'win32'), patch.dict(sys.modules, pythoncom=com):
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError, 'device unavailable'):
                    with audio.backend_context(lambda: object()):
                        raise RuntimeError('device unavailable')
        self.assertEqual(com.CoInitializeEx.call_count, 2)
        self.assertEqual(com.CoUninitialize.call_count, 2)

    def test_linux_backend_does_not_import_pythoncom(self):
        with patch.object(audio.sys, 'platform', 'linux'), patch.dict(sys.modules, pythoncom=None):
            backend = object()
            with audio.backend_context(lambda: backend) as actual:
                self.assertIs(actual, backend)


if __name__ == '__main__':
    unittest.main()
