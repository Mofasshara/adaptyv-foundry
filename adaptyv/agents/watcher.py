from __future__ import annotations

import sqlite3

from adaptyv.agents.anomaly import AnomalyDetector
from adaptyv.agents.email import EmailDrafter
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.models import Actor, Draft


class Watcher:
    def __init__(self, client, detector: AnomalyDetector, drafter: EmailDrafter,
                approval_store: ApprovalStore, conn: sqlite3.Connection) -> None:
        if not approval_store.shares_connection_with(conn):
            raise ValueError(
                "Watcher's conn must be the exact same connection object as approval_store's "
                "-- the atomic before_commit hook can only be atomic if both write through one connection")
        self._client = client
        self._detector = detector
        self._drafter = drafter
        self._store = approval_store
        self._conn = conn
        self.errors: list[tuple[str, str, Exception]] = []
        conn.execute(
            "CREATE TABLE IF NOT EXISTS watcher_processed (key TEXT PRIMARY KEY, draft_id TEXT NOT NULL)"
        )
        conn.commit()

    def run(self, experiment_ids: list[str] | None = None) -> list[Draft]:
        if experiment_ids is None:
            experiment_ids = [e.id for e in self._client.experiments.list()]
        created: list[Draft] = []
        for experiment_id in experiment_ids:
            for result in self._client.experiments.results(experiment_id):
                key = f"{experiment_id}:{result.id}:{self._drafter.model}"
                if self._already_processed(key):
                    continue
                try:
                    findings = self._detector.detect(result)
                    email = self._drafter.draft(result, findings)
                    body = f"Subject: {email.subject}\n\n{email.body}"
                    draft = self._store.create_draft(
                        experiment_id, body, result_id=result.id, anomalies=findings,
                        created_by=Actor(kind="agent", id="watcher"),
                        before_commit=lambda draft_id, key=key: self._conn.execute(
                            "INSERT INTO watcher_processed (key, draft_id) VALUES (?, ?)",
                            (key, draft_id)))
                except Exception as exc:  # noqa: BLE001 - isolate one bad result, keep the batch alive
                    self.errors.append((experiment_id, result.id, exc))
                    continue
                created.append(draft)
        return created

    def _already_processed(self, key: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM watcher_processed WHERE key=?", (key,)).fetchone()
        return row is not None
