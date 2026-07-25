from adaptyv import AdaptyvClient
from adaptyv.models import (CreateExpRequest, CreateExpResponse, CostEstimateRequest,
                            CostEstimateResponse, ExperimentSpec, SequenceInput)

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
