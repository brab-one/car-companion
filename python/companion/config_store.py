"""Loads the JSON files in config/, checks them, and keeps the last good
version of each, so a broken edit never leaves the companion without a face.

When a file is broken, the companion uses, in this order:
  1. the version it is already running (also the last good one),
  2. config/.good/<name>.json, the last version that passed the checks,
  3. the built-in defaults in defaults.py.

poll() notices files that changed on disk (edited by hand, copied by
deploy.sh), and save() stores what the app sends, so changes apply without
a restart."""

import copy
import json
from pathlib import Path

from . import defaults
from .jsonfile import dumps_compact, write_text_atomic
from .validate import check

NAMES = ("faces", "animations", "rules", "places", "clips", "settings")


class ConfigStore:
    def __init__(self, folder, log, names=NAMES):
        """log(level, text, source) reports problems."""
        self.folder = Path(folder)
        self.names = names
        self.log = log
        self.data = {}    # name -> data in use; replaced, never changed in place
        self.errors = {}  # name -> problems with the file on disk ([] when fine)
        self.source = {}  # name -> "file", "last_good" or "defaults"
        self._stamps = {}

    def load_all(self):
        for name in self.names:
            self.load(name)

    def load(self, name):
        """(Re)load one file. Returns its problems ([] when it was fine)."""
        path = self.folder / f"{name}.json"
        self._stamps[name] = _stamp(path)
        data, text, errors = _read(name, path)
        self.errors[name] = errors
        if not errors:
            self.data[name] = data
            self.source[name] = "file"
            self._keep_good(name, text)
        elif name in self.data:
            if self.source[name] == "file":
                self.source[name] = "last_good"  # keep running with what we have
        else:
            good, _, good_errors = _read(name, self._good_path(name))
            if not good_errors:
                self.data[name], self.source[name] = good, "last_good"
            else:
                fallback, _ = check(name, copy.deepcopy(defaults.FILES[name]))
                self.data[name], self.source[name] = fallback, "defaults"
        return errors

    def save(self, name, raw):
        """Check and store a whole file sent by the app. Returns its problems ([] when saved)."""
        data, errors = check(name, raw)
        if errors:
            return errors
        path = self.folder / f"{name}.json"
        text = dumps_compact(raw)
        try:
            write_text_atomic(path, text)
        except OSError as e:
            return [f"{name}.json: could not save the file ({e})"]
        self.data[name], self.errors[name], self.source[name] = data, [], "file"
        self._stamps[name] = _stamp(path)  # no need to reload what we just wrote
        self._keep_good(name, text)
        return []

    def poll(self):
        """Reload the files that changed on disk. Returns their names."""
        changed = []
        for name in self.names:
            if _stamp(self.folder / f"{name}.json") != self._stamps.get(name):
                self.load(name)
                changed.append(name)
        return changed

    def _good_path(self, name):
        return self.folder / ".good" / f"{name}.json"

    def _keep_good(self, name, text):
        """Copy a file that passed the checks. Writes only when it changed, so rarely."""
        good = self._good_path(name)
        try:
            if good.exists() and good.read_text(encoding="utf-8") == text:
                return
            good.parent.mkdir(exist_ok=True)
            write_text_atomic(good, text)
        except OSError as e:
            self.log("warn", f"could not save the last good copy of {name}.json: {e}", "config")


def _read(name, path):
    """Return (data, text, errors) for one file."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, None, [f"{name}.json: file not found"]
    except (OSError, ValueError) as e:
        return None, None, [f"{name}.json: cannot read the file ({e})"]
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as e:
        return None, text, [f"{name}.json: invalid JSON at line {e.lineno}, column {e.colno}: {e.msg}"]
    data, errors = check(name, raw)
    return data, text, errors


def _stamp(path):
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)
