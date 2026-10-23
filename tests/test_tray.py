import unittest
from unittest.mock import patch

from tray import TrayIcon


class _Icon:
    _systray_manager = None


class TrayTests(unittest.TestCase):
    def test_linux_requires_a_systray_manager(self):
        tray = TrayIcon(
            None,
            on_show=lambda: None,
            on_open_folder=lambda: None,
            on_toggle=lambda: None,
            on_quit=lambda: None,
        )
        tray.icon = _Icon()
        with patch("tray.sys.platform", "linux"):
            self.assertFalse(tray.docked)
            tray.icon._systray_manager = object()
            self.assertTrue(tray.docked)

    def test_non_linux_platforms_are_docked(self):
        tray = TrayIcon(
            None,
            on_show=lambda: None,
            on_open_folder=lambda: None,
            on_toggle=lambda: None,
            on_quit=lambda: None,
        )
        tray.icon = _Icon()
        with patch("tray.sys.platform", "win32"):
            self.assertTrue(tray.docked)


if __name__ == "__main__":
    unittest.main()
