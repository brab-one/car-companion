#!/usr/bin/env python3
"""Put his eyes into the microcontroller's boot animation, so they show half a
second after power-on instead of Arduino's logo, until the sketch takes over
(it waits for Linux, about 20 s).

    python3 tools/boot_eyes.py            write it onto the board (adb, USB cable)
    python3 tools/boot_eyes.py --arduino  back to Arduino's own animation
    python3 tools/boot_eyes.py --file F   only save the animation as file F

The microcontroller's loader plays the boot animation from its own flash area
(192 kB at 0x080D0000): a 16-byte header (0xBA, length of the loop, length of
the end, 0), then frames of 104 bytes, one brightness 0..255 per LED, row by
row, 16 ms each. It plays the loop until Linux is up, then the end once. An
area without that header (0xBA) gets Arduino's animation. Writing it uses the
OpenOCD App Lab flashes sketches with; it does not touch the sketch. Standard
library only."""

import argparse
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ADDRESS = 0x080D0000   # the "bootanimation" partition (board package, arduino_uno_q_stm32u585xx.overlay)
AREA_SIZE = 192 * 1024
FRAME_MS = 16

# The same eyes as sketch/sketch.ino: change both.
COLS, ROWS = 13, 8
EYE_COLS = (2, 8)            # first column of each eye; each is 3 wide
LIT, CORNER = 255, 80        # brightness 0..255; the sketch's 7 and 2 of 0..7
OPEN = (2, 6)                # top and bottom row
BLINK = ((3, 5), (4, 4), (4, 4), (3, 5))
BLINK_MS = 45
OPEN_MS = 2400               # between blinks; the loop is checked for Linux after each round

# Run on the board (as the arduino user, no password). "reset halt" stops the
# microcontroller before its loader reads the area (it would keep the old one in
# its cache); the end restarts the sketch the way App Lab does after flashing
# (flash_sketch.cfg in the board package).
OPENOCD_START = "reset_config srst_only srst_nogate srst_push_pull connect_assert_srst\ninit\nreset halt\n"
OPENOCD_END = "reset\nsleep 100\nmww 0x40036400 0xCAFFEEEE\nshutdown\n"
REMOTEOCD = "$(ls /home/arduino/.arduino15/packages/arduino/tools/remoteocd/*/remoteocd | tail -n 1)"


def eyes(top, bottom):
    frame = bytearray(COLS * ROWS)
    round_ = bottom - top >= 3
    for first in EYE_COLS:
        for row in range(top, bottom + 1):
            for col in range(first, first + 3):
                corner = round_ and row in (top, bottom) and col != first + 1
                frame[row * COLS + col] = CORNER if corner else LIT
    return bytes(frame)


def frames(ms):
    return max(1, round(ms / FRAME_MS))


def animation():
    loop = eyes(*OPEN) * frames(OPEN_MS) + b"".join(eyes(*rows) * frames(BLINK_MS) for rows in BLINK)
    end = eyes(*OPEN)
    data = struct.pack("<4I", 0xBA, len(loop), len(end), 0) + loop + end
    assert len(data) <= AREA_SIZE
    return data


def on_board(script, files=(), then=""):
    """Push files to /tmp on the board, run an OpenOCD script there, then the
    shell command `then`. Returns the output, ending in "exit=0" when all went well."""
    for local, remote in files:
        subprocess.run(["adb", "push", str(local), remote], check=True, capture_output=True)
    cfg = "/tmp/boot_eyes.cfg"
    with tempfile.NamedTemporaryFile("w", suffix=".cfg") as f:
        f.write(script)
        f.flush()
        subprocess.run(["adb", "push", f.name, cfg], check=True, capture_output=True)
    # remoteocd wants a firmware file even when the script names none.
    command = f"{REMOTEOCD} upload -f {cfg} {cfg}" + (f" && {then}" if then else "")
    out = subprocess.run(["adb", "shell", f"{command}; echo exit=$?; rm -f /tmp/boot_eyes.*"],
                         capture_output=True, text=True).stdout
    return out.strip()


def main():
    parser = argparse.ArgumentParser(description="Put his eyes into the microcontroller's boot animation.")
    parser.add_argument("--arduino", action="store_true", help="back to Arduino's own animation")
    parser.add_argument("--file", type=Path, help="only save the animation as this file")
    args = parser.parse_args()

    if args.arduino:
        # Erasing the first page removes the header, so the loader plays its own animation.
        out = on_board(OPENOCD_START + f"flash erase_address {ADDRESS:#x} 0x2000\n" + OPENOCD_END)
        ok = out.endswith("exit=0")
        print("Arduino's boot animation is back." if ok else out)
        sys.exit(0 if ok else 1)

    data = animation()
    if args.file:
        args.file.write_bytes(data)
        print(f"{args.file}: {len(data)} bytes")
        return
    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / "boot_eyes.bin"
        local.write_bytes(data)
        # Read it back after a fresh "reset halt" and compare, then restart the sketch.
        out = on_board(OPENOCD_START
                       + f"flash write_image erase /tmp/boot_eyes.bin {ADDRESS:#x} bin\n"
                       + f"reset halt\ndump_image /tmp/boot_eyes.check {ADDRESS:#x} {len(data)}\n"
                       + OPENOCD_END, [(local, "/tmp/boot_eyes.bin")],
                       then="cmp /tmp/boot_eyes.bin /tmp/boot_eyes.check")
    ok = out.endswith("exit=0")
    print(f"Boot animation written and checked ({len(data)} bytes): his eyes from power-on." if ok else out)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
