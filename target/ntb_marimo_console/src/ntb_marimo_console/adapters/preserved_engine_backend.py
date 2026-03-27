from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from .contracts import (
    PipelineBackend,
    PipelineQueryRequest,
    PipelineSummary,
    WatchmanContextLike,
    WatchmanSweepRequest,
)


class PreservedEngineBackend(PipelineBackend):
    """Thin adapter over preserved `ninjatradebuilder.execution_facade`.

    No preserved-engine logic is copied or reimplemented here.
    """

    def __init__(self, *, model_adapter: object) -> None:
        self._model_adapter = model_adapter
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
