from adaptyv.governance.db import connect
from adaptyv.governance.feedback import FeedbackStore
from adaptyv.governance.models import Actor


def test_record_and_read_corrections():
    fs = FeedbackStore(connect())
    fs.record_correction("d1", "Better wording here.", Actor(kind="human", id="alice"))
    rows = fs.corrections()
    assert len(rows) == 1
    assert rows[0]["draft_id"] == "d1"
    assert rows[0]["corrected_body"] == "Better wording here."
    assert rows[0]["corrected_by"] == "alice"
