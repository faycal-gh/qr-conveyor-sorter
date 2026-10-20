"""NetworkManager boundary. Secrets travel in root-only keyfiles, never argv."""

import ipaddress
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

AP_UUID = "c21e5d04-bd50-4cd8-bd6c-4ff222db3748"
AP_ADDRESS = "192.168.4.1"


def split_fields(line):
    fields, current, escaped = [], "", False
    for char in line:
        if escaped:
            current += char
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            fields.append(current)
            current = ""
        else:
            current += char
    return fields + [current]


def key_string(text):
    return text.replace("\\", "\\\\").replace(" ", "\\s")


class NetworkManager:
    def __init__(
        self,
        config,
        profile_dir="/etc/NetworkManager/system-connections",
        runner=subprocess.run,
    ):
        self.config = config
        self.interface = config["interface"]
        self.directory = Path(profile_dir)
        self.runner = runner

    def nm(self, *arguments):
        try:
            return self.runner(
                ["nmcli", "--wait", "40", *arguments],
                capture_output=True,
                text=True,
                check=True,
                timeout=45,
                env={**os.environ, "LC_ALL": "C"},
            ).stdout.strip()
        except (subprocess.SubprocessError, OSError):
            # nmcli errors may echo profile details; never propagate raw output.
            raise RuntimeError(
                "Network operation failed; check password, signal and DHCP"
            ) from None

    def active_uuid(self):
        return self.nm("-g", "GENERAL.CON-UUID", "device", "show", self.interface)

    def address(self):
        if self.active_uuid() == AP_UUID:
            return None
        for entry in self.nm(
            "-g", "IP4.ADDRESS", "device", "show", self.interface
        ).splitlines():
            try:
                address = ipaddress.IPv4Interface(entry).ip
            except ValueError:
                continue
            if (
                not (
                    address.is_link_local
                    or address.is_loopback
                    or address.is_unspecified
                )
                and str(address) != AP_ADDRESS
            ):
                return str(address)
        return None

    def write_profile(self, credentials, identifier, hotspot=False):
        name = "qr-wifi-setup" if hotspot else "qr-wifi-trial-" + identifier
        profile = (
            f"[connection]\nid={name}\nuuid={identifier}\ntype=wifi\n"
            f"interface-name={self.interface}\nautoconnect=false\n\n[wifi]\n"
            "ssid="
            + "".join(f"{byte};" for byte in credentials["ssid"].encode("utf-8"))
            + "\n"
            f"mode={'ap' if hotspot else 'infrastructure'}\n"
            f"hidden={str(credentials.get('hidden', False)).lower()}\n"
        )
        if credentials["security"] != "open":
            profile += (
                "\n[wifi-security]\nkey-mgmt=" + credentials["security"] + "\n"
                "psk=" + key_string(credentials["password"]) + "\n"
            )
            if hotspot:
                profile += "proto=rsn;\npairwise=ccmp;\ngroup=ccmp;\n"
        profile += "\n[ipv4]\n" + (
            "method=shared\naddress1=192.168.4.1/24\n" if hotspot else "method=auto\n"
        )
        profile += "\n[ipv6]\nmethod=disabled\n"
        path = self.directory / (name + ".nmconnection")
        descriptor, name = tempfile.mkstemp(dir=self.directory, prefix=".qr-wifi-")
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(profile)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        self.nm("connection", "load", str(path))
        return path

    def start_hotspot(self):
        self.write_profile(
            {
                "ssid": self.config["ssid"],
                "password": self.config["password"],
                "security": "wpa-psk",
            },
            AP_UUID,
            True,
        )
        self.nm("connection", "up", "uuid", AP_UUID, "ifname", self.interface)

    def stop_hotspot(self):
        if self.active_uuid() == AP_UUID:
            self.nm("connection", "down", "uuid", AP_UUID)

    def scan(self):
        output = self.nm(
            "-t",
            "-f",
            "SSID,SIGNAL,SECURITY",
            "device",
            "wifi",
            "list",
            "ifname",
            self.interface,
            "--rescan",
            "yes",
        )
        networks = {}
        for line in output.splitlines():
            fields = split_fields(line)
            if len(fields) != 3 or not fields[0] or not fields[1].isdigit():
                continue
            ssid, signal, security = fields
            entry = {
                "ssid": ssid,
                "signal": int(signal),
                "security": security or "Open",
            }
            if ssid not in networks or entry["signal"] > networks[ssid]["signal"]:
                networks[ssid] = entry
        return sorted(networks.values(), key=lambda entry: -entry["signal"])

    def connect(self, credentials):
        identifier = str(uuid.uuid4())
        path = self.directory / ("qr-wifi-trial-" + identifier + ".nmconnection")
        try:
            path = self.write_profile(credentials, identifier)
            self.nm("connection", "up", "uuid", identifier, "ifname", self.interface)
            address = self.address()
            if self.active_uuid() != identifier or not address:
                raise RuntimeError("Wi-Fi did not receive a usable IPv4 address")
            self.nm(
                "connection",
                "modify",
                "uuid",
                identifier,
                "connection.autoconnect",
                "yes",
            )
            return address
        except RuntimeError:
            try:
                self.nm("connection", "delete", "uuid", identifier)
            finally:
                path.unlink(missing_ok=True)
            raise

    def recover_trials(self):
        """Promote a verified active trial after a crash; discard inactive unfinished trials."""
        active = self.active_uuid()
        for path in self.directory.glob("qr-wifi-trial-*.nmconnection"):
            identifier = path.stem.removeprefix("qr-wifi-trial-")
            autoconnect = self.nm(
                "-g", "connection.autoconnect", "connection", "show", "uuid", identifier
            )
            if autoconnect == "yes":
                continue
            if identifier == active and self.address():
                self.nm(
                    "connection",
                    "modify",
                    "uuid",
                    identifier,
                    "connection.autoconnect",
                    "yes",
                )
            else:
                self.nm("connection", "delete", "uuid", identifier)
                path.unlink(missing_ok=True)
