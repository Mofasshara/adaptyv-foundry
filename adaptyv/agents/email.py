from __future__ import annotations

import re

from pydantic import BaseModel

from adaptyv.errors import UnresolvedPlaceholderError
from adaptyv.governance.models import AnomalyFinding
from adaptyv.models import AffinityResultSummary, ResultInfo

EMAIL_DRAFT_MODEL = "claude-opus-4-8"

_PLACEHOLDER = re.compile(r"\{\{([\w-]+)\}\}")
# Matches a standalone number, but not a digit glued onto an identifier
# (e.g. the "1" in "binder-1" or "seq1") -- the lookbehind requires the
# character immediately before a candidate match to be neither a word
# character nor a hyphen.
_NUMBER = re.compile(r"(?<![\w-])-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?%?")


class EmailDraftSchema(BaseModel):
    subject: str
    body: str


def build_fact_sheet(result: ResultInfo) -> dict[str, str]:
    """Pure. One opaque-ID entry per non-null kd_mean -- the only per-sequence
    measurements the drafter may cite. IDs are a plain counter (kd_1, kd_2,
    ...), not derived from sequence names: names can contain arbitrary
    characters or collide, and a placeholder token must always be a single,
    unambiguous, unique, substitution-safe identifier."""
    facts: dict[str, str] = {}
    i = 0
    for s in result.summary:
        if isinstance(s, AffinityResultSummary) and s.kd_mean is not None:
            i += 1
            facts[f"kd_{i}"] = f"{s.kd_mean:.2e} {s.kd_units}"
    return facts


def _templated_evidence(findings: list[AnomalyFinding], fact_sheet: dict[str, str]) -> list[str]:
    """Render each finding's evidence line with its own embedded numbers
    replaced by fresh opaque placeholders (added to fact_sheet as a side
    effect), so the drafter can copy anomaly evidence verbatim -- as
    instructed -- while every number it echoes still resolves through the
    exact same placeholder mechanism as a real Kd value. No numeric literal
    from evidence text ever reaches the model as a bare digit."""
    lines: list[str] = []
    for idx, f in enumerate(findings, start=1):
        counter = {"n": 0}

        def _replace(m: re.Match) -> str:
            counter["n"] += 1
            fact_id = f"ev_{idx}_{counter['n']}"
            fact_sheet[fact_id] = m.group(0)
            return f"{{{{{fact_id}}}}}"

        templated = _NUMBER.sub(_replace, f.evidence)
        lines.append(f"- [{f.severity.value}] {f.rule}: {templated}")
    return lines


def substitute_facts(body: str, fact_sheet: dict[str, str]) -> str:
    """Deny-by-default: a number may reach the output ONLY via a placeholder
    that resolves to a real fact. Any digit typed directly by the drafter
    (never wrapped in {{...}}) is rejected outright, and any leftover brace
    character after substitution (malformed, unclosed, or empty placeholder
    syntax) is rejected too -- there is no code path by which a raw or
    unverified number can survive into a persisted draft.
    """
    without_placeholders = _PLACEHOLDER.sub("", body)
    if _NUMBER.search(without_placeholders):
        raise UnresolvedPlaceholderError(
            f"drafter emitted a raw number outside any placeholder in: {body!r}")

    def _replace(m: re.Match) -> str:
        fact_id = m.group(1)
        if fact_id not in fact_sheet:
            raise UnresolvedPlaceholderError(
                f"drafter emitted unknown placeholder '{{{{{fact_id}}}}}' — not in the fact sheet")
        return fact_sheet[fact_id]

    resolved = _PLACEHOLDER.sub(_replace, body)
    if "{" in resolved or "}" in resolved:
        raise UnresolvedPlaceholderError(
            f"drafter emitted malformed or unbalanced placeholder syntax in: {body!r}")
    return resolved


class EmailDrafter:
    def __init__(self, client, model: str = EMAIL_DRAFT_MODEL) -> None:
        self._client = client
        self.model = model  # public: Watcher reads this to build its idempotency key

    def draft(self, result: ResultInfo, findings: list[AnomalyFinding]) -> EmailDraftSchema:
        fact_sheet = build_fact_sheet(result)
        finding_lines = _templated_evidence(findings, fact_sheet)  # mutates fact_sheet
        system = (
            "You draft professional, plain-English customer update emails for a protein "
            "validation lab. You may reference numeric results ONLY via the exact "
            "placeholder tokens written literally as {{token}} — including every number "
            "inside the anomaly findings below, which are already given to you as "
            "placeholder tokens; copy them exactly. Never write a number yourself. Use "
            "the qualitative details (binding strength, performance, anomaly notes) "
            "directly as given."
        )
        fact_lines = "\n".join(f"- {{{{{fid}}}}}: a binding-affinity (Kd) value" for fid in fact_sheet
                               if fid.startswith("kd_"))
        finding_block = "\n".join(finding_lines)
        user = (
            f"Result title: {result.title}\n\n"
            f"Available numeric placeholders:\n{fact_lines or '(none)'}\n\n"
            f"Anomaly findings:\n{finding_block or '(none)'}\n\n"
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
        resolved_subject = substitute_facts(draft.subject, fact_sheet)
        resolved_body = substitute_facts(draft.body, fact_sheet)
        return EmailDraftSchema(subject=resolved_subject, body=resolved_body)
