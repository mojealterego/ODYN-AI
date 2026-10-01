from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from .bitemporal_store import BitemporalMemoryNode, MemoryEpisode


class RAGRetriever(Protocol):
    def retrieve_relevant_scoped(self, query: str, *, episode_ids: tuple[int, ...], top_k: int = 4) -> list[dict[str, Any]]: ...


class CrossEncoder(Protocol):
    def score(self, query: str, text: str) -> float: ...


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
class TemporalEvidenceResult:
    query: str
    valid_at: datetime
    transaction_at: datetime
    items: tuple[TemporalRAGItem, ...]
    eligible_episode_ids: tuple[int, ...]
    evidence: tuple[dict[str, Any], ...]
    decision_cycle_ids: tuple[str, ...]
    rag_context: str
    reranker: str


class TemporalRAGRetriever:
    """Temporal scope -> vector retrieval -> reranking -> reliability -> causal trace."""

    def __init__(self, store: BitemporalMemoryNode, *, rag: RAGRetriever | None = None, cross_encoder: CrossEncoder | None = None) -> None:
        self.store = store
        self.rag = rag
        self.cross_encoder = cross_encoder

    def retrieve(self, query: str, *, valid_at: datetime | None, transaction_at: datetime | None, top_k: int = 8, event_types: tuple[str, ...] | None = None, decision_cycle_id: str | None = None) -> TemporalEvidenceResult:
        query = query.strip()
        if not query:
            raise ValueError("query cannot be empty")
        if valid_at is None:
            raise ValueError("valid_at is required")
        if transaction_at is None:
            raise ValueError("transaction_at is required")
        if top_k < 1:
            raise ValueError("top_k must be >= 1")

        episodes = self.store.query(valid_at=valid_at, transaction_at=transaction_at)
        if event_types:
            allowed = set(event_types)
            episodes = [e for e in episodes if e.event_type in allowed]
        if decision_cycle_id:
            episodes = [e for e in episodes if str(e.payload.get("decision_cycle_id", "")) == decision_cycle_id]

        eligible_ids = tuple(e.id for e in episodes)
        items = tuple(self._to_item(e) for e in episodes[-top_k:])

        candidates: list[dict[str, Any]] = []
        if self.rag and eligible_ids:
            candidates = list(self.rag.retrieve_relevant_scoped(query, episode_ids=eligible_ids, top_k=top_k))

        by_id = {e.id: e for e in episodes}
        for candidate in candidates:
            episode = by_id.get(candidate.get("episode_id"))
            if episode is None:
                candidate["source_reliability"] = 0.0
                candidate["final_score"] = 0.0
                continue
            embedding_score = max(0.0, min(1.0, float(candidate.get("score", 0.0))))
            reliability = max(0.0, min(1.0, float(episode.payload.get("source_reliability", 0.5))))
            cross_score = embedding_score
            if self.cross_encoder is not None:
                cross_score = max(0.0, min(1.0, float(self.cross_encoder.score(query, str(candidate.get("text", ""))))))
            candidate["embedding_score"] = embedding_score
            candidate["cross_encoder_score"] = cross_score
            candidate["source_reliability"] = reliability
            candidate["final_score"] = 0.45 * cross_score + 0.35 * embedding_score + 0.20 * reliability

        candidates.sort(key=lambda item: float(item.get("final_score", 0.0)), reverse=True)
        evidence = tuple(candidates[:top_k])

        snapshot = self.store.memory_snapshot(valid_at=valid_at, transaction_at=transaction_at)
        visible = {e.id: e for e in snapshot.episodic}
        outgoing: dict[int, list[int]] = {}
        for edge in snapshot.edges:
            outgoing.setdefault(edge.source_id, []).append(edge.target_id)

        cycles = {cycle for item in items for cycle in item.decision_cycle_ids}
        for item in evidence:
            episode_id = item.get("episode_id")
            if episode_id is None:
                continue
            for target_id in outgoing.get(int(episode_id), []):
                target = visible.get(target_id)
                if target and target.event_type == "cognitive_decision":
                    cycle = target.payload.get("decision_cycle_id")
                    if cycle:
                        cycles.add(str(cycle))

        context = "\n".join(f"[episode={item.get('episode_id')} score={float(item.get('final_score', 0.0)):.4f}] {item.get('text', '')}" for item in evidence)
        return TemporalEvidenceResult(
            query=query,
            valid_at=valid_at,
            transaction_at=transaction_at,
            items=items,
            eligible_episode_ids=eligible_ids,
            evidence=evidence,
            decision_cycle_ids=tuple(sorted(cycles)),
            rag_context=f"\n[TEMPORAL EVIDENCE]: {context}\n" if context else "",
            reranker="cross_encoder" if self.cross_encoder is not None else "embedding",
        )

    @staticmethod
    def _to_item(episode: MemoryEpisode) -> TemporalRAGItem:
        cycle = episode.payload.get("decision_cycle_id")
        return TemporalRAGItem(
            episode_id=episode.id,
            event_type=episode.event_type,
            payload=episode.payload,
            valid_time_start=episode.valid_time_start,
            valid_time_end=episode.valid_time_end,
            transaction_time_start=episode.transaction_time_start,
            transaction_time_end=episode.transaction_time_end,
            decision_cycle_ids=(str(cycle),) if cycle else (),
        )
