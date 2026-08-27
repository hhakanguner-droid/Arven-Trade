"""Safe, persisted progress signals for ARVEN Trade analysis jobs."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

logger = logging.getLogger(__name__)

AGENT_PIYASA = "Piyasa Analisti"
AGENT_DUYARLILIK = "Duyarlılık Analisti"
AGENT_HABER = "Haber Analisti"
AGENT_TEMEL = "Temel Analist"
AGENT_KAP = "KAP Araştırmacısı"
AGENT_BOGA = "Boğa Görüş Araştırmacısı"
AGENT_AYI = "Ayı Görüş Araştırmacısı"
AGENT_RISK = "Risk Yöneticisi"
AGENT_TRADER = "İşlem (Trader) Ajanı"

ARVEN_AGENT_NAMES = (
    AGENT_PIYASA,
    AGENT_DUYARLILIK,
    AGENT_HABER,
    AGENT_TEMEL,
    AGENT_KAP,
    AGENT_BOGA,
    AGENT_AYI,
    AGENT_RISK,
    AGENT_TRADER,
)

_NODE_AGENT = {
    "Market Analyst": AGENT_PIYASA,
    "tools_market": AGENT_PIYASA,
    "Sentiment Analyst": AGENT_DUYARLILIK,
    "tools_social": AGENT_DUYARLILIK,
    "News Analyst": AGENT_HABER,
    "tools_news": AGENT_HABER,
    "Fundamentals Analyst": AGENT_TEMEL,
    "tools_fundamentals": AGENT_TEMEL,
    "KAP Analyst": AGENT_KAP,
    "tools_kap": AGENT_KAP,
    "Bull Researcher": AGENT_BOGA,
    "Bear Researcher": AGENT_AYI,
    "Trader": AGENT_TRADER,
    "Aggressive Analyst": AGENT_RISK,
    "Neutral Analyst": AGENT_RISK,
    "Conservative Analyst": AGENT_RISK,
    "Portfolio Manager": AGENT_RISK,
}

_CLEAR_COMPLETES = {
    "Msg Clear Market": AGENT_PIYASA,
    "Msg Clear Sentiment": AGENT_DUYARLILIK,
    "Msg Clear News": AGENT_HABER,
    "Msg Clear Fundamentals": AGENT_TEMEL,
    "Msg Clear KAP": AGENT_KAP,
}

_RECOGNIZED_NODES = set(_NODE_AGENT) | set(_CLEAR_COMPLETES) | {"Research Manager"}


class ArvenJobProgressCallback(BaseCallbackHandler):
    """Persist stage boundaries without exposing prompts, messages, or chain-of-thought."""

    raise_error = False

    def __init__(
        self,
        store: Any,
        job_id: str,
        *,
        stale_progress_seconds: int = 300,
    ) -> None:
        self.store = store
        self.job_id = str(job_id)
        self.stale_progress_seconds = max(1, int(stale_progress_seconds))
        self._completed: list[str] = []
        self._run_nodes: dict[str, str] = {}
        self._current_agent: str | None = None

    @staticmethod
    def _run_key(run_id: UUID | str | None) -> str:
        return "" if run_id is None else str(run_id)

    @staticmethod
    def _node_name(serialized: dict[str, Any] | None, metadata: dict[str, Any] | None) -> str | None:
        if metadata:
            node = metadata.get("langgraph_node")
            if node:
                return str(node)
        if serialized:
            name = serialized.get("name")
            if name in _RECOGNIZED_NODES:
                return str(name)
            ident = serialized.get("id")
            if isinstance(ident, list) and ident:
                candidate = str(ident[-1])
                if candidate in _RECOGNIZED_NODES:
                    return candidate
        return None

    def _mark_completed(self, names: Iterable[str]) -> None:
        for name in names:
            if name in ARVEN_AGENT_NAMES and name not in self._completed:
                self._completed.append(name)

    def _percent(self) -> int:
        complete = len(self._completed)
        if complete >= len(ARVEN_AGENT_NAMES):
            return 99
        base = int((complete / len(ARVEN_AGENT_NAMES)) * 100)
        if self._current_agent and self._current_agent not in self._completed:
            base = max(base, 1)
        return min(99, base)

    def _persist(self) -> None:
        try:
            self.store.update_progress(
                self.job_id,
                current_agent=self._current_agent,
                completed_agents=self._completed,
                progress_percent=self._percent(),
                stale_progress_seconds=self.stale_progress_seconds,
            )
        except Exception as exc:  # progress telemetry must never abort the analysis
            logger.warning(
                "ARVEN progress update failed job_id=%s error_type=%s",
                self.job_id,
                type(exc).__name__,
            )

    def _on_node_start(self, node: str) -> None:
        completed = _CLEAR_COMPLETES.get(node)
        if completed:
            self._mark_completed([completed])
            if self._current_agent == completed:
                self._current_agent = None
            self._persist()
            return

        if node == "Research Manager":
            self._mark_completed([AGENT_BOGA, AGENT_AYI])
            self._current_agent = None
            self._persist()
            return

        agent = _NODE_AGENT.get(node)
        if agent is None:
            return

        if agent == AGENT_RISK:
            self._mark_completed([AGENT_TRADER])
        self._current_agent = agent
        self._persist()

    def _on_node_end(self, node: str) -> None:
        if node == "Trader":
            self._mark_completed([AGENT_TRADER])
            if self._current_agent == AGENT_TRADER:
                self._current_agent = None
            self._persist()
        elif node == "Portfolio Manager":
            self._mark_completed([AGENT_RISK])
            if self._current_agent == AGENT_RISK:
                self._current_agent = None
            self._persist()
        elif node in _NODE_AGENT:
            # Tool/agent loop completion is a genuine heartbeat/progress boundary,
            # but the analyst is only marked complete by its Msg Clear node.
            self._persist()

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        del inputs, parent_run_id, tags, kwargs
        node = self._node_name(serialized, metadata)
        if node is None:
            return None
        self._run_nodes[self._run_key(run_id)] = node
        self._on_node_start(node)
        return None

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        del outputs, parent_run_id, kwargs
        node = self._run_nodes.pop(self._run_key(run_id), None)
        if node:
            self._on_node_end(node)
        return None

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        del error, parent_run_id, kwargs
        self._run_nodes.pop(self._run_key(run_id), None)
        try:
            self.store.heartbeat(self.job_id)
        except Exception:
            pass
        return None
