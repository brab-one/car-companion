import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from companion import board
from tests import ROOT

spec = importlib.util.spec_from_file_location("board_helper", ROOT / "board" / "board_helper.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

FREQS = "300000 614400 864000 1017600 1305600 1420800 1612800 1804800 2016000"
NOT_BOOSTED = 1420800  # like the UNO Q: higher only with boost on


def make_sys(root):
    p = Path(root) / "sys/devices/system/cpu/cpufreq/policy0"
    p.mkdir(parents=True)
    files = {"scaling_available_frequencies": FREQS, "scaling_available_governors": "ondemand userspace performance schedutil",
             "scaling_max_freq": str(NOT_BOOSTED), "scaling_cur_freq": "864000", "cpuinfo_max_freq": "2016000",
             "scaling_governor": "schedutil", "boost": "0", "related_cpus": "0 1 2 3"}
    for name, value in files.items():
        (p / name).write_text(value + "\n")
    return p


class FakeBoard(helper.Board):
    """The kernel's part: the top frequencies need boost; nmcli keeps one setting."""

    def __init__(self, root):
        self.commands = []
        self.powersave = "0 (default)"
        super().__init__(root, run=self.fake_nmcli)

    def write(self, policy, name, value):
        if name == "scaling_max_freq" and self.read(policy, "boost") == "0":
            value = min(int(value), NOT_BOOSTED)
        super().write(policy, name, value)

    def fake_nmcli(self, args, **kwargs):
        self.commands.append(args[1:])
        out = ""
        if args[1:4] == ["-t", "-f", "NAME,TYPE,DEVICE"]:
            out = "Home\\: Wi-Fi:802-11-wireless:wlan0\ndocker0:bridge:docker0\n"
        elif args[1:3] == ["-g", "802-11-wireless.powersave"]:
            out = self.powersave + "\n"
        elif args[1:3] == ["connection", "modify"]:
            self.powersave = args[-1]
        return type("Done", (), {"stdout": out})()


class HelperTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.policy = make_sys(self.tmp.name)
        self.board = FakeBoard(self.tmp.name)
        self.default = self.board.current()

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, name):
        return (self.policy / name).read_text().strip()

    def test_it_knows_the_boards_own_values(self):
        self.assertEqual(self.default, {"cpu": {"policy0": {"max_khz": NOT_BOOSTED, "governor": "schedutil", "boost": "0"}},
                                        "wifi_powersave": "default"})

    def test_a_higher_limit_turns_boost_on_and_null_puts_everything_back(self):
        now, problems = helper.apply({"cpu_max_mhz": 2016, "cpu_governor": "performance"}, self.default, self.board)
        self.assertEqual((problems, self.read("scaling_max_freq"), self.read("boost"), self.read("scaling_governor")),
                         ([], "2016000", "1", "performance"))
        self.assertEqual(now["cpu_max_mhz"], 2016)
        helper.apply({}, self.default, self.board)
        self.assertEqual((self.read("scaling_max_freq"), self.read("boost"), self.read("scaling_governor")),
                         (str(NOT_BOOSTED), "0", "schedutil"))

    def test_it_takes_the_nearest_frequency_it_has_and_refuses_unknown_policies(self):
        _, problems = helper.apply({"cpu_max_mhz": 1700, "cpu_governor": "turbo"}, self.default, self.board)
        self.assertEqual(self.read("scaling_max_freq"), "1612800")
        self.assertEqual(self.read("scaling_governor"), "schedutil")
        self.assertEqual(problems, ["the processor has no power policy 'turbo' (it has: ondemand, userspace, "
                                    "performance, schedutil)"])

    def test_wifi_power_saving(self):
        now, _ = helper.apply({"wifi_powersave": False}, self.default, self.board)
        self.assertIn(["connection", "modify", "Home: Wi-Fi", "802-11-wireless.powersave", "disable"], self.board.commands)
        self.assertIn(["connection", "up", "Home: Wi-Fi"], self.board.commands)
        self.assertEqual(now["wifi_powersave"], "disable")
        self.board.commands.clear()
        helper.apply({"wifi_powersave": False}, self.default, self.board)  # already so: no reconnect
        self.assertNotIn(["connection", "up", "Home: Wi-Fi"], self.board.commands)

    def test_board_json_is_checked_again(self):
        path = Path(self.tmp.name) / "board.json"
        path.write_text(json.dumps({"cpu_max_mhz": "fast", "cpu_governor": "rm -rf /", "wifi_powersave": 1}))
        cfg, problems = helper.load_config(path)
        self.assertEqual((cfg, len(problems)), ({}, 3))
        self.assertEqual(helper.load_config(path.with_name("missing.json"))[0], {})


class InfoTest(unittest.TestCase):
    def test_what_the_board_is_doing(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_sys(tmp)
            zones = Path(tmp) / "sys/class/thermal"
            for i, (kind, milli) in enumerate([("cpuss0-thermal", 38700), ("cpuss1-thermal", 41200), ("gpu-thermal", 50000)]):
                (zones / f"thermal_zone{i}").mkdir(parents=True)
                (zones / f"thermal_zone{i}" / "type").write_text(kind)
                (zones / f"thermal_zone{i}" / "temp").write_text(str(milli))
            (Path(tmp) / "proc").mkdir()
            (Path(tmp) / "proc/meminfo").write_text("MemTotal: 3758020 kB\nMemFree: 431932 kB\nMemAvailable: 2289916 kB\n")
            (Path(tmp) / "proc/loadavg").write_text("0.41 0.86 0.77 1/407 180\n")
            (Path(tmp) / "proc/uptime").write_text("2400.5 9000.1\n")
            (Path(tmp) / "config").mkdir()
            (Path(tmp) / "config" / board.STATUS_FILE).write_text(json.dumps({"now": {"cpu_max_mhz": 2016}, "problems": []}))
            data = board.info(Path(tmp) / "config", root=tmp)
        self.assertEqual(data["cpu"], {"cur_mhz": 864, "max_mhz": 1421, "hw_max_mhz": 2016, "governor": "schedutil",
                                       "freqs_mhz": [300, 614, 864, 1018, 1306, 1421, 1613, 1805, 2016],
                                       "governors": ["ondemand", "userspace", "performance", "schedutil"], "cores": 4})
        self.assertEqual((data["temp_c"], data["memory_mb"], data["load"], data["uptime_s"]),
                         (41.2, {"total": 3669, "used": 1433}, [0.41, 0.86, 0.77], 2400.5))
        self.assertEqual(data["helper"]["now"], {"cpu_max_mhz": 2016})


if __name__ == "__main__":
    unittest.main()
