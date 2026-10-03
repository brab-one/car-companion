"""Place pictures: 128 x 128 PNG files in assets/images/, where the web page
can load them. The app sends new ones already cropped and scaled (the
browser does that), so here they are only checked and saved."""

import base64
import binascii
import re
import struct
from pathlib import Path

from .jsonfile import write_bytes_atomic

NAME = re.compile(r"[a-z0-9_-]{1,40}\.png")
SIZE = 128
MAX_BYTES = 300_000
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class Images:
    def __init__(self, folder):
        self.folder = Path(folder)

    def names(self):
        if not self.folder.is_dir():
            return []
        return sorted(p.name for p in self.folder.glob("*.png") if NAME.fullmatch(p.name))

    def save(self, name, png_base64):
        """Check and store one picture. Returns None, or an error message."""
        if not (isinstance(name, str) and NAME.fullmatch(name)):
            return f"bad file name {name!r}: use small letters, digits, - and _, ending in .png"
        try:
            data = base64.b64decode(png_base64 or "", validate=True)
        except (binascii.Error, TypeError, ValueError):
            return "the picture data is not valid base64"
        if len(data) > MAX_BYTES:
            return f"the picture is too big ({len(data) // 1000} kB, at most {MAX_BYTES // 1000} kB)"
        if not data.startswith(PNG_SIGNATURE) or data[12:16] != b"IHDR":
            return "the picture is not a PNG file"
        width, height = struct.unpack(">II", data[16:24])
        if (width, height) != (SIZE, SIZE):
            return f"the picture is {width} x {height}, it must be {SIZE} x {SIZE}"
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            write_bytes_atomic(self.folder / name, data)
        except OSError as e:
            return f"could not save the picture ({e})"
        return None
