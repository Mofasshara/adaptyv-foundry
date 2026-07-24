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
