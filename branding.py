"""Branding helpers shared by the GUI and the tray icon."""

import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageTk

ASSET_NAME = "ehu-mark.png"


def _asset_paths():
    paths = []
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
        paths.append(base / "assets" / "brand" / ASSET_NAME)
        paths.append(base / "docs" / "assets" / "brand" / ASSET_NAME)
        paths.append(Path(sys.executable).resolve().parent / "assets" / "brand" / ASSET_NAME)
        paths.append(Path(sys.executable).resolve().parent / "docs" / "assets" / "brand" / ASSET_NAME)
    here = Path(__file__).resolve().parent
    paths.append(here / "docs" / "assets" / "brand" / ASSET_NAME)
    paths.append(here / "assets" / "brand" / ASSET_NAME)
    paths.append(here / "docs" / "assets" / "brand" / ASSET_NAME)
    for extra in os.environ.get("CLOUDFS_BRAND_DIR", "").split(os.pathsep):
        if extra:
            paths.append(Path(extra) / ASSET_NAME)
    return paths


def load_logo(size=None):
    """Return a PIL image with the EHU mark, or a generated fallback."""
    for path in _asset_paths():
        if path.is_file():
            try:
                image = Image.open(path).convert("RGBA")
                if size is not None:
                    image = image.resize(size, Image.LANCZOS)
                return image
            except Exception:
                continue
    # Fallback: a simple cloud in EHU blue.
    side = size[0] if size else 64
    image = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((4, 4, side - 4, side - 4), fill=(21, 101, 192, 255))
    draw.ellipse((side // 4, side // 3, 3 * side // 4, 2 * side // 3),
                 fill=(255, 255, 255, 255))
    return image


def photo_image(root, size=(32, 32)):
    """Return a Tk PhotoImage with the EHU mark."""
    return ImageTk.PhotoImage(load_logo(size))