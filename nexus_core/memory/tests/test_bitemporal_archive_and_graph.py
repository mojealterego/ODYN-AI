from __future__ import annotations

from datetime import datetime, timezone

from nexus_core.memory.bitemporal_store import BitemporalMemoryNode


def test_archived_payload_can_be_read_back_after_compression(tmp_path) -> None:
    store = BitemporalMemoryNode(str(tmp_path / "memory.db"))
    record = store.record_episode(
        "odyn",
        "old_event",
        {"value": "historical"},
        datetime(2020, 1, 1, tzinfo=timezone.utc),
    )

    assert store.archive_before(datetime(2021, 1, 1, tzinfo=timezone.utc)) == 1
    assert store.get_archived_payload(record.id) == {"value": "historical"}


def test_snapshot_excludes_edges_created_after_transaction_cutoff(tmp_path) -> None:
    store = BitemporalMemoryNode(str(tmp_path / "memory.db"))
    valid = datetime(2026, 4, 1, tzinfo=timezone.utc)
    tx = datetime(2026, 4, 2, tzinfo=timezone.utc)

    source = store.record_episode(
        "odyn", "decision", {"value": "accepted"}, valid, transaction_time=tx
    )
    target = store.record_episode(
        "odyn",
        "result",
        {"ok": True},
        valid,
        transaction_time=tx,
    )

    store.link(
        source.id,
        target.id,
        "verified_by",
        created_at=datetime(2026, 4, 3, tzinfo=timezone.utc),
    )

    historical = store.memory_snapshot(valid_at=valid, transaction_at=tx)
    current = store.memory_snapshot(
        valid_at=valid,
        transaction_at=datetime(2026, 4, 4, tzinfo=timezone.utc),
    )

    assert historical.edges == []
    assert len(current.edges) == 1
