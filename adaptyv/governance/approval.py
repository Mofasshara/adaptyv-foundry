from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from adaptyv.errors import (AnomalyNotAcknowledgedError, DraftNotFoundError, InvalidTransitionError, SelfApprovalError)
from adaptyv.governance.audit import AuditLog
from adaptyv.governance.models import (Actor, ActorKind, AnomalyFinding, Draft, DraftStatus, has_unacknowledged_critical)


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
        if has_unacknowledged_critical(draft):
            raise AnomalyNotAcknowledgedError(
                f"draft {draft_id} has an unacknowledged critical anomaly; acknowledge before approving")
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

    def acknowledge_anomaly(self, draft_id: str, reviewer: Actor) -> Draft:
        self.get(draft_id)  # raises DraftNotFoundError if missing
        self._require_human(reviewer)
        self._conn.execute(
            "UPDATE drafts SET anomalies_acknowledged=1, acknowledged_by=? WHERE draft_id=?",
            (json.dumps(reviewer.model_dump(mode="json")), draft_id))
        self._conn.commit()
        self._audit.record(reviewer, "anomaly.acknowledge", "draft", draft_id, "acknowledged")
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
