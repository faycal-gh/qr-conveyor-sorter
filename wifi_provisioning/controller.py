"""Serialized single-adapter provisioning state machine."""

import socket


def validate_credentials(request):
    ssid = request.get("ssid")
    password = request.get("password", "")
    security = request.get("security", "wpa-psk")
    hidden = request.get("hidden", False)
    if not isinstance(ssid, str) or not 1 <= len(ssid.encode("utf-8")) <= 32:
        raise ValueError("SSID must contain 1–32 UTF-8 bytes")
    if any(ord(c) < 32 or ord(c) == 127 for c in ssid):
        raise ValueError("SSID contains unsupported control characters")
    if security not in ("open", "wpa-psk", "sae") or type(hidden) is not bool:
        raise ValueError("Choose Open, WPA/WPA2 Personal or WPA3 Personal")
    if not isinstance(password, str) or any(
        ord(c) < 32 or ord(c) > 126 for c in password
    ):
        raise ValueError("Password must use printable ASCII characters")
    if security == "open":
        password = ""
    elif not 8 <= len(password) <= 63:
        raise ValueError("Personal Wi-Fi password must contain 8–63 characters")
    return {"ssid": ssid, "password": password, "security": security, "hidden": hidden}


class Controller:
    def __init__(self, network, now):
        self.network = network
        self.lost_since = now
        self.state = "waiting"
        self.ip = None
        self.error = ""
        self.networks = []
        self.pending = None

    def status(self):
        return {
            "state": self.state,
            "ip": self.ip,
            "error": self.error,
            "networks": self.networks,
            "hostname": socket.gethostname() + ".local",
        }

    def setup(self):
        self.network.start_hotspot()
        self.state = "setup"
        self.ip = None

    def request(self, request, now):
        action = request.get("action")
        if action == "status":
            return self.status()
        if self.pending:
            raise ValueError("An operation is already in progress")
        if self.state != "setup" or action not in ("connect", "rescan"):
            raise ValueError("Action is available only in setup mode")
        credentials = validate_credentials(request) if action == "connect" else None
        self.pending = (now + 8, action, credentials)
        self.state = "connecting" if action == "connect" else "scanning"
        self.error = ""
        return self.status()

    def execute_pending(self):
        _, action, credentials = self.pending
        try:
            self.network.stop_hotspot()
            if action == "rescan":
                self.networks = self.network.scan()
                self.setup()
            else:
                self.ip = self.network.connect(credentials)
                self.state = "online"
                self.lost_since = None
        except RuntimeError as exc:
            self.error = str(exc)
            self.setup()
        finally:
            self.pending = None

    def tick(self, now):
        if self.pending:
            if now >= self.pending[0]:
                self.execute_pending()
            return
        if self.state == "setup":
            return
        self.ip = self.network.address()
        if self.ip:
            self.state = "online"
            self.lost_since = None
        else:
            if self.lost_since is None:
                self.lost_since = now
            self.state = "waiting"
            if now - self.lost_since >= 60:
                self.setup()
