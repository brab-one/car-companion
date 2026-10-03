"""The speech bubble: what the companion says, drawn on the display.

The text is wrapped and drawn here, with font.py, into a 1-bit picture, so
the renderers (the simulator canvas, later the OLED sketch) only copy bits
and need no font. The bubble sits at the bottom of the display with a tail
pointing up at the face; the eyes move up to make room (lift()).
See PROTOCOL.md, "Scenes", for how renderers draw it."""

import base64

from . import font

SIZE = 128
MARGIN = 3     # from the display's edges
PAD = 4        # between the outline and the text
TAIL = 6       # how far the tail reaches up
MAX_LINES = 3
MAX_CHARS = (SIZE - 2 * MARGIN - 2 * PAD - 2) // font.ADVANCE  # 18 characters per line


def wrap(text, width=MAX_CHARS, max_lines=MAX_LINES):
    """Split text into lines of at most `width` characters, breaking at spaces.
    Too long for max_lines: the last line ends with "..."."""
    lines, line = [], ""
    for word in font.normalize(text).split():
        while len(word) > width:  # a word longer than a line is cut
            if line:
                lines.append(line)
                line = ""
            lines.append(word[:width])
            word = word[width:]
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}" if line else word
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: width - 3].rstrip() + "..."
    return lines or [""]


def bubble(text, color="#FFFFFF"):
    """The bubble for one line of speech, as scene data."""
    lines = wrap(text)
    text_w = max(len(line) for line in lines) * font.ADVANCE - 1
    text_h = len(lines) * font.LINE - (font.LINE - font.HEIGHT)
    w = text_w + 2 * PAD + 2
    h = text_h + 2 * PAD + 2
    w, h = w + w % 2, h + h % 2  # even, so the centre is a whole pixel
    top = SIZE - MARGIN - h
    left = (SIZE - w) // 2
    stride = (text_w + 7) // 8
    bits = bytearray(stride * text_h)
    for i, line in enumerate(lines):
        for x, y in font.pixels(line):
            y += i * font.LINE
            bits[y * stride + x // 8] |= 0x80 >> (x % 8)
    return {
        "x": left + w // 2, "y": top + h // 2, "w": w, "h": h, "r": 5,
        "color": color,
        "tail": [SIZE // 2, top - TAIL],  # the tip; its base is on the bubble's top edge
        "text": {"x": left + 1 + PAD, "y": top + 1 + PAD, "w": text_w, "h": text_h,
                 "bits": base64.b64encode(bytes(bits)).decode("ascii")},
    }


def lift(b):
    """How far the eyes move up (negative pixels) while this bubble shows."""
    return -(b["h"] // 2)


def seconds(text, min_s, per_char_s):
    """How long a line stays: a minimum, plus time to read it."""
    return min(10.0, min_s + per_char_s * len(text))
