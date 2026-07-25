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
    assert facts["kd_1"] == "1.20e-09 M"


def _result_with_two_sequences():
    return ResultInfo.model_validate({
        "id": "r2", "title": "Affinity results (two sequences)", "experiment_id": "e1",
        "result_type": "affinity", "created_at": "2026-07-20T10:00:00Z", "metadata": {},
        "summary": [
            {"result_type": "affinity", "sequence": {"aa_string": "MKAA", "name": "dup-binder"},
             "kd_units": "M", "binding_strength": "strong", "positive_control": False,
             "performance": {"verdict": "pass"}, "kd_mean": 1.2e-9, "replicates": []},
            {"result_type": "affinity", "sequence": {"aa_string": "MKZZ", "name": "dup-binder"},
             "kd_units": "M", "binding_strength": "weak", "positive_control": False,
             "performance": {"verdict": "pass"}, "kd_mean": 9.9e-6, "replicates": []},
        ]})


def test_build_fact_sheet_assigns_distinct_sequential_ids_even_with_duplicate_names():
    # Opaque, counter-based IDs never collide, regardless of what the
    # underlying sequence names are (even identical names, as here) --
    # unlike name-derived keys, there is no disambiguation logic needed
    # because there is nothing to disambiguate.
    facts = build_fact_sheet(_result_with_two_sequences())
    assert facts == {"kd_1": "1.20e-09 M", "kd_2": "9.90e-06 M"}


def test_substitute_facts_replaces_token():
    out = substitute_facts("Kd was {{kd_1}}.", {"kd_1": "1.20e-09 M"})
    assert out == "Kd was 1.20e-09 M."


def test_substitute_facts_raises_on_unresolved_token():
    with pytest.raises(UnresolvedPlaceholderError):
        substitute_facts("Kd was {{kd_unknown}}.", {"kd_1": "1.20e-09 M"})


def test_substitute_facts_raises_on_raw_number_with_no_placeholder_even_if_it_matches_a_real_fact():
    # The core hallucination-prevention property: a number is never accepted
    # just because it HAPPENS to equal a real fact -- it must actually come
    # through a resolved placeholder. A model that types the correct value
    # directly, without using {{kd_1}}, is still rejected.
    with pytest.raises(UnresolvedPlaceholderError):
        substitute_facts("Kd was 1.20e-09 M.", {"kd_1": "1.20e-09 M"})


def test_substitute_facts_raises_on_unrelated_raw_number():
    with pytest.raises(UnresolvedPlaceholderError):
        substitute_facts("Customer sample count is 2", {"kd_1": "1.20e-09 M"})


def test_substitute_facts_raises_on_malformed_placeholder_with_space():
    with pytest.raises(UnresolvedPlaceholderError):
        substitute_facts("Kd was {{bad token}}.", {"kd_1": "1.20e-09 M"})


def test_substitute_facts_raises_on_empty_placeholder():
    with pytest.raises(UnresolvedPlaceholderError):
        substitute_facts("Kd was {{}}.", {"kd_1": "1.20e-09 M"})


def test_substitute_facts_raises_on_multiline_placeholder():
    with pytest.raises(UnresolvedPlaceholderError):
        substitute_facts("Kd was {{bad\ntoken}}.", {"kd_1": "1.20e-09 M"})


def test_substitute_facts_raises_on_unclosed_placeholder():
    # The exact adversarial example: a token missing its closing braces.
    with pytest.raises(UnresolvedPlaceholderError):
        substitute_facts("Kd was {{kd_1 M.", {"kd_1": "1.20e-09 M"})


def test_substitute_facts_does_not_misread_a_hyphenated_label_as_a_negative_number():
    out = substitute_facts("Binder-1 showed strong binding with Kd {{kd_1}}.", {"kd_1": "1.20e-09 M"})
    assert out == "Binder-1 showed strong binding with Kd 1.20e-09 M."


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
        body="Binder-1 showed strong binding with Kd {{kd_1}}."))
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


def test_drafter_raises_on_raw_number_in_body_with_no_placeholder():
    fake_response = _FakeParseResponse(EmailDraftSchema(subject="s", body="Model says Kd 9.99e-09 M"))
    drafter = EmailDrafter(client=_FakeClient(fake_response))
    with pytest.raises(UnresolvedPlaceholderError):
        drafter.draft(_result(), findings=[])


def test_drafter_raises_on_raw_number_in_subject_with_no_placeholder():
    fake_response = _FakeParseResponse(EmailDraftSchema(subject="Results 42", body="no tokens here"))
    drafter = EmailDrafter(client=_FakeClient(fake_response))
    with pytest.raises(UnresolvedPlaceholderError):
        drafter.draft(_result(), findings=[])


def test_drafter_prompt_templates_anomaly_evidence_numbers_instead_of_leaving_them_raw():
    # The findings section of the prompt must never contain a bare digit --
    # every number in evidence text is replaced by its own placeholder
    # before the model ever sees it, so "copy this verbatim" can never
    # reintroduce a raw number.
    fake_response = _FakeParseResponse(EmailDraftSchema(subject="s", body="no tokens here"))
    client = _FakeClient(fake_response)
    drafter = EmailDrafter(client=client)
    finding = AnomalyFinding(rule="kd_out_of_bounds", severity="warning",
                             evidence="binder-1 kd_mean=1.0e-06 M outside plausible range")
    drafter.draft(_result(), findings=[finding])
    sent_prompt = str(client.messages.calls[0]["messages"])
    assert "outside plausible range" in sent_prompt
    assert "1.0e-06" not in sent_prompt  # the raw number must not appear ...
    assert "{{ev_1_1}}" in sent_prompt   # ... only its placeholder does


def test_drafter_allows_a_number_that_appears_verbatim_in_anomaly_evidence():
    # Anomaly evidence legitimately contains numbers (replicate counts, kd
    # values) that the drafter is instructed to echo directly. Because the
    # evidence text is pre-templated with placeholders (see test above), the
    # fake client's verbatim echo of the templated evidence resolves cleanly.
    finding = AnomalyFinding(rule="missing_replicates", severity="warning",
                             evidence="binder-1 has 0 replicate(s), policy requires 2")
    fake_response = _FakeParseResponse(EmailDraftSchema(
        subject="s", body="binder-1 has {{ev_1_1}} replicate(s), policy requires {{ev_1_2}}"))
    drafter = EmailDrafter(client=_FakeClient(fake_response))
    out = drafter.draft(_result(), findings=[finding])  # must not raise
    assert "0 replicate" in out.body


def test_drafter_uses_configured_model_and_public_model_attribute():
    fake_response = _FakeParseResponse(EmailDraftSchema(subject="s", body="no tokens here"))
    client = _FakeClient(fake_response)
    drafter = EmailDrafter(client=client, model="claude-custom-1")

    assert drafter.model == "claude-custom-1"

    drafter.draft(_result(), findings=[])

    assert client.messages.calls[0]["model"] == "claude-custom-1"


def test_drafter_validates_subject_not_just_body():
    fake_response = _FakeParseResponse(EmailDraftSchema(
        subject="Results: {{not_a_real_fact}}", body="no tokens here"))
    drafter = EmailDrafter(client=_FakeClient(fake_response))
    with pytest.raises(UnresolvedPlaceholderError):
        drafter.draft(_result(), findings=[])


def test_drafter_substitutes_placeholder_in_subject_when_valid():
    fake_response = _FakeParseResponse(EmailDraftSchema(
        subject="Kd result: {{kd_1}}", body="See details above."))
    drafter = EmailDrafter(client=_FakeClient(fake_response))
    out = drafter.draft(_result(), findings=[])
    assert out.subject == "Kd result: 1.20e-09 M"
