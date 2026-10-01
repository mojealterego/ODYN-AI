from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from .bitemporal_store import BitemporalMemoryNode, MemoryEpisode


class RAGRetriever(Protocol):
    def retrieve_relevant(self, query: str, top_k: int = 4) -> str: ...

    def retrieve_relevant_scoped(
        self,
        query: str,
        *,
        episode_ids: tuple[int, ...],
        top_k: int = 4,
    ) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class TemporalRAGItem:
    episode_id: int
    event_type: str
    payload: dict[str, Any]
    valid_time_start: datetime
    valid_time_end: datetime | None
    transaction_time_start: datetime
    transaction_time_end: datetime | None
    decision_cycle_ids: tuple[str, ...]


@dataclass(frozen=True)
class TemporalRAGResult:
    query: str
    valid_at: datetime
    transaction_at: datetime
    items: tuple[TemporalRAGItem, ...]
    decision_cycle_ids: tuple[str, ...]
    rag_context: str
    eligible_episode_ids: tuple[int, ...] = ()
    scoped_evidence: tuple[dict[str, Any], ...] = ()


class TemporalRAGRetriever:
    """Temporal filter first, vector retrieval second, causal enrichment last."""

    def __init__(
        self,
        store: BitemporalMemoryNode,
        *,
        rag: RAGRetriever | None = None,
    ) -> None:
        self.store = store
        self.rag = rag

    def retrieve(
        self,
        query: str,
        *,
        valid_at: datetime | None,
        transaction_at: datetime | None,
        top_k: int = 8,
        event_types: tuple[str, ...] | None = None,
        decision_cycle_id: str | None = None,
    ) -> TemporalRAGResult:
        query = query.strip()
        if not query:
            raise ValueError("query cannot be empty")
        if valid_at is None:
            raise ValueError("valid_at is required")
        if transaction_at is None:
            raise ValueError("transaction_at is required")
        if top_k < 1:
            raise ValueError("top_k must be >= 1")

        episodes = self.store.query(
            valid_at=valid_at,
            transaction_at=transaction_at,
        )
        if event_types:
            allowed = set(event_types)
            episodes = [
                episode for episode in episodes
                if episode.event_type in allowed
            ]

        if decision_cycle_id:
            episodes = [
                episode
                for episode in episodes
                if str(episode.payload.get("decision_cycle_id", ""))
                == decision_cycle_id
            ]

        items = tuple(
            self._to_item(episode)
            for episode in episodes[-top_k:]
        )
        eligible_episode_ids = tuple(item.episode_id for item in items)

        scoped_evidence: list[dict[str, Any]] = []
        semantic = ""
        if self.rag and eligible_episode_ids:
            scoped_method = getattr(
                self.rag,
                "retrieve_relevant_scoped",
                None,
            )
            if callable(scoped_method):
                scoped_evidence = list(
                    scoped_method(
                        query,
                        episode_ids=eligible_episode_ids,
                        top_k=top_k,
                    )
                )
                scoped_evidence.sort(
                    key=lambda item: float(item.get("score", 0.0)),
                    reverse=True,
                )
                context = "\n".join(
                    f"[episode={item.get('episode_id')}] {item.get('text', '')}"
                    for item in scoped_evidence
                )
                semantic = (
                    f"\n[TEMPORAL-SCOPED RAG]: {context}\n"
                    if context else ""
                )

        cycle_ids = set()
        for item in items:
            cycle_ids.update(item.decision_cycle_ids)

        snapshot = self.store.memory_snapshot(
            valid_at=valid_at,
            transaction_at=transaction_at,
        )
        visible_by_id = {
            episode.id: episode for episode in snapshot.episodic
        }
        outgoing: dict[int, list[int]] = {}
        for edge in snapshot.edges:
            outgoing.setdefault(edge.source_id, []).append(edge.target_id)

        enriched_cycles = set(cycle_ids)
        for item in items:
            for target_id in outgoing.get(item.episode_id, []):
                target = visible_by_id.get(target_id)
                if target is None or target.event_type != "cognitive_decision":
                    continue
                cycle = target.payload.get("decision_cycle_id")
                if cycle:
                    enriched_cycles.add(str(cycle))

        return TemporalRAGResult(
            query=query,
            valid_at=valid_at,
            transaction_at=transaction_at,
            items=items,
            decision_cycle_ids=tuple(sorted(enriched_cycles)),
            rag_context=semantic,
            eligible_episode_ids=eligible_episode_ids,
            scoped_evidence=tuple(scoped_evidence),
        )

    @staticmethod
    def _to_item(episode: MemoryEpisode) -> TemporalRAGItem:
        cycle = episode.payload.get("decision_cycle_id")
        cycles = (str(cycle),) if cycle else ()
        return TemporalRAGItem(
            episode_id=episode.id,
            event_type=episode.event_type,
            payload=episode.payload,
            valid_time_start=episode.valid_time_start,
            valid_time_end=episode.valid_time_end,
            transaction_time_start=episode.transaction_time_start,
            transaction_time_end=episode.transaction_time_end,
            decision_cycle_ids=cycles,
        )
