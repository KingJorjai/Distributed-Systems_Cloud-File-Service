"""Smoke test for the desktop GUI module (no display required)."""

import os
import sys
import types
import unittest

ORIGINALS = {}


def _install_mocks():
    global ORIGINALS
    for mod in ["tkinter", "tkinter.ttk", "tkinter.filedialog",
                "tkinter.simpledialog", "tkinter.messagebox", "tkinter.font",
                "app_logging", "autostart", "config", "gui_controller",
                "single_instance"]:
        ORIGINALS[mod] = sys.modules.get(mod)

    tk_mock = types.ModuleType("tkinter")
    tk_mock.Tk = type("Tk", (), {})
    tk_mock.StringVar = lambda *a, **k: None
    tk_mock.BooleanVar = lambda *a, **k: None
    tk_mock.Frame = type("Frame", (), {})
    tk_mock.Label = type("Label", (), {})
    tk_mock.Button = type("Button", (), {})
    tk_mock.Entry = type("Entry", (), {})
    tk_mock.Text = type("Text", (), {})
    tk_mock.ttk = types.ModuleType("ttk")
    tk_mock.ttk.Frame = type("Frame", (), {})
    tk_mock.ttk.Label = type("Label", (), {})
    tk_mock.ttk.Button = type("Button", (), {})
    tk_mock.ttk.Entry = type("Entry", (), {})
    tk_mock.ttk.Combobox = type("Combobox", (), {})
    tk_mock.ttk.Notebook = type("Notebook", (), {})
    tk_mock.ttk.Checkbutton = type("Checkbutton", (), {})
    tk_mock.filedialog = types.ModuleType("filedialog")
    tk_mock.simpledialog = types.ModuleType("simpledialog")
    tk_mock.messagebox = types.ModuleType("messagebox")

    tkfont_mock = types.ModuleType("tkinter.font")
    tkfont_mock.families = lambda: {"DejaVu Sans", "Helvetica"}
    sys.modules["tkinter.font"] = tkfont_mock
    tk_mock.font = tkfont_mock

    sys.modules["tkinter"] = tk_mock
    sys.modules["tkinter.ttk"] = tk_mock.ttk
    sys.modules["tkinter.filedialog"] = tk_mock.filedialog
    sys.modules["tkinter.simpledialog"] = tk_mock.simpledialog
    sys.modules["tkinter.messagebox"] = tk_mock.messagebox

    import pathlib
    for mod in ["app_logging", "autostart", "config", "gui_controller", "single_instance"]:
        sys.modules[mod] = types.ModuleType(mod)

    cfg = sys.modules["config"]
    cfg.default_config_path = lambda: "/tmp/config.toml"
    cfg.load_config = lambda p: types.SimpleNamespace(client=types.SimpleNamespace(
        server="localhost", port=50012, local_path="/tmp/cf", tls_ca_file="",
        tls_server_name="", state_dir="/tmp/state", peers=""
    ))

    as_ = sys.modules["autostart"]
    as_.is_enabled = lambda: False
    as_.enable = lambda: None
    as_.disable = lambda: None

    si = sys.modules["single_instance"]
    si.InstanceLock = lambda *a, **k: None
    si.AlreadyRunningError = type("AlreadyRunningError", (Exception,), {})

    gc = sys.modules["gui_controller"]
    gc.GuiController = type("GuiController", (), {})

    al = sys.modules["app_logging"]
    al.default_log_file = lambda c: pathlib.Path("/tmp") / (c + ".log")

    os.environ.setdefault("DISPLAY", ":0")


def _restore_mocks():
    for mod, orig in ORIGINALS.items():
        if orig is None:
            sys.modules.pop(mod, None)
        else:
            sys.modules[mod] = orig
    for mod in ["gui_app", "theme", "branding"]:
        sys.modules.pop(mod, None)


class GuiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _install_mocks()
        import branding
        import gui_app
        import theme
        cls.gui_app = gui_app
        cls.theme = theme
        cls.branding = branding

    @classmethod
    def tearDownClass(cls):
        _restore_mocks()

    def test_module_imports(self):
        self.assertTrue(hasattr(self.gui_app, "GuiApp"))

    def test_gui_app_has_expected_methods(self):
        expected = ["login", "register", "logout", "share", "unshare",
                    "refresh_shares", "change_password", "save_settings",
                    "toggle_sync", "show", "hide", "quit"]
        for method in expected:
            self.assertTrue(hasattr(self.gui_app.GuiApp, method), method)

    def test_theme_module(self):
        self.assertTrue(hasattr(self.theme, "apply"))
        self.assertTrue(hasattr(self.theme, "EHU_BLUE"))
        self.assertEqual(self.theme.EHU_BLUE, "#1565C0")

    def test_branding_module(self):
        self.assertTrue(hasattr(self.branding, "load_logo"))
        self.assertTrue(hasattr(self.branding, "photo_image"))
        img = self.branding.load_logo(size=(16, 16))
        self.assertEqual(img.size, (16, 16))


if __name__ == "__main__":
    unittest.main()