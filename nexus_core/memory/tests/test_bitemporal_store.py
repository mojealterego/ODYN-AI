from __future__ import annotations

from datetime import datetime, timedelta, timezone

from nexus_core.memory.bitemporal_store import BitemporalMemoryNode


def test_records_episode_and_recovers_transaction_state(tmp_path):
    db = tmp_path / "memory.db"
    store = BitemporalMemoryNode(str(db))

    valid_start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    recorded = store.record_episode(
        "odyn",
        "observation",
        {"value": "A"},
        valid_start,
    )

    assert recorded.id > 0
    assert recorded.transaction_time_start is not None

    state = store.point_in_time_recovery(recorded.transaction_time_start)
    assert len(state) == 1
    assert state[0].payload == {"value": "A"}


def test_revision_closes_previous_transaction_version(tmp_path):
    store = BitemporalMemoryNode(str(tmp_path / "memory.db"))
    valid_start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    first = store.record_episode(
        "odyn", "fact", {"value": "A"}, valid_start
    )
    second = store.record_episode(
        "odyn", "fact", {"value": "B"}, valid_start, replaces_id=first.id
    )

    assert second.id != first.id

    first_version = store.get_episode(first.id)
    assert first_version.transaction_time_end == second.transaction_time_start

    current = store.point_in_time_recovery(second.transaction_time_start)
    assert [item.payload for item in current] == [{"value": "B"}]


def test_valid_time_query_uses_world_time_axis(tmp_path):
    store = BitemporalMemoryNode(str(tmp_path / "memory.db"))
    start = datetime(2026, 2, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    store.record_episode("odyn", "event", {"ok": True}, start, end)

    assert len(store.query(valid_at=start + timedelta(hours=12))) == 1
    assert len(store.query(valid_at=end)) == 0


def test_working_memory_is_consolidated_and_cleared(tmp_path):
    store = BitemporalMemoryNode(str(tmp_path / "memory.db"))

    store.update_working_memory("task", {"name": "calculator"})
    records = store.commit_to_long_term_archive()

    assert len(records) == 1
    assert store.working_memory == {}
    assert records[0].event_type == "cognitive_consolidation"


def test_archive_compresses_payload_without_deleting_source(tmp_path):
    store = BitemporalMemoryNode(str(tmp_path / "memory.db"))
    record = store.record_episode(
        "odyn", "old_event", {"large": "x" * 100}, datetime(2020, 1, 1, tzinfo=timezone.utc)
    )

    archived = store.archive_before(datetime(2021, 1, 1, tzinfo=timezone.utc))

    assert archived == 1
    assert store.get_episode(record.id).payload == {"large": "x" * 100}
    assert store.archived_count() == 1
