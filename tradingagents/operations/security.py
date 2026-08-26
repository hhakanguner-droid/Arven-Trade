"""Secret-safe logging helpers for production ARVEN Trade processes."""

from __future__ import annotations

import logging
import os
import re
import traceback
from collections.abc import Mapping
from typing import Any

_SECRET_KEY_MARKERS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "PRIVATE_KEY")
_TOKEN_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)((?:api[_-]?key|token|secret|password)\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
)


def _is_secret_key(key: Any) -> bool:
    upper = str(key).upper()
    return any(marker in upper for marker in _SECRET_KEY_MARKERS)


def _secret_values(environ: Mapping[str, str]) -> list[str]:
    values: set[str] = set()
    for key, value in environ.items():
        if not _is_secret_key(key):
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


def _redact_structured_value(
    value: Any,
    *,
    environ: Mapping[str, str] | None = None,
) -> Any:
    if isinstance(value, str):
        return redact_sensitive_text(value, environ=environ)
    if isinstance(value, Mapping):
        return {
            key: (
                "[REDACTED]"
                if _is_secret_key(key)
                else _redact_structured_value(item, environ=environ)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_structured_value(item, environ=environ) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_structured_value(item, environ=environ) for item in value)
    return value


def _redact_record(
    record: logging.LogRecord,
    *,
    environ: Mapping[str, str] | None = None,
) -> None:
    record.msg = redact_sensitive_text(record.getMessage(), environ=environ)
    record.args = ()

    for key, value in list(record.__dict__.items()):
        if key in {"msg", "args", "exc_info", "exc_text", "stack_info"}:
            continue
        if _is_secret_key(key):
            record.__dict__[key] = "[REDACTED]"
        else:
            record.__dict__[key] = _redact_structured_value(value, environ=environ)

    if record.exc_info:
        rendered = "".join(traceback.format_exception(*record.exc_info))
        record.exc_text = redact_sensitive_text(rendered, environ=environ)
    elif record.exc_text:
        record.exc_text = redact_sensitive_text(record.exc_text, environ=environ)
    if record.stack_info:
        record.stack_info = redact_sensitive_text(record.stack_info, environ=environ)


class SecretRedactionFilter(logging.Filter):
    """Logging filter that prevents secrets from reaching configured handlers."""

    def __init__(self, environ: Mapping[str, str] | None = None):
        super().__init__()
        self.environ = environ

    def filter(self, record: logging.LogRecord) -> bool:
        _redact_record(record, environ=self.environ)
        return True


def _ensure_handler_filter(handler: logging.Handler) -> None:
    if any(isinstance(item, SecretRedactionFilter) for item in handler.filters):
        return
    handler.addFilter(SecretRedactionFilter())


def _install_existing_handler_filters() -> None:
    for handler in logging.getLogger().handlers:
        _ensure_handler_filter(handler)
    for item in logging.root.manager.loggerDict.values():
        if isinstance(item, logging.Logger):
            for handler in item.handlers:
                _ensure_handler_filter(handler)


def install_secret_redaction() -> None:
    """Install process-wide redaction before and after structured ``extra`` fields."""
    current_factory = logging.getLogRecordFactory()
    if not getattr(current_factory, "_arven_secret_redaction", False):

        def redacting_factory(*args, **kwargs):
            record = current_factory(*args, **kwargs)
            _redact_record(record)
            return record

        redacting_factory._arven_secret_redaction = True  # type: ignore[attr-defined]
        logging.setLogRecordFactory(redacting_factory)

    _install_existing_handler_filters()

    current_add_handler = logging.Logger.addHandler
    if getattr(current_add_handler, "_arven_secret_redaction", False):
        return

    def redacting_add_handler(self, handler):
        _ensure_handler_filter(handler)
        return current_add_handler(self, handler)

    redacting_add_handler._arven_secret_redaction = True  # type: ignore[attr-defined]
    logging.Logger.addHandler = redacting_add_handler
