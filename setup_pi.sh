#!/bin/bash
set -euo pipefail
export LC_ALL=C
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if [[ $EUID -eq 0 ]]; then
    echo '[ERROR] Run ./setup_pi.sh as your normal Pi user; sudo is requested only for missing packages.' >&2
    exit 1
fi
packages=(python3-venv python3-opencv python3-gpiozero python3-lgpio util-linux)
missing=()
for package in "${packages[@]}"; do
    if [[ $(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true) != 'install ok installed' ]]; then
        missing+=("$package")
    fi
done
if (( ${#missing[@]} )); then
    sudo apt-get update
    sudo apt-get install -y --no-install-recommends "${missing[@]}"
else
    echo '[SETUP] OS dependencies already installed; skipping apt.'
fi
if [[ ! -x .venv/bin/python ]] || ! grep -q '^include-system-site-packages = true$' .venv/pyvenv.cfg; then
    python3 -m venv --system-site-packages .venv
fi
.venv/bin/python - <<'PY'
import cv2, gpiozero, lgpio
if not cv2.videoio_registry.hasBackend(cv2.CAP_FFMPEG):
    raise SystemExit('[ERROR] OpenCV needs its FFmpeg backend for bounded IP Webcam capture.')
print('[SETUP] OpenCV/FFmpeg and GPIO libraries available. No GPIO or camera opened.')
PY
if [[ ! -f config.local.json ]]; then
    ./run_qr.sh --configure
else
    echo '[SETUP] Existing local settings retained. View: ./run_qr.sh --show-config'
fi
echo '[SETUP] Ready. Run ./run_qr.sh (simulation until you explicitly enable hardware).'
