from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class SQLiteRunStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    mode TEXT,
                    config_hash TEXT,
                    started_at TEXT,
                    ended_at TEXT,
                    session_path TEXT,
                    manifest_path TEXT,
                    latest_summary_path TEXT,
                    latest_health_path TEXT,
                    latest_artifact_manifest_path TEXT,
                    updated_at TEXT,
                    payload_json TEXT
                );
                CREATE TABLE IF NOT EXISTS checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    checkpoint_ts TEXT NOT NULL,
                    session_path TEXT,
                    summary_path TEXT,
                    health_path TEXT,
                    artifact_manifest_path TEXT,
                    counters_json TEXT,
                    payload_json TEXT,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                );
                CREATE INDEX IF NOT EXISTS idx_checkpoints_run_id_ts ON checkpoints (run_id, checkpoint_ts);
                """
            )

    def record_run_started(
        self,
        *,
        run_id: str,
        mode: str,
        config_hash: str,
        started_at: str,
        session_path: str,
        manifest_path: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        payload_json = json.dumps(payload or {}, sort_keys=True, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    run_id, mode, config_hash, started_at, session_path, manifest_path,
                    updated_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    mode=excluded.mode,
                    config_hash=excluded.config_hash,
                    session_path=excluded.session_path,
                    manifest_path=excluded.manifest_path,
                    updated_at=excluded.updated_at,
                    payload_json=excluded.payload_json
                """,
                (run_id, mode, config_hash, started_at, session_path, manifest_path, started_at, payload_json),
            )

    def record_checkpoint(
        self,
        *,
        run_id: str,
        checkpoint_ts: str,
        session_path: str,
        summary_path: str,
        health_path: str,
        artifact_manifest_path: str,
        counters: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        counters_json = json.dumps(counters or {}, sort_keys=True, ensure_ascii=False)
        payload_json = json.dumps(payload or {}, sort_keys=True, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO checkpoints (
                    run_id, checkpoint_ts, session_path, summary_path, health_path,
                    artifact_manifest_path, counters_json, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, checkpoint_ts, session_path, summary_path, health_path, artifact_manifest_path, counters_json, payload_json),
            )
            conn.execute(
                """
                UPDATE runs
                SET latest_summary_path=?, latest_health_path=?, latest_artifact_manifest_path=?, updated_at=?
                WHERE run_id=?
                """,
                (summary_path, health_path, artifact_manifest_path, checkpoint_ts, run_id),
            )

    def mark_run_completed(self, *, run_id: str, ended_at: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET ended_at=?, updated_at=? WHERE run_id=?",
                (ended_at, ended_at, run_id),
            )

    def load_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["payload_json"] = json.loads(payload.get("payload_json") or "{}")
        return payload

    def load_latest_checkpoint(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM checkpoints WHERE run_id=? ORDER BY checkpoint_ts DESC, id DESC LIMIT 1",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["counters_json"] = json.loads(payload.get("counters_json") or "{}")
        payload["payload_json"] = json.loads(payload.get("payload_json") or "{}")
        return payload
