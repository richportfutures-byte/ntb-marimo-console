from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters.contracts import JsonDict
from .runtime_profiles import (
    RuntimeProfile,
    default_profile_id_for_mode,
    get_runtime_profile,
    list_preserved_runtime_profiles,
)


@dataclass(frozen=True)
class PreservedFixtureArtifacts:
    packet_bundle: JsonDict
    query_packet: JsonDict


class PreservedFixtureNormalizationError(RuntimeError):
    pass


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[4]


def authoritative_seed_bundle_path() -> Path:
    return workspace_root() / "source" / "ntb_engine" / "tests" / "fixtures" / "packets.valid.json"


def build_preserved_fixture_artifacts(
    fixtures_root: str | Path,
    *,
    profile: RuntimeProfile,
) -> PreservedFixtureArtifacts:
    if profile.runtime_mode != "preserved_engine":
        raise PreservedFixtureNormalizationError(
            f"Runtime profile {profile.profile_id} is not a preserved-engine profile."
        )

    artifacts_root = profile.resolve_artifact_root(fixtures_root)
    seed_bundle = _load_json_object(authoritative_seed_bundle_path())
    target_premarket = _load_json_object(profile.premarket_packet_path(artifacts_root))
    target_snapshot = _load_json_object(profile.live_snapshot_path(artifacts_root, lockout=False))

    shared = _require_mapping(seed_bundle.get("shared"), "shared", "authoritative seed bundle")
    contracts = _require_mapping(seed_bundle.get("contracts"), "contracts", "authoritative seed bundle")
    seed_contract_payload = _require_mapping(
        contracts.get(profile.contract),
        profile.contract,
        "authoritative seed bundle contracts",
    )

    contract_metadata = copy.deepcopy(
        _require_mapping(
            seed_contract_payload.get("contract_metadata"),
            "contract_metadata",
            f"{profile.contract} seed contract payload",
        )
    )
    market_packet = copy.deepcopy(
        _require_mapping(
            seed_contract_payload.get("market_packet"),
            "market_packet",
            f"{profile.contract} seed contract payload",
        )
    )
    contract_specific_extension = copy.deepcopy(
        _require_mapping(
            seed_contract_payload.get("contract_specific_extension"),
            "contract_specific_extension",
            f"{profile.contract} seed contract payload",
        )
    )
    challenge_state = copy.deepcopy(
        _require_mapping(shared.get("challenge_state"), "challenge_state", "authoritative seed shared payload")
    )
    attached_visuals = copy.deepcopy(
        _require_mapping(shared.get("attached_visuals"), "attached_visuals", "authoritative seed shared payload")
    )

    _validate_target_overlay_inputs(target_premarket, target_snapshot, profile=profile)
    _apply_overlay(
        profile=profile,
        market_packet=market_packet,
        contract_specific_extension=contract_specific_extension,
        target_premarket=target_premarket,
        target_snapshot=target_snapshot,
    )

    packet_bundle: JsonDict = {
        "shared": {
            "challenge_state": challenge_state,
            "attached_visuals": attached_visuals,
        },
        "contracts": {
            profile.contract: {
                "contract_metadata": contract_metadata,
                "market_packet": market_packet,
                "contract_specific_extension": contract_specific_extension,
            }
        },
    }
    query_packet: JsonDict = {
        "$schema": "historical_packet_v1",
        "challenge_state": copy.deepcopy(challenge_state),
        "attached_visuals": copy.deepcopy(attached_visuals),
        "contract_metadata": copy.deepcopy(contract_metadata),
        "market_packet": copy.deepcopy(market_packet),
        "contract_specific_extension": copy.deepcopy(contract_specific_extension),
    }
    return PreservedFixtureArtifacts(
        packet_bundle=packet_bundle,
        query_packet=query_packet,
    )


def write_preserved_fixture_artifacts(
    fixtures_root: str | Path,
    *,
    profile: RuntimeProfile,
) -> PreservedFixtureArtifacts:
    artifacts_root = profile.resolve_artifact_root(fixtures_root)
    artifacts = build_preserved_fixture_artifacts(fixtures_root, profile=profile)
    _write_json(profile.packet_bundle_path(artifacts_root), artifacts.packet_bundle)
    _write_json(profile.pipeline_query_path(artifacts_root), artifacts.query_packet)
    return artifacts


def refresh_preserved_fixture_artifacts(
    fixtures_root: str | Path,
    *,
    profiles: tuple[RuntimeProfile, ...] | None = None,
) -> dict[str, PreservedFixtureArtifacts]:
    selected_profiles = profiles if profiles is not None else list_preserved_runtime_profiles()
    return {
        profile.profile_id: write_preserved_fixture_artifacts(fixtures_root, profile=profile)
        for profile in selected_profiles
    }


def build_preserved_es_fixture_artifacts(fixtures_root: str | Path) -> PreservedFixtureArtifacts:
    profile = get_runtime_profile(default_profile_id_for_mode("preserved_engine"))
    return build_preserved_fixture_artifacts(fixtures_root, profile=profile)


def write_preserved_es_fixture_artifacts(fixtures_root: str | Path) -> PreservedFixtureArtifacts:
    profile = get_runtime_profile(default_profile_id_for_mode("preserved_engine"))
    return write_preserved_fixture_artifacts(fixtures_root, profile=profile)


def _apply_overlay(
    *,
    profile: RuntimeProfile,
    market_packet: JsonDict,
    contract_specific_extension: JsonDict,
    target_premarket: JsonDict,
    target_snapshot: JsonDict,
) -> None:
    prior_day = _require_mapping(target_premarket.get("prior_day"), "prior_day", "target pre-market packet")
    current_session = target_premarket.get("current_session")
    current_session_payload = current_session if isinstance(current_session, dict) else None
    snapshot_market = _require_mapping(target_snapshot.get("market"), "market", "target live snapshot")

    market_packet["timestamp"] = _require_str(target_snapshot.get("timestamp_et"), "timestamp_et", "target live snapshot")
    market_packet["current_price"] = _require_number(
        snapshot_market.get("current_price"),
        "market.current_price",
        "target live snapshot",
    )
    market_packet["cumulative_delta"] = _require_number(
        snapshot_market.get("cumulative_delta"),
        "market.cumulative_delta",
        "target live snapshot",
    )
    market_packet["prior_day_high"] = _require_number(prior_day.get("high"), "prior_day.high", "target pre-market packet")
    market_packet["prior_day_low"] = _require_number(prior_day.get("low"), "prior_day.low", "target pre-market packet")
    market_packet["prior_day_close"] = _require_number(prior_day.get("close"), "prior_day.close", "target pre-market packet")
    market_packet["previous_session_vah"] = _require_number(prior_day.get("vah"), "prior_day.vah", "target pre-market packet")
    market_packet["previous_session_val"] = _require_number(prior_day.get("val"), "prior_day.val", "target pre-market packet")
    market_packet["previous_session_poc"] = _require_number(prior_day.get("poc"), "prior_day.poc", "target pre-market packet")
    market_packet["current_session_vah"] = _session_value(
        current_session_payload,
        "vah",
        fallback=prior_day.get("vah"),
        owner="target pre-market packet",
    )
    market_packet["current_session_val"] = _session_value(
        current_session_payload,
        "val",
        fallback=prior_day.get("val"),
        owner="target pre-market packet",
    )
    market_packet["current_session_poc"] = _session_value(
        current_session_payload,
        "poc",
        fallback=prior_day.get("poc"),
        owner="target pre-market packet",
    )
    market_packet["session_range"] = _require_number(
        prior_day.get("session_range"),
        "prior_day.session_range",
        "target pre-market packet",
    )
    market_packet["vwap"] = _session_value(
        current_session_payload,
        "vwap",
        fallback=prior_day.get("poc"),
        owner="target pre-market packet",
    )
    market_packet["event_calendar_remainder"] = _retarget_event_dates(
        market_packet.get("event_calendar_remainder"),
        _require_str(target_premarket.get("session_date"), "session_date", "target pre-market packet"),
    )

    if profile.contract == "ES":
        breadth_pct = _extract_breadth_pct(target_snapshot)
        contract_specific_extension["breadth"] = (
            f"positive {breadth_pct:.0%} advancers"
            if breadth_pct >= 0.5
            else f"negative {breadth_pct:.0%} advancers"
        )


def _retarget_event_dates(events: Any, session_date: str) -> list[dict[str, Any]]:
    if not isinstance(events, list):
        raise PreservedFixtureNormalizationError("Seed market_packet.event_calendar_remainder must be a list.")
    normalized: list[dict[str, Any]] = []
    for item in events:
        event = _require_mapping(item, "event entry", "seed market packet")
        clone = copy.deepcopy(event)
        event_time = clone.get("time")
        if isinstance(event_time, str) and "T" in event_time:
            clone["time"] = session_date + event_time[event_time.index("T") :]
        normalized.append(clone)
    return normalized


def _extract_breadth_pct(target_snapshot: JsonDict) -> float:
    cross_asset = _require_mapping(target_snapshot.get("cross_asset"), "cross_asset", "target live snapshot")
    breadth = _require_mapping(cross_asset.get("breadth"), "cross_asset.breadth", "target live snapshot")
    return _require_number(
        breadth.get("current_advancers_pct"),
        "cross_asset.breadth.current_advancers_pct",
        "target live snapshot",
    )


def _session_value(
    current_session_payload: JsonDict | None,
    field_name: str,
    *,
    fallback: Any,
    owner: str,
) -> float:
    if current_session_payload is not None and field_name in current_session_payload:
        return _require_number(
            current_session_payload.get(field_name),
            f"current_session.{field_name}",
            owner,
        )
    return _require_number(
        fallback,
        f"prior_day.{field_name}",
        owner,
    )


def _validate_target_overlay_inputs(
    target_premarket: JsonDict,
    target_snapshot: JsonDict,
    *,
    profile: RuntimeProfile,
) -> None:
    contract = _require_str(target_premarket.get("contract"), "contract", "target pre-market packet")
    session_date = _require_str(target_premarket.get("session_date"), "session_date", "target pre-market packet")
    snapshot_contract = _require_str(target_snapshot.get("contract"), "contract", "target live snapshot")
    timestamp = _require_str(target_snapshot.get("timestamp_et"), "timestamp_et", "target live snapshot")

    if contract != profile.contract or snapshot_contract != profile.contract:
        raise PreservedFixtureNormalizationError(
            f"Runtime profile {profile.profile_id} is frozen to contract {profile.contract}."
        )
    if session_date != profile.session_date:
        raise PreservedFixtureNormalizationError(
            f"Runtime profile {profile.profile_id} requires session_date {profile.session_date}."
        )
    if not timestamp.startswith(session_date):
        raise PreservedFixtureNormalizationError(
            "Target live snapshot timestamp_et must align with the pre-market session date."
        )


def _load_json_object(path: Path) -> JsonDict:
    with path.open("r", encoding="utf-8") as handle:
        parsed = json.load(handle)
    if not isinstance(parsed, dict):
        raise PreservedFixtureNormalizationError(f"Expected object JSON at {path}.")
    return parsed


def _write_json(path: Path, payload: JsonDict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _require_mapping(value: Any, field_name: str, owner: str) -> JsonDict:
    if not isinstance(value, dict):
        raise PreservedFixtureNormalizationError(f"{owner} is missing object field {field_name}.")
    return value


def _require_str(value: Any, field_name: str, owner: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PreservedFixtureNormalizationError(f"{owner} is missing non-empty string field {field_name}.")
    return value


def _require_number(value: Any, field_name: str, owner: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PreservedFixtureNormalizationError(f"{owner} is missing numeric field {field_name}.")
    return float(value)
