from __future__ import annotations

from datetime import datetime
from typing import Optional

import dateparser
import pytz


def normalize_date(phrase: str, tz_name: Optional[str] = "UTC") -> str | None:
    tz = pytz.timezone(tz_name or "UTC")
    dt = dateparser.parse(
        phrase,
        settings={"TIMEZONE": str(tz), "RETURN_AS_TIMEZONE_AWARE": True},
    )
    if not dt:
        return None
    return dt.astimezone(pytz.UTC).isoformat()
