from __future__ import annotations

import re

from adaptyv.agents.email import EmailDraftSchema

_PROMPT_TOKEN = re.compile(r"\{\{([\w-]+)\}\}")


class _FakeParseResponse:
    def __init__(self, parsed_output: EmailDraftSchema) -> None:
        self.parsed_output = parsed_output


class _FakeMessages:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def parse(self, **kwargs) -> _FakeParseResponse:
        self.calls.append(kwargs)
        prompt = str(kwargs.get("messages", [{}])[0].get("content", ""))
        fact_ids = _PROMPT_TOKEN.findall(prompt)
        if fact_ids:
            lines = [f"Measured value for {fid}: {{{{{fid}}}}}." for fid in fact_ids]
        else:
            lines = ["No quantitative results are available for this update."]
        return _FakeParseResponse(EmailDraftSchema(subject="Eval run update", body="\n".join(lines)))


class DeterministicFakeClient:
    """A fake Anthropic client for the eval loop: echoes back every fact
    placeholder token the real EmailDrafter offers, so `draft()`'s actual
    substitution + guard logic is genuinely exercised — no network call,
    fully reproducible."""

    def __init__(self) -> None:
        self.messages = _FakeMessages()
