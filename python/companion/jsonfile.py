"""File writes that survive a power cut: after one, the disk holds either the
old file or the new one, never a mix. Use these for every write in the app."""

import json
import os
from pathlib import Path


def write_text_atomic(path, text):
    write_bytes_atomic(path, text.encode("utf-8"))


def write_bytes_atomic(path, data):
    """Write to a temp file in the same folder, flush it to disk, then rename it."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    _fsync_dir(path.parent)


def dumps_compact(data, width=100):
    """JSON text laid out like the files in config/: records such as a place or a
    mood on one line each, bigger structures spread over several lines."""
    def flat(value):  # only plain values, or lists of plain values
        items = value.values() if isinstance(value, dict) else value
        return all(not isinstance(v, (dict, list)) or
                   (isinstance(v, list) and not any(isinstance(x, (dict, list)) for x in v))
                   for v in items)

    def fmt(value, indent):
        one_line = json.dumps(value, ensure_ascii=False)
        if (not isinstance(value, (dict, list)) or not value or flat(value)
                or indent + len(one_line) <= width):
            return one_line
        pad = " " * (indent + 2)
        if isinstance(value, dict):
            items = [f"{pad}{json.dumps(k, ensure_ascii=False)}: {fmt(v, indent + 2)}"
                     for k, v in value.items()]
            return "{\n" + ",\n".join(items) + "\n" + " " * indent + "}"
        items = [pad + fmt(v, indent + 2) for v in value]
        return "[\n" + ",\n".join(items) + "\n" + " " * indent + "]"
    return fmt(data, 0) + "\n"


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
