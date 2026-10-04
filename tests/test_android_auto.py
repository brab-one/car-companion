import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

from companion import defaults
from tests import ROOT


def load(name):
    spec = importlib.util.spec_from_file_location(f"aa_{name}", ROOT / "android_auto" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


protocol = load("protocol")
setting = load("setting")


class Messages(unittest.TestCase):
    def test_wifi_start_request_is_framed_protobuf(self):
        # ip_address = "10.0.0.1" (field 1), port = 5288 (field 2, varint 0xa8 0x29)
        self.assertEqual(protocol.wifi_start_request("10.0.0.1", 5288),
                         b"\x00\x0d\x00\x01" b"\x0a\x0810.0.0.1" b"\x10\xa8\x29")

    def test_wifi_info_response_fields(self):
        message = protocol.wifi_info_response("CarCompanion", "secret12", "14:b5:cd:ea:3b:ef")
        message_id, payload = protocol.read_message(io.BytesIO(message).read)
        self.assertEqual(message_id, protocol.WIFI_INFO_RESPONSE)
        self.assertEqual(protocol.fields(payload), {1: b"CarCompanion", 2: b"secret12", 3: b"14:b5:cd:ea:3b:ef",
                                                    4: protocol.WPA2_PERSONAL, 5: protocol.DYNAMIC})

    def test_reads_messages_split_over_several_reads(self):
        data = protocol.frame(protocol.WIFI_INFO_REQUEST, b"") + protocol.frame(protocol.WIFI_CONNECT_STATUS, b"\x08\x00")
        stream = io.BytesIO(data)
        read = lambda n: stream.read(min(n, 3))  # at most 3 bytes at a time, like a slow socket
        self.assertEqual(protocol.read_message(read), (protocol.WIFI_INFO_REQUEST, b""))
        self.assertEqual(protocol.read_message(read), (protocol.WIFI_CONNECT_STATUS, b"\x08\x00"))
        self.assertIsNone(protocol.read_message(read))

    def test_a_cut_off_message_is_the_end(self):
        self.assertIsNone(protocol.read_message(io.BytesIO(b"\x00\x05\x00\x02ab").read))

    def test_large_numbers_round_trip(self):
        self.assertEqual(protocol.fields(protocol._number(2, 300) + protocol._number(9, 2 ** 31)), {2: 300, 9: 2 ** 31})


class Setting(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / ".good").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, text, good=None):
        (self.dir / "settings.json").write_text(text)
        if good is not None:
            (self.dir / ".good" / "settings.json").write_text(good)

    def test_the_same_defaults_as_the_companion(self):
        self.assertEqual(setting.DEFAULTS, defaults.SETTINGS["android_auto"])

    def test_off_with_the_defaults_until_switched_on(self):
        self.assertEqual(setting.read(self.dir), setting.DEFAULTS)  # no settings.json yet
        self.write('{"fps": 30}')
        self.assertFalse(setting.read(self.dir)["enabled"])
        self.write('{"android_auto": {"enabled": true, "wifi_band": "5"}}')
        self.assertEqual(setting.read(self.dir), {**setting.DEFAULTS, "enabled": True, "wifi_band": "5"})

    def test_the_last_good_copy_comes_first(self):
        # What the companion checked last: a broken or wrong file does not switch anything.
        self.write('{"android_auto": {"ena', good='{"android_auto": {"enabled": true}}')
        self.assertTrue(setting.read(self.dir)["enabled"])
        self.write('{"android_auto": {"enabled": "yes"}}', good='{"android_auto": {"enabled": false}}')
        self.assertFalse(setting.read(self.dir)["enabled"])


if __name__ == "__main__":
    unittest.main()
