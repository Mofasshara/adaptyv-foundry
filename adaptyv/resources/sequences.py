from __future__ import annotations
from typing import TYPE_CHECKING
from adaptyv.models import SequenceAddRequest, SequenceAddResponse, SequenceInfo, SequenceListItem
if TYPE_CHECKING:
    from adaptyv.client import AdaptyvClient


class SequencesResource:
    def __init__(self, client: "AdaptyvClient") -> None:
        self._c = client

    def list(self, **q):
        params = {k: v for k, v in q.items() if v is not None}
        return self._c._paged("/api/v1/sequences", SequenceListItem, params)

    def get(self, sequence_id: str) -> SequenceInfo:
        return SequenceInfo.model_validate(
            self._c._request("GET", f"/api/v1/sequences/{sequence_id}"))

    def add(self, request: SequenceAddRequest) -> SequenceAddResponse:
        data = self._c._request("POST", "/api/v1/sequences",
                                 json=request.model_dump(exclude_none=True))
        return SequenceAddResponse.model_validate(data)
