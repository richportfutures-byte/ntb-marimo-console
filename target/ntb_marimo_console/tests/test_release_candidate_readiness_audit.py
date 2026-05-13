from __future__ import annotations

from pathlib import Path

import pytest


AUDIT_DOC_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "release_candidate_readiness_audit.md"
)

LIVE_PROOF_ARTIFACT_DIRECTORY = (
    Path(__file__).resolve().parents[1] / "docs" / "live_proof"
)
LIVE_REHEARSAL_RESULT_PATH = (
    LIVE_PROOF_ARTIFACT_DIRECTORY / "five_contract_live_rehearsal_result_2026-05-12.md"
)
BLOCKED_LIVE_REHEARSAL_RESULT_PATH = (
    LIVE_PROOF_ARTIFACT_DIRECTORY / "five_contract_live_rehearsal_blocked_result_2026-05-13.md"
)
SUBSCRIPTION_ONLY_LIVE_REHEARSAL_RESULT_PATH = (
    LIVE_PROOF_ARTIFACT_DIRECTORY / "five_contract_live_rehearsal_subscription_only_result_2026-05-13.md"
)
LEVELONE_LIVE_MARKET_DATA_RESULT_PATH = (
    LIVE_PROOF_ARTIFACT_DIRECTORY / "five_contract_levelone_live_market_data_result_2026-05-13.md"
)

FORBIDDEN_SENSITIVE_FRAGMENTS = (
    "Authorization: Bearer",
    "Bearer ey",
    "access_token=",
    "refresh_token=",
    "app_key=",
    "app_secret=",
    "customerId=",
    "correlId=",
    "accountId=",
    "schwabClientCustomerId",
    "schwabClientCorrelId",
    "wss://",
    "https://streamer-api",
    "streamer-api.schwab.com",
    ".state/secrets",
    "schwab_live.env",
    "token.json",
)


@pytest.fixture(scope="module")
def audit_text() -> str:
    assert AUDIT_DOC_PATH.exists(), "release candidate readiness audit doc must exist"
    return AUDIT_DOC_PATH.read_text(encoding="utf-8")


def real_five_contract_live_proof_artifact_exists() -> bool:
    if not LIVE_PROOF_ARTIFACT_DIRECTORY.exists():
        return False
    for entry in LIVE_PROOF_ARTIFACT_DIRECTORY.glob("*five_contract*live*"):
        if entry.is_file():
            return True
    return False


def test_audit_doc_exists(audit_text: str) -> None:
    assert audit_text.strip(), "audit doc must not be empty"
    assert "Release Candidate Readiness Audit" in audit_text


def test_audit_names_final_target_universe(audit_text: str) -> None:
    for contract in ("ES", "NQ", "CL", "6E", "MGC"):
        assert f"`{contract}`" in audit_text, f"audit must name {contract} as a final target contract"
    assert "Final target contracts: `ES`, `NQ`, `CL`, `6E`, `MGC`" in audit_text


def test_audit_names_zn_and_gc_as_excluded(audit_text: str) -> None:
    assert "Excluded contracts: `ZN`, `GC`" in audit_text
    assert "`ZN` may remain only as source-engine history" in audit_text
    assert "`GC` is excluded" in audit_text


def test_audit_states_mgc_is_not_gc_and_gc_is_not_supported(audit_text: str) -> None:
    assert "`MGC` is Micro Gold" in audit_text
    assert "`MGC` is not `GC`" in audit_text
    assert "`GC` is not a synonym, alias, profile name, label, or substitute for `MGC`" in audit_text


def test_audit_states_manual_only_execution(audit_text: str) -> None:
    assert "Manual execution only" in audit_text
    assert "manual-only" in audit_text


def test_audit_states_preserved_engine_decision_authority(audit_text: str) -> None:
    assert "preserved engine remains the sole decision authority" in audit_text
    assert "does not introduce a second decision authority outside the preserved engine" in audit_text


def test_audit_states_default_launch_remains_non_live(audit_text: str) -> None:
    assert "Default launch remains non-live" in audit_text
    assert "default launch is non-live" in audit_text


def test_audit_states_live_behavior_is_opt_in(audit_text: str) -> None:
    assert "Live behavior is explicitly opt-in" in audit_text
    assert "Live behavior is opt-in" in audit_text


def test_audit_states_no_fixture_fallback_after_live_failure(audit_text: str) -> None:
    assert "No fixture fallback after live failure" in audit_text
    assert "no fallback to fixture data" in audit_text


def test_audit_states_15_second_minimum_refresh_floor(audit_text: str) -> None:
    assert "15-second minimum refresh floor" in audit_text
    assert "MIN_STREAM_REFRESH_FLOOR_SECONDS = 15.0" in audit_text
    assert "minimum refresh floor seconds is 15" in audit_text


def test_audit_distinguishes_fixture_evidence_from_real_live_proof(audit_text: str) -> None:
    assert "Deterministic fixture / non-live evidence" in audit_text
    assert "Manual live rehearsal checklist evidence" in audit_text
    assert "Real live Schwab evidence" in audit_text
    assert "Fixture evidence is not represented as real live evidence" in audit_text


def test_audit_records_bounded_levelone_proof_without_chart_or_production_claim(audit_text: str) -> None:
    artifact_present = real_five_contract_live_proof_artifact_exists()
    assert artifact_present
    assert "market_data_received=no" in audit_text
    assert "received_contracts_count=0" in audit_text
    assert "blocking_reason=required_env_keys_missing" in audit_text
    assert "runtime_start_attempted=no" in audit_text
    assert "subscribed_contracts_count=5" in audit_text
    assert "live_login_succeeded=yes" in audit_text
    assert "live_subscribe_succeeded=yes" in audit_text
    assert "market_data_received=yes" in audit_text
    assert "received_contracts_count=5" in audit_text
    assert "market_data_diagnostic=levelone_futures_updates_received" in audit_text
    assert "bounded LEVELONE_FUTURES delivery" in audit_text
    assert "CHART_FUTURES proof remains pending" in audit_text
    assert "Production live readiness remains withheld" in audit_text
    affirmative_claims = (
        "chart_futures delivery is proven",
        "production live readiness is proven",
        "production release is ready",
        "is a fully production-proven live-trading platform",
    )
    for claim in affirmative_claims:
        assert claim.lower() not in audit_text.lower(), (
            "audit must not promote LEVELONE_FUTURES evidence into CHART_FUTURES or production readiness"
        )


def test_audit_includes_explicit_verdict(audit_text: str) -> None:
    assert "Verdict:" in audit_text
    assert "**Verdict: CONDITIONALLY READY**" in audit_text
    assert "fixture-verified personal release candidate" in audit_text


def test_audit_includes_release_blockers_or_proof_gaps(audit_text: str) -> None:
    assert "Release Blockers and Proof Gaps" in audit_text
    assert "bounded real-live LEVELONE_FUTURES evidence item" in audit_text
    assert "Successful live login and successful live subscription remain insufficient" in audit_text
    assert "Bounded real LEVELONE_FUTURES market data has been recorded" in audit_text
    assert "Real CHART_FUTURES delivery has not been recorded" in audit_text
    assert "Symbol entitlement and rollover proof beyond the exact reported run has not been recorded" in audit_text
    assert "Full live-session Marimo usability has not been proven" in audit_text


def test_audit_does_not_include_secret_like_strings(audit_text: str) -> None:
    for fragment in FORBIDDEN_SENSITIVE_FRAGMENTS:
        assert fragment not in audit_text, f"audit must not include sensitive fragment {fragment!r}"


def test_audit_does_not_include_forbidden_sensitive_labels(audit_text: str) -> None:
    forbidden_labels = (
        "raw auth header",
        "bearer token value",
        "customer id value",
        "correl id value",
        "account id value",
        "raw streamer url",
    )
    lowered = audit_text.lower()
    for label in forbidden_labels:
        assert label not in lowered, f"audit must not surface forbidden sensitive label {label!r}"


def test_live_rehearsal_result_records_partial_fail_closed_outcome() -> None:
    assert LIVE_REHEARSAL_RESULT_PATH.exists(), "D3 sanitized live rehearsal result must be recorded"
    text = LIVE_REHEARSAL_RESULT_PATH.read_text(encoding="utf-8")

    assert "**PARTIAL / FAIL-CLOSED**" in text
    assert "| live_login_succeeded | yes |" in text
    assert "| live_subscribe_succeeded | yes |" in text
    assert "| subscribed_contracts_count | 5 |" in text
    assert "| market_data_received | no |" in text
    assert "| received_contracts_count | 0 |" in text
    assert "does not prove production live readiness" in text
    assert "must remain fail-closed" in text
    assert "market-data delivery proof" in text


def test_live_rehearsal_result_has_no_sensitive_values() -> None:
    text = LIVE_REHEARSAL_RESULT_PATH.read_text(encoding="utf-8")

    for fragment in FORBIDDEN_SENSITIVE_FRAGMENTS:
        assert fragment not in text, f"live rehearsal result must not include sensitive fragment {fragment!r}"


def test_blocked_live_rehearsal_result_records_fail_closed_before_runtime_start() -> None:
    assert BLOCKED_LIVE_REHEARSAL_RESULT_PATH.exists(), "blocked live rehearsal result must be recorded"
    text = BLOCKED_LIVE_REHEARSAL_RESULT_PATH.read_text(encoding="utf-8")

    assert "**PARTIAL / FAIL-CLOSED**" in text
    assert "blocked before runtime start" in text
    assert "| mode | blocked |" in text
    assert "| status | blocked |" in text
    assert "| live_flag | yes |" in text
    assert "| operator_live_runtime_env | yes |" in text
    assert "| env_keys_present | no |" in text
    assert "| runtime_start_attempted | no |" in text
    assert "| live_login_succeeded | no |" in text
    assert "| live_subscribe_succeeded | no |" in text
    assert "| subscribed_contracts_count | 0 |" in text
    assert "| market_data_received | no |" in text
    assert "| received_contracts_count | 0 |" in text
    assert "| values_printed | no |" in text
    assert "| blocking_reason | required_env_keys_missing |" in text
    assert "does not prove production live readiness" in text
    assert "real LEVELONE_FUTURES market data for ES, NQ, CL, 6E, and MGC" in text
    assert "real CHART_FUTURES delivery for ES, NQ, CL, 6E, and MGC" in text
    assert "symbol entitlement and rollover proof" in text
    assert "full live-session Marimo usability" in text


def test_blocked_live_rehearsal_result_has_no_sensitive_values() -> None:
    text = BLOCKED_LIVE_REHEARSAL_RESULT_PATH.read_text(encoding="utf-8")

    for fragment in FORBIDDEN_SENSITIVE_FRAGMENTS:
        assert fragment not in text, f"blocked live rehearsal result must not include sensitive fragment {fragment!r}"


def test_subscription_only_live_rehearsal_result_records_partial_fail_closed_outcome() -> None:
    assert SUBSCRIPTION_ONLY_LIVE_REHEARSAL_RESULT_PATH.exists(), (
        "subscription-only live rehearsal result must be recorded"
    )
    text = SUBSCRIPTION_ONLY_LIVE_REHEARSAL_RESULT_PATH.read_text(encoding="utf-8")

    assert "**PARTIAL / FAIL-CLOSED**" in text
    assert "| mode | live |" in text
    assert "| status | ok |" in text
    assert "| repo_check | yes |" in text
    assert "| live_flag | yes |" in text
    assert "| operator_live_runtime_env | yes |" in text
    assert "| env_keys_present | yes |" in text
    assert "| token_path_under_target_state | yes |" in text
    assert "| token_file_present | yes |" in text
    assert "| token_file_parseable | yes |" in text
    assert "| token_contract_valid | yes |" in text
    assert "| access_token_present | yes |" in text
    assert "| refresh_token_present | yes |" in text
    assert "| token_fresh | no |" in text
    assert "| streamer_credentials_obtained | yes |" in text
    assert "| runtime_start_attempted | yes |" in text
    assert "| live_login_succeeded | yes |" in text
    assert "| live_subscribe_succeeded | yes |" in text
    assert "| subscribed_contracts_count | 5 |" in text
    assert "| market_data_received | no |" in text
    assert "| received_contracts_count | 0 |" in text
    assert "| repeated_login_on_refresh | no |" in text
    assert "| cleanup_status | ok |" in text
    assert "| duration_seconds | 10.0 |" in text
    assert "| values_printed | no |" in text
    assert "successful subscription is not live market-data proof" in text
    assert "real LEVELONE_FUTURES delivery for ES, NQ, CL, 6E, or MGC" in text
    assert "real CHART_FUTURES delivery" in text
    assert "symbol entitlement or rollover correctness" in text
    assert "Production release remains premature" in text
    assert "No live-readiness acceptance, QUERY_READY state, D3 completion, or production release readiness" in text


def test_subscription_only_result_has_no_sensitive_values_or_production_ready_claim() -> None:
    text = SUBSCRIPTION_ONLY_LIVE_REHEARSAL_RESULT_PATH.read_text(encoding="utf-8")
    lowered = text.lower()

    for fragment in FORBIDDEN_SENSITIVE_FRAGMENTS:
        assert fragment not in text, (
            f"subscription-only live rehearsal result must not include sensitive fragment {fragment!r}"
        )
    forbidden_claims = (
        "production live readiness is proven",
        "production release is ready",
        "d3 complete",
        "query_ready satisfied",
        "live-readiness acceptance satisfied",
    )
    for claim in forbidden_claims:
        assert claim not in lowered


def test_levelone_live_market_data_result_records_bounded_success_only() -> None:
    assert LEVELONE_LIVE_MARKET_DATA_RESULT_PATH.exists(), (
        "bounded five-contract LEVELONE_FUTURES live result must be recorded"
    )
    text = LEVELONE_LIVE_MARKET_DATA_RESULT_PATH.read_text(encoding="utf-8")

    assert "**BOUNDED LEVELONE_FUTURES LIVE DELIVERY RECORDED**" in text
    assert "| mode | live |" in text
    assert "| status | ok |" in text
    assert "| repo_check | yes |" in text
    assert "| live_flag | yes |" in text
    assert "| operator_live_runtime_env | yes |" in text
    assert "| env_keys_present | yes |" in text
    assert "| token_path_under_target_state | yes |" in text
    assert "| token_file_present | yes |" in text
    assert "| token_file_parseable | yes |" in text
    assert "| token_contract_valid | yes |" in text
    assert "| access_token_present | yes |" in text
    assert "| refresh_token_present | yes |" in text
    assert "| token_fresh | no |" in text
    assert "| streamer_credentials_obtained | yes |" in text
    assert "| runtime_start_attempted | yes |" in text
    assert "| live_login_succeeded | yes |" in text
    assert "| live_subscribe_succeeded | yes |" in text
    assert "| subscribed_contracts_count | 5 |" in text
    assert "| market_data_received | yes |" in text
    assert "| received_contracts_count | 5 |" in text
    assert "| market_data_diagnostic | levelone_futures_updates_received |" in text
    assert "| repeated_login_on_refresh | no |" in text
    assert "| cleanup_status | ok |" in text
    assert "| duration_seconds | 30.0 |" in text
    assert "| values_printed | no |" in text
    assert "proves bounded live LEVELONE_FUTURES delivery" in text
    assert "CHART_FUTURES" in text
    assert "Production release remains premature" in text
    assert "raw market values and raw streamer payloads were not recorded" in text.lower()


def test_levelone_live_market_data_result_preserves_contract_boundaries() -> None:
    text = LEVELONE_LIVE_MARKET_DATA_RESULT_PATH.read_text(encoding="utf-8")

    for contract in ("ES", "NQ", "CL", "6E", "MGC"):
        assert f"- {contract}" in text
    assert "- ZN" in text
    assert "- GC" in text
    assert "MGC is Micro Gold. It is not GC" in text
    assert "GC is not a substitute for MGC" in text


def test_levelone_live_market_data_result_has_no_sensitive_values_or_raw_market_data() -> None:
    text = LEVELONE_LIVE_MARKET_DATA_RESULT_PATH.read_text(encoding="utf-8")
    lowered = text.lower()

    for fragment in FORBIDDEN_SENSITIVE_FRAGMENTS:
        assert fragment not in text, (
            f"bounded LEVELONE_FUTURES live result must not include sensitive fragment {fragment!r}"
        )
    forbidden_fragments = (
        "raw quote value:",
        "raw streamer payload:",
        "bid=",
        "ask=",
        "last=",
        "price=",
        "open=",
        "high=",
        "low=",
        "close=",
    )
    for fragment in forbidden_fragments:
        assert fragment not in lowered


def test_levelone_live_market_data_result_does_not_claim_chart_or_production_ready() -> None:
    text = LEVELONE_LIVE_MARKET_DATA_RESULT_PATH.read_text(encoding="utf-8").lower()

    forbidden_claims = (
        "chart_futures delivery is proven",
        "chart_futures proof has passed",
        "production live readiness is proven",
        "production release is ready",
        "query_ready satisfied",
        "live-readiness acceptance satisfied",
        "d3 complete",
    )
    for claim in forbidden_claims:
        assert claim not in text
