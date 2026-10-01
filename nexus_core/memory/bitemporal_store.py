from __future__ import annotations

import gzip
import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    value = _utc(value)
    return value.isoformat() if value else None


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return _utc(parsed)


@dataclass(frozen=True)
class MemoryEpisode:
    id: int
    agent_id: str
    event_type: str
    payload: dict[str, Any]
    valid_time_start: datetime
    valid_time_end: datetime | None
    transaction_time_start: datetime
    transaction_time_end: datetime | None


@dataclass(frozen=True)
class ProceduralSkill:
    skill_name: str
    code_reference: str
    fitness_score: float
    last_updated: datetime


class BitemporalMemoryNode:
    """Bitemporal CoALA memory for ODYN AI."""

    def __init__(self, db_path: str = "nexus_bitemporal.db", *, busy_timeout_ms: int = 5000) -> None:
        path = Path(db_path)
        if path.parent != Path("."):
            path.parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(
            str(path), check_same_thread=False, timeout=busy_timeout_ms / 1000
        )
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self.working_memory: dict[str, Any] = {}

        with self._lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
            self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self.conn:
            self._migrate_legacy_schema()
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS episodic_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    valid_time_start TEXT NOT NULL,
                    valid_time_end TEXT,
                    transaction_time_start TEXT NOT NULL,
                    transaction_time_end TEXT,
                    UNIQUE(id)
                );
                CREATE INDEX IF NOT EXISTS idx_episode_valid_time
                    ON episodic_memory(valid_time_start, valid_time_end);
                CREATE INDEX IF NOT EXISTS idx_episode_transaction_time
                    ON episodic_memory(transaction_time_start, transaction_time_end);
                CREATE INDEX IF NOT EXISTS idx_episode_agent_type
                    ON episodic_memory(agent_id, event_type);

                CREATE TABLE IF NOT EXISTS procedural_memory (
                    skill_name TEXT PRIMARY KEY,
                    code_reference TEXT NOT NULL,
                    fitness_score REAL NOT NULL DEFAULT 0.0,
                    last_updated TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_edges (
                    source_id INTEGER NOT NULL,
                    target_id INTEGER NOT NULL,
                    relation TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(source_id, target_id, relation),
                    FOREIGN KEY(source_id) REFERENCES episodic_memory(id),
                    FOREIGN KEY(target_id) REFERENCES episodic_memory(id)
                );

                CREATE TABLE IF NOT EXISTS memory_archive (
                    episode_id INTEGER PRIMARY KEY,
                    archived_at TEXT NOT NULL,
                    payload_gzip BLOB NOT NULL,
                    FOREIGN KEY(episode_id) REFERENCES episodic_memory(id)
                );
                """
            )

    def _migrate_legacy_schema(self) -> None:
        """Upgrade the original single transaction-time schema in place.

        Older ODYN databases used one transaction timestamp. The bitemporal
        implementation needs an explicit transaction interval, so existing
        rows become open transaction versions starting at their legacy time.
        """
        columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(episodic_memory)").fetchall()
        }
        if not columns:
            return
        if "transaction_time_start" not in columns:
            self.conn.execute(
                "ALTER TABLE episodic_memory ADD COLUMN transaction_time_start TEXT"
            )
            if "transaction_time" in columns:
                self.conn.execute(
                    """
                    UPDATE episodic_memory
                    SET transaction_time_start = transaction_time
                    WHERE transaction_time_start IS NULL
                    """
                )
        if "transaction_time_end" not in columns:
            self.conn.execute(
                "ALTER TABLE episodic_memory ADD COLUMN transaction_time_end TEXT"
            )

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _row_to_episode(row: sqlite3.Row) -> MemoryEpisode:
        return MemoryEpisode(
            id=int(row["id"]),
            agent_id=row["agent_id"],
            event_type=row["event_type"],
            payload=json.loads(row["payload"]),
            valid_time_start=_parse(row["valid_time_start"]),
            valid_time_end=_parse(row["valid_time_end"]),
            transaction_time_start=_parse(row["transaction_time_start"]),
            transaction_time_end=_parse(row["transaction_time_end"]),
        )

    def record_episode(
        self, agent_id: str, event_type: str, data: dict[str, Any],
        valid_start: datetime, valid_end: datetime | None = None, *,
        transaction_time: datetime | None = None, replaces_id: int | None = None,
    ) -> MemoryEpisode:
        if not agent_id.strip():
            raise ValueError("agent_id cannot be empty")
        if not event_type.strip():
            raise ValueError("event_type cannot be empty")
        if not isinstance(data, dict):
            raise TypeError("episode payload must be a dictionary")

        valid_start = _utc(valid_start)
        valid_end = _utc(valid_end)
        transaction_time = _utc(transaction_time) or self._now()
        if valid_end is not None and valid_end <= valid_start:
            raise ValueError("valid_end must be later than valid_start")

        payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        tx_start = _iso(transaction_time)

        with self._lock, self.conn:
            if replaces_id is not None:
                current = self.conn.execute(
                    "SELECT transaction_time_start, transaction_time_end FROM episodic_memory WHERE id = ?",
                    (replaces_id,),
                ).fetchone()
                if current is None:
                    raise KeyError(f"Episode {replaces_id} does not exist")
                if current["transaction_time_end"] is not None:
                    raise ValueError("Only the current transaction version can be replaced")
                if tx_start <= current["transaction_time_start"]:
                    raise ValueError("replacement transaction_time must be later")
                self.conn.execute(
                    "UPDATE episodic_memory SET transaction_time_end = ? WHERE id = ?",
                    (tx_start, replaces_id),
                )

            cursor = self.conn.execute(
                """
                INSERT INTO episodic_memory (
                    agent_id, event_type, payload, valid_time_start, valid_time_end,
                    transaction_time_start, transaction_time_end
                ) VALUES (?, ?, ?, ?, ?, ?, NULL)
                """,
                (agent_id.strip(), event_type.strip(), payload, _iso(valid_start),
                 _iso(valid_end), tx_start),
            )
            episode_id = int(cursor.lastrowid)

        return self.get_episode(episode_id)

    def get_episode(self, episode_id: int) -> MemoryEpisode:
        with self._lock:
            row = self.conn.execute("SELECT * FROM episodic_memory WHERE id = ?", (episode_id,)).fetchone()
        if row is None:
            raise KeyError(f"Episode {episode_id} does not exist")
        return self._row_to_episode(row)

    def point_in_time_recovery(
        self, target_time: datetime, *, agent_id: str | None = None
    ) -> list[MemoryEpisode]:
        target = _iso(target_time)
        query = """
            SELECT * FROM episodic_memory
            WHERE transaction_time_start <= ?
              AND (transaction_time_end IS NULL OR transaction_time_end > ?)
        """
        params: list[Any] = [target, target]
        if agent_id is not None:
            query += " AND agent_id = ?"
            params.append(agent_id)
        query += " ORDER BY transaction_time_start ASC, id ASC"
        with self._lock:
            rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_episode(row) for row in rows]

    def query(
        self, *, valid_at: datetime | None = None, transaction_at: datetime | None = None,
        agent_id: str | None = None, event_type: str | None = None,
    ) -> list[MemoryEpisode]:
        if valid_at is None and transaction_at is None:
            return self._current(agent_id=agent_id, event_type=event_type)

        clauses: list[str] = []
        params: list[Any] = []
        if valid_at is not None:
            value = _iso(valid_at)
            clauses.append("valid_time_start <= ? AND (valid_time_end IS NULL OR valid_time_end > ?)")
            params.extend([value, value])
        if transaction_at is not None:
            value = _iso(transaction_at)
            clauses.append("transaction_time_start <= ? AND (transaction_time_end IS NULL OR transaction_time_end > ?)")
            params.extend([value, value])
        else:
            clauses.append("transaction_time_end IS NULL")
        if agent_id is not None:
            clauses.append("agent_id = ?")
            params.append(agent_id)
        if event_type is not None:
            clauses.append("event_type = ?")
            params.append(event_type)

        with self._lock:
            rows = self.conn.execute(
                f"SELECT * FROM episodic_memory WHERE {' AND '.join(clauses)} "
                "ORDER BY transaction_time_start ASC, id ASC", params
            ).fetchall()
        return [self._row_to_episode(row) for row in rows]

    def _current(self, *, agent_id: str | None = None, event_type: str | None = None) -> list[MemoryEpisode]:
        clauses = ["transaction_time_end IS NULL"]
        params: list[Any] = []
        if agent_id is not None:
            clauses.append("agent_id = ?")
            params.append(agent_id)
        if event_type is not None:
            clauses.append("event_type = ?")
            params.append(event_type)
        with self._lock:
            rows = self.conn.execute(
                f"SELECT * FROM episodic_memory WHERE {' AND '.join(clauses)} "
                "ORDER BY transaction_time_start ASC, id ASC", params
            ).fetchall()
        return [self._row_to_episode(row) for row in rows]

    def update_working_memory(self, key: str, value: Any) -> None:
        if not key.strip():
            raise ValueError("working-memory key cannot be empty")
        with self._lock:
            self.working_memory[key] = value

    def get_working_memory(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self.working_memory.get(key, default)

    def commit_to_long_term_archive(self) -> list[MemoryEpisode]:
        """Atomically persist and clear the current Working Memory snapshot.

        If a database operation fails, working memory remains intact so the
        caller can retry without silently losing state.
        """
        with self._lock:
            if not self.working_memory:
                return []

            now = self._now()
            tx_start = _iso(now)
            snapshot = list(self.working_memory.items())
            inserted_ids: list[int] = []

            with self.conn:
            for key, value in snapshot:
                payload = json.dumps(
                    {"key": key, "value": value},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                cursor = self.conn.execute(
                    """
                    INSERT INTO episodic_memory (
                        agent_id, event_type, payload, valid_time_start, valid_time_end,
                        transaction_time_start, transaction_time_end
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL)
                    """,
                    ("nexus_core", "cognitive_consolidation", payload, tx_start, None, tx_start),
                )
                    inserted_ids.append(int(cursor.lastrowid))

            records = [self._row_to_episode(
                self.conn.execute("SELECT * FROM episodic_memory WHERE id = ?", (item_id,)).fetchone()
            ) for item_id in inserted_ids]
            self.working_memory.clear()
            return records

    def upsert_procedural_skill(
        self, skill_name: str, code_reference: str, fitness_score: float, *,
        updated_at: datetime | None = None,
    ) -> ProceduralSkill:
        if not skill_name.strip():
            raise ValueError("skill_name cannot be empty")
        if not 0.0 <= fitness_score <= 1.0:
            raise ValueError("fitness_score must be between 0 and 1")
        updated_at = _utc(updated_at) or self._now()
        with self._lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO procedural_memory (skill_name, code_reference, fitness_score, last_updated)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(skill_name) DO UPDATE SET
                    code_reference=excluded.code_reference,
                    fitness_score=excluded.fitness_score,
                    last_updated=excluded.last_updated
                """,
                (skill_name.strip(), code_reference, fitness_score, _iso(updated_at)),
            )
            row = self.conn.execute(
                "SELECT * FROM procedural_memory WHERE skill_name = ?", (skill_name.strip(),)
            ).fetchone()
        return ProceduralSkill(
            skill_name=row["skill_name"], code_reference=row["code_reference"],
            fitness_score=float(row["fitness_score"]), last_updated=_parse(row["last_updated"])
        )

    def link(self, source_id: int, target_id: int, relation: str) -> None:
        if not relation.strip():
            raise ValueError("relation cannot be empty")
        with self._lock, self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO memory_edges (source_id, target_id, relation, created_at) "
                "VALUES (?, ?, ?, ?)",
                (source_id, target_id, relation.strip(), _iso(self._now())),
            )

    def related(self, episode_id: int, relation: str | None = None) -> list[MemoryEpisode]:
        query = """
            SELECT e.* FROM episodic_memory e
            JOIN memory_edges edge ON edge.target_id = e.id
            WHERE edge.source_id = ?
        """
        params: list[Any] = [episode_id]
        if relation is not None:
            query += " AND edge.relation = ?"
            params.append(relation)
        query += " ORDER BY e.transaction_time_start ASC"
        with self._lock:
            rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_episode(row) for row in rows]

    def archive_before(self, cutoff: datetime) -> int:
        cutoff_iso = _iso(cutoff)
        now = _iso(self._now())
        with self._lock, self.conn:
            rows = self.conn.execute(
                """
                SELECT id, payload FROM episodic_memory
                WHERE valid_time_start < ?
                  AND id NOT IN (SELECT episode_id FROM memory_archive)
                ORDER BY id ASC
                """, (cutoff_iso,)
            ).fetchall()
            for row in rows:
                compressed = gzip.compress(row["payload"].encode("utf-8"), compresslevel=6)
                self.conn.execute(
                    "INSERT INTO memory_archive (episode_id, archived_at, payload_gzip) VALUES (?, ?, ?)",
                    (row["id"], now, compressed),
                )
        return len(rows)

    def archived_count(self) -> int:
        with self._lock:
            row = self.conn.execute("SELECT COUNT(*) AS count FROM memory_archive").fetchone()
        return int(row["count"])

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def __enter__(self) -> "BitemporalMemoryNode":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
