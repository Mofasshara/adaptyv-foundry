from __future__ import annotations
from typing import TYPE_CHECKING
from adaptyv.models import ResultInfo
if TYPE_CHECKING:
    from adaptyv.client import AdaptyvClient


class ResultsResource:
    def __init__(self, client: "AdaptyvClient") -> None:
        self._c = client

    def list(self, **q):
        params = {k: v for k, v in q.items() if v is not None}
        return self._c._paged("/api/v1/results", ResultInfo, params)

    def get(self, result_id: str) -> ResultInfo:
        return ResultInfo.model_validate(self._c._request("GET", f"/api/v1/results/{result_id}"))
