"""Compact, deterministic ARVEN Trade view models.

The TradingAgents graph produces long-form reports.  Web/PWA surfaces should not
render those reports verbatim: this module projects a completed graph state into
short, JSON-safe decision cards while preserving the original detailed text for
explicit drill-down.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from tradingagents.agents.utils.rating import parse_rating

_RATING_PRESENTATION = {
    "Buy": ("positive", "POZİTİF", "AL"),
    "Overweight": ("positive", "POZİTİF", "POZİSYONU ARTIR"),
    "Hold": ("neutral", "NÖTR", "İZLE"),
    "Underweight": ("cautious", "TEMKİNLİ", "POZİSYONU AZALT"),
    "Sell": ("negative", "NEGATİF", "SAT"),
}

_AGENT_FIELDS = (
    ("market", "Market Analyst", "market_report"),
    ("sentiment", "Sentiment Analyst", "sentiment_report"),
    ("news", "News Analyst", "news_report"),
    ("kap", "KAP Analyst", "kap_report"),
    ("fundamentals", "Fundamentals Analyst", "fundamentals_report"),
)

_MARKDOWN_TOKEN_RE = re.compile(r"[`*_>#]+")
_WHITESPACE_RE = re.compile(r"\s+")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _plain_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = _MARKDOWN_TOKEN_RE.sub("", text)
    text = re.sub(r"\[(.*?)\]\([^)]*\)", r"\1", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _shorten(value: Any, *, max_chars: int = 220, sentences: int = 1) -> str:
    text = _plain_text(value)
    if not text:
        return ""
    parts = [part.strip() for part in _SENTENCE_RE.split(text) if part.strip()]
    shortened = " ".join(parts[: max(1, int(sentences))]) if parts else text
    if len(shortened) <= max_chars:
        return shortened
    return shortened[: max(1, max_chars - 1)].rstrip(" ,;:-") + "…"


def _nested_text(state: Mapping[str, Any], container: str, key: str) -> str:
    value = state.get(container)
    if not isinstance(value, Mapping):
        return ""
    return _plain_text(value.get(key))


def _risk_level(state: Mapping[str, Any]) -> str:
    text = " ".join(
        filter(
            None,
            (
                _nested_text(state, "risk_debate_state", "judge_decision"),
                _plain_text(state.get("final_trade_decision")),
            ),
        )
    ).casefold()
    high_terms = ("high risk", "yüksek risk", "risk: high", "risk: yüksek")
    low_terms = ("low risk", "düşük risk", "risk: low", "risk: düşük")
    if any(term in text for term in high_terms):
        return "high"
    if any(term in text for term in low_terms):
        return "low"
    return "medium"


def _agent_cards(state: Mapping[str, Any]) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    for key, label, field in _AGENT_FIELDS:
        summary = _shorten(state.get(field), max_chars=180)
        if summary:
            cards.append({"key": key, "label": label, "summary": summary})

    nested = (
        ("bull", "Bull Researcher", "investment_debate_state", "bull_history"),
        ("bear", "Bear Researcher", "investment_debate_state", "bear_history"),
        ("risk", "Risk Manager", "risk_debate_state", "judge_decision"),
    )
    for key, label, container, field in nested:
        summary = _shorten(_nested_text(state, container, field), max_chars=180)
        if summary:
            cards.append({"key": key, "label": label, "summary": summary})

    trader = _shorten(state.get("trader_investment_plan"), max_chars=180)
    if trader:
        cards.append({"key": "trader", "label": "Trader Agent", "summary": trader})
    return cards


def build_analysis_view(final_state: Mapping[str, Any]) -> dict[str, Any]:
    """Project a completed TradingAgents state into a compact ARVEN UI payload.

    This function is deliberately deterministic and network-free.  Long reports
    remain available in ``details`` for explicit drill-down, while every field
    intended for the primary dashboard is bounded to a short display value.
    """
    decision = _plain_text(final_state.get("final_trade_decision"))
    rating = parse_rating(decision)
    tone, stance_label, action_label = _RATING_PRESENTATION[rating]

    thesis_source = (
        _nested_text(final_state, "risk_debate_state", "judge_decision")
        or decision
        or _plain_text(final_state.get("trader_investment_plan"))
    )

    details = {
        "market": _plain_text(final_state.get("market_report")),
        "sentiment": _plain_text(final_state.get("sentiment_report")),
        "news": _plain_text(final_state.get("news_report")),
        "kap": _plain_text(final_state.get("kap_report")),
        "fundamentals": _plain_text(final_state.get("fundamentals_report")),
        "bull": _nested_text(final_state, "investment_debate_state", "bull_history"),
        "bear": _nested_text(final_state, "investment_debate_state", "bear_history"),
        "risk": _nested_text(final_state, "risk_debate_state", "judge_decision"),
        "trader": _plain_text(final_state.get("trader_investment_plan")),
        "final_decision": decision,
    }

    return {
        "ticker": _plain_text(final_state.get("company_of_interest")),
        "trade_date": _plain_text(final_state.get("trade_date")),
        "rating": rating,
        "tone": tone,
        "stance_label": stance_label,
        "action_label": action_label,
        "risk_level": _risk_level(final_state),
        "short_thesis": _shorten(thesis_source, max_chars=320, sentences=3),
        "agents": _agent_cards(final_state),
        "details": details,
    }


def build_history_card(record: Mapping[str, Any]) -> dict[str, Any]:
    """Create a compact dashboard card from one Phase 11 history row."""
    decision = _plain_text(record.get("final_decision"))
    rating = str(record.get("rating") or record.get("signal") or parse_rating(decision))
    if rating not in _RATING_PRESENTATION:
        rating = parse_rating(decision)
    tone, stance_label, action_label = _RATING_PRESENTATION[rating]

    performance = []
    raw_points = record.get("performance")
    if isinstance(raw_points, list):
        for point in raw_points:
            if not isinstance(point, Mapping):
                continue
            performance.append(
                {
                    "horizon_days": point.get("horizon_days"),
                    "raw_return": point.get("raw_return"),
                    "benchmark_return": point.get("benchmark_return"),
                    "alpha_return": point.get("alpha_return"),
                }
            )

    return {
        "id": record.get("id"),
        "ticker": _plain_text(record.get("ticker")),
        "trade_date": _plain_text(record.get("trade_date")),
        "rating": rating,
        "tone": tone,
        "stance_label": stance_label,
        "action_label": action_label,
        "entry_price": record.get("entry_price"),
        "benchmark_ticker": record.get("benchmark_ticker"),
        "short_decision": _shorten(decision, max_chars=240, sentences=2),
        "performance": performance,
    }
