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


def test_migrates_legacy_transaction_time_schema(tmp_path):
    import sqlite3

    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE episodic_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT,
            event_type TEXT,
            payload TEXT,
            valid_time_start DATETIME,
            valid_time_end DATETIME,
            transaction_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        INSERT INTO episodic_memory
        (agent_id, event_type, payload, valid_time_start, transaction_time)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("odyn", "legacy", '{"value":"kept"}', "2026-01-01T00:00:00+00:00", "2026-01-02T00:00:00+00:00"),
    )
    conn.commit()
    conn.close()

    store = BitemporalMemoryNode(str(db))
    recovered = store.point_in_time_recovery(
        datetime(2026, 1, 3, tzinfo=timezone.utc)
    )

    assert [item.payload for item in recovered] == [{"value": "kept"}]


def test_working_memory_consolidation_is_atomic(tmp_path):
    store = BitemporalMemoryNode(str(tmp_path / "memory.db"))

    store.update_working_memory("first", {"value": 1})
    store.update_working_memory("second", {"value": 2})

    records = store.commit_to_long_term_archive()

    assert {item.payload["key"] for item in records} == {"first", "second"}
    assert {item.payload["value"] for item in records} == {1, 2}
    assert store.working_memory == {}


def test_procedural_skill_versions_are_bitemporal(tmp_path):
    store = BitemporalMemoryNode(str(tmp_path / "memory.db"))
    valid = datetime(2026, 3, 1, tzinfo=timezone.utc)
    tx1 = datetime(2026, 3, 2, tzinfo=timezone.utc)
    tx2 = datetime(2026, 3, 3, tzinfo=timezone.utc)

    first = store.upsert_procedural_skill(
        "web.build.verified", "builder.v1", 0.6,
        updated_at=tx1, valid_time=valid,
        transaction_time=tx1,
    )
    second = store.upsert_procedural_skill(
        "web.build.verified", "builder.v2", 0.95,
        updated_at=tx2, valid_time=valid,
        transaction_time=tx2,
    )

    assert first.code_reference == "builder.v1"
    assert second.code_reference == "builder.v2"

    historical = store.procedural_query(
        valid_at=valid,
        transaction_at=tx1,
    )
    assert [(skill.skill_name, skill.code_reference) for skill in historical] == [
        ("web.build.verified", "builder.v1")
    ]

    current = store.procedural_query(
        valid_at=valid,
        transaction_at=tx2,
    )
    assert [(skill.skill_name, skill.code_reference) for skill in current] == [
        ("web.build.verified", "builder.v2")
    ]


def test_memory_snapshot_reconstructs_episodic_procedural_and_graph_state(tmp_path):
    store = BitemporalMemoryNode(str(tmp_path / "memory.db"))
    valid = datetime(2026, 4, 1, tzinfo=timezone.utc)
    tx = datetime(2026, 4, 2, tzinfo=timezone.utc)

    episode = store.record_episode(
        "odyn", "decision", {"value": "accepted"}, valid,
        transaction_time=tx,
    )
    store.upsert_procedural_skill(
        "coding.test", "skill.v1", 0.9,
        updated_at=tx, valid_time=valid,
        transaction_time=tx,
    )
    target = store.record_episode(
        "odyn", "result", {"ok": True}, valid,
        transaction_time=datetime(2026, 4, 3, tzinfo=timezone.utc),
    )
    store.link(episode.id, target.id, "verified_by", created_at=datetime(2026, 4, 3, tzinfo=timezone.utc))

    snapshot = store.memory_snapshot(valid_at=valid, transaction_at=tx)

    assert [item.payload for item in snapshot.episodic] == [{"value": "accepted"}]
    assert [item.code_reference for item in snapshot.procedural] == ["skill.v1"]
    assert snapshot.edges == []
