"""Wireless Android Auto bridge, phase 1: the phone side.

The phone pairs with the board over Bluetooth. When it connects, the board tells
it over an RFCOMM channel which Wi-Fi to join and where to connect (protocol.py).
The board runs that Wi-Fi as an access point, and the phone opens its Android
Auto connection to the board over TCP. Phase 2 passes that connection on to the
car over USB; for now the board only logs it.

Runs in its own container (compose.yaml) as root with the system D-Bus mounted:
BlueZ for Bluetooth, NetworkManager for the access point (it also hands out the
phone's address). The flow follows WirelessAndroidAutoDongle's aawgd (MIT).

It starts with the board and follows android_auto in the companion's settings
(setting.py), which Configure > Board and later the phone app change: switched
on, the access point, the Bluetooth service and the port for the phone; switched
off, none of them, and the board's Wi-Fi and Bluetooth are as before. Every
CHECK_S it reports what it does to the companion (for Configure > Board), whose
answer may ask it to open pairing for a phone."""

import json
import os
import secrets
import signal
import socket
import subprocess
import threading
import time
import urllib.request
import uuid
from pathlib import Path

import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

import protocol
import setting

BLUEZ = "org.bluez"
NM = "org.freedesktop.NetworkManager"
AA_UUID = "4de17a00-52cb-11e6-bdf4-0800200c9a66"   # the Android Auto wireless service
HSP_HS_UUID = "00001108-0000-1000-8000-00805f9b34fb"
HSP_AG_UUID = "00001112-0000-1000-8000-00805f9b34fb"
OUR = "/com/carcompanion/aa"
PROFILE_ID = "car-companion-aa"   # the access point's NetworkManager profile
RETRY_S = 20                       # how often to call the paired phones until one is on the Wi-Fi
CHECK_S = 2                        # how often to read the settings and report
DEFAULT_CHANNEL = {"2.4": 6, "5": 36}
AP_INTERFACE = "ap0"              # the second, virtual interface, when the board stays on your Wi-Fi

INTERFACE = os.environ.get("AA_INTERFACE", "wlan0")
ADDRESS = os.environ.get("AA_ADDRESS", "10.0.0.1")
PORT = int(os.environ.get("AA_PORT", "5288"))
DATA = Path(os.environ.get("AA_DATA", "/data"))
COMPANION = os.environ.get("AA_COMPANION", "http://127.0.0.1:7000")  # the app (python/main.py)
CONFIG = Path(os.environ.get("AA_CONFIG", "/config"))                  # the companion's config/

phone_on_wifi = threading.Event()


def log(text):
    print(time.strftime("%H:%M:%S"), text, flush=True)


def wifi_secrets(mac, name, password):
    """The access point's name and password: the settings', else made up once and kept in DATA."""
    path = DATA / "wifi.json"
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        saved = {"ssid": "CarCompanion-" + mac.replace(":", "")[-4:].upper(), "password": secrets.token_urlsafe(12)}
        DATA.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(saved))
    return name or saved["ssid"], password or saved["password"]


# ---- Wi-Fi: the access point, through NetworkManager ---------------------------------

def access_point_settings(interface, mac, ssid, password, band, channel, uuid_):
    return dbus.Dictionary({
        "connection": dbus.Dictionary({"id": PROFILE_ID, "uuid": uuid_, "type": "802-11-wireless",
                                       "interface-name": interface, "autoconnect": False}, signature="sv"),
        "802-11-wireless": dbus.Dictionary({"mode": "ap", "ssid": dbus.ByteArray(ssid.encode()),
                                            "band": "a" if band == "5" else "bg",
                                            "channel": dbus.UInt32(channel),
                                            # ap0's own address (wlan0 has the permanent one)
                                            "assigned-mac-address": mac}, signature="sv"),
        "802-11-wireless-security": dbus.Dictionary({"key-mgmt": "wpa-psk", "psk": password,
                                                     "proto": dbus.Array(["rsn"], signature="s"),
                                                     "pairwise": dbus.Array(["ccmp"], signature="s"),
                                                     "group": dbus.Array(["ccmp"], signature="s")}, signature="sv"),
        # "shared": NetworkManager gives the phone an address (dnsmasq) on ADDRESS/24.
        "ipv4": dbus.Dictionary({"method": "shared", "address-data": dbus.Array(
            [dbus.Dictionary({"address": ADDRESS, "prefix": dbus.UInt32(24)}, signature="sv")],
            signature="a{sv}")}, signature="sv"),
        "ipv6": dbus.Dictionary({"method": "disabled"}, signature="sv"),
    }, signature="sa{sv}")


def channel_of(mhz):
    """2.4 GHz channel of a frequency, or None."""
    return 14 if mhz == 2484 else (mhz - 2407) // 5 if 2412 <= mhz <= 2472 else None


def may_beacon(band, channel):
    """Whether the Wi-Fi's rules allow an access point there. The UNO Q's chip
    marks every 5 GHz channel "No IR" (it may only listen there), whatever
    country is set: its kernel ignores countries set by hand."""
    mhz = 2407 + 5 * channel if band == "2.4" else 5000 + 5 * channel
    out = subprocess.run(["iw", "phy", "phy0", "channels"], capture_output=True, text=True).stdout
    entry = out.split(f"* {mhz} MHz", 1)
    if len(entry) < 2:
        return False  # not a channel of this chip
    flags = entry[1].split("* ", 1)[0]
    return "No IR" not in flags and "Disabled" not in flags


class AccessPoint:
    def __init__(self, bus):
        self.bus = bus
        self.nm = dbus.Interface(bus.get_object(NM, "/org/freedesktop/NetworkManager"), NM)
        self.settings = dbus.Interface(bus.get_object(NM, "/org/freedesktop/NetworkManager/Settings"),
                                       NM + ".Settings")
        self.device = self.nm.GetDeviceByIpIface(INTERFACE)
        self.active = None
        self.ap_mac = None  # the second interface's address

    def permanent_mac(self):
        """The Wi-Fi's own address (NetworkManager uses random ones while it scans)."""
        return str(self._props(self.device).Get(NM + ".Device.Wireless", "PermHwAddress")).lower()

    def home(self):
        """The network wlan0 is on as a client, as (name, MHz), or None."""
        try:
            wifi = self._props(self.device)
            if wifi.Get(NM + ".Device.Wireless", "Mode") != 2:  # 2: a client of an access point
                return None
            ap = wifi.Get(NM + ".Device.Wireless", "ActiveAccessPoint")
            active = wifi.Get(NM + ".Device", "ActiveConnection")
            if ap == "/" or active == "/":
                return None
            return (str(self._props(active).Get(NM + ".Connection.Active", "Id")),
                    int(self._props(ap).Get(NM + ".AccessPoint", "Frequency")))
        except dbus.DBusException:
            return None

    def start(self, ssid, password, band, channel, country, keep_wifi):
        """Bring the access point up: with keep_wifi on a second interface, so wlan0
        stays on your Wi-Fi; on 2.4 GHz when 5 GHz is not allowed or does not come up.
        Returns (BSSID, band, channel, interface) as it runs."""
        if country:
            subprocess.run(["iw", "reg", "set", country], check=False)  # the country's Wi-Fi rules
        home = self.home()
        interfaces = [INTERFACE]
        if keep_wifi:
            try:
                interfaces.insert(0, self._second_interface())
            except (RuntimeError, OSError, subprocess.CalledProcessError, dbus.DBusException) as e:
                log(f"Wi-Fi: no second interface ({e}); the access point takes wlan0, away from your Wi-Fi")
        for interface in interfaces:
            tries = [(band, channel or DEFAULT_CHANNEL[band])]
            if interface == AP_INTERFACE and not channel and home and channel_of(home[1]):
                tries = [(band, channel_of(home[1]) if band == "2.4" else DEFAULT_CHANNEL[band])]  # one channel for both
            if band != "2.4":
                tries.append(("2.4", channel_of(home[1]) if home and channel_of(home[1]) else DEFAULT_CHANNEL["2.4"]))
            for band_, channel_ in tries:
                if not may_beacon(band_, channel_):
                    log(f"Wi-Fi: the board's Wi-Fi allows no access point on {band_} GHz, channel {channel_}")
                    continue
                mac = "permanent" if interface == INTERFACE else self.ap_mac
                profile = self._profile(access_point_settings, interface, mac, ssid, password, band_, channel_)
                try:
                    self.active = self.nm.ActivateConnection(profile, self.nm.GetDeviceByIpIface(interface), "/")
                except dbus.DBusException as e:
                    log(f"Wi-Fi: {interface}: {e.get_dbus_message()}")
                    continue
                if self._wait_activated():
                    bssid = Path(f"/sys/class/net/{interface}/address").read_text().strip()
                    stays = f", the board stays on {home[0]!r}" if interface == AP_INTERFACE and home else ""
                    log(f"Wi-Fi: access point {ssid!r} on {interface}, {band_} GHz, channel {channel_}, {ADDRESS},"
                        f" BSSID {bssid}{stays}")
                    return bssid, band_, channel_, interface
                log(f"Wi-Fi: the access point did not come up on {interface}, {band_} GHz, channel {channel_}")
            if interface == AP_INTERFACE:
                self._remove_second_interface()
        raise RuntimeError("the access point did not come up")

    def _second_interface(self):
        """A virtual interface for the access point next to wlan0, with an address of
        its own (wlan0's, marked as locally made), for NetworkManager to run it."""
        mac = self.permanent_mac()
        self.ap_mac = f"{int(mac[:2], 16) | 2:02x}{mac[2:]}"
        if not Path(f"/sys/class/net/{AP_INTERFACE}").exists():
            subprocess.run(["iw", "dev", INTERFACE, "interface", "add", AP_INTERFACE, "type", "__ap",
                            "addr", self.ap_mac], check=True, capture_output=True)
        for _ in range(40):
            try:
                device = self.nm.GetDeviceByIpIface(AP_INTERFACE)
                break
            except dbus.DBusException:
                time.sleep(0.25)
        else:
            raise RuntimeError(f"NetworkManager does not see {AP_INTERFACE}")
        props = self._props(device)
        props.Set(NM + ".Device", "Managed", True)
        props.Set(NM + ".Device", "Autoconnect", False)  # only for the access point, never your network
        for _ in range(40):  # "unavailable" until wpa_supplicant has taken it on
            if props.Get(NM + ".Device", "State") >= 30:  # 30: disconnected, i.e. ready
                return AP_INTERFACE
            time.sleep(0.25)
        raise RuntimeError(f"{AP_INTERFACE} does not get ready")

    def _remove_second_interface(self):
        if Path(f"/sys/class/net/{AP_INTERFACE}").exists():
            subprocess.run(["iw", "dev", AP_INTERFACE, "del"], check=False, capture_output=True)
            return True
        return False

    def stop(self):
        """Switch the access point off and remove its profile, also one left over from
        before (a crash, a power cut): NetworkManager goes back to your network."""
        found = False
        for active in self._props("/org/freedesktop/NetworkManager").Get(NM, "ActiveConnections"):
            try:
                if self._props(active).Get(NM + ".Connection.Active", "Id") == PROFILE_ID:
                    self.nm.DeactivateConnection(active)
                    found = True
            except dbus.DBusException:
                pass  # went meanwhile
        for path in self.settings.ListConnections():
            connection = dbus.Interface(self.bus.get_object(NM, path), NM + ".Settings.Connection")
            if connection.GetSettings()["connection"]["id"] == PROFILE_ID:
                connection.Delete()
                found = True
        self.active = None
        if self._remove_second_interface():
            found = True
        if found:
            log("Wi-Fi: access point off (wlan0 is on your Wi-Fi, or goes back to it)")

    def _profile(self, make, *args):
        for path in self.settings.ListConnections():
            connection = dbus.Interface(self.bus.get_object(NM, path), NM + ".Settings.Connection")
            current = connection.GetSettings()
            if current["connection"]["id"] == PROFILE_ID:
                connection.Update(make(*args, current["connection"]["uuid"]))
                return path
        return self.settings.AddConnection(make(*args, str(uuid.uuid4())))

    def _wait_activated(self, timeout_s=30):
        props = self._props(self.active)
        for _ in range(timeout_s * 2):
            try:
                state = props.Get(NM + ".Connection.Active", "State")
            except dbus.DBusException:
                return False  # gone: activation failed
            if state == 2:  # activated
                return True
            if state == 4:  # deactivated
                return False
            time.sleep(0.5)
        return False

    def _props(self, path):
        return dbus.Interface(self.bus.get_object(NM, path), "org.freedesktop.DBus.Properties")


# ---- Bluetooth: pairing, the Android Auto service, calling the phone ---------------------

class Agent(dbus.service.Object):
    """Accepts pairing without a PIN ("Just Works"), like a car or headset does.
    The board is only pairable for pairing_min minutes at a time (Bluetooth.open_pairing)."""
    IFACE = "org.bluez.Agent1"

    def __init__(self, bus, path, trust):
        super().__init__(bus, path)
        self.trust = trust

    @dbus.service.method(IFACE, in_signature="", out_signature="")
    def Release(self):
        pass

    @dbus.service.method(IFACE, in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid_):
        self.trust(device)

    @dbus.service.method(IFACE, in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        return "0000"

    @dbus.service.method(IFACE, in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        return dbus.UInt32(0)

    @dbus.service.method(IFACE, in_signature="ouq", out_signature="")
    def DisplayPasskey(self, device, passkey, entered):
        pass

    @dbus.service.method(IFACE, in_signature="os", out_signature="")
    def DisplayPinCode(self, device, pincode):
        pass

    @dbus.service.method(IFACE, in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        log(f"Bluetooth: pairing with {device_name(self.connection, device)}")
        self.trust(device)

    @dbus.service.method(IFACE, in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        self.trust(device)

    @dbus.service.method(IFACE, in_signature="", out_signature="")
    def Cancel(self):
        pass


class Profile(dbus.service.Object):
    """A Bluetooth service the board offers; BlueZ hands over each connection."""
    IFACE = "org.bluez.Profile1"

    def __init__(self, bus, path, name, on_connection, devices):
        super().__init__(bus, path)
        self.name = name
        self.on_connection = on_connection
        self.devices = devices  # the phones that connected, to hang up on when switched off
        self.sockets = set()

    @dbus.service.method(IFACE, in_signature="", out_signature="")
    def Release(self):
        log(f"Bluetooth: {self.name} released")

    @dbus.service.method(IFACE, in_signature="oha{sv}", out_signature="")
    def NewConnection(self, device, fd, properties):
        log(f"Bluetooth: {self.name} connection from {device_name(self.connection, device)}")
        self.devices.add(str(device))
        sock = socket.socket(fileno=fd.take())
        sock.setblocking(True)  # BlueZ hands it over non-blocking
        self.sockets.add(sock)
        threading.Thread(target=self._run, args=(sock,), daemon=True).start()

    def _run(self, sock):
        try:
            self.on_connection(sock)
        except OSError:
            pass  # closed: the phone went, or Android Auto was switched off
        finally:
            self.sockets.discard(sock)

    def close(self):
        """Hang up its connections and leave the bus."""
        for sock in list(self.sockets):
            hang_up(sock)
        self.remove_from_connection()

    @dbus.service.method(IFACE, in_signature="o", out_signature="")
    def RequestDisconnection(self, device):
        log(f"Bluetooth: {self.name} disconnected by {device_name(self.connection, device)}")


def hang_up(sock):
    """Wake whoever reads it; it may have closed already."""
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def device_name(bus, path):
    try:
        props = dbus.Interface(bus.get_object(BLUEZ, path), "org.freedesktop.DBus.Properties")
        return str(props.Get(BLUEZ + ".Device1", "Alias"))
    except dbus.DBusException:
        return str(path)


def tell_phone_the_wifi(sock, ssid, password, bssid):
    """The handshake on the Android Auto service's RFCOMM channel (protocol.py)."""
    with sock:
        sock.sendall(protocol.wifi_start_request(ADDRESS, PORT))
        log(f"Bluetooth: sent WifiStartRequest ({ADDRESS}:{PORT})")
        while (message := protocol.read_message(sock.recv)) is not None:
            message_id, payload = message
            log(f"Bluetooth: phone sent {protocol.NAMES.get(message_id, message_id)} {protocol.fields(payload)}")
            if message_id == protocol.WIFI_INFO_REQUEST:
                sock.sendall(protocol.wifi_info_response(ssid, password, bssid))
                log(f"Bluetooth: sent WifiInfoResponse ({ssid!r}, BSSID {bssid})")
    log("Bluetooth: Android Auto channel closed")


def hold(sock):
    """The headset (HSP) connection only makes the phone start Android Auto; keep it open."""
    with sock:
        while sock.recv(1024):
            pass


class Bluetooth:
    def __init__(self, bus):
        self.bus = bus
        self.adapter_path = next(path for path, ifaces in self._objects().items() if BLUEZ + ".Adapter1" in ifaces)
        self.adapter = dbus.Interface(bus.get_object(BLUEZ, self.adapter_path), "org.freedesktop.DBus.Properties")
        bluez = bus.get_object(BLUEZ, "/org/bluez")
        self.agents = dbus.Interface(bluez, BLUEZ + ".AgentManager1")
        self.profiles = dbus.Interface(bluez, BLUEZ + ".ProfileManager1")
        self.objects = []        # what we put on the bus: the agent and the two profiles
        self.timer = None        # call_phones() again and again
        self.devices = set()     # phones we connected to, or that connected to our services
        self.pairing_until = 0.0  # time.monotonic() when pairing closes

    def start(self, ssid, password, bssid, pairing_s):
        self.adapter.Set(BLUEZ + ".Adapter1", "Powered", True)
        self.objects = [Agent(self.bus, OUR + "/agent", self.trust)]
        self.agents.RegisterAgent(OUR + "/agent", "NoInputNoOutput")
        self.agents.RequestDefaultAgent(OUR + "/agent")
        self.objects.append(Profile(self.bus, OUR + "/profile", "Android Auto",
                                    lambda sock: tell_phone_the_wifi(sock, ssid, password, bssid), self.devices))
        # BlueZ picks a free RFCOMM channel; the phone finds it by the service's UUID.
        # (Channel 8, which the dongle project uses, is taken on the board.)
        self.profiles.RegisterProfile(OUR + "/profile", AA_UUID, {"Name": "AA Wireless", "Role": "server"})
        self.objects.append(Profile(self.bus, OUR + "/hsp", "headset", hold, self.devices))
        try:
            self.profiles.RegisterProfile(OUR + "/hsp", HSP_HS_UUID, {"Name": "HSP HS"})
        except dbus.DBusException as e:  # PipeWire may offer it already; the phone connects to that then
            log(f"Bluetooth: headset service not added ({e.get_dbus_message()})")
        log("Bluetooth: Android Auto service ready")
        self.open_pairing(pairing_s)
        self.call_phones()  # now, and then every RETRY_S until a phone is on the Wi-Fi
        self.timer = GLib.timeout_add_seconds(RETRY_S, self.call_phones)

    def open_pairing(self, seconds):
        """Let a new phone pair for a while; BlueZ closes it again by itself."""
        for prop in ("DiscoverableTimeout", "PairableTimeout"):
            self.adapter.Set(BLUEZ + ".Adapter1", prop, dbus.UInt32(seconds))
        self.adapter.Set(BLUEZ + ".Adapter1", "Pairable", True)
        self.adapter.Set(BLUEZ + ".Adapter1", "Discoverable", True)
        self.pairing_until = time.monotonic() + seconds
        name = str(self.adapter.Get(BLUEZ + ".Adapter1", "Alias"))
        log(f"Bluetooth: pair your phone with {name!r} in the next {seconds // 60} min")

    def stop(self):
        """Take everything back: the services, the agent, the calls to the phones,
        their connections, and pairing; the board is no longer visible."""
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = None
        for undo in (lambda: self.profiles.UnregisterProfile(OUR + "/profile"),
                     lambda: self.profiles.UnregisterProfile(OUR + "/hsp"),
                     lambda: self.agents.UnregisterAgent(OUR + "/agent")):
            try:
                undo()
            except dbus.DBusException:
                pass  # was not there (e.g. PipeWire has the headset service)
        for obj in self.objects:
            if isinstance(obj, Profile):
                obj.close()
            else:
                obj.remove_from_connection()
        self.objects = []
        for device in self.devices:
            try:
                dbus.Interface(self.bus.get_object(BLUEZ, device), BLUEZ + ".Device1").Disconnect()
                log(f"Bluetooth: hung up on {device_name(self.bus, device)}")
            except dbus.DBusException:
                pass  # gone already
        self.devices.clear()
        self.hide()

    def hide(self):
        """Not visible and not pairable; also what a crash or power cut left on."""
        self.pairing_until = 0.0
        for prop in ("Discoverable", "Pairable"):
            try:
                self.adapter.Set(BLUEZ + ".Adapter1", prop, False)
            except dbus.DBusException:
                pass

    def paired(self):
        """The names of the paired phones."""
        return sorted(str(ifaces[BLUEZ + ".Device1"].get("Alias")) for ifaces in self._objects().values()
                      if ifaces.get(BLUEZ + ".Device1", {}).get("Paired"))

    def trust(self, device):
        props = dbus.Interface(self.bus.get_object(BLUEZ, device), "org.freedesktop.DBus.Properties")
        props.Set(BLUEZ + ".Device1", "Trusted", True)

    def call_phones(self):
        """Like a car, connect to the paired phones (headset profile), every RETRY_S
        until one comes over the Wi-Fi: that makes the phone start wireless Android
        Auto. Runs in the main loop and does not wait for the answers: BlueZ hands
        the connection to the main loop meanwhile (Profile.NewConnection)."""
        if phone_on_wifi.is_set():
            self.timer = None
            return GLib.SOURCE_REMOVE
        for path, ifaces in self._objects().items():
            device = ifaces.get(BLUEZ + ".Device1")
            if not device or not device.get("Paired"):
                continue
            name = str(device.get("Alias"))
            self.devices.add(str(path))
            dbus.Interface(self.bus.get_object(BLUEZ, path), BLUEZ + ".Device1").ConnectProfile(
                HSP_AG_UUID, timeout=30,
                reply_handler=lambda name=name: log(f"Bluetooth: connected to {name}"),
                error_handler=lambda e, name=name: log(f"Bluetooth: {name} not reachable ({e.get_dbus_message()})"))
        return GLib.SOURCE_CONTINUE

    def _objects(self):
        manager = dbus.Interface(self.bus.get_object(BLUEZ, "/"), "org.freedesktop.DBus.ObjectManager")
        return manager.GetManagedObjects()


# ---- the phone's Android Auto connection ---------------------------------------------------

def post(path, body=None, timeout=3):
    """To the companion app (python/main.py); returns its JSON answer."""
    request = urllib.request.Request(COMPANION + path, method="POST", data=json.dumps(body).encode() if body else None,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read() or b"null")


def tell_companion(connected):
    """The companion app shows it: an animation and a line (rules.json, "android_auto")."""
    try:
        post(f"/android_auto?connected={'true' if connected else 'false'}")
    except (OSError, ValueError) as e:
        log(f"Companion app: not reached ({e})")


class PhoneServer:
    """The port the phone opens its Android Auto connection to, over the Wi-Fi."""

    def __init__(self):
        phone_on_wifi.clear()
        self.sock = socket.create_server(("0.0.0.0", PORT), reuse_port=True)
        self.clients = set()
        self.lock = threading.Lock()
        threading.Thread(target=self._serve, daemon=True).start()
        log(f"Android Auto: waiting for the phone on port {PORT}")

    def close(self):
        """Stop listening and hang up; the companion hears it from _watch()."""
        self.sock.shutdown(socket.SHUT_RDWR)  # wakes accept()
        self.sock.close()
        for client in list(self.clients):
            hang_up(client)

    def _serve(self):
        while True:
            try:
                client, (host, port) = self.sock.accept()
            except OSError:
                return  # closed
            phone_on_wifi.set()
            log(f"Android Auto: the phone connected from {host} (phase 2 passes this on to the car)")
            threading.Thread(target=self._watch, args=(client,), daemon=True).start()

    def _watch(self, client):
        """Phase 1: the car would speak first, so the phone waits; log what comes until it gives up."""
        with self.lock:
            self.clients.add(client)
            if len(self.clients) == 1:
                tell_companion(True)
        total = 0
        with client:
            try:
                while data := client.recv(16384):
                    total += len(data)
            except OSError:
                pass
        log(f"Android Auto: the phone's connection closed ({total} bytes received)")
        with self.lock:
            self.clients.discard(client)
            if not self.clients:
                tell_companion(False)


class Passthrough:
    """Follows android_auto in the companion's settings and reports to it."""

    def __init__(self, bus):
        self.wifi, self.bluetooth = AccessPoint(bus), Bluetooth(bus)
        self.server = None
        self.applied = None      # the settings it runs with
        self.retry_at = 0.0
        self.state, self.error, self.running = "off", "", {}
        self.reached = True      # whether the last report reached the companion
        # A clean start, whatever a crash or power cut left switched on.
        self.wifi.stop()
        self.bluetooth.hide()

    def follow(self):
        aa = setting.read(CONFIG)
        wanted = {k: aa[k] for k in ("keep_wifi", "wifi_name", "wifi_password", "wifi_band", "wifi_channel",
                                     "country")}
        if self.server and (not aa["enabled"] or wanted != self.applied):
            log("Android Auto: switched off in the settings" if not aa["enabled"]
                else "Android Auto: settings changed, starting again")
            self.stop()
        if aa["enabled"] and not self.server and time.monotonic() >= self.retry_at:
            log("Android Auto: switched on in the settings")
            self.start(aa, wanted)
        elif not aa["enabled"]:
            self.state, self.error, self.retry_at = "off", "", 0.0  # also after a failed start
        self.report(aa)
        return GLib.SOURCE_CONTINUE

    def start(self, aa, wanted):
        try:
            ssid, password = wifi_secrets(self.wifi.permanent_mac(), aa["wifi_name"], aa["wifi_password"])
            bssid, band, channel, interface = self.wifi.start(ssid, password, aa["wifi_band"], aa["wifi_channel"],
                                                              aa["country"], aa["keep_wifi"])
            self.server = PhoneServer()
            self.bluetooth.start(ssid, password, bssid, round(aa["pairing_min"] * 60))
        except (RuntimeError, OSError, dbus.DBusException) as e:
            error = e.get_dbus_message() if isinstance(e, dbus.DBusException) else str(e)
            log(f"Android Auto: could not start ({error}); trying again in a minute")
            self.stop()
            self.state, self.error = "error", error
            self.retry_at = time.monotonic() + 60
            return
        self.applied = wanted
        self.state, self.error = "on", ""
        self.running = {"wifi_name": ssid, "wifi_password": password, "band": band, "channel": channel,
                        "interface": interface}

    def stop(self):
        self.bluetooth.stop()
        if self.server:
            self.server.close()
            self.server = None
        self.wifi.stop()
        self.applied, self.state, self.running = None, "off", {}

    def report(self, aa):
        """What it does, for Configure > Board; the answer may ask to open pairing."""
        home = self.wifi.home()
        status = {"state": self.state, "error": self.error, **self.running, "home": home[0] if home else None,
                  "phone": bool(self.server and self.server.clients),
                  "pairing_s": max(0, round(self.bluetooth.pairing_until - time.monotonic())),
                  "paired": self.bluetooth.paired()}
        try:
            answer = post("/android_auto/status", status, timeout=2) or {}
        except (OSError, ValueError) as e:
            if self.reached:
                log(f"Companion app: not reached ({e}); trying on")
            self.reached = False
            return
        self.reached = True
        if answer.get("pair") and self.server:
            self.bluetooth.open_pairing(round(aa["pairing_min"] * 60))


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    loop = GLib.MainLoop()
    passthrough = Passthrough(dbus.SystemBus())

    def stop():
        loop.quit()
        return GLib.SOURCE_REMOVE
    # The main loop waits in C, where Python's own signal handlers would not run.
    for number in (signal.SIGTERM, signal.SIGINT):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, number, stop)

    log(f"Android Auto bridge: follows android_auto in {CONFIG}/settings.json")
    passthrough.follow()
    GLib.timeout_add_seconds(CHECK_S, passthrough.follow)
    try:
        loop.run()
    finally:
        if passthrough.server:
            passthrough.stop()


if __name__ == "__main__":
    main()
