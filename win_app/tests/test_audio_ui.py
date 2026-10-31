"""Exercise actual Qt audio controls without opening devices or network sockets."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from types import SimpleNamespace, MethodType
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QApplication
import app_config
from kvm_bridge_win import WindowsApplication
from core import protocol


class AudioUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.ident = protocol.id_text(b'b' * 16)
        self.peers = [dict(id=self.ident, name='Linux PC', platform='linux', token='paired')]
        self.ui = SimpleNamespace(_config=app_config.Config(host='', port=24820, auth_token=''),
                                  book=SimpleNamespace(peers=lambda: self.peers),
                                  _audio_started=False, _persist=Mock(return_value=True))
        for name in ('_refresh_audio', '_change_audio'):
            setattr(self.ui, name, MethodType(getattr(WindowsApplication, name), self.ui))
        self.module = WindowsApplication._audio_module(self.ui, self.ui._config)
        self.addCleanup(self.module.deleteLater)

    def test_choose_destination_then_toggle_send_and_receive(self):
        self.assertFalse(self.ui.audio_send_check.isEnabled())
        self.ui.audio_target_combo.setCurrentIndex(1)
        self.assertEqual(self.ui._config.audio_target, self.ident)
        self.ui.audio_send_check.setChecked(True)
        self.assertTrue(self.ui._config.audio_send)
        self.ui.audio_receive_check.setChecked(True)
        self.assertTrue(self.ui._config.audio_receive)
        self.assertFalse(self.ui._config.audio_send)
        self.assertFalse(self.ui.audio_send_check.isChecked())
        self.assertEqual(self.ui._config.audio_target, self.ident)
        self.assertEqual(self.ui._persist.call_count, 3)

    def test_mute_is_opt_in_and_saved_without_changing_send_or_target(self):
        self.assertFalse(self.ui.audio_mute_check.isChecked())
        with patch('sys.platform', 'win32'):
            self.ui.audio_target_combo.setCurrentIndex(1)
            self.ui.audio_send_check.setChecked(True)
            self.assertTrue(self.ui.audio_mute_check.isEnabled())
            self.ui.audio_mute_check.setChecked(True)
            self.assertTrue(self.ui._config.audio_mute_local)
            self.assertTrue(self.ui._config.audio_send)
            self.assertEqual(self.ui._config.audio_target, self.ident)
            self.ui._persist.return_value = False
            self.ui.audio_mute_check.setChecked(False)
            self.assertTrue(self.ui._config.audio_mute_local)
            self.assertTrue(self.ui.audio_mute_check.isChecked())
            self.ui._persist.return_value = True
            self.ui.audio_send_check.setChecked(False)
            self.assertFalse(self.ui.audio_mute_check.isEnabled())

    def test_linux_mute_option_is_unavailable(self):
        with patch('sys.platform', 'linux'):
            self.ui.audio_target_combo.setCurrentIndex(1)
            self.ui.audio_send_check.setChecked(True)
            self.assertFalse(self.ui.audio_mute_check.isEnabled())

    def test_failed_save_restores_checkbox(self):
        self.ui._persist.return_value = False
        self.ui.audio_receive_check.setChecked(True)
        self.assertFalse(self.ui._config.audio_receive)
        self.assertFalse(self.ui.audio_receive_check.isChecked())

    def test_removed_target_requires_new_selection(self):
        self.ui.audio_target_combo.setCurrentIndex(1)
        self.ui.audio_send_check.setChecked(True)
        self.peers.clear()
        self.ui._refresh_audio()
        self.assertEqual(self.ui.audio_target_combo.currentData(), '')
        self.assertIn('Choose', self.ui.audio_status_label.text())
        self.assertEqual(self.ui._config.audio_target, self.ident)


if __name__ == '__main__':
    unittest.main()
