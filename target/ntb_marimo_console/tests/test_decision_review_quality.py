from __future__ import annotations

import json

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.decision_review_audit import build_decision_review_audit_event
from ntb_marimo_console.decision_review_quality import (
    DECISION_REVIEW_NARRATIVE_QUALITY_SCHEMA,
    validate_decision_review_narrative_quality,
)
from ntb_marimo_console.decision_review_replay import build_decision_review_replay_vm


CREATED_AT = "2026-05-09T12:00:00Z"


def test_quality_passes_for_read_only_replay_with_source_and_run_reference() -> None:
    replay = build_decision_review_replay_vm(
        complete_audit_event(),
        audit_replay_record=audit_replay_record(),
    ).to_dict()
    quality = replay["narrative_quality"]

    encoded = json.dumps(quality, sort_keys=True)
    decoded = json.loads(encoded)

    assert decoded["schema"] == DECISION_REVIEW_NARRATIVE_QUALITY_SCHEMA
    assert decoded["status"] == "PASS"
    assert decoded["source_reference_present"] is True
    assert decoded["replay_reference_present"] is True
    assert decoded["manual_only_language_present"] is True
    assert decoded["preserved_engine_authority_language_present"] is True
    assert decoded["raw_json_primary_surface_detected"] is False
    assert decoded["unsafe_execution_language_detected"] is False
    assert decoded["unsupported_market_read_claim_detected"] is False
    assert decoded["unsupported_contract_language_detected"] is False
    assert decoded["missing_narrative_detected"] is False
    assert decoded == replay["narrative_quality"]


def test_quality_missing_replay_or_narrative_returns_explicit_status_without_crashing() -> None:
    absent = build_decision_review_replay_vm(None).to_dict()["narrative_quality"]
    assert absent["status"] == "FAIL"
    assert absent["missing_narrative_detected"] is True
    assert "replay_surface_available" in absent["blocking_reasons"]

    partial_event = build_decision_review_audit_event(
        decision_review={"surface": "Decision Review", "has_result": False, "message": "No pipeline result loaded."},
        live_thesis_monitor=None,
        created_at=CREATED_AT,
    ).to_dict()
    partial = build_decision_review_replay_vm(partial_event).to_dict()["narrative_quality"]
    assert partial["status"] == "WARN"
    assert partial["missing_narrative_detected"] is True
    assert "missing_narrative_detected" in partial["warnings"]


def test_quality_detects_missing_source_or_replay_reference() -> None:
    replay = build_decision_review_replay_vm(complete_audit_event()).to_dict()
    quality = replay["narrative_quality"]

    assert quality["status"] == "WARN"
    assert quality["source_reference_present"] is True
    assert quality["replay_reference_present"] is False
    assert "replay_reference_present" in quality["warnings"]

    no_source = dict(replay)
    no_source["source"] = "unknown"
    no_source["source_fields"] = []
    quality_no_source = validate_decision_review_narrative_quality(no_source).to_dict()

    assert quality_no_source["source_reference_present"] is False
    assert "source_reference_present" in quality_no_source["warnings"]


def test_quality_detects_missing_manual_only_and_preserved_engine_authority_language() -> None:
    replay = build_decision_review_replay_vm(
        complete_audit_event(),
        audit_replay_record=audit_replay_record(),
    ).to_dict()
    replay["manual_only_execution"] = False
    replay["preserved_engine_authority"] = False
    replay["authority_statement"] = "Review fields are available."
    replay["readiness_explanation"] = "Review fields are available."

    quality = validate_decision_review_narrative_quality(replay).to_dict()

    assert quality["status"] == "FAIL"
    assert quality["manual_only_language_present"] is False
    assert quality["preserved_engine_authority_language_present"] is False
    assert "manual_only_language_present" in quality["blocking_reasons"]
    assert "preserved_engine_authority_language_present" in quality["blocking_reasons"]


def test_quality_detects_unsafe_authority_language_and_fields() -> None:
    replay = build_decision_review_replay_vm(
        complete_audit_event(),
        audit_replay_record=audit_replay_record(),
    ).to_dict()
    replay["transition_summary"] = "buy now"

    quality = validate_decision_review_narrative_quality(replay).to_dict()

    assert quality["status"] == "FAIL"
    assert quality["unsafe_execution_language_detected"] is True
    assert "unsafe_execution_language_detected" in quality["blocking_reasons"]

    replay["transition_summary"] = "review only"
    replay["order"] = "synthetic"
    field_quality = validate_decision_review_narrative_quality(replay).to_dict()
    assert field_quality["unsafe_execution_language_detected"] is True


def test_quality_detects_raw_json_primary_surface() -> None:
    replay = build_decision_review_replay_vm(
        complete_audit_event(),
        audit_replay_record=audit_replay_record(),
    ).to_dict()

    quality = validate_decision_review_narrative_quality(replay, primary_surface_text='```json\n{"x": 1}\n```').to_dict()

    assert quality["status"] == "FAIL"
    assert quality["raw_json_primary_surface_detected"] is True
    assert "raw_json_primary_surface_detected" in quality["blocking_reasons"]


def test_quality_preserves_contract_universe_without_promoting_zn_or_gc() -> None:
    replay = build_decision_review_replay_vm(
        complete_audit_event(contract="MGC", setup_id="mgc_setup_1", trigger_id="mgc_trigger_1"),
        audit_replay_record=audit_replay_record(),
    ).to_dict()
    rendered = json.dumps(replay, sort_keys=True)

    assert final_target_contracts() == ("ES", "NQ", "CL", "6E", "MGC")
    assert "ZN" not in final_target_contracts()
    assert "GC" not in final_target_contracts()
    assert replay["contract"] == "MGC"
    assert replay["narrative_quality"]["unsupported_contract_language_detected"] is False
    assert '"GC"' not in rendered
    assert "Micro Gold" not in rendered

    unsupported = validate_decision_review_narrative_quality(
        replay,
        primary_surface_text="Contract GC replay is unsupported.",
    ).to_dict()
    assert unsupported["status"] == "FAIL"
    assert unsupported["unsupported_contract_language_detected"] is True


def test_professional_no_trade_market_read_contract_passes_with_evidence_and_attribution() -> None:
    replay = build_decision_review_replay_vm(
        complete_audit_event(),
        audit_replay_record=audit_replay_record(),
    ).to_dict()

    quality = validate_decision_review_narrative_quality(
        replay,
        primary_surface_text=professional_no_trade_market_read(),
    ).to_dict()

    assert quality["status"] == "PASS"
    assert quality["source_reference_present"] is True
    assert quality["replay_reference_present"] is True
    assert quality["manual_only_language_present"] is True
    assert quality["preserved_engine_authority_language_present"] is True
    assert quality["raw_json_primary_surface_detected"] is False
    assert quality["unsafe_execution_language_detected"] is False
    assert quality["unsupported_market_read_claim_detected"] is False
    assert quality["unsupported_contract_language_detected"] is False
    assert quality["missing_narrative_detected"] is False


def test_market_read_contract_fails_unsupported_market_claim_even_when_prose_is_polished() -> None:
    replay = build_decision_review_replay_vm(
        complete_audit_event(),
        audit_replay_record=audit_replay_record(),
    ).to_dict()

    quality = validate_decision_review_narrative_quality(
        replay,
        primary_surface_text=(
            professional_no_trade_market_read()
            + " Footprint confirms hidden buyers and DOM shows a guaranteed upside continuation."
        ),
    ).to_dict()

    assert quality["status"] == "FAIL"
    assert quality["unsupported_market_read_claim_detected"] is True
    assert "unsupported_market_read_claim_detected" in quality["blocking_reasons"]
    assert _check_message(quality, "unsupported_market_read_claim_detected") == (
        "Unsupported market-read claim was detected."
    )


def test_market_read_contract_fails_execution_implying_language() -> None:
    replay = build_decision_review_replay_vm(
        complete_audit_event(),
        audit_replay_record=audit_replay_record(),
    ).to_dict()

    quality = validate_decision_review_narrative_quality(
        replay,
        primary_surface_text=professional_no_trade_market_read() + " Buy now if price reclaims VWAP.",
    ).to_dict()

    assert quality["status"] == "FAIL"
    assert quality["unsafe_execution_language_detected"] is True
    assert "unsafe_execution_language_detected" in quality["blocking_reasons"]
    assert _check_message(quality, "unsafe_execution_language_detected") == "Unsafe authority language was detected."


def test_market_read_contract_fails_preserved_engine_authority_confusion() -> None:
    replay = build_decision_review_replay_vm(
        complete_audit_event(),
        audit_replay_record=audit_replay_record(),
    ).to_dict()
    replay["manual_only_execution"] = False
    replay["preserved_engine_authority"] = False
    replay["authority_statement"] = "Narrative review decides whether this setup is acceptable."
    replay["readiness_explanation"] = "Narrative review can approve the setup without the preserved pipeline."

    quality = validate_decision_review_narrative_quality(
        replay,
        primary_surface_text="This market read is cautious and avoids execution wording.",
    ).to_dict()

    assert quality["status"] == "FAIL"
    assert quality["manual_only_language_present"] is False
    assert quality["preserved_engine_authority_language_present"] is False
    assert "manual_only_language_present" in quality["blocking_reasons"]
    assert "preserved_engine_authority_language_present" in quality["blocking_reasons"]


def test_market_read_contract_fails_unsupported_contract_language() -> None:
    replay = build_decision_review_replay_vm(
        complete_audit_event(contract="MGC", setup_id="mgc_setup_1", trigger_id="mgc_trigger_1"),
        audit_replay_record=audit_replay_record(),
    ).to_dict()

    quality = validate_decision_review_narrative_quality(
        replay,
        primary_surface_text=professional_no_trade_market_read(contract="MGC") + " Compare this GC read to ZN.",
    ).to_dict()

    assert quality["status"] == "FAIL"
    assert quality["unsupported_contract_language_detected"] is True
    assert "unsupported_contract_language_detected" in quality["blocking_reasons"]


def test_market_read_contract_fails_raw_json_primary_surface() -> None:
    replay = build_decision_review_replay_vm(
        complete_audit_event(),
        audit_replay_record=audit_replay_record(),
    ).to_dict()

    quality = validate_decision_review_narrative_quality(
        replay,
        primary_surface_text='{"contract":"ES","final_decision":"NO_TRADE"}',
    ).to_dict()

    assert quality["status"] == "FAIL"
    assert quality["raw_json_primary_surface_detected"] is True
    assert "raw_json_primary_surface_detected" in quality["blocking_reasons"]


def test_market_read_contract_fails_when_replay_source_attribution_is_blocked() -> None:
    replay = build_decision_review_replay_vm(
        complete_audit_event(),
        audit_replay_record={
            "source": "stage_e_jsonl",
            "stage_e_live_backend": True,
            "replay_available": True,
            "last_run_id": None,
            "last_final_decision": "NO_TRADE",
        },
    ).to_dict()
    replay["source"] = "unknown"
    replay["source_fields"] = []

    quality = validate_decision_review_narrative_quality(
        replay,
        primary_surface_text=professional_no_trade_market_read(),
    ).to_dict()

    assert quality["status"] == "FAIL"
    assert quality["source_reference_present"] is False
    assert quality["replay_reference_present"] is False
    assert "source_reference_present" in quality["warnings"]
    assert "replay_reference_present" in quality["blocking_reasons"]
    assert _check_message(quality, "replay_reference_present") == (
        "Replay reference is unavailable, blocked, or inconsistent."
    )


def complete_audit_event(
    *,
    contract: str = "ES",
    setup_id: str = "es_setup_1",
    trigger_id: str = "es_trigger_1",
) -> dict[str, object]:
    return build_decision_review_audit_event(
        decision_review={
            "surface": "Decision Review",
            "has_result": True,
            "contract": contract,
            "termination_stage": "contract_market_read",
            "final_decision": "NO_TRADE",
            "stage_a_status": "READY",
            "stage_b_outcome": "NO_TRADE",
            "narrative_available": True,
            "engine_reasoning": {
                "available": True,
                "market_regime": "choppy",
                "directional_bias": "unclear",
                "evidence_score": 3,
                "confidence_band": "LOW",
                "structural_notes": "Choppy tape; review only.",
                "outcome": "NO_TRADE",
            },
        },
        live_thesis_monitor={
            "setup_id": setup_id,
            "trigger_id": trigger_id,
            "trigger_state": "QUERY_READY",
            "blocking_reasons": [],
            "invalid_reasons": [],
            "missing_fields": [],
            "state_flags": {"stale": False, "lockout": False, "blocked": False},
            "transition_narrative": {
                "narrative_available": True,
                "state_label": "QUERY_READY",
                "transition_summary": f"setup {setup_id} / trigger {trigger_id}: deterministic trigger state recorded.",
                "readiness_explanation": (
                    "The preserved pipeline must still decide; QUERY_READY does not approve or authorize a trade, "
                    "and execution remains manual."
                ),
                "blocking_explanation": None,
                "invalidation_explanation": None,
                "missing_data_explanation": None,
                "operator_guidance": "Use this deterministic read model for audit context only.",
                "source_fields": ["state", "setup_id", "trigger_id"],
            },
        },
        profile_id=f"preserved_{contract.lower()}_phase1",
        created_at=CREATED_AT,
        source="fixture",
    ).to_dict()


def professional_no_trade_market_read(*, contract: str = "ES") -> str:
    return (
        f"{contract} market read: price is rotating near VWAP, breadth is mixed, and the recorded "
        "trigger state is QUERY_READY for review context only. The preserved engine result is NO_TRADE, "
        "so this is a professional pass on the setup rather than a trade approval. Source fields and "
        "the replay run reference are present; execution remains manual and the preserved pipeline "
        "remains the decision authority."
    )


def _check_message(quality: dict[str, object], check_id: str) -> str:
    checks = quality["checks"]
    assert isinstance(checks, list)
    for check in checks:
        assert isinstance(check, dict)
        if check["check_id"] == check_id:
            return str(check["message"])
    raise AssertionError(f"Missing quality check: {check_id}")


def audit_replay_record() -> dict[str, object]:
    return {
        "source": "fixture_backed",
        "stage_e_live_backend": False,
        "replay_available": True,
        "last_run_id": "run-1",
        "last_final_decision": "NO_TRADE",
    }
