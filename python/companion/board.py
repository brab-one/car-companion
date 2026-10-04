"""The board itself: its processor, temperature, memory and load, read from
/sys and /proc, which the app's container may read but not change.

The settings for the board (processor limit and power policy, Wi-Fi power
saving) are in config/board.json. The board helper (board/board_helper.py, a
small root service installed once with tools/install_board_helper.sh)
applies them and writes what it did to config/.board_applied.json."""

import json
from pathlib import Path

CPUFREQ = "sys/devices/system/cpu/cpufreq"
THERMAL = "sys/class/thermal"
STATUS_FILE = ".board_applied.json"  # in config/, written by the board helper


def info(config_dir, root="/", on_board=True):
    """What the board is doing now, for the Board tab."""
    root = Path(root)
    return {
        "on_board": on_board,
        "cpu": _cpu(root / CPUFREQ),
        "temp_c": _temperature(root / THERMAL),
        "memory_mb": _memory(root / "proc" / "meminfo"),
        "load": _numbers(root / "proc" / "loadavg", 3),
        "uptime_s": next(iter(_numbers(root / "proc" / "uptime", 1)), None),
        "helper": _read_json(Path(config_dir) / STATUS_FILE),
    }


def _cpu(cpufreq):
    policies = sorted(cpufreq.glob("policy*"))
    if not policies:
        return None
    p = policies[0]  # the UNO Q's four cores share one policy

    def mhz(name):  # the files are in kHz
        return round(int(_text(p / name) or 0) / 1000)

    return {
        "cur_mhz": mhz("scaling_cur_freq"),
        "max_mhz": mhz("scaling_max_freq"),
        "hw_max_mhz": mhz("cpuinfo_max_freq"),
        "governor": _text(p / "scaling_governor"),
        "freqs_mhz": sorted(round(int(f) / 1000) for f in (_text(p / "scaling_available_frequencies") or "").split()),
        "governors": (_text(p / "scaling_available_governors") or "").split(),
        "cores": sum(len((_text(q / "related_cpus") or "").split()) for q in policies),
    }


def _temperature(thermal):
    """The hottest processor sensor, in °C (all sensors when none is named after the processor)."""
    temps = {}
    for zone in thermal.glob("thermal_zone*"):
        try:
            temps[_text(zone / "type")] = int(_text(zone / "temp")) / 1000
        except (TypeError, ValueError):
            continue
    cpu = [t for name, t in temps.items() if name and "cpu" in name.lower()]
    values = cpu or list(temps.values())
    return round(max(values), 1) if values else None


def _memory(meminfo):
    fields = {}
    for line in (_text(meminfo) or "").splitlines():
        key, _, rest = line.partition(":")
        if rest.split():
            fields[key] = int(rest.split()[0])  # kB
    if "MemTotal" not in fields:
        return None
    total = fields["MemTotal"] // 1024
    return {"total": total, "used": total - fields.get("MemAvailable", fields.get("MemFree", 0)) // 1024}


def _numbers(path, count):
    try:
        return [float(v) for v in (_text(path) or "").split()[:count]]
    except ValueError:
        return []


def _text(path):
    try:
        return path.read_text().strip()
    except OSError:
        return None


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
