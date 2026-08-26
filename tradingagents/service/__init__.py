"""ARVEN Trade web-service primitives.

FastAPI is kept behind the optional ``web`` extra; importing this package does
not require the web stack.
"""

from .core import AnalysisService, HistoryUnavailable
from .jobs import AnalysisJobStore, IdempotencyConflict, QueueCapacityExceeded

__all__ = [
    "AnalysisJobStore",
    "AnalysisService",
    "HistoryUnavailable",
    "IdempotencyConflict",
    "QueueCapacityExceeded",
]
