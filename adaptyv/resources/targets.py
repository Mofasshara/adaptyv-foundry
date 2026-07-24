from __future__ import annotations
from typing import TYPE_CHECKING
from adaptyv.models import TargetInfo
if TYPE_CHECKING:
    from adaptyv.client import AdaptyvClient


class TargetsResource:
    def __init__(self, client: "AdaptyvClient") -> None:
        self._c = client

    def list(self, *, search=None, selfservice_only=None, detailed=None, limit=None, offset=None):
        params = {k: v for k, v in dict(search=search, selfservice_only=selfservice_only,
                  detailed=detailed, limit=limit, offset=offset).items() if v is not None}
        return self._c._paged("/api/v1/targets", TargetInfo, params)

    def get(self, target_id: str) -> TargetInfo:
        return TargetInfo.model_validate(self._c._request("GET", f"/api/v1/targets/{target_id}"))
