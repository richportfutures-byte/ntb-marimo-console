from __future__ import annotations

from pathlib import Path


RC_CUT_PATH = Path(__file__).resolve().parents[1] / "docs" / "release_candidate_cut_2026-05-12.md"


def rc_cut_text() -> str:
    assert RC_CUT_PATH.exists(), "release-candidate cut record must exist"
    return RC_CUT_PATH.read_text(encoding="utf-8")


def test_release_candidate_cut_records_exact_clean_checkpoint_and_contract_boundary() -> None:
    text = rc_cut_text()

    assert "Clean checkpoint used for the cut: `110f09a Add performance review layer`" in text
    assert "Supported target contracts: `ES`, `NQ`, `CL`, `6E`, `MGC`" in text
    assert "Excluded contracts: `ZN`, `GC`" in text
    assert "`MGC` is Micro Gold and is not `GC`" in text
    assert "`GC` is not a synonym, substitute, label, alias, or runtime profile for `MGC`" in text
    assert "`ZN` remains excluded from final target support" in text


def test_release_candidate_cut_preserves_manual_only_and_preserved_engine_authority() -> None:
    text = rc_cut_text()

    assert "Execution is manual-only" in text
    assert "Pipeline decisions remain preserved-engine-derived" in text
    assert "The preserved engine remains the sole decision authority" in text
    assert "No query authorization can be derived from review metrics" in text
    assert "Review metrics are descriptive only and do not prove statistical edge" in text


def test_release_candidate_cut_preserves_d3_partial_fail_closed_language() -> None:
    text = rc_cut_text()

    assert "PARTIAL / FAIL-CLOSED" in text
    for row in (
        "| live_login_succeeded | yes |",
        "| live_subscribe_succeeded | yes |",
        "| subscribed_contracts_count | 5 |",
        "| market_data_received | no |",
        "| received_contracts_count | 0 |",
        "| repeated_login_on_refresh | no |",
        "| cleanup_status | ok |",
        "| values_printed | no |",
    ):
        assert row in text
    assert "must remain fail-closed from the D3 result" in text


def test_release_candidate_cut_does_not_claim_production_live_readiness() -> None:
    text = rc_cut_text()
    lowered = text.lower()

    assert "not a production-live Schwab readiness claim" in text
    assert "Production-live Schwab readiness remains unproven" in text
    assert "does not prove `LEVELONE_FUTURES` real delivery across `ES`, `NQ`, `CL`, `6E`, and `MGC`" in text
    assert "does not prove production live `CHART_FUTURES` delivery" in text
    forbidden_claims = (
        "production live schwab readiness is proven",
        "production-live schwab readiness is proven",
        "chart_futures production live delivery is proven",
        "levelone_futures real delivery across es, nq, cl, 6e, and mgc is proven",
        "statistical edge is proven",
    )
    for claim in forbidden_claims:
        assert claim not in lowered


def test_release_candidate_cut_keeps_default_non_live_and_fixture_safe_boundaries() -> None:
    text = rc_cut_text()

    assert "Default launch is non-live" in text
    assert "Live behavior remains explicitly opt-in" in text
    assert "Fixture-safe default tests require no Schwab credentials" in text
    assert "No fixture fallback after live failure remains preserved" in text
    assert "15-second minimum refresh floor remains preserved" in text
