import pytest

from adaptyv import AdaptyvClient
from adaptyv.models import (CreateExpRequest, CreateExpResponse, CostEstimateRequest,
                            CostEstimateResponse, ExperimentConfirmationResponse,
                            ExperimentSpec, SequenceInput)

def _spec():
    return ExperimentSpec(experiment_type="affinity", method="bli",
                          target_id="44444444-0000-0000-0000-000000000001",
                          sequences={"binder-1": SequenceInput(aa_string="MKAA")})

def test_create_returns_experiment_id():
    r = AdaptyvClient(mock=True).experiments.create(
        CreateExpRequest(name="My run", experiment_spec=_spec()))
    assert isinstance(r, CreateExpResponse) and r.experiment_id

def test_cost_estimate_returns_response():
    r = AdaptyvClient(mock=True).experiments.cost_estimate(CostEstimateRequest(experiment_spec=_spec()))
    assert isinstance(r, CostEstimateResponse)

def test_cost_estimate_breakdown_matches_the_real_schema_shape():
    # Regression test: the mock previously returned {"breakdown": {"total_usd": ...}},
    # which doesn't match the real CostBreakdown schema (pricing_version, assay,
    # total_cents required) at all -- this proves the typed model actually
    # validates against real required fields, not just "some dict came back".
    r = AdaptyvClient(mock=True).experiments.cost_estimate(CostEstimateRequest(experiment_spec=_spec()))
    assert r.breakdown is not None
    assert r.breakdown.pricing_version
    assert r.breakdown.total_cents > 0
    assert r.breakdown.assay.experiment_type == "affinity"

def test_submit_returns_typed_confirmation_response():
    r = AdaptyvClient(mock=True).experiments.submit("11111111-1111-1111-1111-111111111111")
    assert isinstance(r, ExperimentConfirmationResponse)
    assert r.previous_status and r.status and r.confirmed_at

def test_experiment_spec_rejects_affinity_missing_method_and_target_id():
    with pytest.raises(ValueError):
        ExperimentSpec(experiment_type="affinity",
                       sequences={"binder-1": SequenceInput(aa_string="MKAA")})

def test_experiment_spec_rejects_thermostability_with_method_set():
    # method is REJECTED (not just optional) for non-binding types.
    with pytest.raises(ValueError):
        ExperimentSpec(experiment_type="thermostability", method="bli",
                       sequences={"s1": SequenceInput(aa_string="MKAA")})

def test_experiment_spec_rejects_empty_sequences():
    with pytest.raises(ValueError):
        ExperimentSpec(experiment_type="thermostability", sequences={})
