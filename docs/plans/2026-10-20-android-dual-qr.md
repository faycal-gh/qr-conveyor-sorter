# Android dual-motor QR implementation plan

**Goal:** Launch the existing coordinated two-motor QR scanner with one command, using a saved Android IP Webcam URL and explicit persistent hardware consent.

**Architecture:** Extend `src/camera.py` with a bounded FFmpeg stream capture that retains only its newest frame and stops on failure. Keep the existing parser, QR removal gate, coordinated pulse loop, pin assignments and polarity. Add an ignored local configuration and a launcher which validates saved hardware acknowledgment before invoking the existing scanner.

**Tech stack:** Existing Python/OpenCV/gpiozero/lgpio, Python standard library, Bash.

1. Add failing URL, camera failure/freshness, and restart/removal tests in `tests/test_ip_camera.py`; implement the IP camera and startup QR gate. Run targeted pytest.
2. Add a failing overlapping-command test; add a nonblocking lock around the existing controller execution without altering pulse generation.
3. Add failing local settings, confirmation invalidation, first-run and CLI tests in `tests/test_qr_launcher.py`; implement `src/qr_launcher.py`. Persist configuration atomically in ignored `config.local.json`, with checked motor settings bound to the acknowledgment.
4. Create executable `setup_pi.sh` and `run_qr.sh`; verify shell behavior with stub interpreters, LF files and executable Git modes. Setup installs only missing apt packages and keeps Wi-Fi/SSH settings untouched.
5. Update README, Pi setup and ULN2803 wiring docs. Review all changed code and docs; run the complete test suite, static checks and shell checks. Confirm no provisioning changes or private device settings, then commit and push `main` without force.
