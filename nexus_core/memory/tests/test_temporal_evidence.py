from datetime import datetime, timezone

from nexus_core.memory.bitemporal_store import BitemporalMemoryNode
from nexus_core.memory.temporal_rag import TemporalRAGRetriever


class FakeEvidenceRAG:
    def __init__(self, entries):
        self.entries = entries

    def retrieve_relevant_scoped(self, query, *, episode_ids, top_k=4):
        allowed = set(episode_ids)
        return [item for item in self.entries if item["episode_id"] in allowed][:top_k]


class CrossEncoder:
    def score(self, query, text):
        return 0.95 if "primary" in text else 0.10


def test_temporal_evidence_reranks_with_cross_encoder_and_reliability(tmp_path):
    store = BitemporalMemoryNode(str(tmp_path / "memory.db"))
    valid = datetime(2026, 9, 1, tzinfo=timezone.utc)

    primary = store.record_episode(
        "odyn",
        "research_source",
        {"fact": "primary evidence", "source_reliability": 0.95, "decision_cycle_id": "dc-1"},
        valid,
        transaction_time=datetime(2026, 9, 2, tzinfo=timezone.utc),
    )
    secondary = store.record_episode(
        "odyn",
        "research_source",
        {"fact": "secondary evidence", "source_reliability": 0.50},
        valid,
        transaction_time=datetime(2026, 9, 3, tzinfo=timezone.utc),
    )

    rag = FakeEvidenceRAG([
        {"episode_id": secondary.id, "text": "secondary evidence", "score": 0.99},
        {"episode_id": primary.id, "text": "primary evidence", "score": 0.70},
    ])

    result = TemporalRAGRetriever(
        store,
        rag=rag,
        cross_encoder=CrossEncoder(),
    ).retrieve(
        "evidence",
        valid_at=valid,
        transaction_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
        top_k=2,
    )

    assert [item["episode_id"] for item in result.evidence] == [primary.id, secondary.id]
    assert result.evidence[0]["source_reliability"] == 0.95
    assert result.decision_cycle_ids == ("dc-1",)


def test_temporal_evidence_uses_embedding_fallback_without_cross_encoder(tmp_path):
    store = BitemporalMemoryNode(str(tmp_path / "memory.db"))
    valid = datetime(2026, 9, 1, tzinfo=timezone.utc)
    episode = store.record_episode(
        "odyn",
        "research_source",
        {"fact": "evidence", "source_reliability": 0.8},
        valid,
        transaction_time=datetime(2026, 9, 2, tzinfo=timezone.utc),
    )
    rag = FakeEvidenceRAG([
        {"episode_id": episode.id, "text": "evidence", "score": 0.8},
    ])

    result = TemporalRAGRetriever(store, rag=rag).retrieve(
        "evidence",
        valid_at=valid,
        transaction_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
    )

    assert result.evidence[0]["final_score"] > 0
    assert result.reranker == "embedding"
