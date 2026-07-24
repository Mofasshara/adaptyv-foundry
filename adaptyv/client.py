from __future__ import annotations
import os
from typing import Any, Type, TypeVar
from pydantic import BaseModel, TypeAdapter
from adaptyv.transport import MockTransport, Transport

M = TypeVar("M", bound=BaseModel)


class AdaptyvClient:
    def __init__(self, api_key: str | None = None, *, mock: bool = False,
                 base_url: str = "https://devs.adaptyvbio.com",
                 transport: Transport | None = None) -> None:
        self.base_url = base_url
        if transport is not None:
            self._transport = transport
        elif mock:
            self._transport = MockTransport()
        else:
            from adaptyv.live_transport import LiveTransport  # deferred (Task 7)
            self._transport = LiveTransport(base_url=base_url,
                                            api_key=api_key or os.environ.get("ADAPTYV_API_KEY"))
        from adaptyv.resources.experiments import ExperimentsResource
        self.experiments = ExperimentsResource(self)

    def _request(self, method: str, path: str, *, params=None, json=None) -> Any:
        return self._transport.request(method, path, params=params, json=json)

    def _paged(self, path: str, model: Type[M], params: dict) -> list[M]:
        env = self._request("GET", path, params=params)
        adapter = TypeAdapter(model)
        return [adapter.validate_python(i) for i in env["items"]]
