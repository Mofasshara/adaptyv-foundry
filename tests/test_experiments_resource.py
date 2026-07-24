from adaptyv import AdaptyvClient
from adaptyv.models import ExperimentListItem, ExperimentStatus, ExpInfo, ResultInfo


def test_list_returns_list_items():
    exps = AdaptyvClient(mock=True).experiments.list()
    assert all(isinstance(e, ExperimentListItem) for e in exps)
    assert any(e.status is ExperimentStatus.DONE for e in exps)


def test_get_detail_by_uuid():
    exp = AdaptyvClient(mock=True).experiments.get("11111111-1111-1111-1111-111111111111")
    assert isinstance(exp, ExpInfo) and exp.experiment_spec.experiment_type.value == "affinity"


def test_results_are_typed_and_discriminated():
    c = AdaptyvClient(mock=True)
    results = c.experiments.results("11111111-1111-1111-1111-111111111111")
    assert results and isinstance(results[0], ResultInfo)
    assert results[0].summary[0].result_type == "affinity"
