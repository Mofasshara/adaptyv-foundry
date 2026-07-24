from __future__ import annotations

import re

from pydantic import BaseModel

from adaptyv.errors import UnresolvedPlaceholderError
from adaptyv.governance.models import AnomalyFinding
from adaptyv.models import AffinityResultSummary, ResultInfo

EMAIL_DRAFT_MODEL = "claude-opus-4-8"

# Fact-sheet keys are derived from sequence names (build_fact_sheet), which routinely
# contain hyphens (e.g. "binder-1") -- \w alone would silently fail to match those
# tokens, letting an un-substituted {{...}} slip through unresolved-placeholder
# detection entirely. Include '-' explicitly so every emitted token is checked.
_PLACEHOLDER = re.compile(r"\{\{([\w-]+)\}\}")


class EmailDraftSchema(BaseModel):
    subject: str
    body: str


def _slug(name: str) -> str:
    return name.strip()


def build_fact_sheet(result: ResultInfo) -> dict[str, str]:
    """Pure. One entry per non-null kd_mean — the only numbers the drafter may cite.

    Labels are derived from sequence name (or an aa_string prefix), which can
    collide across summary entries. On collision the first occurrence keeps
    the bare key; subsequent collisions are disambiguated with a numeric
    suffix (_2, _3, ...) so every measured kd_mean still gets a unique,
    correctly-attributed fact_id instead of silently overwriting an earlier one.
    """
    facts: dict[str, str] = {}
    for s in result.summary:
        if isinstance(s, AffinityResultSummary) and s.kd_mean is not None:
            label = _slug(s.sequence.name or s.sequence.aa_string[:8])
            key = f"kd_mean_{label}"
            if key in facts:
                suffix = 2
                while f"{key}_{suffix}" in facts:
                    suffix += 1
                key = f"{key}_{suffix}"
            facts[key] = f"{s.kd_mean:.2e} {s.kd_units}"
    return facts


def substitute_facts(body: str, fact_sheet: dict[str, str]) -> str:
    def _replace(m: re.Match) -> str:
        fact_id = m.group(1)
        if fact_id not in fact_sheet:
            raise UnresolvedPlaceholderError(
                f"drafter emitted unknown placeholder '{{{{{fact_id}}}}}' — not in the fact sheet")
        return fact_sheet[fact_id]
    return _PLACEHOLDER.sub(_replace, body)


class EmailDrafter:
    def __init__(self, client, model: str = EMAIL_DRAFT_MODEL) -> None:
        self._client = client
        self.model = model  # public: Watcher reads this to build its idempotency key

    def draft(self, result: ResultInfo, findings: list[AnomalyFinding]) -> EmailDraftSchema:
        fact_sheet = build_fact_sheet(result)
        system = (
            "You draft professional, plain-English customer update emails for a protein "
            "validation lab. You may reference numeric results ONLY via the exact "
            "placeholder tokens listed below, written literally as {{token}} in your body "
            "text — never write a number yourself. Use the qualitative details (binding "
            "strength, performance, anomaly notes) directly as given."
        )
        fact_lines = "\n".join(f"- {{{{{fid}}}}}: a binding-affinity (Kd) value" for fid in fact_sheet)
        finding_lines = "\n".join(f"- [{f.severity.value}] {f.rule}: {f.evidence}" for f in findings)
        user = (
            f"Result title: {result.title}\n\n"
            f"Available numeric placeholders:\n{fact_lines or '(none)'}\n\n"
            f"Anomaly findings:\n{finding_lines or '(none)'}\n\n"
            "Write a short customer update email (subject + body) summarizing these results."
        )
        response = self._client.messages.parse(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": user}],
            system=system,
            output_format=EmailDraftSchema,
        )
        draft = response.parsed_output
        resolved_body = substitute_facts(draft.body, fact_sheet)
        return EmailDraftSchema(subject=draft.subject, body=resolved_body)
