"""File writes that survive a power cut: after one, the disk holds either the
old file or the new one, never a mix. Use these for every write in the app."""

import os
from pathlib import Path


def write_text_atomic(path, text):
    """Write to a temp file in the same folder, flush it to disk, then rename it."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    _fsync_dir(path.parent)


def _fsync_dir(folder):
    # Makes the rename itself durable. Not every system supports it; that is fine.
    try:
        fd = os.open(folder, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)
