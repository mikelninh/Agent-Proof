from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .models import EvalPack, RunRecord


class Store:
    def __init__(self, path: str | None = None):
        self.path = path or os.getenv("AGENTPROOF_DB", "agentproof.db")
        self._init()

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS packs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    pack_id TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                """
            )

    def upsert_pack(self, pack: EvalPack):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO packs(id,name,payload) VALUES(?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name,payload=excluded.payload",
                (pack.id, pack.name, pack.model_dump_json()),
            )

    def get_pack(self, pack_id: str) -> EvalPack | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM packs WHERE id=?", (pack_id,)).fetchone()
        return EvalPack.model_validate_json(row["payload"]) if row else None

    def list_packs(self) -> list[EvalPack]:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM packs ORDER BY name").fetchall()
        return [EvalPack.model_validate_json(r["payload"]) for r in rows]

    def save_run(self, run: RunRecord):
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO runs(id,created_at,pack_id,payload) VALUES(?,?,?,?)",
                (run.id, run.created_at, run.pack_id, run.model_dump_json()),
            )

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM runs WHERE id=?", (run_id,)).fetchone()
        return RunRecord.model_validate_json(row["payload"]) if row else None

    def list_runs(self, limit: int = 50) -> list[RunRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [RunRecord.model_validate_json(r["payload"]) for r in rows]

    def seed_from_directory(self, directory: str | Path):
        directory = Path(directory)
        if not directory.exists():
            return
        for path in directory.glob("*.json"):
            self.upsert_pack(EvalPack.model_validate_json(path.read_text(encoding="utf-8")))
