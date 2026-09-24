from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    if path is None:
        path = Path(__file__).resolve().parents[1] / "config.json"
    else:
        path = Path(path)

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)
