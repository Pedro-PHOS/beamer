"""Windows endpoint mute control. Imports no native APIs until explicitly enabled.

The endpoint ID comes from the active recorder, so a default-device change cannot
silence or restore a different speaker. All COM pointers stay on the audio worker.
"""
import ctypes
import uuid
from contextlib import contextmanager


class _GUID(ctypes.Structure):
    _fields_ = [('Data1', ctypes.c_uint32), ('Data2', ctypes.c_uint16),
                ('Data3', ctypes.c_uint16), ('Data4', ctypes.c_ubyte * 8)]

    @classmethod
    def of(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


def _check(result):
    if result < 0:
        raise OSError(f'Windows audio mute failed: 0x{result & 0xffffffff:08x}')


def _method(pointer, index, result, *arguments):
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(result, ctypes.c_void_p, *arguments)(table[index])


class WindowsEndpointMute:
    """IAudioEndpointVolume bound to one endpoint; caller owns COM initialization."""
    def __init__(self, device_id):
        self.pointer = ctypes.c_void_p()
        enum = ctypes.c_void_p()
        device = ctypes.c_void_p()
        hr = ctypes.c_int32
        guid_ptr = ctypes.POINTER(_GUID)
        output = ctypes.POINTER(ctypes.c_void_p)
        create = ctypes.WinDLL('ole32').CoCreateInstance
        create.argtypes = [guid_ptr, ctypes.c_void_p, ctypes.c_uint32, guid_ptr, output]
        create.restype = hr
        try:
            _check(create(ctypes.byref(_GUID.of('bcde0395-e52f-467c-8e3d-c4579291692e')),
                None, 23, ctypes.byref(_GUID.of('a95664d2-9614-4f35-a746-de8db63617e6')),
                ctypes.byref(enum)))
            # IMMDeviceEnumerator::GetDevice, after IUnknown and endpoint enumeration.
            _check(_method(enum, 5, hr, ctypes.c_wchar_p, output)(enum, str(device_id), ctypes.byref(device)))
            # IMMDevice::Activate(IID_IAudioEndpointVolume).
            _check(_method(device, 3, hr, guid_ptr, ctypes.c_uint32, ctypes.c_void_p, output)(
                device, ctypes.byref(_GUID.of('5cdf2c82-841e-4546-9722-0cf74078229a')),
                23, None, ctypes.byref(self.pointer)))
        except BaseException:
            self.close()
            raise
        finally:
            for pointer in (device, enum):
                if pointer.value:
                    _method(pointer, 2, ctypes.c_uint32)(pointer)

    def get(self):
        muted = ctypes.c_int32()
        _check(_method(self.pointer, 15, ctypes.c_int32, ctypes.POINTER(ctypes.c_int32))(
            self.pointer, ctypes.byref(muted)))
        return bool(muted.value)

    def set(self, muted):
        _check(_method(self.pointer, 14, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p)(
            self.pointer, int(muted), None))

    def close(self):
        if self.pointer.value:
            _method(self.pointer, 2, ctypes.c_uint32)(self.pointer)
            self.pointer = ctypes.c_void_p()


@contextmanager
def muted_output(device_id, controller=WindowsEndpointMute):
    """Restore the previous mute state on normal exit, cancellation or stream failure."""
    endpoint = controller(device_id)
    try:
        previous = endpoint.get()
        try:
            if not previous:
                endpoint.set(True)
            yield
        finally:
            # An already-muted device must stay muted. Never change its volume.
            if not previous:
                endpoint.set(previous)
    finally:
        endpoint.close()
