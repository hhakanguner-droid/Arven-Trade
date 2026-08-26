"""FastAPI application factory for ARVEN Trade."""

from __future__ import annotations

import hmac
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tradingagents.history.store import AnalysisHistoryStore
from tradingagents.operations import create_production_runtime
from tradingagents.operations.security import redact_sensitive_text

from .core import AnalysisService, HistoryUnavailable
from .jobs import AnalysisJobStore, IdempotencyConflict, QueueCapacityExceeded

logger = logging.getLogger(__name__)

_BIST_TICKER = re.compile(r"^[A-Z0-9]{1,12}(?:\.IS)?$")
_BEARER = HTTPBearer(auto_error=False)
_MIN_API_TOKEN_LENGTH = 32


def _normalize_bist_ticker(value: str) -> str:
    ticker = value.strip().upper()
    if "." not in ticker:
        ticker = f"{ticker}.IS"
    if not _BIST_TICKER.fullmatch(ticker):
        raise ValueError("ticker must be a BIST symbol such as THYAO or THYAO.IS")
    return ticker


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)

    ticker: str = Field(min_length=1, max_length=20)
    trade_date: date
    estimated_cost_usd: float | None = Field(default=None, ge=0)

    @field_validator("ticker")
    @classmethod
    def normalize_bist_ticker(cls, value: str) -> str:
        return _normalize_bist_ticker(value)

    @model_validator(mode="after")
    def reject_future_trade_date(self) -> AnalysisRequest:
        today = datetime.now(ZoneInfo("Europe/Istanbul")).date()
        if self.trade_date > today:
            raise ValueError("trade_date cannot be in the future")
        return self


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_positive_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive integer")
    return value


def _resolve_auth(api_token: str | None, auth_disabled: bool | None) -> tuple[str | None, bool]:
    disabled = (
        _env_bool("TRADINGAGENTS_API_AUTH_DISABLED", False)
        if auth_disabled is None
        else bool(auth_disabled)
    )
    token = api_token if api_token is not None else os.getenv("TRADINGAGENTS_API_TOKEN")
    token = token.strip() if token else None
    if not disabled and not token:
        raise RuntimeError(
            "ARVEN API authentication is enabled but TRADINGAGENTS_API_TOKEN is not configured"
        )
    if not disabled and token and len(token) < _MIN_API_TOKEN_LENGTH:
        raise RuntimeError(
            f"TRADINGAGENTS_API_TOKEN must be at least {_MIN_API_TOKEN_LENGTH} characters"
        )
    return token, disabled


def _default_service() -> AnalysisService:
    runtime = create_production_runtime()
    default_db = Path(runtime.state_dir) / "web_jobs.db"
    db_path = Path(os.getenv("TRADINGAGENTS_API_JOB_DB", str(default_db))).expanduser()
    max_pending = _env_positive_int("TRADINGAGENTS_API_MAX_PENDING_JOBS", 100)
    max_terminal = _env_positive_int("TRADINGAGENTS_API_MAX_TERMINAL_JOBS", 5000)

    history_store = None
    config = getattr(getattr(runtime, "graph", None), "config", {}) or {}
    history_path = config.get("analysis_history_path")
    if config.get("analysis_history_enabled", True) and history_path:
        try:
            history_store = AnalysisHistoryStore(history_path)
        except Exception as exc:  # history remains fail-open for analysis execution
            logger.warning(
                "ARVEN API history unavailable error_type=%s message=%s",
                type(exc).__name__,
                redact_sensitive_text(exc),
            )

    return AnalysisService(
        runtime,
        AnalysisJobStore(db_path),
        history_store=history_store,
        max_pending_jobs=max_pending,
        max_terminal_jobs=max_terminal,
    )


def create_app(
    service: AnalysisService | None = None,
    *,
    api_token: str | None = None,
    auth_disabled: bool | None = None,
) -> FastAPI:
    """Build the authenticated Phase 13 API; production auth fails closed by default."""
    token, disabled = _resolve_auth(api_token, auth_disabled)
    owns_service = service is None
    analysis_service = service or _default_service()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        if owns_service:
            analysis_service.close()

    app = FastAPI(
        title="ARVEN Trade API",
        version="1.0",
        docs_url=None if not disabled else "/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    origins = [
        item.strip()
        for item in os.getenv("TRADINGAGENTS_API_CORS_ORIGINS", "").split(",")
        if item.strip()
    ]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        )

    def require_auth(
        credentials: HTTPAuthorizationCredentials | None = Depends(_BEARER),
    ) -> None:
        if disabled:
            return
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
        if not hmac.compare_digest(credentials.credentials, token or ""):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    def query_ticker(value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return _normalize_bist_ticker(value)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    def history_unavailable(exc: HistoryUnavailable) -> HTTPException:
        return HTTPException(status_code=503, detail=str(exc))

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/health", dependencies=[Depends(require_auth)])
    def api_health() -> dict[str, Any]:
        return analysis_service.health()

    @app.post(
        "/api/v1/analyses",
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_auth)],
    )
    def submit_analysis(
        request: AnalysisRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        key = idempotency_key.strip() if idempotency_key else None
        if key and len(key) > 200:
            raise HTTPException(status_code=400, detail="Idempotency-Key is too long")
        try:
            return analysis_service.submit(
                request.ticker,
                request.trade_date.isoformat(),
                estimated_cost_usd=request.estimated_cost_usd,
                idempotency_key=key,
            )
        except IdempotencyConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except QueueCapacityExceeded as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc

    @app.get(
        "/api/v1/analyses/{job_id}",
        dependencies=[Depends(require_auth)],
    )
    def analysis_status(job_id: str) -> dict[str, Any]:
        job = analysis_service.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Analysis job not found")
        return job

    @app.get("/api/v1/history", dependencies=[Depends(require_auth)])
    def list_history(
        ticker: str | None = Query(default=None, min_length=1, max_length=20),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> list[dict[str, Any]]:
        try:
            return analysis_service.list_history(query_ticker(ticker), limit=limit)
        except HistoryUnavailable as exc:
            raise history_unavailable(exc) from exc

    @app.get("/api/v1/history/{analysis_id}", dependencies=[Depends(require_auth)])
    def history_detail(analysis_id: int) -> dict[str, Any]:
        try:
            record = analysis_service.get_history(analysis_id)
        except HistoryUnavailable as exc:
            raise history_unavailable(exc) from exc
        if record is None:
            raise HTTPException(status_code=404, detail="Analysis history record not found")
        return record

    @app.get("/api/v1/compare/{ticker}", dependencies=[Depends(require_auth)])
    def compare_history(
        ticker: str,
        count: int = Query(default=2, ge=1, le=20),
    ) -> list[dict[str, Any]]:
        normalized = query_ticker(ticker)
        try:
            return analysis_service.compare_history(normalized or ticker, count=count)
        except HistoryUnavailable as exc:
            raise history_unavailable(exc) from exc

    @app.get("/api/v1/performance", dependencies=[Depends(require_auth)])
    def performance_summary(
        ticker: str | None = Query(default=None, min_length=1, max_length=20),
    ) -> dict[str, Any]:
        try:
            return analysis_service.performance_summary(query_ticker(ticker))
        except HistoryUnavailable as exc:
            raise history_unavailable(exc) from exc

    return app
