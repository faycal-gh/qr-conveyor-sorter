import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def api():
    assert importlib.util.find_spec("wifi_provisioning"), (
        "Provisioning package is missing"
    )
    from wifi_provisioning.controller import Controller, validate_credentials

    return Controller, validate_credentials


class Network:
    def __init__(self):
        self.ip = None
        self.hotspot = False
        self.fail = False
        self.saved = []
        self.scans = 0

    def address(self):
        return self.ip

    def start_hotspot(self):
        self.hotspot = True

    def stop_hotspot(self):
        self.hotspot = False

    def scan(self):
        self.scans += 1
        return [{"ssid": "Office", "signal": 82, "security": "WPA2"}]

    def connect(self, credentials):
        if self.fail:
            raise RuntimeError("Authentication or IP assignment failed")
        self.ip = "192.168.1.42"
        self.saved.append(credentials["ssid"])
        return self.ip


@pytest.mark.parametrize("restored", [False, True])
def test_boot_and_loss_allow_full_60_seconds(restored):
    Controller, _ = api()
    net = Network()
    control = Controller(net, now=0)
    control.tick(59)
    assert not net.hotspot
    if restored:
        net.ip = "192.168.1.8"
    control.tick(60)
    assert net.hotspot is not restored
    if restored:
        net.ip = None
        control.tick(70)
        control.tick(129)
        assert not net.hotspot
        control.tick(130)
        assert net.hotspot


def test_saved_connection_and_service_restart_do_not_start_hotspot():
    Controller, _ = api()
    net = Network()
    net.ip = "192.168.1.8"
    for boot in (0, 200):
        control = Controller(net, now=boot)
        control.tick(boot + 61)
        assert control.status()["ip"] == net.ip
        assert not net.hotspot


@pytest.mark.parametrize("fail", [False, True])
def test_connection_transition_is_delayed_serialized_and_recovers(fail):
    Controller, _ = api()
    net = Network()
    control = Controller(net, now=0)
    control.tick(60)
    net.fail = fail
    reply = control.request(
        {
            "action": "connect",
            "ssid": "Office",
            "password": "test-secret",
            "security": "wpa-psk",
        },
        61,
    )
    assert reply["state"] == "connecting"
    assert "test-secret" not in str(reply)
    with pytest.raises(ValueError, match="progress"):
        control.request({"action": "rescan"}, 62)
    control.tick(68)
    assert net.hotspot
    control.tick(69)
    assert net.hotspot is fail
    assert control.status()["state"] == ("setup" if fail else "online")
    assert bool(control.status()["error"]) is fail
    if not fail:
        assert net.saved == ["Office"]
        assert control.status()["ip"] == "192.168.1.42"


def test_scan_temporarily_switches_adapter_and_restores_portal():
    Controller, _ = api()
    net = Network()
    control = Controller(net, now=0)
    control.tick(60)
    control.request({"action": "rescan"}, 61)
    control.tick(69)
    assert net.hotspot
    assert control.status()["networks"][0]["signal"] == 82


@pytest.mark.parametrize(
    "fields",
    [
        {"ssid": ""},
        {"ssid": "x" * 33},
        {"ssid": "x\n[evil]"},
        {"ssid": "Office", "password": "short"},
        {"ssid": "Office", "security": "enterprise"},
        {"ssid": "Office", "hidden": "false"},
        {"ssid": "Office", "password": "secret\nkey=value"},
    ],
)
def test_invalid_credentials_are_rejected(fields):
    _, validate = api()
    with pytest.raises(ValueError):
        validate({"password": "test-secret", "security": "wpa-psk", **fields})


def test_ssid_shell_characters_remain_literal():
    _, validate = api()
    ssid = '$(touch /tmp/pwn);"'
    assert (
        validate({"ssid": ssid, "password": "test-secret", "security": "wpa-psk"})[
            "ssid"
        ]
        == ssid
    )


def network_api():
    assert importlib.util.find_spec("wifi_provisioning.network"), (
        "Network backend missing"
    )
    from wifi_provisioning.network import NetworkManager, split_fields

    return NetworkManager, split_fields


def test_nmcli_escaped_network_names_and_security_are_preserved():
    _, split_fields = network_api()
    assert split_fields(r"Cafe\:west\\room:80:WPA2") == [
        "Cafe:west\\room",
        "80",
        "WPA2",
    ]


@pytest.mark.parametrize("fail", [False, True])
def test_trial_profile_is_private_secret_never_in_argv_and_failure_removes_trial(
    tmp_path, fail
):
    NetworkManager, _ = network_api()
    commands = []
    profiles = []

    def run(argv, **kwargs):
        commands.append(argv)
        if "load" in argv:
            path = Path(argv[-1])
            profiles.append(path.read_text())
            assert path.stat().st_mode & 0o077 == 0 or sys.platform == "win32"
        if "up" in argv and fail:
            raise RuntimeError("Network operation failed")
        from subprocess import CompletedProcess

        if "GENERAL.CON-UUID" in argv:
            output = profiles[-1].split("uuid=")[1].splitlines()[0]
        elif "IP4.ADDRESS" in argv:
            output = "192.168.1.42/24\n"
        else:
            output = ""
        return CompletedProcess(argv, 0, output, "")

    net = NetworkManager(
        {"interface": "wlan0", "ssid": "Setup", "password": "setup-secret"},
        profile_dir=tmp_path,
        runner=run,
    )
    credentials = {
        "ssid": "$(echo injected)",
        "password": "test-secret",
        "security": "wpa-psk",
        "hidden": True,
    }
    if fail:
        with pytest.raises(RuntimeError):
            net.connect(credentials)
        assert not list(tmp_path.glob("qr-wifi-trial-*"))
    else:
        assert net.connect(credentials) == "192.168.1.42"
        assert any("connection.autoconnect" in cmd for cmd in commands)
    assert "test-secret" in profiles[0]
    assert all("test-secret" not in str(cmd) for cmd in commands)
    assert "hidden=true" in profiles[0]
    assert "[evil]" not in profiles[0]


def test_hotspot_address_is_never_reported_as_client_connection(tmp_path):
    NetworkManager, _ = network_api()
    from subprocess import CompletedProcess

    def run(argv, **kwargs):
        return CompletedProcess(argv, 0, "192.168.4.1/24\n", "")

    net = NetworkManager({"interface": "wlan0"}, profile_dir=tmp_path, runner=run)
    assert net.address() is None


def test_http_requests_require_same_origin_and_secret_token():
    assert importlib.util.find_spec("wifi_provisioning.web"), "Web boundary missing"
    from wifi_provisioning.web import allowed_request

    assert allowed_request(
        "192.168.4.1:8080", "http://192.168.4.1:8080", "token", "token"
    )
    assert not allowed_request("evil.test", "http://evil.test", "token", "token")
    assert not allowed_request("192.168.4.1:8080", "http://evil.test", "token", "token")
    assert not allowed_request(
        "192.168.4.1:8080", "http://192.168.4.1:8080", "", "token"
    )


def test_single_instance_lock_blocks_duplicate_and_releases_on_exit(tmp_path):
    assert importlib.util.find_spec("wifi_provisioning.daemon"), "Daemon missing"
    from wifi_provisioning.daemon import instance_lock

    lock = tmp_path / "lock"
    with (
        instance_lock(lock),
        pytest.raises(RuntimeError, match="already running"),
        instance_lock(lock),
    ):
        pytest.fail("duplicate acquired lock")
    with instance_lock(lock):
        pass


def test_rpc_rejects_malformed_or_oversized_payload_without_echoing_secret():
    assert importlib.util.find_spec("wifi_provisioning.ipc"), "IPC missing"
    from wifi_provisioning.ipc import decode_request

    for payload in (b"password=secret", b"[]", b"x" * 8193, b"[" * 4000 + b"]" * 4000):
        with pytest.raises(ValueError) as error:
            decode_request(payload)
        assert "secret" not in str(error.value)


def test_failed_keyfile_load_removes_secret_file(tmp_path):
    NetworkManager, _ = network_api()
    from subprocess import CompletedProcess

    def run(argv, **kwargs):
        if "load" in argv:
            raise RuntimeError("Network operation failed")
        return CompletedProcess(argv, 0, "", "")

    net = NetworkManager({"interface": "wlan0"}, profile_dir=tmp_path, runner=run)
    with pytest.raises(RuntimeError):
        net.connect(
            {"ssid": "Office", "password": "test-secret", "security": "wpa-psk"}
        )
    assert not list(tmp_path.glob("*.nmconnection"))


def test_daemon_restart_promotes_only_verified_active_trial(tmp_path):
    NetworkManager, _ = network_api()
    from subprocess import CompletedProcess

    active = "88b28e13-a274-4b20-ac9f-4fe289982512"
    inactive = "12053cec-33a8-4784-a99b-77ddc4a324f9"
    commands = []

    def run(argv, **kwargs):
        commands.append(argv)
        if "GENERAL.CON-UUID" in argv:
            output = active
        elif "IP4.ADDRESS" in argv:
            output = "192.168.1.42/24"
        elif "show" in argv:
            output = "no"
        else:
            output = ""
        return CompletedProcess(argv, 0, output, "")

    for identifier in (active, inactive):
        (tmp_path / f"qr-wifi-trial-{identifier}.nmconnection").write_text("unfinished")
    net = NetworkManager({"interface": "wlan0"}, profile_dir=tmp_path, runner=run)
    net.recover_trials()
    assert (tmp_path / f"qr-wifi-trial-{active}.nmconnection").exists()
    assert not (tmp_path / f"qr-wifi-trial-{inactive}.nmconnection").exists()
    assert any("modify" in argv and active in argv for argv in commands)
    assert not any("delete" in argv and active in argv for argv in commands)


def test_scan_parses_and_deduplicates_real_nmcli_output(tmp_path):
    NetworkManager, _ = network_api()
    from subprocess import CompletedProcess

    def run(argv, **kwargs):
        return CompletedProcess(
            argv, 0, "Office:20:WPA2\nOffice:82:WPA2\nCafe\\:West:45:--\n:9:WPA2", ""
        )

    net = NetworkManager({"interface": "wlan0"}, profile_dir=tmp_path, runner=run)
    assert net.scan() == [
        {"ssid": "Office", "signal": 82, "security": "WPA2"},
        {"ssid": "Cafe:West", "signal": 45, "security": "--"},
    ]


def test_scan_failure_restores_setup_and_allows_next_attempt():
    Controller, _ = api()

    class FailingScan(Network):
        def scan(self):
            raise RuntimeError("Scan unavailable; please retry")

    net = FailingScan()
    control = Controller(net, now=0)
    control.tick(60)
    control.request({"action": "rescan"}, 61)
    control.tick(69)
    assert net.hotspot
    assert control.status()["error"] == "Scan unavailable; please retry"
    assert control.request({"action": "rescan"}, 70)["state"] == "scanning"


def test_http_boundary_serves_status_and_blocks_cross_origin_actions():
    import http.client
    import json
    import threading
    from http.server import HTTPServer

    from wifi_provisioning.web import Handler

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection(*server.server_address, timeout=3)
        connection.request("GET", "/", headers={"Host": "192.168.4.1:8080"})
        response = connection.getresponse()
        assert response.status == 200
        assert b"Before you connect" in response.read()
        assert "frame-ancestors 'none'" in response.getheader("Content-Security-Policy")
        connection.request(
            "POST",
            "/api/action",
            body=json.dumps({"action": "rescan"}),
            headers={"Host": "192.168.4.1:8080", "Origin": "http://evil.test"},
        )
        response = connection.getresponse()
        assert response.status == 403
        response.read()
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_disconnected_ipc_client_cannot_crash_service():
    from wifi_provisioning.daemon import serve_request

    class ResetConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def settimeout(self, _timeout):
            pass

        def recv(self, _size):
            raise ConnectionResetError()

        def sendall(self, _payload):
            raise BrokenPipeError()

    # A Unix transport reset is a boundary failure, not a controller failure.
    class Listener:
        def accept(self):
            return ResetConnection(), None

    Controller, _ = api()
    control = Controller(Network(), now=0)
    serve_request(Listener(), control)
    assert control.status()["state"] == "waiting"


def test_interrupted_profile_replacement_preserves_previous_file(tmp_path, monkeypatch):
    import os
    from subprocess import CompletedProcess

    from wifi_provisioning.network import AP_UUID, NetworkManager

    path = tmp_path / "qr-wifi-setup.nmconnection"
    path.write_text("previous working profile")

    def interrupted(_source, _destination):
        raise OSError("Disk error")

    monkeypatch.setattr(os, "replace", interrupted)
    net = NetworkManager(
        {"interface": "wlan0"},
        profile_dir=tmp_path,
        runner=lambda argv, **kwargs: CompletedProcess(argv, 0, "", ""),
    )
    with pytest.raises(OSError, match="Disk error"):
        net.write_profile(
            {"ssid": "Setup", "password": "test-secret", "security": "wpa-psk"},
            AP_UUID,
            True,
        )
    assert path.read_text() == "previous working profile"
    assert list(tmp_path.iterdir()) == [path]
