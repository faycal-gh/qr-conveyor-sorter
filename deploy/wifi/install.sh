#!/bin/bash
set -euo pipefail
umask 077
export LC_ALL=C

[[ $EUID -eq 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
action=${1:-preflight}
target=/opt/qr-wifi
config=/etc/qr-wifi/config.json
interface=wlan0
if [[ -f $config ]]; then
    interface=$(python3 -c 'import json; print(json.load(open("/etc/qr-wifi/config.json"))["interface"])')
fi

preflight() {
    for command in python3 nmcli systemctl ip; do
        command -v "$command" >/dev/null || { echo "Missing: $command" >&2; exit 1; }
    done
    systemctl is-active --quiet NetworkManager || { echo 'NetworkManager must already manage Wi-Fi. No changes made.' >&2; exit 1; }
    [[ $(nmcli -g GENERAL.TYPE device show "$interface") == wifi ]] || { echo 'Configure a valid Wi-Fi interface.' >&2; exit 1; }
    [[ $(nmcli -g WIFI-PROPERTIES.AP device show "$interface") == yes ]] || { echo 'Adapter does not advertise AP support.' >&2; exit 1; }
    [[ $(nmcli radio wifi) == enabled ]] || { echo 'Enable Wi-Fi and set the WLAN country with raspi-config first.' >&2; exit 1; }
    if ip -4 route show | grep -Eq '^192\.168\.4\.0/24 ' && ! nmcli -g GENERAL.CON-UUID device show "$interface" | grep -qx 'c21e5d04-bd50-4cd8-bd6c-4ff222db3748'; then
        echo '192.168.4.0/24 conflicts with an existing network. Resolve before activating.' >&2
        exit 1
    fi
    if [[ -f $config ]]; then
        (cd "$target" && python3 -c 'from wifi_provisioning.daemon import read_config; read_config()')
    fi
    echo 'Preflight passed. No network changes or scans performed.'
    nmcli -g GENERAL.STATE,IP4.ADDRESS device show "$interface"
}

cancel_timer() {
    systemctl stop qr-wifi-rollback.timer 2>/dev/null || true
    systemctl reset-failed qr-wifi-rollback.service 2>/dev/null || true
}

rollback() {
    cancel_timer
    systemctl disable --now qr-wifi.service
    systemctl stop qr-wifi-web.service
    # The owned AP may survive an unclean daemon exit.
    if [[ $(nmcli -g GENERAL.CON-UUID device show "$interface") == c21e5d04-bd50-4cd8-bd6c-4ff222db3748 ]]; then
        nmcli connection down uuid c21e5d04-bd50-4cd8-bd6c-4ff222db3748
    fi
    if [[ $(nmcli -g GENERAL.STATE device show "$interface") != 100* ]]; then
        nmcli device set "$interface" autoconnect yes
    fi
    echo 'Provisioning disabled. Saved client profiles and SSH settings retained.'
}

case "$action" in
preflight)
    preflight
    ;;
install)
    preflight
    if systemctl is-active --quiet qr-wifi.service; then
        echo 'For upgrades, run rollback while connected to normal Wi-Fi before installing.' >&2
        exit 1
    fi
    source_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
    [[ -f $source_root/wifi_provisioning/daemon.py ]] || { echo 'Install from the repository.' >&2; exit 1; }
    apt-get update
    apt-get install -y python3 dnsmasq-base avahi-daemon
    getent group qr-wifi >/dev/null || groupadd --system qr-wifi
    id qr-wifi >/dev/null 2>&1 || useradd --system --gid qr-wifi --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin qr-wifi
    install -d -m 0755 "$target" "$target/wifi_provisioning" "$target/wifi_provisioning/static"
    install -m 0644 "$source_root"/wifi_provisioning/*.py "$target/wifi_provisioning/"
    install -m 0644 "$source_root"/wifi_provisioning/static/* "$target/wifi_provisioning/static/"
    install -m 0755 "$source_root/deploy/wifi/install.sh" "$target/install.sh"
    install -m 0644 "$source_root"/deploy/wifi/*.service /etc/systemd/system/
    install -d -m 0700 /etc/qr-wifi
    if [[ ! -f $config ]]; then
        python3 - <<'PY'
import json, os, secrets
path = '/etc/qr-wifi/config.json'
with open(path, 'x', encoding='utf-8') as stream:
    json.dump({'interface': 'wlan0', 'ssid': 'RaspberryPi-Setup', 'password': secrets.token_urlsafe(18)}, stream, indent=2)
os.chmod(path, 0o600)
PY
    fi
    chmod 0600 "$config"
    systemctl daemon-reload
    systemd-analyze verify /etc/systemd/system/qr-wifi.service /etc/systemd/system/qr-wifi-web.service
    echo 'Installed only. No service enabled or started. Configuration: /etc/qr-wifi/config.json (root only).'
    ;;
activate)
    preflight
    [[ -f $target/wifi_provisioning/daemon.py && -f $config ]] || { echo 'Install first.' >&2; exit 1; }
    if systemctl is-active --quiet qr-wifi.service; then
        echo 'Already active. Confirm the existing activation or run rollback.'
        exit 0
    fi
    cancel_timer
    systemctl reset-failed qr-wifi.service qr-wifi-web.service
    systemd-run --collect --unit=qr-wifi-rollback --on-active=5m --timer-property=AccuracySec=1s /bin/bash "$target/install.sh" rollback
    systemctl enable --now qr-wifi.service
    echo 'Activated with a five-minute rollback timer. Check status, then run: sudo bash /opt/qr-wifi/install.sh confirm'
    ;;
confirm)
    systemctl is-active --quiet qr-wifi.service || { echo 'Service is not active.' >&2; exit 1; }
    cancel_timer
    echo 'Activation confirmed; automatic provisioning remains enabled across boots.'
    ;;
force)
    systemctl is-active --quiet qr-wifi.service || { echo 'Activate the service first.' >&2; exit 1; }
    touch /run/qr-wifi/force
    echo 'Setup requested. Wi-Fi SSH will disconnect; use the setup hotspot.'
    ;;
rollback|normal)
    rollback
    ;;
uninstall)
    rollback
    systemctl reset-failed qr-wifi.service qr-wifi-web.service 2>/dev/null || true
    rm -f /etc/systemd/system/qr-wifi.service /etc/systemd/system/qr-wifi-web.service
    systemctl daemon-reload
    nmcli connection delete uuid c21e5d04-bd50-4cd8-bd6c-4ff222db3748 2>/dev/null || true
    echo 'Units and setup profile removed. /opt/qr-wifi and root-only configuration retained for rollback; saved Wi-Fi retained.'
    ;;
*)
    echo 'Usage: install.sh {preflight|install|activate|confirm|force|normal|rollback|uninstall}' >&2
    exit 2
    ;;
esac
