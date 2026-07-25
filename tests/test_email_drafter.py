import pytest

from adaptyv.agents.email import (EmailDrafter, EmailDraftSchema, build_fact_sheet,
                                  substitute_facts)
from adaptyv.errors import UngroundedNumberError, UnresolvedPlaceholderError
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


def _result_with_duplicate_labels():
    # Two summary entries sharing the same name -> same derived label. Without
    # disambiguation the second kd_mean silently overwrites the first under
    # "kd_mean_dup-binder", misattributing whichever value survives.
    return ResultInfo.model_validate({
        "id": "r2", "title": "Affinity results (dup labels)", "experiment_id": "e1",
        "result_type": "affinity", "created_at": "2026-07-20T10:00:00Z", "metadata": {},
        "summary": [
            {"result_type": "affinity", "sequence": {"aa_string": "MKAA", "name": "dup-binder"},
             "kd_units": "M", "binding_strength": "strong", "positive_control": False,
             "performance": {"verdict": "pass"}, "kd_mean": 1.2e-9, "replicates": []},
            {"result_type": "affinity", "sequence": {"aa_string": "MKZZ", "name": "dup-binder"},
             "kd_units": "M", "binding_strength": "weak", "positive_control": False,
             "performance": {"verdict": "pass"}, "kd_mean": 9.9e-6, "replicates": []},
        ]})


def test_build_fact_sheet_disambiguates_duplicate_labels():
    facts = build_fact_sheet(_result_with_duplicate_labels())
    # Both measurements must be present, under two DISTINCT keys.
    assert "kd_mean_dup-binder" in facts
    assert "kd_mean_dup-binder_2" in facts
    assert len(facts) == 2
    # And correctly attributed -- not swapped.
    assert facts["kd_mean_dup-binder"] == "1.20e-09 M"
    assert facts["kd_mean_dup-binder_2"] == "9.90e-06 M"


def test_substitute_facts_replaces_token():
    out = substitute_facts("Kd was {{kd_mean_binder-1}}.", {"kd_mean_binder-1": "1.20e-09 M"})
    assert out == "Kd was 1.20e-09 M."


def test_substitute_facts_raises_on_unresolved_token():
    with pytest.raises(UnresolvedPlaceholderError):
        substitute_facts("Kd was {{kd_mean_unknown}}.", {"kd_mean_binder-1": "1.20e-09 M"})


def test_substitute_facts_raises_on_unresolved_hyphenated_token():
    # Regression test for the exact bug this fix closed: a well-formed but
    # UNKNOWN hyphenated placeholder (the realistic hallucination shape, since
    # real fact_sheet keys are hyphenated) must still be caught, not silently
    # passed through unmatched-and-unraised.
    with pytest.raises(UnresolvedPlaceholderError):
        substitute_facts("Kd was {{kd_mean_binder-2}}.", {"kd_mean_binder-1": "1.20e-09 M"})


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


def test_substitute_facts_raises_on_malformed_placeholder_with_space():
    # Regression test: a placeholder-shaped construct that ISN'T [\w-]+ (e.g.
    # contains a space) must still be caught, not silently left in the output
    # untouched and unraised.
    with pytest.raises(UnresolvedPlaceholderError):
        substitute_facts("Kd was {{bad token}}.", {"kd_mean_binder-1": "1.20e-09 M"})


def test_drafter_validates_subject_not_just_body():
    # Regression test: the "never emit a raw placeholder" guarantee must cover
    # the subject line too, not only the body.
    fake_response = _FakeParseResponse(EmailDraftSchema(
        subject="Results: {{not_a_real_fact}}", body="no tokens here"))
    drafter = EmailDrafter(client=_FakeClient(fake_response))
    with pytest.raises(UnresolvedPlaceholderError):
        drafter.draft(_result(), findings=[])


def test_drafter_substitutes_placeholder_in_subject_when_valid():
    fake_response = _FakeParseResponse(EmailDraftSchema(
        subject="Kd result: {{kd_mean_binder-1}}", body="See details above."))
    drafter = EmailDrafter(client=_FakeClient(fake_response))
    out = drafter.draft(_result(), findings=[])
    assert out.subject == "Kd result: 1.20e-09 M"


def test_drafter_raises_on_raw_number_in_body_with_no_placeholder():
    # Regression test: a raw number with NO {{}} syntax at all bypasses
    # substitute_facts entirely -- this needs a separate grounding check.
    fake_response = _FakeParseResponse(EmailDraftSchema(
        subject="s", body="Model says Kd 9.99e-09 M"))
    drafter = EmailDrafter(client=_FakeClient(fake_response))
    with pytest.raises(UngroundedNumberError):
        drafter.draft(_result(), findings=[])


def test_drafter_raises_on_raw_number_in_subject_with_no_placeholder():
    fake_response = _FakeParseResponse(EmailDraftSchema(subject="Results 42", body="no tokens here"))
    drafter = EmailDrafter(client=_FakeClient(fake_response))
    with pytest.raises(UngroundedNumberError):
        drafter.draft(_result(), findings=[])


def test_drafter_allows_a_number_that_appears_verbatim_in_anomaly_evidence():
    # Anomaly evidence legitimately contains numbers (replicate counts, kd
    # values) that the drafter is instructed to echo directly -- these must
    # NOT be flagged as ungrounded. (AnomalyFinding is already imported at
    # the top of this file.)
    finding = AnomalyFinding(rule="missing_replicates", severity="warning",
                             evidence="binder-1 has 0 replicate(s), policy requires 2")
    fake_response = _FakeParseResponse(EmailDraftSchema(
        subject="s", body="binder-1 has 0 replicate(s), policy requires 2"))
    drafter = EmailDrafter(client=_FakeClient(fake_response))
    out = drafter.draft(_result(), findings=[finding])  # must not raise
    assert "0 replicate" in out.body


def test_drafter_allows_a_number_that_matches_a_grounded_fact_via_placeholder():
    # Existing behavior must still work: a real, grounded number substituted
    # via {{fact_id}} is fine.
    fake_response = _FakeParseResponse(EmailDraftSchema(
        subject="s", body="Kd was {{kd_mean_binder-1}}."))
    drafter = EmailDrafter(client=_FakeClient(fake_response))
    out = drafter.draft(_result(), findings=[])  # must not raise
    assert "1.20e-09" in out.body


def test_drafter_does_not_misread_a_hyphenated_label_as_a_negative_number():
    # Regression guard for the number regex: "binder-1" must NOT be parsed as
    # the number "-1". A naive `-?\d+` would match the hyphen in a
    # hyphenated sequence label as a negative sign, and "-1" is never in any
    # fact sheet or evidence text -- a naive regex would incorrectly raise
    # UngroundedNumberError on this completely benign, real sentence.
    fake_response = _FakeParseResponse(EmailDraftSchema(
        subject="s", body="Binder-1 showed strong binding with Kd {{kd_mean_binder-1}}."))
    drafter = EmailDrafter(client=_FakeClient(fake_response))
    out = drafter.draft(_result(), findings=[])  # must not raise
    assert "Binder-1" in out.body


def test_substitute_facts_raises_on_empty_placeholder():
    with pytest.raises(UnresolvedPlaceholderError):
        substitute_facts("Kd was {{}}.", {"kd_mean_binder-1": "1.20e-09 M"})


def test_substitute_facts_raises_on_multiline_placeholder():
    with pytest.raises(UnresolvedPlaceholderError):
        substitute_facts("Kd was {{bad\ntoken}}.", {"kd_mean_binder-1": "1.20e-09 M"})
