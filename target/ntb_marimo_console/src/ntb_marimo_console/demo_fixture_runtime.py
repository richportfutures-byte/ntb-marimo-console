from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from .adapters.audit_replay_store import FixtureAuditReplayStore
from .adapters.premarket_store import FixturePreMarketArtifactStore
from .adapters.run_history_store import FixtureRunHistoryStore
from .adapters.trigger_evaluator import TriggerEvaluator
from .adapters.contracts import (
    JsonDict,
    OperatorRuntimeInputs,
    PipelineBackend,
    PipelineQueryRequest,
    PipelineSummary,
    RuntimeMode,
    RuntimeSelection,
    SessionTarget,
    WatchmanContextLike,
    WatchmanSweepRequest,
)
from .app import Phase1AppDependencies, build_phase1_app
from .runtime_profiles import RuntimeProfile, default_profile_id_for_mode, get_runtime_profile


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
    dependencies = build_phase1_dependencies(artifacts_root)

    return build_phase1_app(backend=backend, inputs=inputs, dependencies=dependencies)


def build_phase1_dependencies(fixtures_root: str | Path) -> Phase1AppDependencies:
    root = Path(fixtures_root)
    run_history_store = FixtureRunHistoryStore(root)
    return Phase1AppDependencies(
        premarket_store=FixturePreMarketArtifactStore(root),
        run_history_store=run_history_store,
        audit_replay_store=FixtureAuditReplayStore(run_history_store),
        trigger_evaluator=TriggerEvaluator(),
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
