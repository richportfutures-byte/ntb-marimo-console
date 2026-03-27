from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from .config import GeminiStartupConfig, load_gemini_startup_config
from .runtime import StructuredGenerationRequest

try:
    from google import genai
    from google.genai import errors as genai_errors
except ImportError:  # pragma: no cover - exercised only when SDK is absent locally
    genai = None  # type: ignore[assignment]
    genai_errors = None  # type: ignore[assignment]


class GeminiAdapterError(ValueError):
    pass


@dataclass(frozen=True)
class GeminiResponsesAdapter:
    client: Any
    model: str
    timeout_seconds: int | None = None
    max_retries: int = 0

    @classmethod
    def from_default_client(cls, *, model: str) -> "GeminiResponsesAdapter":
        if genai is None:
            raise ImportError("google-genai SDK is required to construct the default Gemini client.")
        try:
            config = load_gemini_startup_config(model=model)
        except Exception as exc:
            raise GeminiAdapterError(str(exc)) from exc
        return cls.from_startup_config(config)

    @classmethod
    def from_startup_config(cls, config: GeminiStartupConfig) -> "GeminiResponsesAdapter":
        if genai is None:
            raise ImportError("google-genai SDK is required to construct the default Gemini client.")
        client = genai.Client(
            api_key=config.api_key,
            http_options=cls._build_http_options(config),
        )
        return cls(
            client=client,
            model=config.model,
            timeout_seconds=config.timeout_seconds,
            max_retries=config.max_retries,
        )

    def generate_structured(self, request: StructuredGenerationRequest) -> Mapping[str, Any]:
        try:
            response = self.client.models.generate_content(**self._build_generate_params(request))
        except Exception as exc:
            raise self._wrap_provider_error(exc) from exc
        envelope = self._extract_envelope(response)
        self._validate_boundary(request, envelope)

        payload = envelope["payload"]
        if not isinstance(payload, Mapping):
            raise TypeError("Gemini envelope payload must be a structured object.")

        return dict(payload)

    @staticmethod
    def _build_http_options(config: GeminiStartupConfig) -> Any:
        if genai is None:
            raise ImportError("google-genai SDK is required to construct Gemini HTTP options.")
        return genai.types.HttpOptions(
            timeout=config.timeout_seconds * 1000,
            retryOptions=genai.types.HttpRetryOptions(
                attempts=config.total_attempts,
                initialDelay=config.retry_initial_delay_seconds,
                maxDelay=config.retry_max_delay_seconds,
                expBase=2.0,
                jitter=0.0,
                httpStatusCodes=[408, 429, 500, 502, 503, 504],
            ),
        )

    def _wrap_provider_error(self, exc: Exception) -> GeminiAdapterError:
        if genai_errors is not None and isinstance(exc, genai_errors.httpx.TimeoutException):
            return GeminiAdapterError(
                "Gemini request timed out "
                f"after {self.timeout_seconds or 'configured'} seconds using model {self.model} "
                f"after {self.max_retries + 1} attempt(s)."
            )
        if genai_errors is not None and isinstance(exc, genai_errors.APIError):
            error_text = str(exc)
            if getattr(exc, "code", None) == 504 or "DEADLINE_EXCEEDED" in error_text:
                return GeminiAdapterError(
                    "Gemini request timed out "
                    f"after {self.timeout_seconds or 'configured'} seconds using model {self.model} "
                    f"after {self.max_retries + 1} attempt(s)."
                )
            return GeminiAdapterError(
                "Gemini request failed "
                f"using model {self.model} after {self.max_retries + 1} attempt(s): {error_text}"
            )
        return GeminiAdapterError(
            f"Gemini request failed using model {self.model}: {exc}"
        )

    def _build_generate_params(self, request: StructuredGenerationRequest) -> dict[str, Any]:
        return {
            "model": self.model,
            "contents": request.rendered_prompt,
            "config": {
                "response_mime_type": "application/json",
                "response_json_schema": self._response_envelope_schema(request),
            },
        }

    @staticmethod
    def _response_envelope_schema(request: StructuredGenerationRequest) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "boundary": {
                    "type": "string",
                    "enum": list(request.expected_output_boundaries),
                    "description": (
                        "Boundary selected by the model from the allowed prompt-bound options."
                    ),
                },
                "payload": {
                    "type": "object",
                    "description": GeminiResponsesAdapter._payload_description(request),
                },
            },
            "required": ["boundary", "payload"],
        }

    @staticmethod
    def _payload_description(request: StructuredGenerationRequest) -> str:
        description = (
            "Structured stage payload. Runtime performs final schema validation "
            f"against: {', '.join(request.schema_model_names)}."
        )
        if request.prompt_id == 8:
            description += (
                " For proposed_setup NO_TRADE responses, emit only schema-defined fields: "
                "always include contract and timestamp, use no_trade_reason as the sole reason field, "
                "set all setup-only fields to null, and do not emit extra keys such as "
                "disqualification_reasons or rejection_reasons. For proposed_setup SETUP_PROPOSED "
                "responses, always include outcome exactly as SETUP_PROPOSED, always include "
                "contract and timestamp, set no_trade_reason to null, normalize direction to the "
                "schema enum LONG or SHORT only, restrict setup_class to scalp, "
                "intraday_swing, or session_hold only, provide non-null direction, entry_price, "
                "stop_price, target_1, position_size, risk_dollars, reward_risk_ratio, "
                "setup_class, hold_time_estimate_minutes, rationale, disqualifiers, and "
                "sizing_math, require sizing_math to be a structured object rather than prose, "
                "and enforce target_2 null when position_size is 1 or required when position_size "
                "is greater than 1."
            )
        if request.prompt_id in {2, 3, 4, 5, 6, 7}:
            description += (
                " For sufficiency_gate_output responses, always emit the full schema object: "
                "contract, timestamp, status, missing_inputs, disqualifiers, data_quality_flags, "
                "staleness_check, challenge_state_valid, and event_lockout_detail when applicable. "
                "staleness_check must be an object with packet_age_seconds, stale, and "
                "threshold_seconds, not a string or summary label. event_lockout_detail must be "
                "an object with exactly event_name, event_time, minutes_until, and lockout_type; "
                "lockout_type must be pre_event or post_event only, and even post-event lockout "
                "must still use the field name minutes_until rather than minutes_since or "
                "lockout_threshold_minutes. Do not emit shorthand fields such as reason or "
                "missing_fields. If the Stage A status is READY, continue to Stage B and return "
                "contract_analysis instead of returning sufficiency_gate_output. "
                "For contract_analysis responses, always emit the full schema object with "
                "contract, timestamp, market_regime, directional_bias, key_levels, evidence_score, "
                "confidence_band, value_context, structural_notes, outcome, conflicting_signals, "
                "and assumptions. outcome must be ANALYSIS_COMPLETE or NO_TRADE only, never READY. "
                "market_regime must use only these exact literals: trending_up, trending_down, "
                "range_bound, breakout, breakdown, choppy, unclear, and the model should copy "
                "one literal verbatim rather than inventing near-synonyms such as trend_up. "
                "value_context.relative_to_prior_value_area must use only above, inside, or "
                "below, copied verbatim rather than near-synonyms such as overlapping_higher. "
                "value_context.relative_to_current_developing_value must use only above_vah, "
                "inside_value, or below_val, copied verbatim rather than near-synonyms such as "
                "above. value_context.relative_to_vwap must use only above, at, or below. "
                "value_context.relative_to_prior_day_range must use only above, inside, or "
                "below. key_levels must be an object with support_levels, resistance_levels, "
                "and pivot_level, and each of support_levels and resistance_levels must contain "
                "at most 3 numeric levels. structural_notes must be a single string, not a list. "
                "assumptions must be a JSON array of strings, including single-entry arrays or "
                "[] when empty, never a scalar string. Do "
                "not leak Stage A fields such as status, missing_inputs, disqualifiers, "
                "data_quality_flags, staleness_check, challenge_state_valid, or "
                "event_lockout_detail into contract_analysis."
            )
        if request.prompt_id == 7:
            description += (
                " For Prompt 7 MGC specifically, if macro_fear_catalyst_summary is not none and "
                "DXY and yield drivers remain materially contradictory or the causal map is "
                "unstable, favor outcome NO_TRADE rather than ANALYSIS_COMPLETE unless one "
                "coherent dominant driver is clearly established from structured inputs. "
                "directional_bias must use only the schema literals bullish, bearish, neutral, "
                "or unclear; never emit up, down, long, short, or any synonym."
            )
        if request.prompt_id == 3:
            description += (
                " For Prompt 3 NQ specifically, if relative_strength_vs_es is below 1.0 and "
                "megacap leadership is fragile, lagging, or earnings-risk driven, favor outcome "
                "NO_TRADE rather than ANALYSIS_COMPLETE unless broad leadership and one coherent "
                "dominant driver are clearly established from structured inputs."
            )
        if request.prompt_id == 2:
            description += (
                " For Prompt 2 ES specifically, if breadth, index_cash_tone, or "
                "cumulative_delta materially diverge from price direction and multiple "
                "divergence signals remain unresolved, favor outcome NO_TRADE rather than "
                "ANALYSIS_COMPLETE unless one coherent dominant driver is clearly established "
                "from structured inputs."
            )
        if request.prompt_id == 9:
            description += (
                " For risk_authorization responses, always emit the full schema object with "
                "contract, timestamp, decision, checks_count, checks, rejection_reasons, "
                "adjusted_position_size, adjusted_risk_dollars, remaining_daily_risk_budget, "
                "and remaining_aggregate_risk_budget. decision must be exactly APPROVED, "
                "REJECTED, or REDUCED, and must never be emitted as outcome. checks_count "
                "must equal 13. checks must contain exactly 13 objects in order, each with "
                "check_id, check_name, passed, and detail; check_id must run from 1 through "
                "13 in order. Use rejection_reasons as a list of strings; do not emit "
                "rejection_reason. Do not leak setup fields into risk_authorization, including "
                "direction, position_size, entry_price, stop_price, target_1, target_2, "
                "reward_risk_ratio, or authorized_risk_dollars. For APPROVED, use "
                "rejection_reasons as [] and leave adjusted_position_size and "
                "adjusted_risk_dollars null. For REJECTED, include one or more "
                "rejection_reasons. For REDUCED, include adjusted_position_size and "
                "adjusted_risk_dollars."
            )
        return description

    def _extract_envelope(self, response: Any) -> Mapping[str, Any]:
        if isinstance(response, Mapping):
            if "text" in response:
                return self._parse_text(response["text"])
            if "boundary" in response and "payload" in response:
                return dict(response)
            raise GeminiAdapterError("Gemini response mapping is missing structured envelope content.")

        text = getattr(response, "text", None)
        if text is None:
            raise GeminiAdapterError("Gemini response is missing text.")
        return self._parse_text(text)

    @staticmethod
    def _parse_text(text: Any) -> Mapping[str, Any]:
        if not isinstance(text, str):
            raise TypeError("Gemini response text must be a JSON string.")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise GeminiAdapterError("Gemini response text did not contain valid JSON.") from exc
        if not isinstance(parsed, Mapping):
            raise TypeError("Gemini structured response must decode to an object.")
        if "boundary" not in parsed or "payload" not in parsed:
            raise GeminiAdapterError("Gemini structured response must include boundary and payload.")
        return dict(parsed)

    @staticmethod
    def _validate_boundary(
        request: StructuredGenerationRequest, envelope: Mapping[str, Any]
    ) -> None:
        boundary = envelope["boundary"]
        if not isinstance(boundary, str):
            raise TypeError("Gemini response boundary must be a string.")
        if boundary not in request.expected_output_boundaries:
            raise GeminiAdapterError(
                f"Gemini response boundary {boundary!r} is not allowed for prompt {request.prompt_id}."
            )
