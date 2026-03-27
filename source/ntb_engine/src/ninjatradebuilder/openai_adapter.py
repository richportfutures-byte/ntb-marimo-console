from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from .runtime import StructuredGenerationRequest

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - exercised only when SDK is absent locally
    OpenAI = None  # type: ignore[assignment]


class OpenAIAdapterError(ValueError):
    pass


@dataclass(frozen=True)
class OpenAIResponsesAdapter:
    client: Any
    model: str
    strict_json_schema: bool = False

    @classmethod
    def from_default_client(
        cls,
        *,
        model: str,
        strict_json_schema: bool = False,
    ) -> "OpenAIResponsesAdapter":
        if OpenAI is None:
            raise ImportError("openai SDK is required to construct the default OpenAI client.")
        return cls(client=OpenAI(), model=model, strict_json_schema=strict_json_schema)

    def generate_structured(self, request: StructuredGenerationRequest) -> Mapping[str, Any]:
        response = self.client.responses.create(**self._build_create_params(request))
        envelope = self._extract_envelope(response)
        self._validate_boundary(request, envelope)

        payload = envelope["payload"]
        if not isinstance(payload, Mapping):
            raise TypeError("OpenAI envelope payload must be a structured object.")

        return dict(payload)

    def _build_create_params(self, request: StructuredGenerationRequest) -> dict[str, Any]:
        return {
            "model": self.model,
            "input": request.rendered_prompt,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": self._schema_name(request),
                    "description": self._schema_description(request),
                    "schema": self._response_envelope_schema(request),
                    "strict": self.strict_json_schema,
                }
            },
        }

    @staticmethod
    def _schema_name(request: StructuredGenerationRequest) -> str:
        return f"ninjatradebuilder_prompt_{request.prompt_id}_response_envelope"

    @staticmethod
    def _schema_description(request: StructuredGenerationRequest) -> str:
        boundaries = ", ".join(request.expected_output_boundaries)
        models = ", ".join(request.schema_model_names)
        return (
            "Envelope for NinjaTradeBuilder structured output. "
            f"Allowed boundaries: {boundaries}. Candidate schema models: {models}."
        )

    @staticmethod
    def _response_envelope_schema(request: StructuredGenerationRequest) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "boundary": {
                    "type": "string",
                    "enum": list(request.expected_output_boundaries),
                },
                "payload": {
                    "type": "object",
                    "description": (
                        "Structured stage payload. Runtime performs final schema validation "
                        f"against: {', '.join(request.schema_model_names)}."
                    ),
                },
            },
            "required": ["boundary", "payload"],
        }

    def _extract_envelope(self, response: Any) -> Mapping[str, Any]:
        if isinstance(response, Mapping):
            if "output_text" in response:
                return self._parse_output_text(response["output_text"])
            if "boundary" in response and "payload" in response:
                return dict(response)
            raise OpenAIAdapterError("OpenAI response mapping is missing structured envelope content.")

        output_text = getattr(response, "output_text", None)
        if output_text is None:
            raise OpenAIAdapterError("OpenAI response is missing output_text.")
        return self._parse_output_text(output_text)

    @staticmethod
    def _parse_output_text(output_text: Any) -> Mapping[str, Any]:
        if not isinstance(output_text, str):
            raise TypeError("OpenAI output_text must be a JSON string.")
        try:
            parsed = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise OpenAIAdapterError("OpenAI output_text did not contain valid JSON.") from exc
        if not isinstance(parsed, Mapping):
            raise TypeError("OpenAI structured response must decode to an object.")
        if "boundary" not in parsed or "payload" not in parsed:
            raise OpenAIAdapterError("OpenAI structured response must include boundary and payload.")
        return dict(parsed)

    @staticmethod
    def _validate_boundary(
        request: StructuredGenerationRequest, envelope: Mapping[str, Any]
    ) -> None:
        boundary = envelope["boundary"]
        if not isinstance(boundary, str):
            raise TypeError("OpenAI response boundary must be a string.")
        if boundary not in request.expected_output_boundaries:
            raise OpenAIAdapterError(
                f"OpenAI response boundary {boundary!r} is not allowed for prompt {request.prompt_id}."
            )
