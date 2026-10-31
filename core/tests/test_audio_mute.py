"""Mute lifecycle checks use a fake endpoint and never change host sound settings."""
import unittest
from core.audio_mute import muted_output


class Endpoint:
    def __init__(self, previous=False):
        self.value = previous
        self.events = []

    def get(self):
        return self.value

    def set(self, value):
        self.value = value
        self.events.append(value)

    def close(self):
        self.events.append('close')


class MuteLifecycleTests(unittest.TestCase):
    def test_only_selected_device_is_muted_and_restored(self):
        endpoint = Endpoint()
        devices = []
        def controller(device):
            devices.append(device)
            return endpoint
        with muted_output('captured-endpoint', controller):
            self.assertTrue(endpoint.value)
        self.assertFalse(endpoint.value)
        self.assertEqual(endpoint.events, [True, False, 'close'])
        self.assertEqual(devices, ['captured-endpoint'])

    def test_initially_muted_output_stays_muted(self):
        endpoint = Endpoint(previous=True)
        with muted_output('endpoint', lambda _: endpoint):
            self.assertTrue(endpoint.value)
        self.assertTrue(endpoint.value)
        self.assertEqual(endpoint.events, ['close'])

    def test_failure_restores_output(self):
        endpoint = Endpoint()
        with self.assertRaisesRegex(OSError, 'network disconnected'):
            with muted_output('endpoint', lambda _: endpoint):
                raise OSError('network disconnected')
        self.assertFalse(endpoint.value)
        self.assertEqual(endpoint.events, [True, False, 'close'])

    def test_mute_failure_still_restores_and_closes_endpoint(self):
        endpoint = Endpoint()
        original = endpoint.set
        def fail(value):
            original(value)
            if value:
                raise OSError('mute failed')
        endpoint.set = fail
        with self.assertRaisesRegex(OSError, 'mute failed'):
            with muted_output('endpoint', lambda _: endpoint):
                self.fail('must not start transmission')
        self.assertFalse(endpoint.value)
        self.assertEqual(endpoint.events, [True, False, 'close'])

    def test_restore_failure_still_closes_endpoint(self):
        endpoint = Endpoint()
        def fail_restore(value):
            if not value:
                raise OSError('device disappeared')
        endpoint.set = fail_restore
        with self.assertRaisesRegex(OSError, 'device disappeared'):
            with muted_output('endpoint', lambda _: endpoint):
                pass
        self.assertEqual(endpoint.events, ['close'])
