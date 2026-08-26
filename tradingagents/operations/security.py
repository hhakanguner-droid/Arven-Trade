"""Secret-safe logging helpers for production ARVEN Trade processes."""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping
from typing import Any

_SECRET_KEY_MARKERS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "PRIVATE_KEY")
_TOKEN_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)((?:api[_-]?key|token|secret|password)\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
)


def _secret_values(environ: Mapping[str, str]) -> list[str]:
    values: set[str] = set()
    for key, value in environ.items():
        upper = str(key).upper()
        if not any(marker in upper for marker in _SECRET_KEY_MARKERS):
            continue
        text = str(value)
        if len(text) >= 6:
            values.add(text)
    return sorted(values, key=len, reverse=True)


def redact_sensitive_text(
    value: Any,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Redact configured secrets and common credential shapes from arbitrary text."""
    text = str(value)
    source = os.environ if environ is None else environ
    for secret in _secret_values(source):
        text = text.replace(secret, "[REDACTED]")
    text = _TOKEN_PATTERNS[0].sub(r"\1[REDACTED]", text)
    text = _TOKEN_PATTERNS[1].sub(r"\1[REDACTED]", text)
    text = _TOKEN_PATTERNS[2].sub("[REDACTED]", text)
    return text


class SecretRedactionFilter(logging.Filter):
    """Logging filter that prevents secrets from reaching configured handlers."""

    def __init__(self, environ: Mapping[str, str] | None = None):
        super().__init__()
        self.environ = environ

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        record.msg = redact_sensitive_text(message, environ=self.environ)
        record.args = ()
        return True
