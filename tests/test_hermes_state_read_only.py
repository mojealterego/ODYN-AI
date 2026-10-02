"""Session-history readers cannot create, migrate, or change agent databases."""

import sqlite3

import pytest

from hermes_state import SessionDB


def _seed(path):
    writer = SessionDB(db_path=path)
    writer.create_session("session", "cli")
    writer.set_session_title("session", "Recorded conversation")
    writer.append_message("session", "user", "Original message")
    return writer


def test_read_only_reads_public_history_api_without_changing_database(tmp_path):
    path = tmp_path / "historia # pamięci%.db"
    writer = _seed(path)
    writer.close()
    original_bytes = path.read_bytes()
    reader = SessionDB(db_path=path, read_only=True)
    try:
        assert reader.get_session_title("session") == "Recorded conversation"
        assert reader.get_messages("session")[0]["content"] == "Original message"
        assert reader.list_sessions_rich()[0]["id"] == "session"
    finally:
        reader.close()
    assert path.read_bytes() == original_bytes


def test_read_only_cannot_create_missing_database_or_parent(tmp_path):
    parent = tmp_path / "missing-profile"
    with pytest.raises(sqlite3.OperationalError):
        SessionDB(db_path=parent / "state.db", read_only=True)
    assert not parent.exists()


def test_read_only_does_not_migrate_existing_schema(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE legacy_notes (content TEXT)")
        connection.execute("INSERT INTO legacy_notes VALUES ('preserve this')")
    original_bytes = path.read_bytes()
    reader = SessionDB(db_path=path, read_only=True)
    try:
        rows = reader._conn.execute("SELECT content FROM legacy_notes").fetchall()
        assert rows[0][0] == "preserve this"
        tables = reader._conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        assert [row[0] for row in tables] == ["legacy_notes"]
    finally:
        reader.close()
    assert path.read_bytes() == original_bytes


def test_read_only_rejects_public_and_direct_writes(tmp_path):
    path = tmp_path / "state.db"
    writer = _seed(path)
    reader = SessionDB(db_path=path, read_only=True)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            reader.set_session_title("session", "Unexpected change")
        for statement in ("DELETE FROM messages", "CREATE TABLE unwanted (content TEXT)"):
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                reader._conn.execute(statement)
        assert writer.get_session_title("session") == "Recorded conversation"
        assert len(writer.get_messages("session")) == 1
    finally:
        reader.close()
        writer.close()


def test_read_only_sees_new_committed_wal_messages(tmp_path):
    path = tmp_path / "state.db"
    writer = _seed(path)
    reader = SessionDB(db_path=path, read_only=True)
    try:
        assert len(reader.get_messages("session")) == 1
        writer.append_message("session", "assistant", "Committed after the reader opened")
        messages = reader.get_messages("session")
        assert messages[-1]["content"] == "Committed after the reader opened"
    finally:
        reader.close()
        writer.close()
