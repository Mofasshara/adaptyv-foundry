# Phase 2 — Governance Layer (audit + HITL approval) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the governance layer — a tamper-evident append-only audit log and a human-in-the-loop draft-approval state machine — so customer-update drafts can only be approved by a human, critical anomalies hard-block approval until acknowledged, and every consequential action is recorded and verifiable.

**Architecture:** A self-contained `adaptyv/governance/` package on stdlib `sqlite3` (no new deps). `AuditLog` is an append-only, hash-chained record store with a `verify()` integrity check. `ApprovalStore` is a draft state machine (`PENDING_REVIEW → APPROVED | REJECTED → SENT`) that writes every transition to the audit log, refuses agent self-approval, and blocks approval while a critical anomaly is unacknowledged. Both share one `sqlite3.Connection`. Governance is decoupled from Phase 1: it references experiments/results only by id string and defines its own domain models. The agent (Phase 3) will create drafts through this store; the CLI exposes review + audit for humans.

**Tech Stack:** Python 3.11+, stdlib `sqlite3`, `hashlib`, `json`, `uuid`; pydantic v2 (domain models); Typer (CLI); pytest.

## Global Constraints

- Python **3.11+**, sync only, pydantic v2. Work inside the repo-local venv (`. .venv/bin/activate`); use `python3 -m pytest`.
- **No new runtime dependencies** — governance uses only the standard library (+ existing pydantic/typer).
- Governance domain models subclass a strict base (`extra="forbid"`).
- The audit log is **append-only via its API** — expose no update/delete methods.
- **The agent can never approve/reject/acknowledge** — those require an `Actor` with `kind == "human"`; otherwise raise `SelfApprovalError`.
- New exceptions extend the existing `adaptyv.errors.AdaptyvError` hierarchy.
- TDD: failing test first (fails for the real reason, deps already installed), then minimal code, green, commit.
- Commit messages exactly as written below; **NO `Co-Authored-By`/`Generated with` trailer**. Commit only each task's own files with explicit `git add <paths>` (never `-A`/`-am`); do **not** touch `ROADMAP.md`/docs in task commits.
- End every task with `python3 -m pytest -q` fully green (all prior + new), output pristine.

## Scope note (core vs stretch)

Tasks 1–5 are **core**. Task 6 (feedback store / flywheel source) is **stretch** — build only if time remains. The hash-chain + `verify()` live in the core audit task (Task 2), not the stretch tier: the chain is a few lines and an unverifiable chain has no demo value (logged as a ROADMAP change-log deviation).

---

### Task 1: Governance domain models, errors, db helper

**Files:**
- Create: `adaptyv/governance/__init__.py`
- Create: `adaptyv/governance/db.py`
- Create: `adaptyv/governance/models.py`
- Modify: `adaptyv/errors.py` (add governance exceptions)
- Test: `tests/test_governance_models.py`

**Interfaces:**
- Produces (from `adaptyv.governance.models`): `ActorKind`, `Actor`, `AnomalySeverity`, `AnomalyFinding`, `DraftStatus`, `Draft`, `AuditEntry`, and `has_unacknowledged_critical(draft) -> bool`.
- `adaptyv.governance.db.connect(db_path: str = ":memory:") -> sqlite3.Connection` (row_factory = `sqlite3.Row`).
- Adds to `adaptyv.errors`: `GovernanceError(AdaptyvError)`, `SelfApprovalError`, `AnomalyNotAcknowledgedError`, `InvalidTransitionError`, `DraftNotFoundError` (all subclasses of `GovernanceError`).

- [ ] **Step 1: Write the failing test** — `tests/test_governance_models.py`:
```python
from adaptyv.governance.models import (
    Actor, ActorKind, AnomalyFinding, AnomalySeverity, Draft, DraftStatus,
    has_unacknowledged_critical,
)
from adaptyv.governance.db import connect
from adaptyv.errors import AdaptyvError, GovernanceError, SelfApprovalError


def test_actor_and_enums():
    a = Actor(kind="human", id="alice")
    assert a.kind is ActorKind.HUMAN
    assert DraftStatus.PENDING_REVIEW.value == "pending_review"
    assert AnomalySeverity.CRITICAL.value == "critical"


def test_unacknowledged_critical_helper():
    crit = AnomalyFinding(rule="all_failed", severity="critical", evidence="0/3 expressed")
    warn = AnomalyFinding(rule="kd_bounds", severity="warning", evidence="Kd high")
    d = Draft(draft_id="d1", experiment_id="e1", status="pending_review", body="hi",
              anomalies=[crit], created_by=Actor(kind="agent", id="watcher"),
              created_at="2026-07-24T10:00:00Z")
    assert has_unacknowledged_critical(d) is True
    d.anomalies_acknowledged = True
    assert has_unacknowledged_critical(d) is False
    d2 = d.model_copy(update={"anomalies": [warn], "anomalies_acknowledged": False})
    assert has_unacknowledged_critical(d2) is False


def test_governance_errors_are_adaptyv_errors():
    assert issubclass(GovernanceError, AdaptyvError)
    assert issubclass(SelfApprovalError, GovernanceError)


def test_connect_returns_row_factory_conn():
    conn = connect()
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    row = conn.execute("SELECT x FROM t").fetchone()
    assert row["x"] == 1
```

- [ ] **Step 2: Run** `python3 -m pytest tests/test_governance_models.py -q` → FAIL (`ModuleNotFoundError: adaptyv.governance`).

- [ ] **Step 3: Add governance exceptions** to `adaptyv/errors.py` (append after `TransportError`):
```python
class GovernanceError(AdaptyvError): ...
class SelfApprovalError(GovernanceError): ...
class AnomalyNotAcknowledgedError(GovernanceError): ...
class InvalidTransitionError(GovernanceError): ...
class DraftNotFoundError(GovernanceError): ...
```

- [ ] **Step 4: Create the package + db helper.**
  `adaptyv/governance/__init__.py`: (empty file)
  `adaptyv/governance/db.py`:
```python
from __future__ import annotations

import sqlite3


def connect(db_path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn
```

- [ ] **Step 5: Create the domain models** — `adaptyv/governance/models.py`:
```python
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _G(BaseModel):
    """Strict base for governance domain models."""
    model_config = ConfigDict(extra="forbid")


class ActorKind(str, Enum):
    HUMAN = "human"
    AGENT = "agent"


class Actor(_G):
    kind: ActorKind
    id: str


class AnomalySeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"


class AnomalyFinding(_G):
    rule: str
    severity: AnomalySeverity
    evidence: str
    affected_ids: list[str] = Field(default_factory=list)
    policy_version: str = "v0"


class DraftStatus(str, Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"


class Draft(_G):
    draft_id: str
    experiment_id: str
    status: DraftStatus
    body: str
    result_id: str | None = None
    anomalies: list[AnomalyFinding] = Field(default_factory=list)
    created_by: Actor
    created_at: datetime
    reviewed_by: Actor | None = None
    review_note: str | None = None
    anomalies_acknowledged: bool = False
    acknowledged_by: Actor | None = None


class AuditEntry(_G):
    id: int
    ts: datetime
    actor: Actor
    action: str
    target_type: str
    target_id: str
    outcome: str
    details: dict[str, Any] = Field(default_factory=dict)
    prev_hash: str
    entry_hash: str


def has_unacknowledged_critical(draft: Draft) -> bool:
    if draft.anomalies_acknowledged:
        return False
    return any(a.severity is AnomalySeverity.CRITICAL for a in draft.anomalies)
```

- [ ] **Step 6: Run** `python3 -m pytest tests/test_governance_models.py -q` → PASS.
- [ ] **Step 7: Commit**
```bash
git add adaptyv/governance/__init__.py adaptyv/governance/db.py adaptyv/governance/models.py adaptyv/errors.py tests/test_governance_models.py
git commit -m "feat: governance domain models, errors, sqlite connect helper"
```

---

### Task 2: Append-only, hash-chained audit log + verify()

**Files:**
- Create: `adaptyv/governance/audit.py`
- Test: `tests/test_audit_log.py`

**Interfaces:**
- Consumes: `db.connect`, `models.{Actor, AuditEntry}` (Task 1).
- Produces: `adaptyv.governance.audit.AuditLog(conn)` with
  `record(actor, action, target_type, target_id, outcome, details=None) -> AuditEntry`,
  `entries() -> list[AuditEntry]`, `verify() -> bool`, and module constant `GENESIS`.
  No update/delete methods (append-only API).

- [ ] **Step 1: Write the failing test** — `tests/test_audit_log.py`:
```python
from adaptyv.governance.audit import AuditLog, GENESIS
from adaptyv.governance.db import connect
from adaptyv.governance.models import Actor


def _log():
    return AuditLog(connect())


def test_record_links_hash_chain():
    log = _log()
    a = Actor(kind="agent", id="watcher")
    e1 = log.record(a, "draft.create", "draft", "d1", "pending_review")
    e2 = log.record(Actor(kind="human", id="alice"), "draft.approve", "draft", "d1", "approved")
    assert e1.prev_hash == GENESIS
    assert e2.prev_hash == e1.entry_hash          # chain links
    assert e1.entry_hash != e2.entry_hash


def test_entries_ordered_and_typed():
    log = _log()
    log.record(Actor(kind="agent", id="w"), "a", "draft", "d1", "ok", {"n": 1})
    entries = log.entries()
    assert [e.id for e in entries] == [1]
    assert entries[0].details == {"n": 1}
    assert entries[0].actor.id == "w"


def test_verify_true_for_intact_chain():
    log = _log()
    for i in range(3):
        log.record(Actor(kind="agent", id="w"), f"a{i}", "draft", "d1", "ok")
    assert log.verify() is True


def test_verify_false_after_tamper():
    conn = connect()
    log = AuditLog(conn)
    log.record(Actor(kind="agent", id="w"), "a0", "draft", "d1", "ok")
    log.record(Actor(kind="agent", id="w"), "a1", "draft", "d1", "ok")
    conn.execute("UPDATE audit_log SET outcome='TAMPERED' WHERE id=1")
    conn.commit()
    assert log.verify() is False
```

- [ ] **Step 2: Run** → FAIL (`ModuleNotFoundError: adaptyv.governance.audit`).

- [ ] **Step 3: Implement** — `adaptyv/governance/audit.py`:
```python
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
```

- [ ] **Step 4: Run** → PASS (4 passed). **Step 5: Commit**
```bash
git add adaptyv/governance/audit.py tests/test_audit_log.py
git commit -m "feat: append-only hash-chained audit log with verify()"
```

---

### Task 3: Approval state machine (ApprovalStore)

**Files:**
- Create: `adaptyv/governance/approval.py`
- Test: `tests/test_approval_store.py`

**Interfaces:**
- Consumes: `AuditLog` (Task 2), models + errors (Task 1).
- Produces: `adaptyv.governance.approval.ApprovalStore(conn, audit)` with:
  - `create_draft(experiment_id, body, *, result_id=None, anomalies=None, created_by) -> Draft` (status `PENDING_REVIEW`; audits `draft.create`)
  - `get(draft_id) -> Draft` (raises `DraftNotFoundError`)
  - `list(status=None) -> list[Draft]`
  - `approve(draft_id, reviewer) -> Draft` (human-only else `SelfApprovalError`; `PENDING_REVIEW`-only else `InvalidTransitionError`; audits `draft.approve`)
  - `reject(draft_id, reviewer, note) -> Draft` (human-only; `PENDING_REVIEW`-only; audits `draft.reject`)
  - `mark_sent(draft_id, actor) -> Draft` (`APPROVED`-only; audits `draft.send`)
  - Anomaly gate is added in Task 4.

- [ ] **Step 1: Write the failing test** — `tests/test_approval_store.py`:
```python
import pytest

from adaptyv.errors import DraftNotFoundError, InvalidTransitionError, SelfApprovalError
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.audit import AuditLog
from adaptyv.governance.db import connect
from adaptyv.governance.models import Actor, DraftStatus

AGENT = Actor(kind="agent", id="watcher")
HUMAN = Actor(kind="human", id="alice")


def _store():
    conn = connect()
    return ApprovalStore(conn, AuditLog(conn))


def test_create_draft_is_pending_and_audited():
    s = _store()
    d = s.create_draft("EXP-1", "Your results are ready.", created_by=AGENT)
    assert d.status is DraftStatus.PENDING_REVIEW
    assert d.created_by.id == "watcher"
    assert s._audit.entries()[-1].action == "draft.create"


def test_agent_cannot_approve():
    s = _store()
    d = s.create_draft("EXP-1", "body", created_by=AGENT)
    with pytest.raises(SelfApprovalError):
        s.approve(d.draft_id, AGENT)


def test_human_approve_moves_to_approved_and_audits():
    s = _store()
    d = s.create_draft("EXP-1", "body", created_by=AGENT)
    out = s.approve(d.draft_id, HUMAN)
    assert out.status is DraftStatus.APPROVED and out.reviewed_by.id == "alice"
    assert s._audit.entries()[-1].action == "draft.approve"


def test_reject_records_note():
    s = _store()
    d = s.create_draft("EXP-1", "body", created_by=AGENT)
    out = s.reject(d.draft_id, HUMAN, note="tone off")
    assert out.status is DraftStatus.REJECTED and out.review_note == "tone off"


def test_cannot_approve_already_approved():
    s = _store()
    d = s.create_draft("EXP-1", "body", created_by=AGENT)
    s.approve(d.draft_id, HUMAN)
    with pytest.raises(InvalidTransitionError):
        s.approve(d.draft_id, HUMAN)


def test_mark_sent_requires_approved():
    s = _store()
    d = s.create_draft("EXP-1", "body", created_by=AGENT)
    with pytest.raises(InvalidTransitionError):
        s.mark_sent(d.draft_id, HUMAN)
    s.approve(d.draft_id, HUMAN)
    assert s.mark_sent(d.draft_id, HUMAN).status is DraftStatus.SENT


def test_get_unknown_raises():
    s = _store()
    with pytest.raises(DraftNotFoundError):
        s.get("nope")
```

- [ ] **Step 2: Run** → FAIL (`ModuleNotFoundError: adaptyv.governance.approval`).

- [ ] **Step 3: Implement** — `adaptyv/governance/approval.py`:
```python
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from adaptyv.errors import (DraftNotFoundError, InvalidTransitionError, SelfApprovalError)
from adaptyv.governance.audit import AuditLog
from adaptyv.governance.models import (Actor, ActorKind, AnomalyFinding, Draft, DraftStatus)


class ApprovalStore:
    def __init__(self, conn: sqlite3.Connection, audit: AuditLog) -> None:
        self._conn = conn
        self._audit = audit
        conn.execute(
            """CREATE TABLE IF NOT EXISTS drafts (
                draft_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL, result_id TEXT,
                status TEXT NOT NULL, body TEXT NOT NULL, anomalies TEXT NOT NULL,
                created_by TEXT NOT NULL, created_at TEXT NOT NULL,
                reviewed_by TEXT, review_note TEXT,
                anomalies_acknowledged INTEGER NOT NULL DEFAULT 0, acknowledged_by TEXT)"""
        )
        conn.commit()

    def create_draft(self, experiment_id: str, body: str, *, result_id: str | None = None,
                     anomalies: list[AnomalyFinding] | None = None, created_by: Actor) -> Draft:
        anomalies = anomalies or []
        draft_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO drafts
               (draft_id,experiment_id,result_id,status,body,anomalies,created_by,created_at,anomalies_acknowledged)
               VALUES (?,?,?,?,?,?,?,?,0)""",
            (draft_id, experiment_id, result_id, DraftStatus.PENDING_REVIEW.value, body,
             json.dumps([a.model_dump(mode="json") for a in anomalies]),
             json.dumps(created_by.model_dump(mode="json")), created_at),
        )
        self._conn.commit()
        self._audit.record(created_by, "draft.create", "draft", draft_id, "pending_review",
                           {"experiment_id": experiment_id, "result_id": result_id,
                            "anomaly_count": len(anomalies)})
        return self.get(draft_id)

    def get(self, draft_id: str) -> Draft:
        r = self._conn.execute("SELECT * FROM drafts WHERE draft_id=?", (draft_id,)).fetchone()
        if r is None:
            raise DraftNotFoundError(f"draft {draft_id} not found")
        return self._row_to_draft(r)

    def list(self, status: DraftStatus | None = None) -> list[Draft]:
        if status is None:
            rows = self._conn.execute("SELECT * FROM drafts ORDER BY created_at").fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM drafts WHERE status=? ORDER BY created_at",
                                      (status.value,)).fetchall()
        return [self._row_to_draft(r) for r in rows]

    def approve(self, draft_id: str, reviewer: Actor) -> Draft:
        draft = self.get(draft_id)
        self._require_human(reviewer)
        self._require_status(draft, DraftStatus.PENDING_REVIEW)
        self._set_review(draft_id, DraftStatus.APPROVED, reviewer, None)
        self._audit.record(reviewer, "draft.approve", "draft", draft_id, "approved")
        return self.get(draft_id)

    def reject(self, draft_id: str, reviewer: Actor, note: str) -> Draft:
        draft = self.get(draft_id)
        self._require_human(reviewer)
        self._require_status(draft, DraftStatus.PENDING_REVIEW)
        self._set_review(draft_id, DraftStatus.REJECTED, reviewer, note)
        self._audit.record(reviewer, "draft.reject", "draft", draft_id, "rejected", {"note": note})
        return self.get(draft_id)

    def mark_sent(self, draft_id: str, actor: Actor) -> Draft:
        draft = self.get(draft_id)
        self._require_status(draft, DraftStatus.APPROVED)
        self._conn.execute("UPDATE drafts SET status=? WHERE draft_id=?",
                           (DraftStatus.SENT.value, draft_id))
        self._conn.commit()
        self._audit.record(actor, "draft.send", "draft", draft_id, "sent")
        return self.get(draft_id)

    # -- helpers --
    def _require_human(self, actor: Actor) -> None:
        if actor.kind is not ActorKind.HUMAN:
            raise SelfApprovalError("only a human reviewer may approve/reject/acknowledge a draft")

    def _require_status(self, draft: Draft, expected: DraftStatus) -> None:
        if draft.status is not expected:
            raise InvalidTransitionError(f"draft {draft.draft_id} is {draft.status.value}, expected {expected.value}")

    def _set_review(self, draft_id: str, status: DraftStatus, reviewer: Actor, note: str | None) -> None:
        self._conn.execute(
            "UPDATE drafts SET status=?, reviewed_by=?, review_note=? WHERE draft_id=?",
            (status.value, json.dumps(reviewer.model_dump(mode="json")), note, draft_id))
        self._conn.commit()

    def _row_to_draft(self, r: sqlite3.Row) -> Draft:
        return Draft(
            draft_id=r["draft_id"], experiment_id=r["experiment_id"], result_id=r["result_id"],
            status=r["status"], body=r["body"],
            anomalies=[AnomalyFinding.model_validate(a) for a in json.loads(r["anomalies"])],
            created_by=Actor.model_validate(json.loads(r["created_by"])), created_at=r["created_at"],
            reviewed_by=Actor.model_validate(json.loads(r["reviewed_by"])) if r["reviewed_by"] else None,
            review_note=r["review_note"],
            anomalies_acknowledged=bool(r["anomalies_acknowledged"]),
            acknowledged_by=Actor.model_validate(json.loads(r["acknowledged_by"])) if r["acknowledged_by"] else None)
```

- [ ] **Step 4: Run** → PASS. **Step 5: Commit**
```bash
git add adaptyv/governance/approval.py tests/test_approval_store.py
git commit -m "feat: approval state machine (create/approve/reject/send, no agent self-approval)"
```

---

### Task 4: Critical-anomaly hard-block + acknowledgement

**Files:**
- Modify: `adaptyv/governance/approval.py` (extend `approve`; add `acknowledge_anomaly`)
- Test: `tests/test_anomaly_gate.py`

**Interfaces:**
- Adds `ApprovalStore.acknowledge_anomaly(draft_id, reviewer) -> Draft` (human-only; audits `anomaly.acknowledge`).
- `approve()` now raises `AnomalyNotAcknowledgedError` when the draft has an unacknowledged critical anomaly.

- [ ] **Step 1: Write the failing test** — `tests/test_anomaly_gate.py`:
```python
import pytest

from adaptyv.errors import AnomalyNotAcknowledgedError, SelfApprovalError
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.audit import AuditLog
from adaptyv.governance.db import connect
from adaptyv.governance.models import Actor, AnomalyFinding, DraftStatus

AGENT = Actor(kind="agent", id="watcher")
HUMAN = Actor(kind="human", id="alice")
CRIT = AnomalyFinding(rule="all_failed", severity="critical", evidence="0/3 expressed")
WARN = AnomalyFinding(rule="kd_bounds", severity="warning", evidence="Kd high")


def _store():
    conn = connect()
    return ApprovalStore(conn, AuditLog(conn))


def test_critical_anomaly_blocks_approval():
    s = _store()
    d = s.create_draft("EXP-1", "body", anomalies=[CRIT], created_by=AGENT)
    with pytest.raises(AnomalyNotAcknowledgedError):
        s.approve(d.draft_id, HUMAN)


def test_acknowledge_then_approve_succeeds_and_audits():
    s = _store()
    d = s.create_draft("EXP-1", "body", anomalies=[CRIT], created_by=AGENT)
    ack = s.acknowledge_anomaly(d.draft_id, HUMAN)
    assert ack.anomalies_acknowledged is True and ack.acknowledged_by.id == "alice"
    out = s.approve(d.draft_id, HUMAN)
    assert out.status is DraftStatus.APPROVED
    actions = [e.action for e in s._audit.entries()]
    assert "anomaly.acknowledge" in actions and actions[-1] == "draft.approve"


def test_warning_only_does_not_block():
    s = _store()
    d = s.create_draft("EXP-1", "body", anomalies=[WARN], created_by=AGENT)
    assert s.approve(d.draft_id, HUMAN).status is DraftStatus.APPROVED


def test_agent_cannot_acknowledge():
    s = _store()
    d = s.create_draft("EXP-1", "body", anomalies=[CRIT], created_by=AGENT)
    with pytest.raises(SelfApprovalError):
        s.acknowledge_anomaly(d.draft_id, AGENT)
```

- [ ] **Step 2: Run** → FAIL (`AttributeError: 'ApprovalStore' object has no attribute 'acknowledge_anomaly'` and the critical-block test fails because approve currently succeeds).

- [ ] **Step 3: Implement.** In `approve()`, after `self._require_status(...)` and before `self._set_review(...)`, insert the gate:
```python
        from adaptyv.errors import AnomalyNotAcknowledgedError
        from adaptyv.governance.models import has_unacknowledged_critical
        if has_unacknowledged_critical(draft):
            raise AnomalyNotAcknowledgedError(
                f"draft {draft_id} has an unacknowledged critical anomaly; acknowledge before approving")
```
  Add the method:
```python
    def acknowledge_anomaly(self, draft_id: str, reviewer: Actor) -> Draft:
        self.get(draft_id)  # raises DraftNotFoundError if missing
        self._require_human(reviewer)
        self._conn.execute(
            "UPDATE drafts SET anomalies_acknowledged=1, acknowledged_by=? WHERE draft_id=?",
            (json.dumps(reviewer.model_dump(mode="json")), draft_id))
        self._conn.commit()
        self._audit.record(reviewer, "anomaly.acknowledge", "draft", draft_id, "acknowledged")
        return self.get(draft_id)
```
  (Prefer moving the two `from` imports to the top of the file with the others.)

- [ ] **Step 4: Run** `python3 -m pytest -q` → PASS (all prior + new). **Step 5: Commit**
```bash
git add adaptyv/governance/approval.py tests/test_anomaly_gate.py
git commit -m "feat: critical-anomaly hard-block on approval + human acknowledgement"
```

---

### Task 5: CLI — `adaptyv review` and `adaptyv audit`

**Files:**
- Modify: `adaptyv/cli.py` (add `review` and `audit` sub-apps + a small governance-store opener)
- Test: `tests/test_cli_governance.py`

**Interfaces:**
- `adaptyv review list [--db PATH]` — list drafts (id, status, experiment, critical-anomaly flag).
- `adaptyv review show <draft_id> [--db PATH]` — print body + anomalies.
- `adaptyv review approve <draft_id> --by NAME [--db PATH]`, `reject <draft_id> --by NAME --note TEXT`, `ack <draft_id> --by NAME`.
- `adaptyv audit list [--db PATH]`, `adaptyv audit verify [--db PATH]`.
- Governance-backed by a sqlite file (`--db`, default `adaptyv_governance.db`). Human actions build `Actor(kind="human", id=NAME)`. Governance errors are caught and printed as a clean message with a non-zero exit code (`typer.Exit(1)`), not a traceback.

- [ ] **Step 1: Write the failing test** — `tests/test_cli_governance.py`:
```python
from pathlib import Path

from typer.testing import CliRunner

from adaptyv.cli import app
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.audit import AuditLog
from adaptyv.governance.db import connect
from adaptyv.governance.models import Actor, AnomalyFinding

runner = CliRunner()
CRIT = AnomalyFinding(rule="all_failed", severity="critical", evidence="0/3 expressed")


def _seed(db: str) -> str:
    conn = connect(db)
    store = ApprovalStore(conn, AuditLog(conn))
    d = store.create_draft("EXP-1", "Your results are ready.", anomalies=[CRIT],
                           created_by=Actor(kind="agent", id="watcher"))
    conn.close()
    return d.draft_id


def test_review_list_and_blocked_then_ack_then_approve(tmp_path):
    db = str(tmp_path / "gov.db")
    did = _seed(db)

    r = runner.invoke(app, ["review", "list", "--db", db])
    assert r.exit_code == 0 and did[:8] in r.stdout and "pending_review" in r.stdout

    # approval blocked by critical anomaly
    r = runner.invoke(app, ["review", "approve", did, "--by", "alice", "--db", db])
    assert r.exit_code == 1 and "anomaly" in r.stdout.lower()

    # acknowledge, then approve succeeds
    assert runner.invoke(app, ["review", "ack", did, "--by", "alice", "--db", db]).exit_code == 0
    r = runner.invoke(app, ["review", "approve", did, "--by", "alice", "--db", db])
    assert r.exit_code == 0 and "approved" in r.stdout.lower()


def test_audit_list_and_verify(tmp_path):
    db = str(tmp_path / "gov.db")
    _seed(db)
    r = runner.invoke(app, ["audit", "list", "--db", db])
    assert r.exit_code == 0 and "draft.create" in r.stdout
    r = runner.invoke(app, ["audit", "verify", "--db", db])
    assert r.exit_code == 0 and "ok" in r.stdout.lower()
```

- [ ] **Step 2: Run** → FAIL (no `review`/`audit` commands).

- [ ] **Step 3: Implement** — add to `adaptyv/cli.py`:
```python
from adaptyv.errors import GovernanceError
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.audit import AuditLog
from adaptyv.governance.db import connect
from adaptyv.governance.models import Actor, has_unacknowledged_critical

review = typer.Typer(help="Human review of customer-update drafts")
audit = typer.Typer(help="Audit trail")
app.add_typer(review, name="review")
app.add_typer(audit, name="audit")


def _store(db: str):
    conn = connect(db)
    return ApprovalStore(conn, AuditLog(conn))


def _human(name: str) -> Actor:
    return Actor(kind="human", id=name)


@review.command("list")
def review_list(db: str = typer.Option("adaptyv_governance.db")):
    for d in _store(db).list():
        flag = "  ⚠CRITICAL" if has_unacknowledged_critical(d) else ""
        typer.echo(f"{d.draft_id[:8]}  {d.status.value:14} {d.experiment_id}{flag}")


@review.command("show")
def review_show(draft_id: str, db: str = typer.Option("adaptyv_governance.db")):
    _run(lambda: _show(_store(db), draft_id))


def _show(store, draft_id):
    d = store.get(draft_id)
    typer.echo(f"[{d.status.value}] {d.experiment_id}\n\n{d.body}\n")
    for a in d.anomalies:
        typer.echo(f"  - {a.severity.value.upper()}: {a.rule} — {a.evidence}")


@review.command("approve")
def review_approve(draft_id: str, by: str = typer.Option(...), db: str = typer.Option("adaptyv_governance.db")):
    _run(lambda: typer.echo(f"approved: {_store(db).approve(draft_id, _human(by)).draft_id}"))


@review.command("reject")
def review_reject(draft_id: str, by: str = typer.Option(...), note: str = typer.Option(""),
                  db: str = typer.Option("adaptyv_governance.db")):
    _run(lambda: typer.echo(f"rejected: {_store(db).reject(draft_id, _human(by), note).draft_id}"))


@review.command("ack")
def review_ack(draft_id: str, by: str = typer.Option(...), db: str = typer.Option("adaptyv_governance.db")):
    _run(lambda: typer.echo(f"acknowledged: {_store(db).acknowledge_anomaly(draft_id, _human(by)).draft_id}"))


@audit.command("list")
def audit_list(db: str = typer.Option("adaptyv_governance.db")):
    conn = connect(db)
    for e in AuditLog(conn).entries():
        typer.echo(f"{e.id:3}  {e.ts}  {e.actor.kind.value}:{e.actor.id}  {e.action}  {e.target_id}")


@audit.command("verify")
def audit_verify(db: str = typer.Option("adaptyv_governance.db")):
    ok = AuditLog(connect(db)).verify()
    typer.echo("OK — chain intact" if ok else "FAILED — chain tampered")
    raise typer.Exit(0 if ok else 1)


def _run(fn):
    try:
        fn()
    except GovernanceError as exc:
        typer.echo(f"error: {exc.message}")
        raise typer.Exit(1)
```

- [ ] **Step 4: Run** `python3 -m pytest -q` → PASS. Then smoke it:
  `python3 -c "import subprocess"` not needed; instead: run `adaptyv review list --db /tmp/gov.db` (expected: empty, exit 0). Include output in the report.

- [ ] **Step 5: Commit**
```bash
git add adaptyv/cli.py tests/test_cli_governance.py
git commit -m "feat: adaptyv review + audit CLI commands over the governance store"
```

---

### Task 6 (STRETCH): Feedback store (flywheel data source)

**Files:**
- Create: `adaptyv/governance/feedback.py`
- Modify: `adaptyv/governance/approval.py` (accept an optional corrected body on `reject`)
- Test: `tests/test_feedback_store.py`

**Interfaces:**
- `adaptyv.governance.feedback.FeedbackStore(conn)` with
  `record_correction(draft_id, corrected_body, corrected_by) -> None` and
  `corrections() -> list[dict]` (draft_id, corrected_body, corrected_by, ts).
- The corrected body is the *content* the flywheel (Phase 5) promotes into the eval golden set; the audit log only references it.

- [ ] **Step 1: Write the failing test** — `tests/test_feedback_store.py`:
```python
from adaptyv.governance.db import connect
from adaptyv.governance.feedback import FeedbackStore
from adaptyv.governance.models import Actor


def test_record_and_read_corrections():
    fs = FeedbackStore(connect())
    fs.record_correction("d1", "Better wording here.", Actor(kind="human", id="alice"))
    rows = fs.corrections()
    assert len(rows) == 1
    assert rows[0]["draft_id"] == "d1"
    assert rows[0]["corrected_body"] == "Better wording here."
    assert rows[0]["corrected_by"] == "alice"
```

- [ ] **Step 2: Run** → FAIL (`ModuleNotFoundError: adaptyv.governance.feedback`).

- [ ] **Step 3: Implement** — `adaptyv/governance/feedback.py`:
```python
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
```

- [ ] **Step 4: Run** `python3 -m pytest -q` → PASS. **Step 5: Commit**
```bash
git add adaptyv/governance/feedback.py tests/test_feedback_store.py
git commit -m "feat: feedback store for human corrections (flywheel source)"
```

---

## Phase 2 Definition of Done

- `python3 -m pytest -q` fully green (Phase 1 + governance tests).
- `AuditLog.verify()` returns True for an intact chain and False after any row is tampered.
- A draft created by an agent can only be approved by a human (`SelfApprovalError` otherwise), and a critical anomaly hard-blocks approval until `acknowledge_anomaly` (by a human) is called.
- `adaptyv review list/show/approve/reject/ack` and `adaptyv audit list/verify` work against a sqlite governance DB.
- No new runtime dependencies; governance is stdlib-only.

**Next (Phase 3, written just-in-time):** the ExperimentWatcher agent — versioned anomaly policy + deterministic `AnomalyDetector`, then the `EmailDrafter` (Claude, placeholder-substitution), then the `Watcher` that turns completed results into `PENDING_REVIEW` drafts through this `ApprovalStore` with a durable idempotency key.
