from types import SimpleNamespace

import pytest

from adaptyv.agents.email import (EmailDrafter, EmailDraftSchema, build_fact_sheet,
                                  substitute_facts)
from adaptyv.errors import UnresolvedPlaceholderError
from adaptyv.governance.models import AnomalyFinding
from adaptyv.models import ResultInfo


def _result():
    return ResultInfo.model_validate({
        "id": "r1", "title": "Affinity results", "experiment_id": "e1",
        "result_type": "affinity", "created_at": "2026-07-20T10:00:00Z", "metadata": {},
        "summary": [
            {"result_type": "affinity", "sequence": {"aa_string": "MKAA", "name": "binder-1"},
             "kd_units": "M", "binding_strength": "strong", "positive_control": False,
             "performance": {"verdict": "pass"}, "kd_mean": 1.2e-9, "replicates": []},
        ]})


def test_build_fact_sheet_has_kd_mean_entry():
    facts = build_fact_sheet(_result())
    assert facts["kd_mean_binder-1"] == "1.20e-09 M"


def test_substitute_facts_replaces_token():
    out = substitute_facts("Kd was {{kd_mean_binder-1}}.", {"kd_mean_binder-1": "1.20e-09 M"})
    assert out == "Kd was 1.20e-09 M."


def test_substitute_facts_raises_on_unresolved_token():
    with pytest.raises(UnresolvedPlaceholderError):
        substitute_facts("Kd was {{kd_mean_unknown}}.", {"kd_mean_binder-1": "1.20e-09 M"})


class _FakeParseResponse:
    def __init__(self, parsed_output):
        self.parsed_output = parsed_output


class _FakeMessages:
    def __init__(self, response):
        self._response = response
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _FakeClient:
    def __init__(self, response):
        self.messages = _FakeMessages(response)


def test_drafter_substitutes_placeholder_from_model_output():
    fake_response = _FakeParseResponse(EmailDraftSchema(
        subject="Your results are ready",
        body="Binder-1 showed strong binding with Kd {{kd_mean_binder-1}}."))
    client = _FakeClient(fake_response)
    drafter = EmailDrafter(client=client)

    out = drafter.draft(_result(), findings=[])

    assert "{{" not in out.body
    assert "1.20e-09 M" in out.body
    assert client.messages.calls[0]["output_format"] is EmailDraftSchema


def test_drafter_raises_if_model_emits_unknown_placeholder():
    fake_response = _FakeParseResponse(EmailDraftSchema(
        subject="s", body="Value: {{not_a_real_fact}}"))
    drafter = EmailDrafter(client=_FakeClient(fake_response))
    with pytest.raises(UnresolvedPlaceholderError):
        drafter.draft(_result(), findings=[])


def test_drafter_prompt_includes_anomaly_evidence_text():
    fake_response = _FakeParseResponse(EmailDraftSchema(subject="s", body="no tokens here"))
    client = _FakeClient(fake_response)
    drafter = EmailDrafter(client=client)
    finding = AnomalyFinding(rule="kd_out_of_bounds", severity="warning",
                             evidence="binder-1 kd_mean=1.0 outside plausible range")
    drafter.draft(_result(), findings=[finding])
    sent = client.messages.calls[0]
    joined = str(sent["messages"])
    assert "outside plausible range" in joined


def test_drafter_uses_configured_model_and_public_model_attribute():
    fake_response = _FakeParseResponse(EmailDraftSchema(subject="s", body="no tokens here"))
    client = _FakeClient(fake_response)
    drafter = EmailDrafter(client=client, model="claude-custom-1")

    assert drafter.model == "claude-custom-1"

    drafter.draft(_result(), findings=[])

    assert client.messages.calls[0]["model"] == "claude-custom-1"
