from pathlib import Path
import json
import qrcode

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "test_qr_codes"
OUTPUT.mkdir(exist_ok=True)

payloads = {
    "left.png": "direction:left",
    "right.png": "direction:right",
    "forward.png": "direction:forward",
    "order_left.png": json.dumps({"order_id": "ORD001", "direction": "left"}),
}

for filename, payload in payloads.items():
    img = qrcode.make(payload)
    path = OUTPUT / filename
    img.save(path)
    print(f"Created {path} -> {payload}")
