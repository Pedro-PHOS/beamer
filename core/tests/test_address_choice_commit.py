"""Explicit address commits use the pin signal, including an unchanged address."""

from types import SimpleNamespace
import copy
import threading
import unittest
from unittest import mock

from core.tests.app_methods import load_methods


class AddressCommitTests(unittest.TestCase):
    def test_qt_pin_control_saves_only_the_chosen_machine(self):
        saved = {"peers": [{"token": "first", "host": "192.0.2.10", "host_pinned": True},
                           {"token": "second", "host": "192.0.2.11", "host_pinned": True}]}

        def write(_path, settings):
            saved.update(copy.deepcopy(settings))

        config = SimpleNamespace(SETTINGS_LOCK=threading.RLock(),
                                 load_settings=lambda _: copy.deepcopy(saved), write_settings=write)
        methods = load_methods("win_app/kvm_bridge_win.py", "WindowsApplication",
                               ("_edit_peer", "_set_peer_pin"),
                               {"app_config": config, "ConfigError": ValueError})
        window = methods()
        window.config_path = "synthetic"
        window._after_peers_edit = lambda: None
        window._set_peer_pin("first", False)
        self.assertIs(saved["peers"][0]["host_pinned"], False)
        self.assertIs(saved["peers"][1]["host_pinned"], True)
        window._set_peer_pin("first", True)
        self.assertIs(saved["peers"][0]["host_pinned"], True)
        self.assertEqual(saved["peers"][0]["host"], "192.0.2.10")

    def test_releasing_a_pin_allows_discovery_and_pinning_stops_drift(self):
        from core.tests.test_link import FakeClock, Side

        side = Side()
        side.peer().update(host="192.0.2.10", host_pinned=True)
        def set_pin(value):
            settings = side.settings.load()
            settings["peers"][0]["host_pinned"] = value
            side.settings.save(settings)
        set_pin(False)
        clock = FakeClock()
        link = side.link(clock=clock)
        clock.now += 11
        link.follow([{"name": "Far", "address": "198.51.100.10"}])
        self.assertEqual(link._try_host, "198.51.100.10")
        set_pin(True)
        link.follow([{"name": "Far", "address": "203.0.113.10"}])
        tried = []

        def offline(address, timeout=None):
            tried.append(address)
            link._stop.set()
            raise OSError("synthetic offline peer")

        link._factory = offline
        link._run()
        self.assertEqual(tried, [("192.0.2.10", 24820)])



if __name__ == "__main__":
    unittest.main()
