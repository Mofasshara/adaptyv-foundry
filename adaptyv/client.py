from __future__ import annotations
import os
from typing import Any, Type, TypeVar
from pydantic import BaseModel, TypeAdapter
from adaptyv.errors import TransportError
from adaptyv.transport import MockTransport, Transport

M = TypeVar("M", bound=BaseModel)

_DEFAULT_PAGE_SIZE = 100


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
        from adaptyv.resources.sequences import SequencesResource
        from adaptyv.resources.targets import TargetsResource
        from adaptyv.resources.results import ResultsResource
        self.sequences = SequencesResource(self)
        self.targets = TargetsResource(self)
        self.results = ResultsResource(self)

    def _request(self, method: str, path: str, *, params=None, json=None) -> Any:
        return self._transport.request(method, path, params=params, json=json)

    def _paged(self, path: str, model: Type[M], params: dict) -> list[M]:
        """Fetch every page of a paginated list endpoint and return typed items.

        Starts from the caller-supplied offset/limit in `params` if present
        (used as the starting window), otherwise pages from offset 0 with a
        default page size. Continues requesting subsequent pages (advancing
        offset by however many items the server actually returned) until the
        envelope's `total` has been collected or a page comes back empty,
        which guards against infinite loops on a misbehaving/missing `total`.
        """
        adapter = TypeAdapter(model)
        page_params = dict(params)
        offset = page_params.get("offset", 0)
        page_params.setdefault("limit", _DEFAULT_PAGE_SIZE)
        page_params["offset"] = offset

        results: list[M] = []
        while True:
            env = self._request("GET", path, params=page_params)
            if not isinstance(env, dict) or "items" not in env:
                raise TransportError(
                    f"malformed pagination envelope for GET {path}: expected a dict with an "
                    f"'items' key, got {type(env).__name__!r}"
                )
            items = env["items"]
            results.extend(adapter.validate_python(i) for i in items)
            count = len(items)
            total = env.get("total", offset + count)
            if count == 0 or offset + count >= total:
                break
            offset += count
            page_params["offset"] = offset
        return results
