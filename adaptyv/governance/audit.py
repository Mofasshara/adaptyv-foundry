from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from adaptyv.governance.models import Actor, AuditEntry

GENESIS = "0" * 64


def _canonical(ts: str, actor: Actor, action: str, target_type: str, target_id: str,
               outcome: str, details: dict[str, Any], prev_hash: str) -> str:
    payload = {
        "ts": ts,
        "actor": {"kind": actor.kind.value, "id": actor.id},
        "action": action, "target_type": target_type, "target_id": target_id,
        "outcome": outcome, "details": details, "prev_hash": prev_hash,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _hash(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        conn.execute(
            """CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL, actor_kind TEXT NOT NULL, actor_id TEXT NOT NULL,
                action TEXT NOT NULL, target_type TEXT NOT NULL, target_id TEXT NOT NULL,
                outcome TEXT NOT NULL, details TEXT NOT NULL,
                prev_hash TEXT NOT NULL, entry_hash TEXT NOT NULL)"""
        )
        conn.commit()

    def record(self, actor: Actor, action: str, target_type: str, target_id: str,
               outcome: str, details: dict[str, Any] | None = None) -> AuditEntry:
        details = details or {}
        ts = datetime.now(timezone.utc).isoformat()
        prev = self._last_hash()
        entry_hash = _hash(_canonical(ts, actor, action, target_type, target_id, outcome, details, prev))
        cur = self._conn.execute(
            """INSERT INTO audit_log
               (ts,actor_kind,actor_id,action,target_type,target_id,outcome,details,prev_hash,entry_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (ts, actor.kind.value, actor.id, action, target_type, target_id, outcome,
             json.dumps(details, sort_keys=True), prev, entry_hash),
        )
        self._conn.commit()
        return AuditEntry(id=cur.lastrowid, ts=ts, actor=actor, action=action,
                          target_type=target_type, target_id=target_id, outcome=outcome,
                          details=details, prev_hash=prev, entry_hash=entry_hash)

    def entries(self) -> list[AuditEntry]:
        rows = self._conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
        return [self._row_to_entry(r) for r in rows]

    def verify(self) -> bool:
        prev = GENESIS
        for r in self._conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall():
            if r["prev_hash"] != prev:
                return False
            recomputed = _hash(_canonical(
                r["ts"], Actor(kind=r["actor_kind"], id=r["actor_id"]), r["action"],
                r["target_type"], r["target_id"], r["outcome"],
                json.loads(r["details"]), r["prev_hash"]))
            if recomputed != r["entry_hash"]:
                return False
            prev = r["entry_hash"]
        return True

    def _last_hash(self) -> str:
        row = self._conn.execute("SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
        return row["entry_hash"] if row else GENESIS

    def _row_to_entry(self, r: sqlite3.Row) -> AuditEntry:
        return AuditEntry(
            id=r["id"], ts=r["ts"], actor=Actor(kind=r["actor_kind"], id=r["actor_id"]),
            action=r["action"], target_type=r["target_type"], target_id=r["target_id"],
            outcome=r["outcome"], details=json.loads(r["details"]),
            prev_hash=r["prev_hash"], entry_hash=r["entry_hash"])
