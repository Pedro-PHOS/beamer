"""Regression checks for the Windows/Linux fork's platform boundary."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'win_app'))
import platform_parts
import app_config
from core import keytable


class ForkPlatformTests(unittest.TestCase):
    def test_unsupported_os_never_falls_back_to_windows_backend(self):
        for name in ('darwin', 'freebsd'):
            with self.subTest(platform=name), self.assertRaisesRegex(RuntimeError, 'Windows and Linux'):
                platform_parts.load(name)

    def test_legacy_modifier_settings_keep_windows_linux_physical_keys(self):
        for style in ('semantic', 'positional', 'mac_layout'):
            raw = app_config.config_to_dict(app_config.Config(host='', port=24820, auth_token='', modifier_style=style))
            config = app_config.config_from_dict(raw)
            for source, target in (('windows', 'linux'), ('linux', 'windows')):
                for key in ('ctrl', 'ctrl_r', 'alt', 'alt_r', 'cmd', 'cmd_r', 'numpad_enter'):
                    with self.subTest(style=style, source=source, target=target, key=key):
                        self.assertEqual(keytable.wire_name(key, source, target, config.modifier_style), key)


if __name__ == '__main__':
    unittest.main()
