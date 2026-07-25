from __future__ import annotations

from adaptyv.agents.email import EmailDraftSchema


class StubEmailDrafter:
    """Zero-credential drafter: no Claude call. Shared by the bridge's default
    draft_customer_update path and the `adaptyv watch` CLI command."""
    model = "stub-drafter"

    def draft(self, result, findings) -> EmailDraftSchema:
        lines = [f"Results are in for {result.title}."]
        for f in findings:
            lines.append(f"[{f.severity.value.upper()}] {f.rule}: {f.evidence}")
        if not findings:
            lines.append("No anomalies detected.")
        return EmailDraftSchema(subject=f"Update: {result.title}", body="\n".join(lines))
