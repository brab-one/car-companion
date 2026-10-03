"""Clips: short videos and GIFs shown on the display now and then.

The browser turns a video or GIF into frames of the display's size (scaled
down when bigger, never up) and sends them as one tall PNG, frame under
frame, in parts. ClipFiles stores those in assets/clips/.

ClipPlayer decides when a clip plays: each enabled clip in clips.json comes
every `every_min` minutes and loops for `show_s` seconds, while its optional
"when" conditions hold (same as in rules.json). What the display shows, most
important first: place picture, clip, face (see Companion._update_outputs)."""

import base64
import binascii
import re
import struct
from pathlib import Path

from .jsonfile import write_bytes_atomic
from .rules import holds_all, parse_condition

NAME = re.compile(r"[a-z0-9_-]{1,40}\.png")
SIZE = 128
MAX_FRAMES = 300
MAX_BYTES = 8_000_000
MAX_PARTS = 64
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class ClipFiles:
    """The clip files in assets/clips/, and uploads that arrive in parts."""

    def __init__(self, folder):
        self.folder = Path(folder)
        self._parts = {}  # file name -> {part number: bytes} while an upload arrives

    def names(self):
        if not self.folder.is_dir():
            return []
        return sorted(p.name for p in self.folder.glob("*.png") if NAME.fullmatch(p.name))

    def add_part(self, name, part, parts, data):
        """Store one part of an upload. Returns (done, error): done once all parts are in."""
        if not (isinstance(name, str) and NAME.fullmatch(name)):
            return False, f"bad file name {name!r}: use small letters, digits, - and _, ending in .png"
        if not (type(parts) is int and 1 <= parts <= MAX_PARTS and type(part) is int and 0 <= part < parts):
            return False, f"bad part {part!r} of {parts!r}"
        try:
            chunk = base64.b64decode(data or "", validate=True)
        except (binascii.Error, TypeError, ValueError):
            return False, "the clip data is not valid base64"
        if part == 0:
            self._parts[name] = {}
        pieces = self._parts.setdefault(name, {})
        pieces[part] = chunk
        if sum(len(c) for c in pieces.values()) > MAX_BYTES:
            del self._parts[name]
            return True, f"the clip is too big (at most {MAX_BYTES // 1_000_000} MB)"
        if len(pieces) < parts:
            return False, None
        del self._parts[name]
        return True, self._save(name, b"".join(pieces[i] for i in range(parts)))

    def _save(self, name, data):
        if not data.startswith(PNG_SIGNATURE) or data[12:16] != b"IHDR":
            return "the clip is not a PNG file"
        width, height = struct.unpack(">II", data[16:24])
        if width != SIZE or height % SIZE or not 1 <= height // SIZE <= MAX_FRAMES:
            return f"a clip must be {SIZE} wide and 1 to {MAX_FRAMES} frames of {SIZE} high, not {width} x {height}"
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            write_bytes_atomic(self.folder / name, data)
        except OSError as e:
            return f"could not save the clip ({e})"
        return None


class ClipPlayer:
    """Which clip plays now."""

    def __init__(self):
        self.clips = []       # (clip, conditions) of the enabled clips, in clips.json order
        self.by_id = {}       # every clip, also disabled ones (for "Play now")
        self.current = None   # (clip, start, until) while one plays
        self._next = {}       # clip id -> when it comes next

    def configure(self, clips_cfg, thresholds, now):
        """New clips.json or thresholds. Clips keep their place in the schedule,
        unless a shorter interval brings them sooner."""
        self.clips, self.by_id = [], {}
        for clip in clips_cfg["clips"]:
            self.by_id[clip["id"]] = clip
            if not clip.get("enabled", True):
                continue
            try:
                conditions = [parse_condition(c, thresholds) for c in clip.get("when", [])]
            except ValueError:
                continue  # validate.cross_check() reports it
            self.clips.append((clip, conditions))
            soon = now + clip["every_min"] * 60  # a shorter interval applies at once
            self._next[clip["id"]] = min(self._next.get(clip["id"], soon), soon)
        if self.current and self.current[0]["id"] not in self.by_id:
            self.current = None

    def play(self, clip_id, now):
        """Play a clip now (the app's "Play now"). Returns False for an unknown id."""
        clip = self.by_id.get(clip_id)
        if clip:
            self._start(clip, now)
        return clip is not None

    def update(self, signals, now, blocked):
        """Start or end clips. blocked: something more important is shown (or he sleeps)."""
        if self.current and now >= self.current[2]:
            self.current = None
        if blocked:
            self.current = None
            return
        if self.current is None:
            for clip, conditions in self.clips:
                if now >= self._next[clip["id"]] and holds_all(conditions, signals):
                    self._start(clip, now)
                    break

    def frame(self, now):
        """The frame of the current clip to show now (it loops)."""
        clip, start, _ = self.current
        return int((now - start) * clip["fps"]) % clip["frames"]

    def _start(self, clip, now):
        self.current = (clip, now, now + clip["show_s"])
        self._next[clip["id"]] = now + clip["every_min"] * 60
