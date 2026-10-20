# Wi-Fi provisioning

This service runs independently of the conveyor application. It imports no motor,
camera, QR, or GPIO modules and never starts the conveyor after reconnecting.
For exact installation commands, see [deployment](WIFI_DEPLOYMENT.md).

## Requirements

Target: Raspberry Pi 5, Raspberry Pi OS Bookworm or newer, Python 3.11+, systemd,
and an already active NetworkManager managing the built-in Wi-Fi adapter. Set
your WLAN country using `sudo raspi-config` before deployment. The installer
requires the adapter to advertise AP support and Wi-Fi to be enabled. It installs
`dnsmasq-base` (used by NetworkManager shared mode), Python, and Avahi for mDNS.
It does not replace your network manager, disable SSH, or reboot.

NetworkManager manages DHCP, WPA2, and client reconnection. No standalone
hostapd or dnsmasq service is configured. An existing firewall must permit DHCP,
DNS, and TCP 8080 on the setup interface. The installer does not rewrite firewall
rules. Actual radio/driver compatibility must be verified on your Pi.

## Architecture and workflow

`qr-wifi.service` runs the network daemon as root. `qr-wifi-web.service` runs as
the locked system user `qr-wifi` and binds **only** `192.168.4.1:8080`. They
communicate over `/run/qr-wifi/control.sock` (root:qr-wifi, mode 0660).
The web user cannot read `/etc/qr-wifi/config.json` or NetworkManager keyfiles.
Systemd hardening removes capabilities, protects home directories, and limits
writable locations. The root daemon accepts only status, scan, and connect;
all transitions are serialized. An OS file lock prevents duplicate daemons.

States: `waiting` → `online`, or after 60 seconds without a usable client IPv4
address, `setup`. Normal operation continues monitoring; a loss lasting 60
seconds returns to setup. Short outages reset the timer when connectivity
returns. Internet reachability is **not** required: usable means an assigned
IPv4 address excluding loopback, link-local, and the owned setup address.
NetworkManager performs saved-profile autoconnection; profiles with autoconnect
explicitly disabled by an administrator remain disabled.
When starting without a client connection, the daemon re-enables device-level
autoconnection so a previous manual disconnect does not block saved profiles.

The setup SSID defaults to `RaspberryPi-Setup`, protected by a random WPA2
password generated during installation. Open `http://192.168.4.1:8080` manually.
This is a local portal, not an OS captive-portal redirect; Android may say
“No internet.” Choose to stay connected and temporarily disable automatic
switching to mobile data if the page does not load.

### One adapter and the handoff

The portal initially offers manual SSID entry and a Rescan button. A rescan is
acknowledged immediately, then waits eight seconds before taking down the AP,
scanning in client mode, and restoring the AP. Rejoin setup Wi-Fi and refresh to
see the cached list (SSID, signal percentage, security). No simultaneous AP/client
or AP scanning support is assumed. Scanning can take roughly a minute, longer
on failure. Hidden SSIDs can be entered manually.

Connect follows the same eight-second warning. A **new**, root-only trial
NetworkManager profile is loaded with autoconnect disabled. Existing profiles
are never edited or deleted. The daemon activates the trial and verifies its
active UUID and assigned IPv4 address before enabling autoconnect. Successful
profiles remain on disk for reboot reconnection. Failed trial profiles are
deleted and the setup AP returns. Rejoin it to read the error and retry.
Personal WPA/WPA2, WPA3, and open networks are supported. Enterprise, WEP,
enhanced-open, passwords outside 8–63 printable ASCII characters, and SSIDs
containing control characters are unsupported.

The browser displays a hostname SSH command **before** switching. With one
adapter it cannot reliably receive the final assigned IP. After success,
reconnect your phone/computer to the destination Wi-Fi, then use
`ssh YOUR_USER@raspberrypi.local` (substitute your Pi hostname and login).
Avahi discovery also requires mDNS support and a network that allows multicast
and peer-to-peer traffic. Alternatively, find the Pi in your router’s DHCP client
list. After SSH login, run `hostname -I` or
`nmcli -g IP4.ADDRESS device show wlan0`. The actual assigned address is also
recorded in the service journal and available in daemon status while reachable.
The HTTP portal is stopped after success and is not exposed on your normal LAN.

### Restart and shutdown

On restart, an active owned hotspot is recovered. Inactive unfinished trials are
removed; a verified active unfinished trial is promoted for autoconnection.
Successful saved profiles are retained. A scan cache is in memory and must be
refreshed after a daemon restart. A crash after AP shutdown may require another
60-second wait before setup returns. The daemon stops its portal and owned AP
on shutdown, without taking down an unrelated active client connection.
Systemd retries failed daemons after 30 seconds, at most three starts per five
minutes, to avoid an unbounded restart loop. After resolving an error, use
`sudo systemctl reset-failed qr-wifi.service qr-wifi-web.service` and start again.

## Configuration

`/etc/qr-wifi/config.json` is root-owned, mode 0600, in a mode-0700 directory.
Use `sudoedit /etc/qr-wifi/config.json` before activation. Keys:

| Key | Default | Meaning |
| --- | --- | --- |
| `interface` | `wlan0` | Existing NetworkManager Wi-Fi interface |
| `ssid` | `RaspberryPi-Setup` | Setup SSID, 1–32 UTF-8 bytes |
| `password` | Random per installation | Setup WPA2 password, 8–63 printable ASCII characters |

The setup subnet is fixed at `192.168.4.0/24`, with the Pi at `192.168.4.1`.
Preflight rejects an existing route on this subnet, except the owned setup AP.
Timeout (60 seconds), handoff delay (8 seconds), and port (8080) are fixed.
The installer retains configuration on repeat runs. Do not edit it while the
service is active; apply changes after rollback, then preflight and activate.

## Windows development

From the repository root:

```powershell
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m compileall -q wifi_provisioning
node --check wifi_provisioning/static/app.js
& 'C:/Program Files/Git/bin/bash.exe' -n deploy/wifi/install.sh
```

Tests mock the NetworkManager boundary and use temporary profile directories;
they do not change host networking. Production Python uses only the standard
library, so no new pip requirements are needed. Shell scripts are checked out
with LF line endings. Windows tests do not verify DHCP, association, WPA2,
Avahi, Linux permissions, or systemd behavior.

## Security

Protect and share the setup password only with trusted operators. Anyone on
setup Wi-Fi can configure this Pi; WPA2 is the access control. HTTP is local and
unencrypted above the WPA2 link. Use trusted devices and do not reuse the setup
password as a production Wi-Fi password. Setup is not a public administration
interface and has no cloud dependencies.

Requests require an exact IP Host header, same Origin, and an unpredictable
anti-CSRF header token. SSIDs are rendered as text, never HTML. Request sizes
and socket waits are bounded. Credentials are sent in JSON POST bodies, never
URLs, returned responses, or application logs. Root operations use subprocess
argument lists with no shell. Passwords go into mode-0600 keyfiles rather than
process command arguments. Avoid enabling NetworkManager debug logging, packet
captures, browser request recording, or shell tracing while provisioning.
Saved credentials are readable by root as with ordinary NetworkManager profiles.

## Troubleshooting and hardware acceptance

See [deployment commands](WIFI_DEPLOYMENT.md) for status, logs, force setup,
normal mode, and uninstall. Use local console or Ethernet if Wi-Fi SSH is lost.
The automatic deployment rollback disables provisioning and requests saved
Wi-Fi; it cannot restore a network that is out of range or has changed password.

Before relying on unattended recovery, test on the actual Pi:

1. Activate while on working Wi-Fi; verify SSH stays connected and no AP appears.
2. Confirm activation. Reboot manually and verify the saved network reconnects.
3. Turn off the router for less than 60 seconds, restore it, and verify no AP.
4. Leave it unavailable beyond 60 seconds; join the protected setup AP on Android.
5. Rescan, rejoin setup, select a network, and submit a wrong password. Verify
   automatic AP restoration and a useful error, then try the correct password.
6. Verify a DHCP address and SSH via mDNS or the router’s client list. Reboot
   manually to verify credentials persist.
7. Repeat with a hidden SSID; test daemon restart in setup and during a trial,
   DHCP failure, radio disabled, and rollback from local console/Ethernet.

No hardware acceptance is claimed by automated Windows tests.
