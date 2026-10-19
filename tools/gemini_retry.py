"""Bounded retry-delay handling for Gemini API rate limits."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Mapping

MAX_ATTEMPTS = 6
MAX_RETRY_DELAY_SECONDS = 300


def _seconds(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) if value >= 0 else None
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*s?\s*", value, flags=re.IGNORECASE)
    return float(match.group(1)) if match else None


def _body_retry_delay(body: bytes | str) -> float | None:
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
        return None

    def find(value: Any) -> float | None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key.casefold() in {"retrydelay", "retry_after", "retryafter"}:
                    delay = _seconds(item)
                    if delay is not None:
                        return delay
            for item in value.values():
                delay = find(item)
                if delay is not None:
                    return delay
        elif isinstance(value, list):
            for item in value:
                delay = find(item)
                if delay is not None:
                    return delay
        return None

    return find(payload)


def retry_delay_seconds(headers: Mapping[str, str], body: bytes | str, attempt: int,
                        *, now: datetime | None = None) -> float:
    """Read Retry-After/Gemini retryDelay, otherwise use bounded exponential backoff."""
    header = next((value for key, value in headers.items()
                   if key.casefold() == "retry-after"), None)
    delay = _seconds(header)
    if delay is None and isinstance(header, str):
        try:
            retry_at = parsedate_to_datetime(header)
            current_time = now or datetime.now(timezone.utc)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            delay = (retry_at - current_time).total_seconds()
        except (TypeError, ValueError, OverflowError):
            delay = None
    if delay is None:
        delay = _body_retry_delay(body)
    if delay is None:
        delay = 2 ** max(0, attempt)
    return min(MAX_RETRY_DELAY_SECONDS, max(1.0, delay))
