#!/usr/bin/env python3
"""Draw placeholder place pictures (128 x 128 PNG) into assets/images/ and an
example clip (16 frames of a spinning wheel) into assets/clips/.

    python3 tools/make_placeholders.py           only files that are missing
    python3 tools/make_placeholders.py --force   overwrite them too

Your own photos, videos and GIFs are added in the simulator (Configure >
Places, Clips), which scales them in the browser. Standard library only."""

import argparse
import math
import struct
import zlib
from pathlib import Path

SIZE = 128
ASSETS = Path(__file__).resolve().parent.parent / "assets"
IMAGES = ASSETS / "images"
CLIPS = ASSETS / "clips"
WHEEL_FRAMES = 16


def ridge(points):
    """Mountain outline through (x, y) points: y of the rock's top edge for each column."""
    tops = []
    for x in range(SIZE):
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            if x0 <= x <= x1:
                tops.append(y0 + (y1 - y0) * (x - x0) / max(1, x1 - x0))
                break
    return tops


# Rough outlines (x, y) of the two massifs, drawn by eye, not to scale.
SCHLERN = [(0, 92), (14, 70), (20, 40), (23, 30), (26, 41), (31, 46), (40, 45), (52, 47),
           (66, 44), (80, 46), (94, 45), (104, 48), (110, 66), (118, 80), (127, 88)]
GEISLER = [(0, 84), (10, 62), (17, 44), (22, 58), (29, 36), (35, 54), (42, 30), (48, 50),
           (55, 24), (61, 46), (68, 28), (74, 50), (82, 34), (88, 56), (96, 40), (103, 60),
           (111, 48), (118, 70), (127, 78)]


def scene(points):
    """Sky, rock with a lit and a shaded side, forest and meadow."""
    tops = ridge(points)
    rows = []
    for y in range(SIZE):
        row = []
        for x in range(SIZE):
            if y >= 104:                      # meadow
                px = (86, 150 - (y - 104), 60)
            elif y >= 88 + 4 * ((x // 9) % 2):  # forest edge
                px = (26, 74, 40)
            elif y >= tops[x]:                # rock: lit where the outline rises
                lit = x + 1 < SIZE and tops[x + 1] < tops[x]
                shade = 200 - int((y - tops[x]) * 1.2)
                px = (shade, shade - 6, shade - 16) if lit else (shade - 70, shade - 72, shade - 64)
            else:                             # sky
                k = y / SIZE
                px = (int(40 + 120 * k), int(90 + 110 * k), int(170 + 70 * k))
            row.append(tuple(max(0, min(255, c)) for c in px))
        rows.append(row)
    return rows


def wheel(frame):
    """A five-spoke wheel, turned a little further in every frame (one spoke-gap per loop)."""
    turn = frame / WHEEL_FRAMES * 2 * math.pi / 5
    rows = []
    for y in range(SIZE):
        row = []
        for x in range(SIZE):
            dx, dy = x + 0.5 - SIZE / 2, y + 0.5 - SIZE / 2
            r = math.hypot(dx, dy)
            angle = (math.atan2(dy, dx) - turn) % (2 * math.pi / 5)
            spoke = min(angle, 2 * math.pi / 5 - angle) * r < 5  # 10 px wide spokes
            if r > 60:
                px = (0, 0, 0)
            elif r > 46:
                px = (34, 34, 38)                      # tyre
            elif r > 42:
                px = (190, 196, 206)                   # rim edge
            elif r < 9:
                px = (60, 64, 72)                      # hub
            elif spoke:
                px = (200, 206, 216)                   # spokes
            else:
                px = (12, 12, 14)                      # between the spokes
            row.append(px)
        rows.append(row)
    return rows


def write_png(path, rows):
    raw = b"".join(b"\x00" + bytes(c for px in row for c in px) for row in rows)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", len(rows[0]), len(rows), 8, 2, 0, 0, 0)  # 8-bit RGB
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
                     + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    parser = argparse.ArgumentParser(description="Draw placeholder place pictures.")
    parser.add_argument("--force", action="store_true", help="overwrite existing pictures")
    args = parser.parse_args()
    IMAGES.mkdir(parents=True, exist_ok=True)
    CLIPS.mkdir(parents=True, exist_ok=True)
    jobs = [(IMAGES / "schlern.png", lambda: scene(SCHLERN)), (IMAGES / "geisler.png", lambda: scene(GEISLER)),
            (CLIPS / "wheel.png", lambda: [row for f in range(WHEEL_FRAMES) for row in wheel(f)])]
    for path, draw in jobs:
        if path.exists() and not args.force:
            print(f"kept {path.name} (use --force to overwrite)")
            continue
        write_png(path, draw())
        print(f"wrote {path.relative_to(ASSETS.parent)}")


if __name__ == "__main__":
    main()
