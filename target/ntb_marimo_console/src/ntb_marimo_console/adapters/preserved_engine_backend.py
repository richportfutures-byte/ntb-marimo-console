from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from .contracts import (
    PipelineBackend,
    PipelineNarrative,
    PipelineQueryRequest,
    PipelineSummary,
    WatchmanContextLike,
    WatchmanSweepRequest,
)
from .stage_e_log import resolve_stage_e_log_path


class PreservedEngineBackend(PipelineBackend):
    """Thin adapter over preserved `ninjatradebuilder.execution_facade`.

    No preserved-engine logic is copied or reimplemented here.
    """

    def __init__(
        self,
        *,
        model_adapter: object,
        stage_e_log_root: str | Path | None = None,
    ) -> None:
        self._model_adapter = model_adapter
        self._stage_e_log_root = stage_e_log_root
        from ninjatradebuilder import execution_facade

        self._facade = execution_facade

    def sweep_watchman(
        self,
        request: WatchmanSweepRequest,
    ) -> dict[str, WatchmanContextLike]:
        return cast(
            dict[str, WatchmanContextLike],
            self._facade.sweep_watchman(request.packet_bundle, request.readiness_trigger),
        )

    def run_pipeline(self, request: PipelineQueryRequest) -> object:
        if request.readiness_trigger is not None:
            result, _record = self._facade.run_pipeline_and_log(
                request.packet,
                request.contract,
                request.readiness_trigger,
                model_adapter=self._model_adapter,
                trigger_family=str(request.readiness_trigger.get("trigger_family", "<unresolved>")),
                evaluation_timestamp_iso=request.evaluation_timestamp_iso,
                log_path=resolve_stage_e_log_path(
                    request.contract,
                    root=self._stage_e_log_root,
                ),
            )
            return result

        return self._facade.run_pipeline(
            request.packet,
            request.contract,
            model_adapter=self._model_adapter,
            evaluation_timestamp_iso=request.evaluation_timestamp_iso,
        )

    def summarize_pipeline_result(self, result: object) -> PipelineSummary:
        return cast(PipelineSummary, dict(self._facade.summarize_pipeline_result(result)))

    def narrate_pipeline_result(self, result: object) -> PipelineNarrative:
        """Extract Stage B/C/D narrative from the preserved-engine result.

        Performs plain field extraction only. No interpretation, derivation,
        ranking, or string parsing. Pydantic models are dumped via
        model_dump(mode='json') so the console sees primitive JSON values.
        Missing stages produce explicit None entries.
        """
        return _narrative_from_pipeline_execution_result(result)


class UnavailableEngineBackend(PipelineBackend):
    """Test-safe backend placeholder when preserved engine is not wired."""

    def sweep_watchman(
        self,
        request: WatchmanSweepRequest,
    ) -> dict[str, WatchmanContextLike]:
        return {}

    def run_pipeline(self, request: PipelineQueryRequest) -> object:
        raise RuntimeError("Preserved engine backend is not configured.")

    def summarize_pipeline_result(self, result: object) -> PipelineSummary:
        if isinstance(result, Mapping):
            return cast(PipelineSummary, dict(result))
        return {
            "contract": "UNKNOWN",
            "termination_stage": "UNKNOWN",
            "final_decision": "ERROR",
            "sufficiency_gate_status": None,
            "contract_analysis_outcome": None,
            "proposed_setup_outcome": None,
            "risk_authorization_decision": None,
        }

    def narrate_pipeline_result(self, result: object) -> PipelineNarrative:
        return {
            "contract_analysis": None,
            "proposed_setup": None,
            "risk_authorization": None,
        }


def _narrative_from_pipeline_execution_result(result: object) -> PipelineNarrative:
    """Adapt a `ninjatradebuilder.pipeline.PipelineExecutionResult` to a narrative payload.

    Tolerant of three shapes:
      1. The dataclass itself (preserved-engine path).
      2. A Mapping already shaped like PipelineNarrative or its inner stages.
      3. Anything else - returned as an empty narrative (renderer surfaces unavailable).

    Pydantic submodels are dumped via model_dump so values are primitive JSON.
    """
    if isinstance(result, Mapping):
        contract_analysis = result.get("contract_analysis")
        proposed_setup = result.get("proposed_setup")
        risk_authorization = result.get("risk_authorization")
    else:
        contract_analysis = getattr(result, "contract_analysis", None)
        proposed_setup = getattr(result, "proposed_setup", None)
        risk_authorization = getattr(result, "risk_authorization", None)

    return {
        "contract_analysis": _section_to_dict(contract_analysis),
        "proposed_setup": _section_to_dict(proposed_setup),
        "risk_authorization": _section_to_dict(risk_authorization),
    }


def _section_to_dict(section: object) -> dict[str, object] | None:
    if section is None:
        return None
    model_dump = getattr(section, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump(mode="json", by_alias=True)
        except TypeError:
            dumped = model_dump()
        if isinstance(dumped, Mapping):
            return dict(dumped)
        return None
    if isinstance(section, Mapping):
        return dict(section)
    return None
