"""Agent run registry — SQLite-backed persistence for per-invocation tracking.

Every agent invocation (planner, builder, evaluator, strategist, reflector, CI)
gets a persistent row with id, parent-child, status, telemetry, session_id.

Dual-track design: this registry co-exists with the append-only events.jsonl;
the JSONL remains the audit log, while SQLite enables structured queries
(get_by_task, get_children, status dashboard).

Inspired by CodeMachine-CLI's monitoring/db/schema.ts + repository.ts.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("harness.core.registry")

_SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agent_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id       TEXT,
    parent_run_id INTEGER REFERENCES agent_runs(id) ON DELETE CASCADE,
    role          TEXT    NOT NULL,
    driver        TEXT    NOT NULL,
    agent_name    TEXT    NOT NULL,
    iteration     INTEGER,
    status        TEXT    NOT NULL CHECK(status IN ('running','completed','failed','paused','skipped')),
    readonly      INTEGER DEFAULT 0,
    cwd           TEXT,
    branch        TEXT,
    session_id    TEXT,
    prompt_hash   TEXT,
    prompt_len    INTEGER,
    log_path      TEXT,
    exit_code     INTEGER,
    output_len    INTEGER,
    error         TEXT,
    started_at    TEXT    NOT NULL,
    ended_at      TEXT,
    elapsed_ms    INTEGER,
    created_at    TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_task_id       ON agent_runs(task_id);
CREATE INDEX IF NOT EXISTS idx_parent_run_id ON agent_runs(parent_run_id);
CREATE INDEX IF NOT EXISTS idx_status        ON agent_runs(status);

CREATE TABLE IF NOT EXISTS telemetry (
    run_id        INTEGER PRIMARY KEY REFERENCES agent_runs(id) ON DELETE CASCADE,
    tokens_in     INTEGER DEFAULT 0,
    tokens_out    INTEGER DEFAULT 0,
    cached_tokens INTEGER DEFAULT 0,
    cost          REAL
);
"""


@dataclass
class AgentRun:
    """Read-model for a single agent invocation row."""
    id: int
    task_id: str | None
    parent_run_id: int | None
    role: str
    driver: str
    agent_name: str
    iteration: int | None
    status: str
    readonly: bool
    cwd: str | None
    branch: str | None
    session_id: str | None
    prompt_hash: str | None
    prompt_len: int | None
    log_path: str | None
    exit_code: int | None
    output_len: int | None
    error: str | None
    started_at: str
    ended_at: str | None
    elapsed_ms: int | None
    tokens_in: int = 0
    tokens_out: int = 0
    cached_tokens: int = 0
    cost: float | None = None
    children: list[AgentRun] = field(default_factory=list)


def _prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Registry:
    """SQLite-backed agent run registry.

    Thread-safe for single-writer (the harness main thread) with WAL mode.
    """

    def __init__(self, agents_dir: Path) -> None:
        agents_dir.mkdir(parents=True, exist_ok=True)
        db_path = agents_dir / "registry.db"
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._init_schema()

    def _init_schema(self) -> None:
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version < _SCHEMA_VERSION:
            self._conn.executescript(_SCHEMA_SQL)
            self._conn.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
            self._conn.commit()
            log.debug("registry schema initialized (version=%d)", _SCHEMA_VERSION)

    # ── write operations ──────────────────────────────────────────

    def register(
        self,
        *,
        role: str,
        driver: str,
        agent_name: str,
        task_id: str | None = None,
        parent_run_id: int | None = None,
        iteration: int | None = None,
        readonly: bool = False,
        cwd: str | None = None,
        branch: str | None = None,
        prompt: str = "",
    ) -> int:
        """Insert a new running agent; return the auto-increment id."""
        cur = self._conn.execute(
            """INSERT INTO agent_runs
               (task_id, parent_run_id, role, driver, agent_name, iteration,
                status, readonly, cwd, branch, prompt_hash, prompt_len, started_at)
               VALUES (?, ?, ?, ?, ?, ?, 'running', ?, ?, ?, ?, ?, ?)""",
            (
                task_id, parent_run_id, role, driver, agent_name, iteration,
                1 if readonly else 0,
                cwd, branch,
                _prompt_hash(prompt) if prompt else None,
                len(prompt) if prompt else 0,
                _now_iso(),
            ),
        )
        self._conn.commit()
        run_id = cur.lastrowid
        log.debug("registered run #%d  role=%s driver=%s", run_id, role, driver)
        return run_id  # type: ignore[return-value]

    def complete(
        self,
        run_id: int,
        *,
        exit_code: int = 0,
        output_len: int = 0,
        elapsed_ms: int = 0,
        log_path: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Mark a run as completed."""
        self._conn.execute(
            """UPDATE agent_runs
               SET status='completed', exit_code=?, output_len=?,
                   elapsed_ms=?, ended_at=?, log_path=?, session_id=COALESCE(?, session_id)
               WHERE id=?""",
            (exit_code, output_len, elapsed_ms, _now_iso(), log_path, session_id, run_id),
        )
        self._conn.commit()

    def fail(
        self,
        run_id: int,
        *,
        error: str = "",
        exit_code: int = -1,
        output_len: int = 0,
        elapsed_ms: int = 0,
        log_path: str | None = None,
    ) -> None:
        """Mark a run as failed."""
        self._conn.execute(
            """UPDATE agent_runs
               SET status='failed', error=?, exit_code=?, output_len=?,
                   elapsed_ms=?, ended_at=?, log_path=?
               WHERE id=?""",
            (error[:2000] if error else None, exit_code, output_len,
             elapsed_ms, _now_iso(), log_path, run_id),
        )
        self._conn.commit()

    def update_telemetry(
        self,
        run_id: int,
        *,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cached_tokens: int = 0,
        cost: float | None = None,
    ) -> None:
        """Upsert telemetry for a run (fire-and-forget from stream callbacks)."""
        self._conn.execute(
            """INSERT INTO telemetry (run_id, tokens_in, tokens_out, cached_tokens, cost)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(run_id) DO UPDATE SET
                   tokens_in=excluded.tokens_in,
                   tokens_out=excluded.tokens_out,
                   cached_tokens=excluded.cached_tokens,
                   cost=excluded.cost""",
            (run_id, tokens_in, tokens_out, cached_tokens, cost),
        )
        self._conn.commit()

    def set_session_id(self, run_id: int, session_id: str) -> None:
        """Set the agent session/thread id (for future resume support)."""
        self._conn.execute(
            "UPDATE agent_runs SET session_id=? WHERE id=?",
            (session_id, run_id),
        )
        self._conn.commit()

    # ── read operations ───────────────────────────────────────────

    def get(self, run_id: int) -> AgentRun | None:
        """Fetch a single run by id, with telemetry joined."""
        row = self._conn.execute(
            """SELECT r.*, t.tokens_in, t.tokens_out, t.cached_tokens, t.cost
               FROM agent_runs r
               LEFT JOIN telemetry t ON t.run_id = r.id
               WHERE r.id = ?""",
            (run_id,),
        ).fetchone()
        if not row:
            return None
        return self._row_to_run(row)

    def get_by_task(self, task_id: str) -> list[AgentRun]:
        """All runs for a given task, ordered by id."""
        rows = self._conn.execute(
            """SELECT r.*, t.tokens_in, t.tokens_out, t.cached_tokens, t.cost
               FROM agent_runs r
               LEFT JOIN telemetry t ON t.run_id = r.id
               WHERE r.task_id = ?
               ORDER BY r.id""",
            (task_id,),
        ).fetchall()
        return [self._row_to_run(row) for row in rows]

    def get_children(self, parent_run_id: int) -> list[AgentRun]:
        """Direct children of a parent run."""
        rows = self._conn.execute(
            """SELECT r.*, t.tokens_in, t.tokens_out, t.cached_tokens, t.cost
               FROM agent_runs r
               LEFT JOIN telemetry t ON t.run_id = r.id
               WHERE r.parent_run_id = ?
               ORDER BY r.id""",
            (parent_run_id,),
        ).fetchall()
        return [self._row_to_run(row) for row in rows]

    def get_recent(self, limit: int = 20) -> list[AgentRun]:
        """Most recent runs across all tasks."""
        rows = self._conn.execute(
            """SELECT r.*, t.tokens_in, t.tokens_out, t.cached_tokens, t.cost
               FROM agent_runs r
               LEFT JOIN telemetry t ON t.run_id = r.id
               ORDER BY r.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [self._row_to_run(row) for row in rows]

    def close(self) -> None:
        self._conn.close()

    # ── internal ──────────────────────────────────────────────────

    def _row_to_run(self, row: tuple) -> AgentRun:  # type: ignore[type-arg]
        """Map a SELECT row (agent_runs.* + telemetry columns) to AgentRun."""
        return AgentRun(
            id=row[0],
            task_id=row[1],
            parent_run_id=row[2],
            role=row[3],
            driver=row[4],
            agent_name=row[5],
            iteration=row[6],
            status=row[7],
            readonly=bool(row[8]),
            cwd=row[9],
            branch=row[10],
            session_id=row[11],
            prompt_hash=row[12],
            prompt_len=row[13],
            log_path=row[14],
            exit_code=row[15],
            output_len=row[16],
            error=row[17],
            started_at=row[18],
            ended_at=row[19],
            elapsed_ms=row[20],
            # created_at = row[21]
            tokens_in=row[22] or 0,
            tokens_out=row[23] or 0,
            cached_tokens=row[24] or 0,
            cost=row[25],
        )
