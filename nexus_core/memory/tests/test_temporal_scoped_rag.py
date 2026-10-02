from __future__ import annotations

from datetime import datetime, timezone

from nexus_core.memory.bitemporal_store import BitemporalMemoryNode
from nexus_core.memory.temporal_rag import TemporalRAGRetriever


class ScopedRAG:
    def __init__(self, entries: list[dict]) -> None:
        self.entries = entries
        self.calls: list[tuple[str, tuple[int, ...], int]] = []

    def retrieve_relevant_scoped(
        self,
        query: str,
        *,
        episode_ids: tuple[int, ...],
        top_k: int = 4,
    ) -> list[dict]:
        self.calls.append((query, episode_ids, top_k))
        return [
            entry
            for entry in self.entries
            if entry["episode_id"] in episode_ids
        ][:top_k]


def test_temporal_scoped_retrieval_never_returns_embedding_outside_snapshot(
    tmp_path,
) -> None:
    store = BitemporalMemoryNode(str(tmp_path / "memory.db"))
    valid = datetime(2026, 9, 1, tzinfo=timezone.utc)

    eligible = store.record_episode(
        "odyn",
        "research_source",
        {"fact": "eligible", "decision_cycle_id": "dc-1"},
        valid,
        transaction_time=datetime(2026, 9, 2, tzinfo=timezone.utc),
    )
    future = store.record_episode(
        "odyn",
        "research_source",
        {"fact": "future"},
        valid,
        transaction_time=datetime(2026, 9, 20, tzinfo=timezone.utc),
    )

    rag = ScopedRAG([
        {"episode_id": eligible.id, "text": "eligible evidence", "score": 0.4},
        {"episode_id": future.id, "text": "future evidence", "score": 0.99},
    ])

    result = TemporalRAGRetriever(store, rag=rag).retrieve(
        "evidence",
        valid_at=valid,
        transaction_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
        top_k=5,
    )

    assert rag.calls == [("evidence", (eligible.id,), 5)]
    assert [item["episode_id"] for item in result.scoped_evidence] == [eligible.id]
    assert future.id not in result.eligible_episode_ids


def test_temporal_scoped_retrieval_reranks_semantic_candidates(tmp_path) -> None:
    store = BitemporalMemoryNode(str(tmp_path / "memory.db"))
    valid = datetime(2026, 9, 1, tzinfo=timezone.utc)

    first = store.record_episode(
        "odyn", "research_source", {"fact": "first"},
        valid, transaction_time=datetime(2026, 9, 2, tzinfo=timezone.utc)
    )
    second = store.record_episode(
        "odyn", "research_source", {"fact": "second"},
        valid, transaction_time=datetime(2026, 9, 3, tzinfo=timezone.utc)
    )

    rag = ScopedRAG([
        {"episode_id": first.id, "text": "first", "score": 0.20},
        {"episode_id": second.id, "text": "second", "score": 0.90},
    ])

    result = TemporalRAGRetriever(store, rag=rag).retrieve(
        "query",
        valid_at=valid,
        transaction_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
        top_k=2,
    )

    assert [item["episode_id"] for item in result.scoped_evidence] == [
        second.id,
        first.id,
    ]
