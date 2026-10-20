# Wi-Fi Provisioning Implementation Plan

**Goal:** Add independent NetworkManager provisioning without touching motor or QR behavior.

**Architecture:** A root network daemon serializes transitions over a restricted Unix socket. A separate unprivileged HTTP service serves only the setup interface. NetworkManager owns DHCP and persistent profiles; failed trials never edit existing profiles.

**Tech Stack:** Python 3.11+ standard library, NetworkManager, systemd, pytest.

1. Add failing tests in `tests/test_wifi_provisioning.py` for timeout boundaries, recovery, input validation, profile secrecy, scanning and failed/successful trials. Run with `.venv/Scripts/python -m pytest tests/test_wifi_provisioning.py`.
2. Implement `wifi_provisioning/network.py` and `controller.py`; rerun tests.
3. Add restricted socket daemon, unprivileged HTTP server, and mobile UI in `wifi_provisioning/`; test HTTP validation and serialized requests.
4. Add repeatable `deploy/wifi/install.sh`, service units, explicit activation with timed rollback, and manual recovery commands. Installation must never activate networking.
5. Document exact deployment and recovery commands in `docs/WIFI_PROVISIONING.md` and `docs/WIFI_DEPLOYMENT.md`.
6. Review code, tests, docs, shell syntax and all diffs. Run full pytest suite, compile checks, then commit and push the existing branch without force.
