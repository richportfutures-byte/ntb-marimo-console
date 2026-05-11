from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from typing import cast

from .adapters.schwab_futures_market_data import SchwabFuturesMarketDataAdapter
from .adapters import PreservedEngineBackend
from .adapters.contracts import OperatorRuntimeInputs, PipelineBackend, RuntimeMode
from .app import (
    Phase1AppDependencies,
    Phase1BuildArtifacts,
    build_phase1_payload,
    build_phase1_shell_from_artifacts,
)
from .demo_fixture_runtime import (
    FixturePipelineBackend,
    build_phase1_dependencies,
    build_runtime_inputs_for_profile,
    default_fixtures_root,
    load_json_object,
)
from .market_data import FuturesQuote, FuturesQuoteServiceConfig
from .runtime_profiles import RuntimeProfile, default_profile_id_for_mode, get_runtime_profile


class PreservedModeInitializationError(RuntimeError):
    pass


class RuntimeDataUnavailableError(RuntimeError):
    pass


FixtureQuoteFactory = Callable[[FuturesQuoteServiceConfig], FuturesQuote | None]
SchwabAdapterFactory = Callable[[FuturesQuoteServiceConfig], SchwabFuturesMarketDataAdapter]


@dataclass(frozen=True)
class RuntimeAssembly:
    profile: RuntimeProfile
    artifacts_root: Path
    backend: PipelineBackend
    inputs: OperatorRuntimeInputs
    dependencies: Phase1AppDependencies


_LEGACY_RUNTIME_MODE_ALIASES = {
    "preserved_engine_es": "preserved_engine",
}


def parse_runtime_mode(value: str) -> RuntimeMode:
    normalized = _LEGACY_RUNTIME_MODE_ALIASES.get(
        value.strip().lower(),
        value.strip().lower(),
    )
    if normalized not in {"fixture_demo", "preserved_engine"}:
        raise ValueError(f"Unsupported runtime mode: {value}")
    return cast(RuntimeMode, normalized)


def build_backend_for_profile(
    *,
    profile: RuntimeProfile,
    fixtures_root: str | Path,
    lockout: bool = False,
    model_adapter: object | None = None,
) -> PipelineBackend:
    artifacts_root = profile.resolve_artifact_root(fixtures_root)
    if profile.runtime_mode == "fixture_demo":
        return FixturePipelineBackend(
            artifacts_root,
            profile=profile,
            lockout=lockout,
        )

    if profile.runtime_mode != "preserved_engine":
        raise ValueError(f"Unsupported runtime mode: {profile.runtime_mode}")

    if model_adapter is None:
        raise PreservedModeInitializationError(
            f"Runtime profile {profile.profile_id} requires an explicit model adapter injection."
        )
    generate_structured = getattr(model_adapter, "generate_structured", None)
    if not callable(generate_structured):
        raise PreservedModeInitializationError(
            "Injected model adapter must implement callable generate_structured(...)."
        )

    try:
        return PreservedEngineBackend(
            model_adapter=model_adapter,
        )
    except Exception as exc:  # pragma: no cover - preserves fail-closed behavior
        raise PreservedModeInitializationError(
            f"Failed to initialize preserved backend for profile {profile.profile_id}."
        ) from exc


def build_backend_for_mode(
    *,
    mode: RuntimeMode,
    fixtures_root: str | Path,
    lockout: bool = False,
    model_adapter: object | None = None,
) -> PipelineBackend:
    profile = get_runtime_profile(default_profile_id_for_mode(mode))
    return build_backend_for_profile(
        profile=profile,
        fixtures_root=fixtures_root,
        lockout=lockout,
        model_adapter=model_adapter,
    )


def validate_preserved_runtime_inputs(
    inputs: OperatorRuntimeInputs,
    *,
    profile: RuntimeProfile,
) -> None:
    contract = inputs.selection.session.contract

    packet_bundle = inputs.premarket.packet_bundle
    shared = packet_bundle.get("shared")
    contracts = packet_bundle.get("contracts")
    if not isinstance(shared, Mapping) or not isinstance(contracts, Mapping):
        raise RuntimeDataUnavailableError(
            f"Runtime profile {profile.profile_id} requires packet bundle artifacts with object-valued shared and contracts sections."
        )
    if "challenge_state" not in shared or "attached_visuals" not in shared:
        raise RuntimeDataUnavailableError(
            f"Runtime profile {profile.profile_id} requires packet bundle shared.challenge_state and shared.attached_visuals."
        )

    contract_payload = contracts.get(contract)
    if not isinstance(contract_payload, Mapping):
        raise RuntimeDataUnavailableError(
            f"Runtime profile {profile.profile_id} requires packet bundle data for contract {contract}."
        )
    for key in ("contract_metadata", "market_packet", "contract_specific_extension"):
        if key not in contract_payload:
            raise RuntimeDataUnavailableError(
                f"Runtime profile {profile.profile_id} requires packet bundle contract payload field: {key}."
            )

    packet = inputs.pipeline_query.packet
    required_packet_keys = (
        "challenge_state",
        "attached_visuals",
        "contract_metadata",
        "market_packet",
        "contract_specific_extension",
    )
    missing_packet_keys = [key for key in required_packet_keys if key not in packet]
    if missing_packet_keys:
        missing_text = ", ".join(missing_packet_keys)
        raise RuntimeDataUnavailableError(
            f"Runtime profile {profile.profile_id} requires full historical packet query artifacts; "
            f"missing: {missing_text}."
        )


def build_app_shell_for_profile(
    *,
    profile: RuntimeProfile,
    fixtures_root: str | Path | None = None,
    lockout: bool = False,
    model_adapter: object | None = None,
    market_data_config: FuturesQuoteServiceConfig | None = None,
    market_data_fixture_quote: FuturesQuote | None = None,
    market_data_fixture_quote_factory: FixtureQuoteFactory | None = None,
    market_data_schwab_adapter: SchwabFuturesMarketDataAdapter | None = None,
    market_data_schwab_adapter_factory: SchwabAdapterFactory | None = None,
    query_action_requested: bool = True,
) -> dict[str, object]:
    assembly = assemble_runtime_for_profile(
        profile=profile,
        fixtures_root=fixtures_root,
        lockout=lockout,
        model_adapter=model_adapter,
        market_data_config=market_data_config,
        market_data_fixture_quote=market_data_fixture_quote,
        market_data_fixture_quote_factory=market_data_fixture_quote_factory,
        market_data_schwab_adapter=market_data_schwab_adapter,
        market_data_schwab_adapter_factory=market_data_schwab_adapter_factory,
    )
    return build_app_shell_from_assembly(
        assembly,
        query_action_requested=query_action_requested,
    )


def build_phase1_artifacts_for_profile(
    *,
    profile: RuntimeProfile,
    fixtures_root: str | Path | None = None,
    lockout: bool = False,
    model_adapter: object | None = None,
    market_data_config: FuturesQuoteServiceConfig | None = None,
    market_data_fixture_quote: FuturesQuote | None = None,
    market_data_fixture_quote_factory: FixtureQuoteFactory | None = None,
    market_data_schwab_adapter: SchwabFuturesMarketDataAdapter | None = None,
    market_data_schwab_adapter_factory: SchwabAdapterFactory | None = None,
    query_action_requested: bool = True,
) -> Phase1BuildArtifacts:
    assembly = assemble_runtime_for_profile(
        profile=profile,
        fixtures_root=fixtures_root,
        lockout=lockout,
        model_adapter=model_adapter,
        market_data_config=market_data_config,
        market_data_fixture_quote=market_data_fixture_quote,
        market_data_fixture_quote_factory=market_data_fixture_quote_factory,
        market_data_schwab_adapter=market_data_schwab_adapter,
        market_data_schwab_adapter_factory=market_data_schwab_adapter_factory,
    )
    return build_phase1_artifacts_from_assembly(
        assembly,
        query_action_requested=query_action_requested,
    )


def assemble_runtime_for_profile(
    *,
    profile: RuntimeProfile,
    fixtures_root: str | Path | None = None,
    lockout: bool = False,
    model_adapter: object | None = None,
    market_data_config: FuturesQuoteServiceConfig | None = None,
    market_data_fixture_quote: FuturesQuote | None = None,
    market_data_fixture_quote_factory: FixtureQuoteFactory | None = None,
    market_data_schwab_adapter: SchwabFuturesMarketDataAdapter | None = None,
    market_data_schwab_adapter_factory: SchwabAdapterFactory | None = None,
) -> RuntimeAssembly:
    base_root = Path(fixtures_root) if fixtures_root is not None else default_fixtures_root()
    artifacts_root = profile.resolve_artifact_root(base_root)

    packet_bundle: dict[str, object] | None = None
    if profile.runtime_mode == "preserved_engine":
        try:
            packet_bundle = load_json_object(profile.packet_bundle_path(artifacts_root))
        except Exception as exc:
            raise RuntimeDataUnavailableError(
                f"Runtime profile {profile.profile_id} requires upstream packet_bundle.watchman.json artifacts."
            ) from exc

    inputs = build_runtime_inputs_for_profile(
        artifacts_root,
        profile=profile,
        lockout=lockout,
        packet_bundle=packet_bundle,
    )
    if profile.runtime_mode == "preserved_engine":
        validate_preserved_runtime_inputs(inputs, profile=profile)
    backend = build_backend_for_profile(
        profile=profile,
        fixtures_root=base_root,
        lockout=lockout,
        model_adapter=model_adapter,
    )
    dependencies = build_phase1_dependencies(
        artifacts_root,
        profile=profile,
        market_data_config=market_data_config,
        market_data_fixture_quote=market_data_fixture_quote,
        market_data_fixture_quote_factory=market_data_fixture_quote_factory,
        market_data_schwab_adapter=market_data_schwab_adapter,
        market_data_schwab_adapter_factory=market_data_schwab_adapter_factory,
    )
    return RuntimeAssembly(
        profile=profile,
        artifacts_root=artifacts_root,
        backend=backend,
        inputs=inputs,
        dependencies=dependencies,
    )


def build_app_shell_from_assembly(
    assembly: RuntimeAssembly,
    *,
    query_action_requested: bool = True,
) -> dict[str, object]:
    artifacts = build_phase1_artifacts_from_assembly(
        assembly,
        query_action_requested=query_action_requested,
    )
    return build_phase1_shell_from_artifacts(
        artifacts,
        inputs=assembly.inputs,
        query_action_requested=query_action_requested,
    )


def build_phase1_artifacts_from_assembly(
    assembly: RuntimeAssembly,
    *,
    query_action_requested: bool = True,
) -> Phase1BuildArtifacts:
    return build_phase1_payload(
        backend=assembly.backend,
        inputs=assembly.inputs,
        dependencies=assembly.dependencies,
        query_action_requested=query_action_requested,
    )


def build_app_shell_for_profile_id(
    *,
    profile_id: str,
    fixtures_root: str | Path | None = None,
    lockout: bool = False,
    model_adapter: object | None = None,
    market_data_config: FuturesQuoteServiceConfig | None = None,
    market_data_fixture_quote: FuturesQuote | None = None,
    market_data_fixture_quote_factory: FixtureQuoteFactory | None = None,
    market_data_schwab_adapter: SchwabFuturesMarketDataAdapter | None = None,
    market_data_schwab_adapter_factory: SchwabAdapterFactory | None = None,
    query_action_requested: bool = True,
) -> dict[str, object]:
    profile = get_runtime_profile(profile_id)
    return build_app_shell_for_profile(
        profile=profile,
        fixtures_root=fixtures_root,
        lockout=lockout,
        model_adapter=model_adapter,
        market_data_config=market_data_config,
        market_data_fixture_quote=market_data_fixture_quote,
        market_data_fixture_quote_factory=market_data_fixture_quote_factory,
        market_data_schwab_adapter=market_data_schwab_adapter,
        market_data_schwab_adapter_factory=market_data_schwab_adapter_factory,
        query_action_requested=query_action_requested,
    )


def build_app_shell_for_mode(
    *,
    mode: RuntimeMode,
    fixtures_root: str | Path | None = None,
    lockout: bool = False,
    model_adapter: object | None = None,
    market_data_config: FuturesQuoteServiceConfig | None = None,
    market_data_fixture_quote: FuturesQuote | None = None,
    market_data_fixture_quote_factory: FixtureQuoteFactory | None = None,
    market_data_schwab_adapter: SchwabFuturesMarketDataAdapter | None = None,
    market_data_schwab_adapter_factory: SchwabAdapterFactory | None = None,
    query_action_requested: bool = True,
) -> dict[str, object]:
    profile = get_runtime_profile(default_profile_id_for_mode(mode))
    return build_app_shell_for_profile(
        profile=profile,
        fixtures_root=fixtures_root,
        lockout=lockout,
        model_adapter=model_adapter,
        market_data_config=market_data_config,
        market_data_fixture_quote=market_data_fixture_quote,
        market_data_fixture_quote_factory=market_data_fixture_quote_factory,
        market_data_schwab_adapter=market_data_schwab_adapter,
        market_data_schwab_adapter_factory=market_data_schwab_adapter_factory,
        query_action_requested=query_action_requested,
    )


def build_es_app_shell_for_mode(
    *,
    mode: RuntimeMode,
    fixtures_root: str | Path | None = None,
    lockout: bool = False,
    model_adapter: object | None = None,
    market_data_config: FuturesQuoteServiceConfig | None = None,
    market_data_fixture_quote: FuturesQuote | None = None,
    market_data_fixture_quote_factory: FixtureQuoteFactory | None = None,
    market_data_schwab_adapter: SchwabFuturesMarketDataAdapter | None = None,
    market_data_schwab_adapter_factory: SchwabAdapterFactory | None = None,
    query_action_requested: bool = True,
) -> dict[str, object]:
    """Backward-compatible Phase 1 ES alias."""

    return build_app_shell_for_mode(
        mode=mode,
        fixtures_root=fixtures_root,
        lockout=lockout,
        model_adapter=model_adapter,
        market_data_config=market_data_config,
        market_data_fixture_quote=market_data_fixture_quote,
        market_data_fixture_quote_factory=market_data_fixture_quote_factory,
        market_data_schwab_adapter=market_data_schwab_adapter,
        market_data_schwab_adapter_factory=market_data_schwab_adapter_factory,
        query_action_requested=query_action_requested,
    )
