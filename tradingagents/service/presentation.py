"""Deterministic compact history payloads for ARVEN PC/PWA clients."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_MARKDOWN = re.compile(r"[`*_>#]+")
_LINK = re.compile(r"\[(.*?)\]\([^)]*\)")
_WHITESPACE = re.compile(r"\s+")

_AGENT_FIELDS = (
    ("market", "market_report"),
    ("sentiment", "sentiment_report"),
    ("news", "news_report"),
    ("kap", "kap_report"),
    ("fundamentals", "fundamentals_report"),
    ("trader", "trader_investment_plan"),
)


def compact_text(value: Any, *, max_chars: int = 240) -> str:
    text = "" if value is None else str(value)
    text = _LINK.sub(r"\1", text)
    text = _MARKDOWN.sub("", text)
    text = _WHITESPACE.sub(" ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max(1, max_chars - 1)].rstrip(" ,;:-") + "…"


def _nested_summary(state: Mapping[str, Any], container: str, key: str) -> str:
    value = state.get(container)
    if not isinstance(value, Mapping):
        return ""
    return compact_text(value.get(key), max_chars=180)


def history_card(record: Mapping[str, Any]) -> dict[str, Any]:
    state = record.get("state")
    state = state if isinstance(state, Mapping) else {}
    agents: dict[str, str] = {}
    for label, field in _AGENT_FIELDS:
        summary = compact_text(state.get(field), max_chars=180)
        if summary:
            agents[label] = summary

    bull = _nested_summary(state, "investment_debate_state", "bull_history")
    bear = _nested_summary(state, "investment_debate_state", "bear_history")
    risk = _nested_summary(state, "risk_debate_state", "judge_decision")
    if bull:
        agents["bull"] = bull
    if bear:
        agents["bear"] = bear
    if risk:
        agents["risk"] = risk

    return {
        "id": record.get("id"),
        "ticker": record.get("ticker"),
        "trade_date": record.get("trade_date"),
        "created_at": record.get("created_at"),
        "rating": record.get("rating"),
        "signal": record.get("signal"),
        "entry_price": record.get("entry_price"),
        "benchmark_ticker": record.get("benchmark_ticker"),
        "decision_summary": compact_text(record.get("final_decision"), max_chars=320),
        "agents": agents,
        "performance": record.get("performance") or [],
    }


def history_detail(record: Mapping[str, Any]) -> dict[str, Any]:
    payload = history_card(record)
    payload["final_decision"] = record.get("final_decision")
    payload["state"] = record.get("state") or {}
    payload["benchmark_entry_price"] = record.get("benchmark_entry_price")
    return payload
