"""Convert agent outputs to strict, MySQL-compatible JSON values."""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def _sanitize(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value

    value_type = type(value)
    module = value_type.__module__.split(".", 1)[0]
    type_name = value_type.__name__

    # pandas uses these scalar sentinels for missing values.
    if module == "pandas" and type_name in {"NAType", "NaTType"}:
        return None

    # Handle pandas Timestamp before the general datetime case.
    if module == "pandas" and type_name == "Timestamp":
        return value.isoformat()

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    # NumPy scalars expose item(), which returns their native Python value.
    if module == "numpy" and hasattr(value, "item"):
        return _sanitize(value.item())

    if isinstance(value, float):
        return value if math.isfinite(value) else None

    if isinstance(value, Decimal):
        return float(value) if value.is_finite() else None

    if isinstance(value, dict):
        return {str(_sanitize(key)): _sanitize(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]

    raise TypeError(f"Unsupported value for JSON output: {value_type.__name__}")


def sanitize_json(value: Any) -> Any:
    """Return native JSON data, rejecting anything the database cannot store."""
    sanitized = _sanitize(value)
    # Strict serialization also validates nested output and rejects NaN/Infinity.
    serialized = json.dumps(sanitized, allow_nan=False, ensure_ascii=False)
    return json.loads(serialized)
