from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from .contracts import (
    PipelineBackend,
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
