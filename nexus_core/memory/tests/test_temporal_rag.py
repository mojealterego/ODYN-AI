from __future__ import annotations

from datetime import datetime, timezone
from nexus_core.memory.bitemporal_store import BitemporalMemoryNode
from nexus_core.memory.temporal_rag import TemporalRAGRetriever


class FakeRAG:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def retrieve_relevant(self, query: str, top_k: int = 4) -> str:
        self.calls.append((query, top_k))
        return "SEMANTIC: matching memory"


def test_retriever_requires_both_temporal_coordinates(tmp_path) -> None:
    retriever = TemporalRAGRetriever(BitemporalMemoryNode(str(tmp_path / "m.db")))

    try:
        retriever.retrieve(\n        "what did ODYN know?",\n        transaction_at=None,\n        valid_at=datetime(2026, 9, 1, tzinfo=timezone.utc),\n    )
    except ValueError as exc:
        assert "transaction_at" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_retriever_returns_only_knowledge_valid_then_and_known_by_transaction_cutoff(
    tmp_path,
) -> None:
    store = BitemporalMemoryNode(str(tmp_path / "m.db"))
    valid = datetime(2026, 9, 1, tzinfo=timezone.utc)
    known = datetime(2026, 9, 15, tzinfo=timezone.utc)
    later = datetime(2026, 9, 20, tzinfo=timezone.utc)

    visible = store.record_episode(
        "odyn", "research_source", {"fact": "A", "decision_cycle_id": "dc-1"},
        valid, transaction_time=known,
    )
    store.record_episode(
        "odyn", "research_source", {"fact": "B"},
        valid, transaction_time=later,
    )

    retriever = TemporalRAGRetriever(store)
    result = retriever.retrieve(
        "A",
        valid_at=datetime(2026, 9, 1, 12, tzinfo=timezone.utc),
        transaction_at=datetime(2026, 9, 15, 23, tzinfo=timezone.utc),
    )

    assert [item.episode_id for item in result.items] == [visible.id]
    assert result.items[0].decision_cycle_ids == ("dc-1",)


def test_retriever_joins_rag_evidence_and_decision_cycles(tmp_path) -> None:
    store = BitemporalMemoryNode(str(tmp_path / "m.db"))
    rag = FakeRAG()
    episode = store.record_episode(
        "odyn",
        "cognitive_decision",
        {"decision_cycle_id": "dc-42", "selected_strategy": "test-first"},
        datetime(2026, 9, 1, tzinfo=timezone.utc),
        transaction_time=datetime(2026, 9, 2, tzinfo=timezone.utc),
    )

    result = TemporalRAGRetriever(store, rag=rag).retrieve(
        "test-first",
        valid_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        transaction_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
        top_k=3,
    )

    assert result.rag_context == "SEMANTIC: matching memory"
    assert rag.calls == [("test-first", 3)]
    assert result.items[0].episode_id == episode.id
    assert result.items[0].decision_cycle_ids == ("dc-42",)


def test_retriever_follows_memory_edges_to_find_decision_cycle(tmp_path) -> None:
    store = BitemporalMemoryNode(str(tmp_path / "m.db"))
    source = store.record_episode(
        "odyn", "research_source", {"fact": "evidence"},
        datetime(2026, 9, 1, tzinfo=timezone.utc),
        transaction_time=datetime(2026, 9, 2, tzinfo=timezone.utc),
    )
    decision = store.record_episode(
        "odyn", "cognitive_decision", {"decision_cycle_id": "dc-77"},
        datetime(2026, 9, 1, tzinfo=timezone.utc),
        transaction_time=datetime(2026, 9, 3, tzinfo=timezone.utc),
    )
    store.link(source.id, decision.id, "cognitive_decision")

    result = TemporalRAGRetriever(store).retrieve(
        "evidence",
        valid_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        transaction_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
    )

    assert result.items[0].decision_cycle_ids == ("dc-77",)
