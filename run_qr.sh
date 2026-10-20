#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if [[ ! -x .venv/bin/python ]]; then
    echo '[ERROR] Run ./setup_pi.sh once before starting the scanner.' >&2
    exit 1
fi
if ! command -v flock >/dev/null; then
    echo '[ERROR] flock is required (Raspberry Pi OS: sudo apt install util-linux).' >&2
    exit 1
fi
exec 9>.qr-scanner.lock
flock -n 9 || { echo '[ERROR] Another QR launcher is running. Stop it before continuing.' >&2; exit 75; }
exec .venv/bin/python -u -m src.qr_launcher "$@"
