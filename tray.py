"""System tray icon for the GUI."""

import sys
import threading

from PIL import Image, ImageDraw

try:
    import pystray
except ImportError:
    pystray = None


def make_icon_image():
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((4, 4, 60, 60), fill=(49, 108, 254, 255))
    draw.rectangle((18, 28, 46, 46), fill=(255, 255, 255, 255))
    draw.ellipse((14, 20, 34, 38), fill=(255, 255, 255, 255))
    draw.ellipse((28, 16, 50, 38), fill=(255, 255, 255, 255))
    return image


class TrayIcon:
    """Thin pystray wrapper with a Tk-safe callback dispatch."""

    def __init__(self, root, on_show, on_open_folder, on_toggle, on_quit):
        self.root = root
        self.on_show = on_show
        self.on_open_folder = on_open_folder
        self.on_toggle = on_toggle
        self.on_quit = on_quit
        self.icon = None
        self._pause_label = "Pausar sincronización"

    @property
    def available(self):
        return pystray is not None

    @property
    def docked(self):
        if self.icon is None:
            return False
        if sys.platform.startswith("linux") and hasattr(
            self.icon, "_systray_manager"
        ):
            return self.icon._systray_manager is not None
        return True

    def start(self):
        if pystray is None:
            return False
        menu = pystray.Menu(
            pystray.MenuItem("Mostrar", self._dispatch(self.on_show), default=True),
            pystray.MenuItem("Abrir carpeta", self._dispatch(self.on_open_folder)),
            pystray.MenuItem(
                lambda item: self._pause_label,
                self._dispatch(self.on_toggle),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", self._dispatch(self.on_quit)),
        )
        self.icon = pystray.Icon(
            "cloud-file-service", make_icon_image(), "Cloud File Service", menu
        )
        threading.Thread(target=self.icon.run, daemon=True).start()
        return True

    def _dispatch(self, callback):
        def handler(icon=None, item=None):
            self.root.after(0, callback)

        return handler

    def set_paused(self, paused):
        self._pause_label = (
            "Reanudar sincronización" if paused else "Pausar sincronización"
        )
        if self.icon is not None:
            self.icon.update_menu()

    def stop(self):
        if self.icon is not None:
            self.icon.stop()
            self.icon = None
