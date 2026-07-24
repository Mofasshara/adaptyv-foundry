from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from adaptyv.governance.models import Actor


class FeedbackStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        conn.execute(
            """CREATE TABLE IF NOT EXISTS draft_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT, draft_id TEXT NOT NULL,
                corrected_body TEXT NOT NULL, corrected_by TEXT NOT NULL, ts TEXT NOT NULL)"""
        )
        conn.commit()

    def record_correction(self, draft_id: str, corrected_body: str, corrected_by: Actor) -> None:
        self._conn.execute(
            "INSERT INTO draft_feedback (draft_id,corrected_body,corrected_by,ts) VALUES (?,?,?,?)",
            (draft_id, corrected_body, corrected_by.id, datetime.now(timezone.utc).isoformat()))
        self._conn.commit()

    def corrections(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM draft_feedback ORDER BY id").fetchall()
        return [{"draft_id": r["draft_id"], "corrected_body": r["corrected_body"],
                 "corrected_by": r["corrected_by"], "ts": r["ts"]} for r in rows]
