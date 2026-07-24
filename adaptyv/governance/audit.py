"""Tamper-evident (not tamper-proof) hash-chained audit log.

Trust model — read this before relying on `verify()` for anything:

`AuditLog` chains each entry to its predecessor with a SHA-256 hash over a
canonical JSON encoding of the entry plus the previous entry's hash
(`prev_hash`). `verify()` walks the chain from GENESIS forward and confirms
every link and every entry's recomputed hash still match what's stored.

What this DOES catch:
  - Editing the content of an existing row (its stored `entry_hash` no
    longer matches the recomputed hash).
  - Deleting or reordering a row in the MIDDLE of the chain (the following
    row's `prev_hash` no longer matches, breaking the walk).

What this does NOT catch on its own:
  - Tail truncation. Deleting the most recent N rows leaves a shorter but
    internally-consistent prefix, so a bare `verify()` still returns True
    even though history was erased. The only way to detect this is to have
    pinned the chain's tail *before* the deletion: call `head()` to get
    `(count, last_entry_hash)` at a known-good point, keep that value
    somewhere the writer doesn't control (a separate system, a signed
    channel, a human-witnessed note), and later call
    `verify(expected_head=that_value)` — it fails if the tail has moved
    backward or the count has shrunk.
  - A determined actor with direct database access *and* knowledge of this
    scheme: since there is no secret key or signature involved (this is a
    plain SHA-256 content chain, not an HMAC or a signed log), such an
    actor could delete rows and recompute a new, internally self-consistent
    chain from that point forward. This module gives tamper-EVIDENCE against
    accidental or unsophisticated tampering, not a cryptographic guarantee
    against a motivated insider with DB access. A signed/HMAC'd head
    checkpoint (published or witnessed outside the writer's control) is the
    natural next step if that threat model matters.
"""

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

    def verify(self, expected_head: tuple[int, str] | None = None) -> bool:
        prev = GENESIS
        count = 0
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
            count += 1
        # A chain-walk alone can't see a truncated tail (the surviving
        # prefix is still internally consistent) — see module docstring.
        # A caller that pinned `head()` beforehand can pass it here to
        # additionally catch the tail having moved backward.
        if expected_head is not None and (count, prev) != expected_head:
            return False
        return True

    def head(self) -> tuple[int, str]:
        """Return (row_count, last_entry_hash), or (0, GENESIS) when empty.

        Callers wanting to detect tail-truncation should persist this
        value somewhere outside the writer's control and later pass it as
        `verify(expected_head=...)`.
        """
        row = self._conn.execute("SELECT COUNT(*) AS c FROM audit_log").fetchone()
        count = row["c"] if row else 0
        return (count, self._last_hash())

    def _last_hash(self) -> str:
        row = self._conn.execute("SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
        return row["entry_hash"] if row else GENESIS

    def _row_to_entry(self, r: sqlite3.Row) -> AuditEntry:
        return AuditEntry(
            id=r["id"], ts=r["ts"], actor=Actor(kind=r["actor_kind"], id=r["actor_id"]),
            action=r["action"], target_type=r["target_type"], target_id=r["target_id"],
            outcome=r["outcome"], details=json.loads(r["details"]),
            prev_hash=r["prev_hash"], entry_hash=r["entry_hash"])
