#!/usr/bin/env python3
"""Car Companion board helper: applies config/board.json on the UNO Q.

The companion runs in a container that may only read the board's settings,
so this small service does the changing, as root, on the board itself: the
processor's frequency limit and power policy (governor), and Wi-Fi power
saving. It only writes values the hardware lists as available, applies them
when it starts and whenever the file changes, and writes what it did to
config/.board_applied.json for the Board tab. It never runs anything but
nmcli, and that without a shell.

A setting left at null gets the board's own value back: the one it had when
this service first started after booting.

    car-companion-board-helper            run (as root; systemd starts it)
    car-companion-board-helper --dry-run  say what it would do, change nothing

Installed with tools/install_board_helper.sh. Standard library only."""

import argparse
import datetime
import json
import os
import re
import subprocess
import time
from pathlib import Path

APP = Path(os.environ.get("CAR_COMPANION_APP", "/home/arduino/ArduinoApps/car-companion"))
POLL_S = 2
WIFI_VALUES = ("default", "ignore", "disable", "enable")  # nmcli's names for 802-11-wireless.powersave


class Board:
    """What the helper may change. root and run are replaced in the tests."""

    def __init__(self, root="/", run=subprocess.run, dry_run=False):
        self.cpufreq = Path(root) / "sys/devices/system/cpu/cpufreq"
        self.run = run
        self.dry_run = dry_run

    def policies(self):
        return sorted(self.cpufreq.glob("policy*"))

    def read(self, policy, name):
        return (policy / name).read_text().strip()

    def write(self, policy, name, value):
        if self.dry_run:
            print(f"would write {value} to {policy / name}")
        else:
            (policy / name).write_text(str(value))

    def nmcli(self, *args, change=False):
        if change and self.dry_run:
            print("would run: nmcli " + " ".join(args))
            return ""
        return self.run(["nmcli", *args], capture_output=True, text=True, check=True).stdout

    def wifi(self):
        """The active Wi-Fi connection's (name, device), or None."""
        for line in self.nmcli("-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active").splitlines():
            fields = [f.replace("\\:", ":").replace("\\\\", "\\") for f in re.split(r"(?<!\\):", line)]
            if len(fields) == 3 and fields[1] == "802-11-wireless":
                return fields[0], fields[2]
        return None

    def wifi_powersave(self, name):
        value = self.nmcli("-g", "802-11-wireless.powersave", "connection", "show", name).strip()
        return value.split(" ")[0] if value.split(" ")[0] in WIFI_VALUES else "default"  # e.g. "0 (default)"

    def current(self):
        """The board's own values now, to put back when a setting returns to null."""
        cpu = {p.name: {"max_khz": int(self.read(p, "scaling_max_freq")),
                        "governor": self.read(p, "scaling_governor"),
                        "boost": self.read(p, "boost") if (p / "boost").exists() else None}
               for p in self.policies()}
        wifi = self.wifi()
        return {"cpu": cpu, "wifi_powersave": self.wifi_powersave(wifi[0]) if wifi else None}


def load_config(path):
    """board.json, checked again here: this runs as root. Missing or broken: all null."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, ["board.json is missing or not valid JSON: the board keeps its own values"]
    cfg, problems = {}, []
    mhz = raw.get("cpu_max_mhz")
    if mhz is not None:
        if isinstance(mhz, (int, float)) and not isinstance(mhz, bool) and 100 <= mhz <= 5000:
            cfg["cpu_max_mhz"] = mhz
        else:
            problems.append(f"cpu_max_mhz: {mhz!r} is not a frequency in MHz")
    gov = raw.get("cpu_governor")
    if gov is not None:
        if isinstance(gov, str) and re.fullmatch(r"[a-z_]{1,30}", gov):
            cfg["cpu_governor"] = gov
        else:
            problems.append(f"cpu_governor: {gov!r} is not a governor's name")
    wifi = raw.get("wifi_powersave")
    if wifi is not None:
        if isinstance(wifi, bool):
            cfg["wifi_powersave"] = wifi
        else:
            problems.append(f"wifi_powersave: {wifi!r} is not true or false")
    return cfg, problems


def apply(cfg, board_default, board):
    """Make the board match cfg. Returns (what it has now, problems)."""
    problems, now = [], {}
    for p in board.policies():
        own = board_default["cpu"].get(p.name, {})
        governors = board.read(p, "scaling_available_governors").split()
        gov = cfg.get("cpu_governor") or own.get("governor")
        if gov not in governors:
            problems.append(f"the processor has no power policy {gov!r} (it has: {', '.join(governors)})")
        elif board.read(p, "scaling_governor") != gov:
            board.write(p, "scaling_governor", gov)
        freqs = sorted(int(f) for f in board.read(p, "scaling_available_frequencies").split())
        want = round(cfg["cpu_max_mhz"] * 1000) if "cpu_max_mhz" in cfg else own.get("max_khz", freqs[-1])
        target = max([f for f in freqs if f <= want + 1000], default=freqs[0])  # the nearest it offers, not above
        if int(board.read(p, "scaling_max_freq")) != target:
            board.write(p, "scaling_max_freq", target)
            if int(board.read(p, "scaling_max_freq")) < target and (p / "boost").exists():
                board.write(p, "boost", 1)  # the top frequencies count as boost
                board.write(p, "scaling_max_freq", target)
        if "cpu_max_mhz" not in cfg and own.get("boost") is not None and board.read(p, "boost") != own["boost"]:
            board.write(p, "boost", own["boost"])  # back to the board's own, with its own limit
        reached = int(board.read(p, "scaling_max_freq"))
        if reached < target and not board.dry_run:
            problems.append(f"the board keeps the processor at {reached // 1000} MHz or less")
        now = {"cpu_max_mhz": reached // 1000, "cpu_governor": board.read(p, "scaling_governor")}
    wifi = board.wifi()
    if wifi:
        name, device = wifi
        target = ("enable" if cfg["wifi_powersave"] else "disable") if "wifi_powersave" in cfg \
            else board_default.get("wifi_powersave") or "default"
        if board.wifi_powersave(name) != target:
            board.nmcli("connection", "modify", name, "802-11-wireless.powersave", target, change=True)
            board.nmcli("connection", "up", name, change=True)  # reconnects once, to use it now
        now["wifi_powersave"] = board.wifi_powersave(name)
    return now, problems


def boot_id():
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return None


def write_status(path, status):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(status, indent=1), encoding="utf-8")
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def main():
    parser = argparse.ArgumentParser(description="Apply config/board.json to the board.")
    parser.add_argument("--dry-run", action="store_true", help="say what would change, change nothing")
    args = parser.parse_args()
    board = Board(dry_run=args.dry_run)
    config, status_path = APP / "config" / "board.json", APP / "config" / ".board_applied.json"
    try:
        old = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    # The board's own values: from before this service changed anything since booting.
    board_default = old["board_default"] if old.get("boot_id") == boot_id() and "board_default" in old \
        else board.current()
    stamp = "first"
    while True:
        try:
            changed = config.stat().st_mtime_ns
        except OSError:
            changed = None
        if changed != stamp:
            stamp = changed
            cfg, problems = load_config(config)
            try:
                now, more = apply(cfg, board_default, board)
            except (OSError, ValueError, subprocess.CalledProcessError) as e:
                now, more = {}, [f"could not apply: {e}"]
            status = {"boot_id": boot_id(), "at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                      "board_default": board_default, "now": now, "problems": problems + more}
            if args.dry_run:
                print(json.dumps(status, indent=1))
                return
            write_status(status_path, status)
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
