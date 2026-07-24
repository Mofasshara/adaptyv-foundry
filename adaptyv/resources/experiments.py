from __future__ import annotations
from typing import TYPE_CHECKING
from adaptyv.models import ExperimentListItem, ExpInfo, ResultInfo

if TYPE_CHECKING:
    from adaptyv.client import AdaptyvClient


class ExperimentsResource:
    def __init__(self, client: "AdaptyvClient") -> None:
        self._c = client

    def list(self, *, limit=None, offset=None, search=None, filter=None, sort=None):
        params = {k: v for k, v in dict(limit=limit, offset=offset, search=search,
                                        filter=filter, sort=sort).items() if v is not None}
        return self._c._paged("/api/v1/experiments", ExperimentListItem, params)

    def get(self, experiment_id: str) -> ExpInfo:
        return ExpInfo.model_validate(
            self._c._request("GET", f"/api/v1/experiments/{experiment_id}"))

    def results(self, experiment_id: str) -> list[ResultInfo]:
        return self._c._paged(f"/api/v1/experiments/{experiment_id}/results", ResultInfo, {})
