from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping
from typing import Final

from .adapters.contracts import ContractSymbol, JsonDict, RuntimeMode


class RuntimeProfileError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeProfile:
    profile_id: str
    runtime_mode: RuntimeMode
    contract: ContractSymbol
    session_date: str
    evaluation_timestamp_iso: str
    artifact_root_relative: Path
    artifact_contract_dir: str
    readiness_trigger: JsonDict
    default_model_adapter_ref: str | None = None

    def resolve_artifact_root(self, fixtures_root: str | Path) -> Path:
        return Path(fixtures_root) / self.artifact_root_relative

    def premarket_packet_path(self, artifacts_root: str | Path) -> Path:
        return (
            Path(artifacts_root)
            / "premarket"
            / self.artifact_contract_dir
            / self.session_date
            / "premarket_packet.json"
        )

    def premarket_brief_path(self, artifacts_root: str | Path) -> Path:
        return (
            Path(artifacts_root)
            / "premarket"
            / self.artifact_contract_dir
            / self.session_date
            / "premarket_brief.ready.json"
        )

    def live_snapshot_path(self, artifacts_root: str | Path, *, lockout: bool) -> Path:
        snapshot_name = "trigger_false.json" if lockout else "trigger_true.json"
        return Path(artifacts_root) / "observables" / self.artifact_contract_dir / snapshot_name

    def watchman_context_path(self, artifacts_root: str | Path, *, lockout: bool) -> Path:
        filename = "watchman_context.locked_out.json" if lockout else "watchman_context.ready.json"
        return Path(artifacts_root) / "watchman" / self.artifact_contract_dir / filename

    def packet_bundle_path(self, artifacts_root: str | Path) -> Path:
        return Path(artifacts_root) / "pipeline" / self.artifact_contract_dir / "packet_bundle.watchman.json"

    def pipeline_query_path(self, artifacts_root: str | Path) -> Path:
        return Path(artifacts_root) / "pipeline" / self.artifact_contract_dir / "historical_packet.query.json"

    def pipeline_result_path(self, artifacts_root: str | Path) -> Path:
        return Path(artifacts_root) / "pipeline" / self.artifact_contract_dir / "pipeline_result.no_trade.json"


PROFILE_REGISTRY: Final[dict[str, RuntimeProfile]] = {
    "fixture_es_demo": RuntimeProfile(
        profile_id="fixture_es_demo",
        runtime_mode="fixture_demo",
        contract="ES",
        session_date="2026-03-25",
        evaluation_timestamp_iso="2026-03-25T09:35:00-04:00",
        artifact_root_relative=Path("."),
        artifact_contract_dir="ES",
        readiness_trigger={"trigger_family": "price_level_touch", "price_level": 5604.0},
    ),
    "preserved_es_phase1": RuntimeProfile(
        profile_id="preserved_es_phase1",
        runtime_mode="preserved_engine",
        contract="ES",
        session_date="2026-03-25",
        evaluation_timestamp_iso="2026-03-25T09:35:00-04:00",
        artifact_root_relative=Path("."),
        artifact_contract_dir="ES",
        readiness_trigger={"trigger_family": "price_level_touch", "price_level": 5604.0},
        default_model_adapter_ref="ntb_marimo_console.preserved_fixture_adapter:adapter",
    ),
    "preserved_zn_phase1": RuntimeProfile(
        profile_id="preserved_zn_phase1",
        runtime_mode="preserved_engine",
        contract="ZN",
        session_date="2026-01-14",
        evaluation_timestamp_iso="2026-01-14T10:05:00-05:00",
        artifact_root_relative=Path("."),
        artifact_contract_dir="ZN",
        readiness_trigger={"trigger_family": "price_level_touch", "price_level": 110.40625},
        default_model_adapter_ref="ntb_marimo_console.preserved_fixture_adapter:adapter_zn",
    ),
    "preserved_cl_phase1": RuntimeProfile(
        profile_id="preserved_cl_phase1",
        runtime_mode="preserved_engine",
        contract="CL",
        session_date="2026-01-14",
        evaluation_timestamp_iso="2026-01-14T09:05:00-05:00",
        artifact_root_relative=Path("."),
        artifact_contract_dir="CL",
        readiness_trigger={"trigger_family": "price_level_touch", "price_level": 73.35},
        default_model_adapter_ref="ntb_marimo_console.preserved_fixture_adapter:adapter_cl",
    ),
}

DEFAULT_PROFILE_ID_BY_MODE: Final[dict[RuntimeMode, str]] = {
    "fixture_demo": "fixture_es_demo",
    "preserved_engine": "preserved_es_phase1",
}


def validate_runtime_profile(profile: RuntimeProfile) -> RuntimeProfile:
    if not profile.profile_id.strip():
        raise RuntimeProfileError("Runtime profile definitions require a non-empty profile_id.")
    if profile.artifact_root_relative.is_absolute():
        raise RuntimeProfileError(
            f"Runtime profile {profile.profile_id} must use a relative artifact_root_relative path."
        )
    if not profile.artifact_contract_dir.strip():
        raise RuntimeProfileError(
            f"Runtime profile {profile.profile_id} must define artifact_contract_dir."
        )
    if not profile.session_date.strip():
        raise RuntimeProfileError(
            f"Runtime profile {profile.profile_id} must define session_date."
        )
    if not profile.evaluation_timestamp_iso.strip():
        raise RuntimeProfileError(
            f"Runtime profile {profile.profile_id} must define evaluation_timestamp_iso."
        )
    if not profile.readiness_trigger:
        raise RuntimeProfileError(
            f"Runtime profile {profile.profile_id} must define readiness_trigger."
        )
    if profile.runtime_mode == "preserved_engine" and not profile.default_model_adapter_ref:
        raise RuntimeProfileError(
            f"Preserved runtime profile {profile.profile_id} requires default_model_adapter_ref."
        )
    return profile


def default_profile_id_for_mode(mode: RuntimeMode) -> str:
    return DEFAULT_PROFILE_ID_BY_MODE[mode]


def get_runtime_profile(
    profile_id: str,
    *,
    registry: Mapping[str, RuntimeProfile] | None = None,
) -> RuntimeProfile:
    profiles = registry if registry is not None else PROFILE_REGISTRY
    try:
        profile = profiles[profile_id]
    except KeyError as exc:
        supported = ", ".join(sorted(profiles))
        raise RuntimeProfileError(
            f"Unsupported runtime profile: {profile_id}. Supported profiles: {supported}"
        ) from exc

    validated = validate_runtime_profile(profile)
    if validated.profile_id != profile_id:
        raise RuntimeProfileError(
            "Runtime profile registry key must match RuntimeProfile.profile_id exactly."
        )
    return validated


def list_runtime_profiles(
    *,
    registry: Mapping[str, RuntimeProfile] | None = None,
) -> tuple[RuntimeProfile, ...]:
    profiles = registry if registry is not None else PROFILE_REGISTRY
    return tuple(get_runtime_profile(profile_id, registry=profiles) for profile_id in sorted(profiles))


def list_preserved_runtime_profiles(
    *,
    registry: Mapping[str, RuntimeProfile] | None = None,
) -> tuple[RuntimeProfile, ...]:
    return tuple(
        profile
        for profile in list_runtime_profiles(registry=registry)
        if profile.runtime_mode == "preserved_engine"
    )
