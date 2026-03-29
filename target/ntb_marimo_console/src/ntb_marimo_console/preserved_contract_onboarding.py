from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ninjatradebuilder.pipeline import STAGE_AB_PROMPT_BY_CONTRACT

from .adapters.contracts import ContractSymbol, JsonDict, LIVE_OBSERVABLE_FIELD_PATHS
from .preserved_fixture_artifacts import write_preserved_fixture_artifacts
from .runtime_diagnostics import LaunchRequest, build_preflight_report
from .runtime_modes import build_app_shell_for_profile
from .runtime_profiles import RuntimeProfile, list_preserved_runtime_profiles

EligibilityStatus = Literal["supported_now", "viable_to_onboard_now", "blocked"]

SUPPORTED_PROFILE_CATEGORY = "supported_profile"
VIABLE_PROFILE_CATEGORY = "viable_to_onboard_now"
BLOCKED_MISSING_AUTHORITATIVE_ARTIFACTS = "blocked_missing_authoritative_artifacts"
BLOCKED_INCOMPLETE_PROFILE_TEMPLATE = "blocked_incomplete_profile_template"
BLOCKED_PROMPT_ADAPTER_UNAVAILABLE = "blocked_prompt_adapter_unavailable"
BLOCKED_UNSUPPORTED_QUERY_OBSERVABLE_CONTRACT = "blocked_unsupported_query_observable_contract"
BLOCKED_MISSING_NUMERIC_CROSS_ASSET_SOURCE = "blocked_missing_numeric_cross_asset_source"
BLOCKED_RUNTIME_PREFLIGHT = "blocked_runtime_preflight"
BLOCKED_RUNTIME_ASSEMBLY = "blocked_runtime_assembly"

_CANDIDATE_CONTRACTS: tuple[ContractSymbol, ...] = ("NQ", "CL", "6E", "MGC")
_MISSING = object()


class PreservedContractOnboardingError(RuntimeError):
    def __init__(self, *, category: str, summary: str) -> None:
        super().__init__(summary)
        self.category = category
        self.summary = summary


@dataclass(frozen=True)
class EligibilityCheck:
    name: str
    passed: bool
    category: str
    summary: str


@dataclass(frozen=True)
class ContractEligibilityResult:
    contract: ContractSymbol
    profile_id: str
    status: EligibilityStatus
    reason_category: str
    summary: str
    checks: tuple[EligibilityCheck, ...]


@dataclass(frozen=True)
class ContractEligibilitySnapshot:
    supported_now: tuple[ContractEligibilityResult, ...]
    viable_to_onboard_now: tuple[ContractEligibilityResult, ...]
    blocked: tuple[ContractEligibilityResult, ...]

    @property
    def all_results(self) -> tuple[ContractEligibilityResult, ...]:
        return (*self.supported_now, *self.viable_to_onboard_now, *self.blocked)


@dataclass(frozen=True)
class PreservedProfileTemplate:
    profile_id: str
    contract: ContractSymbol
    session_date: str
    evaluation_timestamp_iso: str
    artifact_contract_dir: str
    readiness_trigger: JsonDict
    default_model_adapter_ref: str
    source_fixture_paths: tuple[str, ...]
    required_live_field_paths: tuple[str, ...]
    premarket_packet: JsonDict
    premarket_brief: JsonDict
    live_snapshot_armed: JsonDict
    live_snapshot_lockout: JsonDict
    run_history_rows: tuple[JsonDict, ...]

    def runtime_profile(self) -> RuntimeProfile:
        return RuntimeProfile(
            profile_id=self.profile_id,
            runtime_mode="preserved_engine",
            contract=self.contract,
            session_date=self.session_date,
            evaluation_timestamp_iso=self.evaluation_timestamp_iso,
            artifact_root_relative=Path("."),
            artifact_contract_dir=self.artifact_contract_dir,
            readiness_trigger=dict(self.readiness_trigger),
            default_model_adapter_ref=self.default_model_adapter_ref,
        )

    def artifact_paths(self, fixtures_root: str | Path) -> dict[str, Path]:
        root = Path(fixtures_root)
        return {
            "pre-market packet": root
            / "premarket"
            / self.artifact_contract_dir
            / self.session_date
            / "premarket_packet.json",
            "pre-market brief": root
            / "premarket"
            / self.artifact_contract_dir
            / self.session_date
            / "premarket_brief.ready.json",
            "live snapshot (armed)": root
            / "observables"
            / self.artifact_contract_dir
            / "trigger_true.json",
            "live snapshot (lockout)": root
            / "observables"
            / self.artifact_contract_dir
            / "trigger_false.json",
            "run history": root
            / "history"
            / self.artifact_contract_dir
            / f"run_history.{self.session_date}.fixture.json",
            "packet bundle": root
            / "pipeline"
            / self.artifact_contract_dir
            / "packet_bundle.watchman.json",
            "pipeline query": root
            / "pipeline"
            / self.artifact_contract_dir
            / "historical_packet.query.json",
        }


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[4]


def default_fixtures_root() -> Path:
    return workspace_root() / "target" / "ntb_marimo_console" / "fixtures" / "golden" / "phase1"


def candidate_contracts() -> tuple[ContractSymbol, ...]:
    return _CANDIDATE_CONTRACTS


def currently_supported_preserved_contracts() -> tuple[ContractSymbol, ...]:
    return tuple(profile.contract for profile in list_preserved_runtime_profiles())


def render_profile_template_checklist(template: PreservedProfileTemplate) -> str:
    artifact_paths = template.artifact_paths(Path("<fixtures-root>"))
    lines = [
        f"Profile Template: {template.profile_id}",
        f"- Contract: {template.contract}",
        f"- Session Date: {template.session_date}",
        f"- Evaluation Timestamp: {template.evaluation_timestamp_iso}",
        "- Required profile fields:",
        "  - profile_id",
        "  - contract",
        "  - session_date",
        "  - evaluation_timestamp_iso",
        "  - artifact_contract_dir",
        "  - readiness_trigger",
        "  - default_model_adapter_ref",
        "- Required artifacts:",
    ]
    for label, path in artifact_paths.items():
        lines.append(f"  - {label}: {path.as_posix()}")
    lines.append("- Required live observable fields:")
    for field_path in template.required_live_field_paths:
        lines.append(f"  - {field_path}")
    lines.append("- Source fixtures:")
    for relative_path in template.source_fixture_paths:
        lines.append(f"  - {relative_path}")
    return "\n".join(lines)


def validate_profile_template(template: PreservedProfileTemplate) -> PreservedProfileTemplate:
    if not template.profile_id.strip():
        raise PreservedContractOnboardingError(
            category=BLOCKED_INCOMPLETE_PROFILE_TEMPLATE,
            summary="Profile template requires a non-empty profile_id.",
        )
    if template.contract != template.artifact_contract_dir:
        raise PreservedContractOnboardingError(
            category=BLOCKED_INCOMPLETE_PROFILE_TEMPLATE,
            summary="Profile template artifact_contract_dir must match the contract symbol exactly.",
        )
    if not template.session_date.strip() or not template.evaluation_timestamp_iso.startswith(template.session_date):
        raise PreservedContractOnboardingError(
            category=BLOCKED_INCOMPLETE_PROFILE_TEMPLATE,
            summary="Profile template evaluation timestamp must align with the declared session_date.",
        )
    if not template.default_model_adapter_ref.strip():
        raise PreservedContractOnboardingError(
            category=BLOCKED_INCOMPLETE_PROFILE_TEMPLATE,
            summary="Profile template requires a non-empty default_model_adapter_ref.",
        )
    if not template.source_fixture_paths:
        raise PreservedContractOnboardingError(
            category=BLOCKED_INCOMPLETE_PROFILE_TEMPLATE,
            summary="Profile template must declare authoritative source fixture paths.",
        )
    if not template.run_history_rows:
        raise PreservedContractOnboardingError(
            category=BLOCKED_INCOMPLETE_PROFILE_TEMPLATE,
            summary="Profile template requires at least one run-history row.",
        )
    for field_path in template.required_live_field_paths:
        if field_path not in LIVE_OBSERVABLE_FIELD_PATHS:
            raise PreservedContractOnboardingError(
                category=BLOCKED_UNSUPPORTED_QUERY_OBSERVABLE_CONTRACT,
                summary=(
                    f"Profile template declares query field {field_path}, which is outside the current "
                    "live observable contract."
                ),
            )

    _validate_contract_payload(template.premarket_packet, template.contract, template.session_date, "pre-market packet")
    _validate_contract_payload(template.premarket_brief, template.contract, template.session_date, "pre-market brief")
    _validate_live_snapshot(
        template.live_snapshot_armed,
        template.contract,
        template.session_date,
        template.required_live_field_paths,
        "armed live snapshot",
    )
    _validate_live_snapshot(
        template.live_snapshot_lockout,
        template.contract,
        template.session_date,
        template.required_live_field_paths,
        "lockout live snapshot",
    )
    for row in template.run_history_rows:
        if row.get("contract") != template.contract:
            raise PreservedContractOnboardingError(
                category=BLOCKED_INCOMPLETE_PROFILE_TEMPLATE,
                summary="Run-history rows must match the template contract.",
            )

    setup = _first_structural_setup(template.premarket_brief)
    trigger = _first_query_trigger(setup)
    if tuple(trigger.get("fields_used", [])) != template.required_live_field_paths:
        raise PreservedContractOnboardingError(
            category=BLOCKED_INCOMPLETE_PROFILE_TEMPLATE,
            summary="Profile template trigger fields must exactly match required_live_field_paths.",
        )
    return template


def materialize_profile_template(
    template: PreservedProfileTemplate,
    fixtures_root: str | Path,
) -> dict[str, Path]:
    validated = validate_profile_template(template)
    paths = validated.artifact_paths(fixtures_root)
    _write_json(paths["pre-market packet"], validated.premarket_packet)
    _write_json(paths["pre-market brief"], validated.premarket_brief)
    _write_json(paths["live snapshot (armed)"], validated.live_snapshot_armed)
    _write_json(paths["live snapshot (lockout)"], validated.live_snapshot_lockout)
    _write_json(paths["run history"], list(validated.run_history_rows))
    return paths


def build_contract_eligibility_snapshot(
    *,
    fixtures_root: str | Path | None = None,
) -> ContractEligibilitySnapshot:
    root = Path(fixtures_root) if fixtures_root is not None else default_fixtures_root()
    supported_now = tuple(_audit_supported_profile(profile, fixtures_root=root) for profile in list_preserved_runtime_profiles())
    supported_contracts = {result.contract for result in supported_now}
    candidate_results = tuple(
        audit_candidate_contract(
            contract,
            fixtures_root=root,
            supported_contracts=supported_contracts,
        )
        for contract in candidate_contracts()
        if contract not in supported_contracts
    )
    viable = tuple(result for result in candidate_results if result.status == "viable_to_onboard_now")
    blocked = tuple(result for result in candidate_results if result.status == "blocked")
    return ContractEligibilitySnapshot(
        supported_now=tuple(sorted(supported_now, key=lambda item: item.contract)),
        viable_to_onboard_now=tuple(sorted(viable, key=lambda item: item.contract)),
        blocked=tuple(sorted(blocked, key=lambda item: item.contract)),
    )


def audit_candidate_contract(
    contract: ContractSymbol,
    *,
    fixtures_root: str | Path | None = None,
    supported_contracts: set[ContractSymbol] | None = None,
) -> ContractEligibilityResult:
    supported = set(currently_supported_preserved_contracts()) if supported_contracts is None else set(supported_contracts)
    if contract in supported:
        profile = next(profile for profile in list_preserved_runtime_profiles() if profile.contract == contract)
        return _audit_supported_profile(profile, fixtures_root=fixtures_root)

    checks: list[EligibilityCheck] = []

    source_paths = _candidate_source_fixture_paths(contract)
    checks.append(_authoritative_artifact_check(contract, source_paths))
    checks.append(_prompt_adapter_viability_check(contract))
    checks.append(_readiness_fixture_coverage_check(contract))

    try:
        template = build_candidate_profile_template(contract)
        validate_profile_template(template)
    except PreservedContractOnboardingError as exc:
        checks.append(
            EligibilityCheck(
                name="required_metadata_completeness",
                passed=False,
                category=exc.category,
                summary=exc.summary,
            )
        )
        checks.append(
            EligibilityCheck(
                name="pipeline_packet_viability",
                passed=False,
                category=exc.category,
                summary="Pipeline packet viability did not run because the candidate template is not currently supportable.",
            )
        )
        checks.append(
            EligibilityCheck(
                name="strict_preflight",
                passed=False,
                category=exc.category,
                summary="Strict preflight did not run because the candidate template is blocked earlier in the audit.",
            )
        )
        return ContractEligibilityResult(
            contract=contract,
            profile_id=_candidate_profile_id(contract),
            status="blocked",
            reason_category=exc.category,
            summary=exc.summary,
            checks=tuple(checks),
        )

    checks.append(
        EligibilityCheck(
            name="required_metadata_completeness",
            passed=True,
            category="required_metadata_completeness",
            summary=f"Candidate template for {contract} is complete and internally consistent.",
        )
    )

    try:
        _prove_candidate_runtime_viability(template)
    except PreservedContractOnboardingError as exc:
        checks.append(
            EligibilityCheck(
                name="pipeline_packet_viability",
                passed=False,
                category=exc.category,
                summary=exc.summary,
            )
        )
        checks.append(
            EligibilityCheck(
                name="strict_preflight",
                passed=False,
                category=exc.category,
                summary="Strict preflight did not pass for the candidate template.",
            )
        )
        return ContractEligibilityResult(
            contract=contract,
            profile_id=template.profile_id,
            status="blocked",
            reason_category=exc.category,
            summary=exc.summary,
            checks=tuple(checks),
        )

    checks.append(
        EligibilityCheck(
            name="pipeline_packet_viability",
            passed=True,
            category="pipeline_packet_viability",
            summary=f"Candidate template for {contract} generates preserved packet_bundle and historical query artifacts that satisfy the current runtime contract.",
        )
    )
    checks.append(
        EligibilityCheck(
            name="strict_preflight",
            passed=True,
            category="strict_preflight",
            summary=f"Candidate template for {contract} passes strict preflight and bounded app assembly without special-case relaxation.",
        )
    )
    return ContractEligibilityResult(
        contract=contract,
        profile_id=template.profile_id,
        status="viable_to_onboard_now",
        reason_category=VIABLE_PROFILE_CATEGORY,
        summary=f"{contract} is viable to onboard now under the current preserved runtime contract.",
        checks=tuple(checks),
    )


def select_single_new_preserved_contract(
    *,
    supported_contracts: set[ContractSymbol] | None = None,
    fixtures_root: str | Path | None = None,
) -> ContractEligibilityResult | None:
    root = Path(fixtures_root) if fixtures_root is not None else default_fixtures_root()
    supported = set(currently_supported_preserved_contracts()) if supported_contracts is None else set(supported_contracts)
    viable = [
        audit_candidate_contract(contract, fixtures_root=root, supported_contracts=supported)
        for contract in candidate_contracts()
        if contract not in supported
    ]
    viable = [result for result in viable if result.status == "viable_to_onboard_now"]
    if len(viable) != 1:
        return None
    return viable[0]


def render_contract_eligibility_report(snapshot: ContractEligibilitySnapshot) -> str:
    lines: list[str] = ["Preserved Contract Eligibility Audit"]
    lines.extend(_render_group("Supported Now", snapshot.supported_now))
    lines.extend(_render_group("Viable To Onboard Now", snapshot.viable_to_onboard_now))
    lines.extend(_render_group("Blocked", snapshot.blocked))
    return "\n".join(lines)


def build_candidate_profile_template(contract: ContractSymbol) -> PreservedProfileTemplate:
    if contract == "CL":
        return _build_cl_profile_template()
    if contract == "NQ":
        raise PreservedContractOnboardingError(
            category=BLOCKED_UNSUPPORTED_QUERY_OBSERVABLE_CONTRACT,
            summary=(
                "NQ is blocked because honest query gating requires a live relative_strength_vs_es field, "
                "and that field is outside the current console observable contract."
            ),
        )
    if contract == "6E":
        raise PreservedContractOnboardingError(
            category=BLOCKED_MISSING_NUMERIC_CROSS_ASSET_SOURCE,
            summary=(
                "6E is blocked because the preserved fixtures expose only textual dxy_context, not the numeric "
                "cross_asset.dxy value needed for explicit boolean query gating."
            ),
        )
    if contract == "MGC":
        raise PreservedContractOnboardingError(
            category=BLOCKED_MISSING_NUMERIC_CROSS_ASSET_SOURCE,
            summary=(
                "MGC is blocked because the preserved fixtures expose only textual dxy_context/yield_context, not the "
                "numeric cross_asset.dxy and cross_asset.cash_10y_yield values needed for explicit boolean query gating."
            ),
        )
    raise PreservedContractOnboardingError(
        category=BLOCKED_INCOMPLETE_PROFILE_TEMPLATE,
        summary=f"Unsupported candidate contract template request: {contract}.",
    )


def _build_cl_profile_template() -> PreservedProfileTemplate:
    historical = _load_json_fixture("source/ntb_engine/tests/fixtures/compiler/cl_historical_input.valid.json")
    extension = _load_json_fixture("source/ntb_engine/tests/fixtures/compiler/cl_extension.valid.json")
    seed_bundle = _load_json_fixture("source/ntb_engine/tests/fixtures/packets.valid.json")
    contracts = seed_bundle.get("contracts")
    if not isinstance(contracts, dict):
        raise PreservedContractOnboardingError(
            category=BLOCKED_MISSING_AUTHORITATIVE_ARTIFACTS,
            summary="Seed packet bundle is missing the contracts section.",
        )
    seed_contract_payload = contracts.get("CL")
    if not isinstance(seed_contract_payload, dict):
        raise PreservedContractOnboardingError(
            category=BLOCKED_MISSING_AUTHORITATIVE_ARTIFACTS,
            summary="Seed packet bundle is missing the CL contract payload.",
        )
    seed_extension = seed_contract_payload.get("contract_specific_extension")
    if not isinstance(seed_extension, dict):
        raise PreservedContractOnboardingError(
            category=BLOCKED_MISSING_AUTHORITATIVE_ARTIFACTS,
            summary="Seed packet bundle is missing CL contract_specific_extension.",
        )
    required_live_field_paths = (
        "market.current_price",
        "market.cumulative_delta",
        "volatility_context.current_volume_vs_average",
        "macro_context.eia_lockout_active",
    )

    return PreservedProfileTemplate(
        profile_id="preserved_cl_phase1",
        contract="CL",
        session_date="2026-01-14",
        evaluation_timestamp_iso="2026-01-14T09:05:00-05:00",
        artifact_contract_dir="CL",
        readiness_trigger={"trigger_family": "price_level_touch", "price_level": 73.35},
        default_model_adapter_ref="ntb_marimo_console.preserved_fixture_adapter:adapter_cl",
        source_fixture_paths=_candidate_source_fixture_paths("CL"),
        required_live_field_paths=required_live_field_paths,
        premarket_packet={
            "contract": "CL",
            "session_date": "2026-01-14",
            "timezone": "America/New_York",
            "prior_day": {
                "high": historical["prior_day_high"],
                "low": historical["prior_day_low"],
                "close": historical["prior_day_close"],
                "poc": historical["previous_session_poc"],
                "vah": historical["previous_session_vah"],
                "val": historical["previous_session_val"],
                "session_range": historical["session_range"],
            },
            "current_session": {
                "vah": historical["current_session_vah"],
                "val": historical["current_session_val"],
                "poc": historical["current_session_poc"],
                "vwap": historical["vwap"],
            },
            "overnight": {
                "high": historical["overnight_high"],
                "low": historical["overnight_low"],
            },
            "macro_context": {
                "eia_timing": extension["eia_timing"],
                "oil_specific_headlines": extension["oil_specific_headlines"],
            },
            "volatility_context": {
                "avg_20d_session_range": historical["avg_20d_session_range"],
                "current_volume_vs_average": historical["current_volume_vs_average"],
                "realized_volatility_context": seed_extension["realized_volatility_context"],
            },
            "metadata": {
                "packet_version": "pmkt_v1",
                "generated_at": "2026-01-14T08:00:00-05:00",
                "provenance": list(_candidate_source_fixture_paths("CL")),
            },
        },
        premarket_brief={
            "contract": "CL",
            "session_date": "2026-01-14",
            "status": "READY",
            "version": "pmkt_brief_v1",
            "structural_setups": [
                {
                    "id": "cl_setup_1",
                    "summary": "CL remains queryable above developing value while EIA is scheduled but not yet locked out.",
                    "description": "Schema-anchored CL preserved profile narrative using EIA timing, volume pace, and explicit observable query conditions.",
                    "fields_used": list(required_live_field_paths),
                    "contract_framework_labels": [
                        "volatility_primary",
                        "eia_timing",
                        "order_flow_confirmation",
                    ],
                    "stage_b_thesis_links": [
                        "cl_pre_eia_value_acceptance",
                    ],
                    "query_triggers": [
                        {
                            "id": "cl_trigger_pre_eia_acceptance",
                            "logic": "pre_eia_acceptance",
                            "description": "Trigger when CL is above developing value with positive delta, above-average volume, and no active EIA lockout.",
                            "observable_conditions": [
                                "market.current_price >= 73.35",
                                "market.cumulative_delta > 0",
                                "volatility_context.current_volume_vs_average >= 1.0",
                                "macro_context.eia_lockout_active == False",
                            ],
                            "fields_used": list(required_live_field_paths),
                        }
                    ],
                    "warnings": [
                        "If the EIA lockout activates, keep the query blocked.",
                        "If delta weakens or volume pace drops below average, keep the query blocked.",
                    ],
                }
            ],
        },
        live_snapshot_armed={
            "contract": "CL",
            "timestamp_et": "2026-01-14T09:05:00-05:00",
            "market": {
                "current_price": historical["current_price"],
                "cumulative_delta": historical["cumulative_delta"],
            },
            "volatility_context": {
                "current_volume_vs_average": historical["current_volume_vs_average"],
            },
            "macro_context": {
                "eia_lockout_active": False,
            },
        },
        live_snapshot_lockout={
            "contract": "CL",
            "timestamp_et": "2026-01-14T10:25:00-05:00",
            "market": {
                "current_price": 73.28,
                "cumulative_delta": 210.0,
            },
            "volatility_context": {
                "current_volume_vs_average": 1.18,
            },
            "macro_context": {
                "eia_lockout_active": True,
            },
        },
        run_history_rows=(
            {
                "run_id": "run_fixture_cl_001",
                "logged_at": "2026-01-14T09:05:00-05:00",
                "contract": "CL",
                "run_type": "pipeline",
                "final_decision": "NO_TRADE",
                "notes": "Fixture-backed CL preserved profile history row",
            },
        ),
    )


def _audit_supported_profile(
    profile: RuntimeProfile,
    *,
    fixtures_root: str | Path | None = None,
) -> ContractEligibilityResult:
    root = Path(fixtures_root) if fixtures_root is not None else default_fixtures_root()
    request = LaunchRequest(
        mode=profile.runtime_mode,
        profile=profile,
        lockout=False,
        fixtures_root=root,
        adapter_binding=profile.default_model_adapter_ref,
    )
    report = build_preflight_report(request)
    if not report.passed:
        failures = tuple(check for check in report.checks if not check.passed)
        summary = failures[0].summary if failures else f"Supported profile {profile.profile_id} failed preflight."
        category = failures[0].category if failures else BLOCKED_RUNTIME_PREFLIGHT
        return ContractEligibilityResult(
            contract=profile.contract,
            profile_id=profile.profile_id,
            status="blocked",
            reason_category=category,
            summary=summary,
            checks=tuple(
                EligibilityCheck(
                    name=check.name,
                    passed=check.passed,
                    category=check.category,
                    summary=check.summary,
                )
                for check in report.checks
            ),
        )
    return ContractEligibilityResult(
        contract=profile.contract,
        profile_id=profile.profile_id,
        status="supported_now",
        reason_category=SUPPORTED_PROFILE_CATEGORY,
        summary=f"{profile.profile_id} passes strict preflight under the current preserved runtime contract.",
        checks=tuple(
            EligibilityCheck(
                name=check.name,
                passed=check.passed,
                category=check.category,
                summary=check.summary,
            )
            for check in report.checks
        ),
    )


def _authoritative_artifact_check(
    contract: ContractSymbol,
    source_paths: tuple[str, ...],
) -> EligibilityCheck:
    missing = [path for path in source_paths if not (workspace_root() / path).exists()]
    if missing:
        return EligibilityCheck(
            name="authoritative_artifact_availability",
            passed=False,
            category=BLOCKED_MISSING_AUTHORITATIVE_ARTIFACTS,
            summary="Missing authoritative source fixtures: " + ", ".join(missing),
        )

    seed_bundle = _load_json_fixture("source/ntb_engine/tests/fixtures/packets.valid.json")
    contracts = seed_bundle.get("contracts")
    if not isinstance(contracts, dict):
        return EligibilityCheck(
            name="authoritative_artifact_availability",
            passed=False,
            category=BLOCKED_MISSING_AUTHORITATIVE_ARTIFACTS,
            summary="Seed packet bundle is missing the contracts section.",
        )
    contract_payload = contracts.get(contract)
    if not isinstance(contract_payload, dict):
        return EligibilityCheck(
            name="authoritative_artifact_availability",
            passed=False,
            category=BLOCKED_MISSING_AUTHORITATIVE_ARTIFACTS,
            summary=f"Seed packet bundle does not contain a contract payload for {contract}.",
        )
    missing_sections = [
        key
        for key in ("contract_metadata", "market_packet", "contract_specific_extension")
        if key not in contract_payload
    ]
    if missing_sections:
        return EligibilityCheck(
            name="authoritative_artifact_availability",
            passed=False,
            category=BLOCKED_MISSING_AUTHORITATIVE_ARTIFACTS,
            summary=f"Seed packet bundle payload for {contract} is missing: {', '.join(missing_sections)}.",
        )
    return EligibilityCheck(
        name="authoritative_artifact_availability",
        passed=True,
        category="authoritative_artifact_availability",
        summary=f"Authoritative source fixtures and seed packet coverage exist for {contract}.",
    )


def _prompt_adapter_viability_check(contract: ContractSymbol) -> EligibilityCheck:
    if contract not in STAGE_AB_PROMPT_BY_CONTRACT:
        return EligibilityCheck(
            name="prompt_adapter_viability",
            passed=False,
            category=BLOCKED_PROMPT_ADAPTER_UNAVAILABLE,
            summary=f"No Stage A/B prompt mapping exists for {contract}.",
        )
    return EligibilityCheck(
        name="prompt_adapter_viability",
        passed=True,
        category="prompt_adapter_viability",
        summary=f"Preserved engine prompt mapping exists for {contract} via prompt {STAGE_AB_PROMPT_BY_CONTRACT[contract]}.",
    )


def _readiness_fixture_coverage_check(contract: ContractSymbol) -> EligibilityCheck:
    if contract == "NQ":
        return EligibilityCheck(
            name="readiness_fixture_coverage",
            passed=False,
            category=BLOCKED_UNSUPPORTED_QUERY_OBSERVABLE_CONTRACT,
            summary=(
                "NQ readiness is blocked because honest query gating requires live relative_strength_vs_es coverage, "
                "and that observable is not part of the current console contract."
            ),
        )
    if contract == "6E":
        return EligibilityCheck(
            name="readiness_fixture_coverage",
            passed=False,
            category=BLOCKED_MISSING_NUMERIC_CROSS_ASSET_SOURCE,
            summary=(
                "6E readiness is blocked because the available fixtures provide session sequencing plus textual dxy_context, "
                "but not the numeric DXY observable needed for explicit boolean query predicates."
            ),
        )
    if contract == "MGC":
        return EligibilityCheck(
            name="readiness_fixture_coverage",
            passed=False,
            category=BLOCKED_MISSING_NUMERIC_CROSS_ASSET_SOURCE,
            summary=(
                "MGC readiness is blocked because the available fixtures provide textual DXY/yield context, "
                "but not numeric DXY or cash 10Y yield observables for explicit boolean query predicates."
            ),
        )
    return EligibilityCheck(
        name="readiness_fixture_coverage",
        passed=True,
        category="readiness_fixture_coverage",
        summary=(
            "CL has enough source coverage to express readable target artifacts and boolean query gating without adding "
            "new UI-side market logic."
        ),
    )


def _prove_candidate_runtime_viability(template: PreservedProfileTemplate) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir) / "phase1"
        materialize_profile_template(template, temp_root)
        profile = template.runtime_profile()
        write_preserved_fixture_artifacts(temp_root, profile=profile)
        request = LaunchRequest(
            mode="preserved_engine",
            profile=profile,
            lockout=False,
            fixtures_root=temp_root,
            adapter_binding=template.default_model_adapter_ref,
        )
        report = build_preflight_report(request)
        if not report.passed or report.resolved_adapter is None:
            failures = [check.summary for check in report.checks if not check.passed]
            raise PreservedContractOnboardingError(
                category=BLOCKED_RUNTIME_PREFLIGHT,
                summary="; ".join(failures) if failures else "Candidate template failed strict preflight.",
            )
        try:
            shell = build_app_shell_for_profile(
                profile=profile,
                fixtures_root=temp_root,
                model_adapter=report.resolved_adapter,
            )
        except Exception as exc:  # pragma: no cover - exercised through tests with actual engine
            raise PreservedContractOnboardingError(
                category=BLOCKED_RUNTIME_ASSEMBLY,
                summary=f"Candidate template failed bounded preserved app assembly: {exc}",
            ) from exc

        runtime = shell.get("runtime", {})
        if runtime.get("runtime_mode") != "preserved_engine" or runtime.get("profile_id") != template.profile_id:
            raise PreservedContractOnboardingError(
                category=BLOCKED_RUNTIME_ASSEMBLY,
                summary="Candidate template did not survive bounded preserved app assembly with the expected runtime identity.",
            )


def _candidate_profile_id(contract: ContractSymbol) -> str:
    return {
        "NQ": "preserved_nq_phase1",
        "CL": "preserved_cl_phase1",
        "6E": "preserved_6e_phase1",
        "MGC": "preserved_mgc_phase1",
    }[contract]


def _candidate_source_fixture_paths(contract: ContractSymbol) -> tuple[str, ...]:
    shared = ("source/ntb_engine/tests/fixtures/packets.valid.json",)
    if contract == "NQ":
        return shared + (
            "source/ntb_engine/tests/fixtures/compiler/nq_historical_input.valid.json",
            "source/ntb_engine/tests/fixtures/compiler/nq_extension.valid.json",
            "source/ntb_engine/tests/fixtures/compiler/nq_relative_strength.valid.json",
        )
    if contract == "CL":
        return shared + (
            "source/ntb_engine/tests/fixtures/compiler/cl_historical_input.valid.json",
            "source/ntb_engine/tests/fixtures/compiler/cl_extension.valid.json",
        )
    if contract == "6E":
        return shared + (
            "source/ntb_engine/tests/fixtures/compiler/6e_historical_input.valid.json",
            "source/ntb_engine/tests/fixtures/compiler/6e_extension.valid.json",
        )
    if contract == "MGC":
        return shared + (
            "source/ntb_engine/tests/fixtures/compiler/mgc_historical_input.valid.json",
            "source/ntb_engine/tests/fixtures/compiler/mgc_extension.valid.json",
        )
    raise PreservedContractOnboardingError(
        category=BLOCKED_INCOMPLETE_PROFILE_TEMPLATE,
        summary=f"Unsupported candidate contract: {contract}.",
    )


def _render_group(title: str, results: tuple[ContractEligibilityResult, ...]) -> list[str]:
    lines = [title + ":"]
    if not results:
        lines.append("- none")
        return lines
    for result in results:
        lines.append(
            f"- {result.contract} -> {result.profile_id}: {result.reason_category} | {result.summary}"
        )
    return lines


def _validate_contract_payload(
    payload: JsonDict,
    contract: ContractSymbol,
    session_date: str,
    owner: str,
) -> None:
    if payload.get("contract") != contract:
        raise PreservedContractOnboardingError(
            category=BLOCKED_INCOMPLETE_PROFILE_TEMPLATE,
            summary=f"{owner} contract must be {contract}.",
        )
    if payload.get("session_date") != session_date:
        raise PreservedContractOnboardingError(
            category=BLOCKED_INCOMPLETE_PROFILE_TEMPLATE,
            summary=f"{owner} session_date must be {session_date}.",
        )


def _validate_live_snapshot(
    payload: JsonDict,
    contract: ContractSymbol,
    session_date: str,
    required_live_field_paths: tuple[str, ...],
    owner: str,
) -> None:
    if payload.get("contract") != contract:
        raise PreservedContractOnboardingError(
            category=BLOCKED_INCOMPLETE_PROFILE_TEMPLATE,
            summary=f"{owner} contract must be {contract}.",
        )
    timestamp = payload.get("timestamp_et")
    if not isinstance(timestamp, str) or not timestamp.startswith(session_date):
        raise PreservedContractOnboardingError(
            category=BLOCKED_INCOMPLETE_PROFILE_TEMPLATE,
            summary=f"{owner} timestamp_et must align with session_date {session_date}.",
        )
    for field_path in required_live_field_paths:
        if _resolve_path(payload, field_path) is _MISSING:
            raise PreservedContractOnboardingError(
                category=BLOCKED_INCOMPLETE_PROFILE_TEMPLATE,
                summary=f"{owner} is missing required live field {field_path}.",
            )


def _first_structural_setup(brief: JsonDict) -> JsonDict:
    setups = brief.get("structural_setups")
    if not isinstance(setups, list) or not setups or not isinstance(setups[0], dict):
        raise PreservedContractOnboardingError(
            category=BLOCKED_INCOMPLETE_PROFILE_TEMPLATE,
            summary="Pre-market brief requires at least one structural setup.",
        )
    return setups[0]


def _first_query_trigger(setup: JsonDict) -> JsonDict:
    triggers = setup.get("query_triggers")
    if not isinstance(triggers, list) or not triggers or not isinstance(triggers[0], dict):
        raise PreservedContractOnboardingError(
            category=BLOCKED_INCOMPLETE_PROFILE_TEMPLATE,
            summary="Pre-market brief requires at least one query trigger.",
        )
    return triggers[0]


def _load_json_fixture(relative_path: str) -> JsonDict:
    path = workspace_root() / relative_path
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise PreservedContractOnboardingError(
            category=BLOCKED_MISSING_AUTHORITATIVE_ARTIFACTS,
            summary=f"Expected object JSON at {path}.",
        )
    return payload


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _resolve_path(payload: JsonDict, field_path: str) -> object:
    current: object = payload
    for segment in field_path.split("."):
        if not isinstance(current, dict) or segment not in current:
            return _MISSING
        current = current[segment]
    return current
