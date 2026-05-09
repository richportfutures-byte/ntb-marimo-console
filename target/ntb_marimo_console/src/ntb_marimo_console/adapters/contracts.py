from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, TypedDict


JsonDict = dict[str, object]
ContractSymbol = Literal["ES", "NQ", "CL", "ZN", "6E", "MGC"]
RuntimeMode = Literal["fixture_demo", "preserved_engine"]
LIVE_OBSERVABLE_FIELD_PATHS: tuple[str, ...] = (
    "contract",
    "timestamp_et",
    "market.current_price",
    "market.cumulative_delta",
    "market.bar_5m_close",
    "market.bar_5m_close_count_at_or_beyond_level",
    "cross_asset.breadth.current_advancers_pct",
    "cross_asset.index_cash_tone",
    "cross_asset.dxy",
    "cross_asset.cash_10y_yield",
    "volatility_context.current_volume_vs_average",
    "session_sequence.asia_complete",
    "session_sequence.london_complete",
    "session_sequence.ny_pending",
    "macro_context.macro_release_context_populated",
    "macro_context.fear_catalyst_state",
    "macro_context.tier1_lockout_active",
    "macro_context.eia_lockout_active",
)


class PipelineSummary(TypedDict):
    contract: str
    termination_stage: str
    final_decision: str
    sufficiency_gate_status: str | None
    contract_analysis_outcome: str | None
    proposed_setup_outcome: str | None
    risk_authorization_decision: str | None


class RunHistoryRowRecord(TypedDict):
    run_id: str
    logged_at: str
    contract: str
    session_date: str | None
    run_type: str
    final_decision: str | None
    termination_stage: str | None
    stage_d_decision: str | None
    notes: str


class AuditReplayRecord(TypedDict):
    source: str
    stage_e_live_backend: bool
    replay_available: bool
    last_run_id: str | None
    last_final_decision: str | None


@dataclass(frozen=True)
class SessionTarget:
    contract: ContractSymbol
    session_date: str


@dataclass(frozen=True)
class RuntimeSelection:
    mode: RuntimeMode
    profile_id: str
    session: SessionTarget


@dataclass(frozen=True)
class PreMarketArtifacts:
    packet: JsonDict
    brief: JsonDict


@dataclass(frozen=True)
class WatchmanSweepRequest:
    packet_bundle: JsonDict
    readiness_trigger: JsonDict


@dataclass(frozen=True)
class PipelineQueryRequest:
    contract: ContractSymbol
    packet: JsonDict
    evaluation_timestamp_iso: str | None = None
    readiness_trigger: JsonDict | None = None


@dataclass(frozen=True)
class OperatorRuntimeInputs:
    selection: RuntimeSelection
    premarket: WatchmanSweepRequest
    live_snapshot: JsonDict
    pipeline_query: PipelineQueryRequest


class WatchmanContextLike(Protocol):
    contract: str
    event_risk_state: str
    vwap_posture_state: str
    value_location_state: str
    level_proximity_state: str
    hard_lockout_flags: list[str]
    awareness_flags: list[str]
    missing_inputs: list[str]


@dataclass(frozen=True)
class TriggerSpec:
    """Frozen trigger contract for Phase 1 query gating.

    Dependencies must be explicitly declared in `required_live_field_paths`.
    """

    id: str
    predicate: str
    required_live_field_paths: tuple[str, ...]
    source_brief_trigger_id: str


@dataclass(frozen=True)
class TriggerEvaluation:
    """Deterministic trigger-evaluation result.

    Invalid triggers fail closed (`is_true=False`).
    """

    trigger_id: str
    is_valid: bool
    is_true: bool
    missing_fields: tuple[str, ...]
    invalid_reasons: tuple[str, ...]


class PipelineBackend(Protocol):
    """Engine boundary consumed by the console.

    This protocol intentionally wraps only preserved execution-facade surfaces
    allowed by the Phase 1 freeze.
    """

    def sweep_watchman(
        self,
        request: WatchmanSweepRequest,
    ) -> dict[str, WatchmanContextLike]: ...

    def run_pipeline(self, request: PipelineQueryRequest) -> object: ...

    def summarize_pipeline_result(self, result: object) -> PipelineSummary: ...


class PreMarketArtifactStore(Protocol):
    """Read-only access to pre-market packet/brief artifacts."""

    def load(self, session: SessionTarget) -> PreMarketArtifacts: ...


class RunHistoryStore(Protocol):
    """Read-only access to bounded run-history rows."""

    def list_rows(self, session: SessionTarget) -> list[RunHistoryRowRecord]: ...


class AuditReplayStore(Protocol):
    """Read-only access to bounded audit/replay state."""

    def load_replay(self, session: SessionTarget) -> AuditReplayRecord: ...
