from __future__ import annotations

import re

from pydantic import BaseModel

from adaptyv.errors import UngroundedNumberError, UnresolvedPlaceholderError
from adaptyv.governance.models import AnomalyFinding
from adaptyv.models import AffinityResultSummary, ResultInfo

EMAIL_DRAFT_MODEL = "claude-opus-4-8"

# Fact-sheet keys are derived from sequence names (build_fact_sheet), which routinely
# contain hyphens (e.g. "binder-1") -- \w alone would silently fail to match those
# tokens, letting an un-substituted {{...}} slip through unresolved-placeholder
# detection entirely. Include '-' explicitly so every emitted token is checked.
_PLACEHOLDER = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
_VALID_FACT_ID = re.compile(r"^[\w-]+$")
_NUMBER = re.compile(r"(?<![\w-])-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?%?")
# The `(?<![\w-])` negative lookbehind is required, not decorative: without
# it, `-?` greedily treats the hyphen in a hyphenated label like "binder-1"
# as a negative sign, extracting the spurious "number" -1 -- which is never
# grounded (no fact or evidence ever produces "-1"), so a naive regex here
# would raise UngroundedNumberError on the completely benign, real sentence
# "Binder-1 showed strong binding...". The lookbehind requires the
# character immediately before a candidate match to be neither a word
# character nor a hyphen, so "binder-1" and "seq1" are correctly seen as
# identifiers, not numbers -- verified empirically before this plan was
# written; see test_drafter_does_not_misread_a_hyphenated_label_as_a_negative_number.


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
        if not _VALID_FACT_ID.match(fact_id) or fact_id not in fact_sheet:
            raise UnresolvedPlaceholderError(
                f"drafter emitted unknown placeholder '{{{{{fact_id}}}}}' — not in the fact sheet")
        return fact_sheet[fact_id]
    return _PLACEHOLDER.sub(_replace, body)


def grounded_numbers(fact_sheet: dict[str, str], findings: list[AnomalyFinding]) -> set[str]:
    """Every number a drafted email is allowed to contain: fact-sheet values
    (the only measurements the model may cite) and numbers appearing
    verbatim in anomaly evidence (the only other grounded-truth text passed
    into the prompt, which the drafter is instructed to echo directly).
    Anything else is fabrication."""
    grounded: set[str] = set()
    for value in fact_sheet.values():
        grounded.update(_NUMBER.findall(value))
    for f in findings:
        grounded.update(_NUMBER.findall(f.evidence))
    return grounded


def find_ungrounded_numbers(text: str, grounded: set[str]) -> list[str]:
    return [n for n in _NUMBER.findall(text) if n not in grounded]


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
        resolved_subject = substitute_facts(draft.subject, fact_sheet)
        resolved_body = substitute_facts(draft.body, fact_sheet)
        grounded = grounded_numbers(fact_sheet, findings)
        for text in (resolved_subject, resolved_body):
            ungrounded = find_ungrounded_numbers(text, grounded)
            if ungrounded:
                raise UngroundedNumberError(
                    f"drafter emitted ungrounded number(s) {ungrounded} not traceable to any fact or anomaly evidence")
        return EmailDraftSchema(subject=resolved_subject, body=resolved_body)
