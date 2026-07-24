from adaptyv import AdaptyvClient
from adaptyv.models import (ResultInfo, SequenceAddRequest, SequenceAddResponse,
                            SequenceEntry, SequenceInfo, TargetInfo)


def test_targets_search_returns_typed():
    ts = AdaptyvClient(mock=True).targets.list(search="IL")
    assert ts and all(isinstance(t, TargetInfo) for t in ts)


def test_targets_get():
    t = AdaptyvClient(mock=True).targets.get("44444444-0000-0000-0000-000000000001")
    assert isinstance(t, TargetInfo) and t.name == "IL-6"


def test_results_get():
    r = AdaptyvClient(mock=True).results.get("aaaaaaaa-0000-0000-0000-000000000001")
    assert isinstance(r, ResultInfo)


def test_sequences_list():
    ss = AdaptyvClient(mock=True).sequences.list()
    assert ss and ss[0].id == "33333333-0000-0000-0000-000000000001"


def test_sequences_get():
    s = AdaptyvClient(mock=True).sequences.get("33333333-0000-0000-0000-000000000001")
    assert isinstance(s, SequenceInfo)
    assert s.experiment.experiment_code == "EXP-1001"
    assert s.aa_string is not None


def test_results_list_discriminated():
    rs = AdaptyvClient(mock=True).results.list()
    assert rs and isinstance(rs[0], ResultInfo)
    assert rs[0].summary[0].result_type == "affinity"


def test_sequences_add():
    r = AdaptyvClient(mock=True).sequences.add(SequenceAddRequest(
        experiment_code="EXP-1001", sequences=[SequenceEntry(aa_string="MKAA")]))
    assert isinstance(r, SequenceAddResponse) and r.added_count == 1
