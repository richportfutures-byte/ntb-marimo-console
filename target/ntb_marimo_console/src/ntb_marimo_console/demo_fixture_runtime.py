from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

from .adapters.schwab_futures_market_data import SchwabFuturesMarketDataAdapter
from .adapters.audit_replay_store import FixtureAuditReplayStore
from .adapters.premarket_store import FixturePreMarketArtifactStore
from .adapters.run_history_store import FixtureRunHistoryStore, JsonlRunHistoryStore
from .adapters.audit_replay_store import JsonlAuditReplayStore
from .adapters.trigger_evaluator import TriggerEvaluator
from .adapters.contracts import (
    JsonDict,
    OperatorRuntimeInputs,
    PipelineBackend,
    PipelineNarrative,
    PipelineQueryRequest,
    PipelineSummary,
    RuntimeMode,
    RuntimeSelection,
    SessionTarget,
    WatchmanContextLike,
    WatchmanSweepRequest,
)
from .app import Phase1AppDependencies, build_phase1_app
from .market_data import (
    FuturesQuote,
    FuturesQuoteServiceConfig,
    build_futures_quote_service,
    resolve_futures_quote_service_config,
)
from .runtime_profiles import RuntimeProfile, default_profile_id_for_mode, get_runtime_profile


FixtureQuoteFactory = Callable[[FuturesQuoteServiceConfig], FuturesQuote | None]
SchwabAdapterFactory = Callable[[FuturesQuoteServiceConfig], SchwabFuturesMarketDataAdapter]


class FixturePipelineBackend(PipelineBackend):
    """Fixture-backed backend for the frozen operator demo path.

    This backend is intentionally deterministic and does not use live Stage E data.
    """

    def __init__(
        self,
        fixtures_root: str | Path,
        *,
        profile: RuntimeProfile,
        lockout: bool = False,
    ) -> None:
        self._root = Path(fixtures_root)
        self._profile = profile
        self._lockout = lockout
        self._summary = self._load_json(self._profile.pipeline_result_path(self._root))
        self._narrative = self._load_optional_narrative()

    def sweep_watchman(
        self,
        request: WatchmanSweepRequest,
    ) -> dict[str, WatchmanContextLike]:
        payload = self._load_json(self._profile.watchman_context_path(self._root, lockout=self._lockout))
        context = SimpleNamespace(**payload)
        return {self._profile.contract: context}

    def run_pipeline(self, request: PipelineQueryRequest) -> object:
        return {
            "fixture_backend": True,
            "contract": request.contract,
            "evaluation_timestamp_iso": request.evaluation_timestamp_iso,
            "packet": request.packet,
        }

    def summarize_pipeline_result(self, result: object) -> PipelineSummary:
        return self._summary

    def narrate_pipeline_result(self, result: object) -> PipelineNarrative:
        """Return the optional sidecar narrative for this fixture, if shipped.

        Default fixture pipeline_result.*.json files are envelope-only and
        carry no narrative. A sibling `pipeline_result.<variant>.narrative.json`
        may optionally ship Stage B/C/D sections for renderer/tests; absence
        is the normal case and surfaces as 'unavailable' in Decision Review.
        """
        return self._narrative

    def _load_optional_narrative(self) -> PipelineNarrative:
        envelope_path = self._profile.pipeline_result_path(self._root)
        narrative_path = envelope_path.with_suffix(".narrative.json")
        if not narrative_path.exists():
            return {
                "contract_analysis": None,
                "proposed_setup": None,
                "risk_authorization": None,
            }
        payload = self._load_json(narrative_path)
        return {
            "contract_analysis": payload.get("contract_analysis") if isinstance(payload.get("contract_analysis"), dict) else None,
            "proposed_setup": payload.get("proposed_setup") if isinstance(payload.get("proposed_setup"), dict) else None,
            "risk_authorization": payload.get("risk_authorization") if isinstance(payload.get("risk_authorization"), dict) else None,
        }

    @staticmethod
    def _load_json(path: Path) -> dict[str, object]:
        with path.open("r", encoding="utf-8") as handle:
            parsed = json.load(handle)
        if not isinstance(parsed, dict):
            raise ValueError(f"Expected object JSON at {path}")
        return parsed


def build_es_fixture_app_shell(
    fixtures_root: str | Path | None = None,
    *,
    lockout: bool = False,
) -> dict[str, object]:
    """Build the ES Phase 1 app shell from frozen fixtures only."""

    profile = get_runtime_profile(default_profile_id_for_mode("fixture_demo"))
    root = Path(fixtures_root) if fixtures_root is not None else default_fixtures_root()
    artifacts_root = profile.resolve_artifact_root(root)
    backend = FixturePipelineBackend(artifacts_root, profile=profile, lockout=lockout)
    inputs = build_runtime_inputs_for_profile(artifacts_root, profile=profile, lockout=lockout)
    dependencies = build_phase1_dependencies(artifacts_root, profile=profile)

    return build_phase1_app(backend=backend, inputs=inputs, dependencies=dependencies)


def build_phase1_dependencies(
    fixtures_root: str | Path,
    *,
    profile: RuntimeProfile | None = None,
    market_data_config: FuturesQuoteServiceConfig | None = None,
    market_data_fixture_quote: FuturesQuote | None = None,
    market_data_fixture_quote_factory: FixtureQuoteFactory | None = None,
    market_data_schwab_adapter: SchwabFuturesMarketDataAdapter | None = None,
    market_data_schwab_adapter_factory: SchwabAdapterFactory | None = None,
) -> Phase1AppDependencies:
    root = Path(fixtures_root)
    if profile is not None and profile.runtime_mode == "preserved_engine":
        run_history_store = JsonlRunHistoryStore()
        audit_replay_store = JsonlAuditReplayStore()
    else:
        run_history_store = FixtureRunHistoryStore(root)
        audit_replay_store = FixtureAuditReplayStore(run_history_store)
    return Phase1AppDependencies(
        premarket_store=FixturePreMarketArtifactStore(root),
        run_history_store=run_history_store,
        audit_replay_store=audit_replay_store,
        trigger_evaluator=TriggerEvaluator(),
        market_data_service=_build_market_data_service(
            market_data_config=market_data_config,
            fixture_quote=market_data_fixture_quote,
            fixture_quote_factory=market_data_fixture_quote_factory,
            schwab_adapter=market_data_schwab_adapter,
            schwab_adapter_factory=market_data_schwab_adapter_factory,
        ),
    )


def build_es_runtime_inputs(
    fixtures_root: str | Path,
    *,
    lockout: bool = False,
    packet_bundle: JsonDict | None = None,
    mode: RuntimeMode = "fixture_demo",
) -> OperatorRuntimeInputs:
    normalized_mode = "preserved_engine" if mode == "preserved_engine_es" else mode
    profile = get_runtime_profile(default_profile_id_for_mode(normalized_mode))
    return build_runtime_inputs_for_profile(
        fixtures_root,
        profile=profile,
        lockout=lockout,
        packet_bundle=packet_bundle,
        mode=normalized_mode,
    )


def build_runtime_inputs_for_profile(
    fixtures_root: str | Path,
    *,
    profile: RuntimeProfile,
    lockout: bool = False,
    packet_bundle: JsonDict | None = None,
    mode: RuntimeMode | None = None,
) -> OperatorRuntimeInputs:
    root = Path(fixtures_root)
    selected_mode = profile.runtime_mode if mode is None else mode
    if selected_mode != profile.runtime_mode:
        raise ValueError(
            f"Runtime profile {profile.profile_id} requires runtime mode {profile.runtime_mode}, got {selected_mode}."
        )

    live_snapshot = load_json_object(profile.live_snapshot_path(root, lockout=lockout))
    query_packet = load_json_object(profile.pipeline_query_path(root))
    bundle = (
        packet_bundle
        if packet_bundle is not None
        else {"shared": {}, "contracts": {profile.contract: {}}}
    )
    session = SessionTarget(contract=profile.contract, session_date=profile.session_date)
    return OperatorRuntimeInputs(
        selection=RuntimeSelection(
            mode=selected_mode,
            profile_id=profile.profile_id,
            session=session,
        ),
        premarket=WatchmanSweepRequest(
            packet_bundle=bundle,
            readiness_trigger=dict(profile.readiness_trigger),
        ),
        live_snapshot=live_snapshot,
        pipeline_query=PipelineQueryRequest(
            contract=profile.contract,
            packet=query_packet,
            evaluation_timestamp_iso=profile.evaluation_timestamp_iso,
            readiness_trigger=dict(profile.readiness_trigger),
        ),
    )


def default_fixtures_root() -> Path:
    return Path(__file__).resolve().parents[2] / "fixtures" / "golden" / "phase1"


def load_json_object(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        parsed = json.load(handle)
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected object JSON at {path}")
    return parsed


def _market_data_target_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_market_data_service(
    *,
    market_data_config: FuturesQuoteServiceConfig | None,
    fixture_quote: FuturesQuote | None,
    fixture_quote_factory: FixtureQuoteFactory | None,
    schwab_adapter: SchwabFuturesMarketDataAdapter | None,
    schwab_adapter_factory: SchwabAdapterFactory | None,
):
    disabled_config = resolve_futures_quote_service_config(
        {},
        target_root=_market_data_target_root(),
    )
    config = market_data_config or disabled_config

    if config.failure_reason is not None or config.provider == "disabled":
        return build_futures_quote_service(config)

    if config.provider != "fixture":
        if config.provider != "schwab":
            return build_futures_quote_service(disabled_config)
        if schwab_adapter is None and schwab_adapter_factory is None:
            return build_futures_quote_service(disabled_config)
        return build_futures_quote_service(
            config,
            schwab_adapter=schwab_adapter,
            schwab_adapter_factory=schwab_adapter_factory,
        )

    if fixture_quote is None and fixture_quote_factory is None:
        return build_futures_quote_service(disabled_config)

    return build_futures_quote_service(
        config,
        fixture_quote=fixture_quote,
        fixture_quote_factory=fixture_quote_factory,
    )
