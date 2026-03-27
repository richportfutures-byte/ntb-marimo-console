from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from .runtime import StructuredGenerationRequest

AdapterResponseFactory = Callable[[StructuredGenerationRequest], Any]
AdapterResponseSpec = Mapping[str, Any] | BaseModel | AdapterResponseFactory


@dataclass
class InProcessStructuredAdapter:
    responses: Mapping[int, AdapterResponseSpec]
    calls: list[dict[str, Any]] = field(default_factory=list)

    def generate_structured(self, request: StructuredGenerationRequest) -> Mapping[str, Any]:
        if request.prompt_id not in self.responses:
            raise ValueError(f"No in-process response configured for prompt_id {request.prompt_id}.")

        response_spec = self.responses[request.prompt_id]
        if callable(response_spec):
            resolved = response_spec(request)
        else:
            resolved = response_spec

        normalized = self._normalize_response(resolved)
        self.calls.append(
            {
                "request": request,
                "raw_response": normalized,
            }
        )
        return normalized

    @staticmethod
    def _normalize_response(response: Any) -> Mapping[str, Any]:
        if isinstance(response, BaseModel):
            return response.model_dump(by_alias=True)
        if isinstance(response, Mapping):
            return dict(response)
        raise TypeError("InProcessStructuredAdapter requires structured mapping responses only.")
