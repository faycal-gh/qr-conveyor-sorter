# Raspberry Pi SSH deployment

Run these **on the Pi**, from your existing checkout after reviewing the changes.
Keep an Ethernet or local-console recovery path for the first radio tests. Replace
the checkout path if needed. Installation never enables or starts provisioning.

```bash
cd ~/qr-conveyor-sorter
git pull --ff-only
sudo bash deploy/wifi/install.sh preflight
sudo bash deploy/wifi/install.sh install
sudoedit /etc/qr-wifi/config.json
sudo bash /opt/qr-wifi/install.sh preflight
```

The configuration already contains a random setup password. Read it privately
with `sudo cat /etc/qr-wifi/config.json`; do not paste it into logs or Git.
Set the correct `interface`, setup `ssid` and `password` before activation.
Preflight is read-only; it does not scan or change the current Wi-Fi connection.
If preflight fails, resolve its message before proceeding.

## Explicit activation

```bash
sudo bash /opt/qr-wifi/install.sh activate
sudo systemctl status qr-wifi.service --no-pager
sudo journalctl -u qr-wifi.service -n 50 --no-pager
sudo systemctl status qr-wifi-rollback.timer --no-pager
```

A five-minute timer will disable provisioning and request saved Wi-Fi unless
you confirm. While your current Wi-Fi works, activation leaves it connected;
the fallback timer starts only when a client IPv4 connection is unavailable.
Verify SSH still works and the journal says `online`. Then cancel rollback:

```bash
sudo bash /opt/qr-wifi/install.sh confirm
```

Do not reboot before confirming: the safety timer is transient and does not
survive a reboot. No installation command automatically reboots the Pi.

## Provision and find SSH

If no client network is available for 60 seconds, join your configured setup SSID
on Android and choose “stay connected” despite the no-internet warning. Open:

```text
http://192.168.4.1:8080
```

Rescan briefly removes the hotspot. Rejoin it and refresh after about a minute,
or enter an SSID manually. Before Connect, save the displayed SSH hostname.
After the handoff, join the destination Wi-Fi and run:

```bash
ssh YOUR_USER@raspberrypi.local
# Substitute your configured hostname and user. If mDNS fails, use the IP
# in the router's DHCP client list:
ssh YOUR_USER@PI_ASSIGNED_IP
```

If connection fails, rejoin the restored setup AP and retry. An IP cannot always
be delivered to the phone before the single adapter switches modes.

## Status, logs, manual setup

```bash
sudo systemctl status qr-wifi.service qr-wifi-web.service --no-pager
sudo journalctl -u qr-wifi.service -u qr-wifi-web.service -b --no-pager
nmcli device status
nmcli -g IP4.ADDRESS device show wlan0
hostname -I
```

The web service is normally inactive when the Pi is on client Wi-Fi. To force
setup, deliberately disconnecting Wi-Fi SSH (save the setup password first):

```bash
sudo bash /opt/qr-wifi/install.sh force
```

## Rollback / restore normal Wi-Fi

From SSH if reachable, otherwise Ethernet or local console:

```bash
sudo bash /opt/qr-wifi/install.sh rollback
nmcli -f NAME,UUID,TYPE connection show
# If needed, activate a specific previously saved client profile:
sudo nmcli connection up uuid YOUR_SAVED_WIFI_UUID ifname wlan0
```

Rollback disables both automatic provisioning at boot and the active setup AP,
keeps all saved client profiles, and requests client autoconnection. `normal`
is an alias for `rollback`. It cannot restore an unavailable network. For a
service that exhausted its restart limit, fix the underlying problem, then:

```bash
sudo systemctl reset-failed qr-wifi.service qr-wifi-web.service
sudo bash /opt/qr-wifi/install.sh activate
# Verify online, then:
sudo bash /opt/qr-wifi/install.sh confirm
```

To upgrade, first rollback while connected over normal Wi-Fi, pull the new
revision, then repeat install, preflight, activate and confirm. Installation
refuses to replace code while the daemon is active.

## Uninstall

```bash
sudo bash /opt/qr-wifi/install.sh uninstall
```

This removes the systemd units and owned setup profile. Application files,
root-only setup configuration, installed OS dependencies, the locked system
user, and saved client Wi-Fi profiles are retained. To reactivate later, install
again from the checkout and follow the explicit activation procedure above.
Architecture, security, supported networks, and hardware acceptance tests are
in [WIFI_PROVISIONING.md](WIFI_PROVISIONING.md).
