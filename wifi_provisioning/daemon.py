"""Root-only serialized network service; no HTTP parsing or GPIO access."""

import json
import logging
import os
import signal
import socket
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

from .controller import Controller, validate_credentials
from .ipc import SOCKET, decode_request, receive
from .network import AP_UUID, NetworkManager

RUNTIME = Path("/run/qr-wifi")
CONFIG = Path("/etc/qr-wifi/config.json")
LOGGER = logging.getLogger(__name__)


@contextmanager
def instance_lock(path):
    with open(path, "a+b") as stream:
        try:
            if os.name == "nt":
                import msvcrt

                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError("Provisioning service is already running") from None
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def read_config():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    validate_credentials(
        {"ssid": config["ssid"], "password": config["password"], "security": "wpa-psk"}
    )
    import re

    if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,15}", config["interface"]):
        raise ValueError("Invalid Wi-Fi interface")
    return config


def portal(command):
    subprocess.run(
        ["systemctl", command, "qr-wifi-web.service"],
        check=True,
        timeout=15,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def serve_request(listener, control):
    connection, _ = listener.accept()
    with connection:
        connection.settimeout(2)
        try:
            request = decode_request(receive(connection))
            reply = control.request(request, time.monotonic())
        except ValueError as exc:
            reply = {"error": str(exc)}
        except OSError:
            return
        try:
            connection.sendall(json.dumps(reply).encode() + b"\n")
        except (BrokenPipeError, ConnectionResetError):
            pass


def run():
    network = NetworkManager(read_config())
    network.recover_trials()
    if network.active_uuid() != AP_UUID and not network.address():
        network.nm("device", "set", network.interface, "autoconnect", "yes")
    control = Controller(network, time.monotonic())
    if network.active_uuid() == AP_UUID:
        control.setup()
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    Path(SOCKET).unlink(missing_ok=True)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(SOCKET)
        os.chmod(SOCKET, 0o660)
        import grp

        os.chown(SOCKET, 0, grp.getgrnam("qr-wifi").gr_gid)
        listener.listen(8)
        listener.settimeout(1)
        previous = None
        try:
            while not stopping:
                if (RUNTIME / "force").exists():
                    (RUNTIME / "force").unlink()
                    control.pending = None
                    control.setup()
                control.tick(time.monotonic())
                if control.state != previous:
                    LOGGER.info(
                        "Wi-Fi state: %s; address: %s",
                        control.state,
                        control.ip or "none",
                    )
                    if control.state == "setup":
                        portal("start")
                    elif control.state == "online":
                        portal("stop")
                    previous = control.state
                try:
                    serve_request(listener, control)
                except TimeoutError:
                    continue
        finally:
            try:
                portal("stop")
            finally:
                network.stop_hotspot()
                Path(SOCKET).unlink(missing_ok=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    with instance_lock(RUNTIME / "instance.lock"):
        run()
