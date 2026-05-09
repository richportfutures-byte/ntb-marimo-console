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


def test_audit_does_not_claim_real_five_contract_proof_unless_artifact_exists(audit_text: str) -> None:
    artifact_present = real_five_contract_live_proof_artifact_exists()
    if artifact_present:
        return
    assert "Real five-contract Schwab live proof is pending operator-run validation" in audit_text
    assert "real-live proof gap" in audit_text
    assert "Manual operator-run proof is still pending" in audit_text
    assert "this is not a deterministic code blocker" in audit_text.lower()
    affirmative_claims = (
        "real five-contract Schwab live session has been proven",
        "real five-contract Schwab live session is verified",
        "real five-contract Schwab live session: pass",
        "real five-contract Schwab live session: passed",
        "real five-contract Schwab live session has passed and is in the repo",
    )
    for claim in affirmative_claims:
        assert claim.lower() not in audit_text.lower(), (
            "audit must not claim real five-contract Schwab live proof unless artifact exists"
        )


def test_audit_includes_explicit_verdict(audit_text: str) -> None:
    assert "Verdict:" in audit_text
    assert "**Verdict: CONDITIONALLY READY**" in audit_text
    assert "fixture-verified personal release candidate" in audit_text


def test_audit_includes_release_blockers_or_proof_gaps(audit_text: str) -> None:
    assert "Release Blockers and Proof Gaps" in audit_text
    assert "real-live proof gap" in audit_text


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
