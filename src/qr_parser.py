from __future__ import annotations

import json
from dataclasses import dataclass

VALID_DIRECTIONS = {"left", "right", "forward"}


@dataclass(frozen=True)
class SortCommand:
    direction: str
    raw_payload: str
    order_id: str | None = None


def parse_qr_payload(payload: str) -> SortCommand | None:
    """Parse supported plain-text or JSON QR payloads.

    Examples:
      direction:left
      direction:right
      direction:forward
      {"order_id":"ORD001","direction":"left"}
    """
    raw = payload.strip()
    if not raw:
        return None

    # JSON format
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None

        if not isinstance(data, dict):
            return None

        direction = str(data.get("direction", "")).strip().lower()
        if direction not in VALID_DIRECTIONS:
            return None

        order_id = data.get("order_id")
        if order_id is not None:
            order_id = str(order_id)

        return SortCommand(
            direction=direction,
            raw_payload=raw,
            order_id=order_id,
        )

    # Simple format: direction:left
    key, separator, direction = raw.lower().partition(":")
    if separator and key.strip() == "direction":
        direction = direction.strip()
        if direction in VALID_DIRECTIONS:
            return SortCommand(direction=direction, raw_payload=raw)

    return None
