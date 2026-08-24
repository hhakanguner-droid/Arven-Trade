"""Application models for ARVEN Trade watchlist notifications."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Literal

AlertSeverity = Literal["low", "medium", "high", "critical"]
AlertCategory = Literal[
    "financials",
    "dividend",
    "capital",
    "mna",
    "commercial",
    "legal",
    "operations",
    "financing",
    "governance",
    "ownership",
    "other",
]


@dataclass(frozen=True)
class WatchlistAlert:
    alert_id: str
    source: str
    ticker: str
    published_at: datetime
    title: str
    summary: str
    url: str
    category: AlertCategory
    severity: AlertSeverity
    score: int
    disclosure_id: int
    is_corrective: bool = False
    has_attachment: bool = False

    def to_dict(self) -> dict:
        data = asdict(self)
        data["published_at"] = self.published_at.isoformat(timespec="minutes")
        return data


@dataclass(frozen=True)
class AlertSourceStatus:
    ticker: str
    source: str
    status: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class WatchlistAlertBatch:
    checked_at: datetime
    alerts: tuple[WatchlistAlert, ...] = field(default_factory=tuple)
    source_statuses: tuple[AlertSourceStatus, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "checked_at": self.checked_at.isoformat(timespec="seconds"),
            "alert_count": len(self.alerts),
            "alerts": [alert.to_dict() for alert in self.alerts],
            "source_statuses": [status.to_dict() for status in self.source_statuses],
        }
