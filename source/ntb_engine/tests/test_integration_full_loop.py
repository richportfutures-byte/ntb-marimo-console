"""Full-loop integration test: packet → sweep → log → read back → view model.

Proves the entire chain works end-to-end with real fixture data and
real Watchman execution (no mocks except for the pipeline Gemini call).
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ninjatradebuilder.execution_facade import (
    sweep_watchman_and_log,
    run_pipeline_and_log,
)
from ninjatradebuilder.logging_record import read_log_records
from ninjatradebuilder.view_models import (
    ReadinessCard,
    diff_watchman_contexts,
    log_history_rows_from_records,
    readiness_cards_from_sweep,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_bundle() -> dict:
    return json.loads((FIXTURES_DIR / "packets.valid.json").read_text(encoding="utf-8"))


def _recheck_trigger() -> dict[str, str]:
    return {
        "trigger_family": "recheck_at_time",
        "recheck_at_time": "2026-01-14T15:15:00Z",
    }


def test_sweep_log_readback_viewmodel_loop(tmp_path: Path) -> None:
    """packet bundle → sweep → log → read back → view model cards + history rows."""
    log_path = tmp_path / "integration.jsonl"

    # 1. Sweep all contracts and log
    sweep_results, records = sweep_watchman_and_log(
        _load_bundle(),
        _recheck_trigger(),
        trigger_family="recheck_at_time",
        log_path=log_path,
    )

    # 2. Verify sweep produced results for supported contracts
    assert len(sweep_results) > 0
    assert len(records) == len(sweep_results)

    # 3. Build readiness cards from sweep (view-model layer)
    cards = readiness_cards_from_sweep(sweep_results)
    assert len(cards) == len(sweep_results)
    assert all(isinstance(card, ReadinessCard) for card in cards)
    assert all(card.status in ("ready", "blocked", "caution") for card in cards)

    # 4. Read back from JSONL
    stored_records = read_log_records(log_path)
    assert len(stored_records) == len(records)
    assert {r.run_id for r in stored_records} == {r.run_id for r in records}

    # 5. Convert to history rows (view-model layer)
    history_rows = log_history_rows_from_records(stored_records)
    assert len(history_rows) == len(stored_records)
    assert all(row.run_type == "watchman_only" for row in history_rows)

    # 6. Filter by contract
    first_contract = cards[0].contract
    filtered_rows = log_history_rows_from_records(
        stored_records, contract_filter=first_contract
    )
    assert all(row.contract == first_contract for row in filtered_rows)
    assert len(filtered_rows) >= 1


def test_sweep_diff_loop(tmp_path: Path) -> None:
    """Two consecutive sweeps with a mutation → diff detects the change."""
    bundle = _load_bundle()
    trigger = _recheck_trigger()

    # First sweep
    sweep_1, _ = sweep_watchman_and_log(
        bundle,
        trigger,
        trigger_family="recheck_at_time",
        log_path=tmp_path / "integration.jsonl",
    )

    # Mutate: flip ES event_risk_state
    es_ctx_1 = sweep_1["ES"]
    es_ctx_2 = es_ctx_1.model_copy(update={"event_risk_state": "elevated"})

    diff = diff_watchman_contexts(es_ctx_1, es_ctx_2)
    assert diff.has_changes
    assert diff.contract == "ES"
    changed_fields = {c.field for c in diff.changes}
    assert "event_risk_state" in changed_fields


def test_pipeline_log_readback_loop(tmp_path: Path) -> None:
    """Single-contract packet → pipeline (mocked) → log → read back → history row."""
    bundle = _load_bundle()
    log_path = tmp_path / "pipeline.jsonl"

    # Build a single ES packet from the bundle
    es_packet = {
        "$schema": "historical_packet_v1",
        "challenge_state": bundle["shared"]["challenge_state"],
        "attached_visuals": bundle["shared"]["attached_visuals"],
        "contract_metadata": bundle["contracts"]["ES"]["contract_metadata"],
        "market_packet": bundle["contracts"]["ES"]["market_packet"],
        "contract_specific_extension": bundle["contracts"]["ES"]["contract_specific_extension"],
    }

    mock_pipeline_result = SimpleNamespace(
        contract="ES",
        final_decision="TRADE_APPROVED",
        termination_stage="risk_authorization",
        sufficiency_gate_output=SimpleNamespace(status="SUFFICIENT"),
        contract_analysis=SimpleNamespace(outcome="ALIGNED"),
        proposed_setup=SimpleNamespace(outcome="SETUP_PROPOSED"),
        risk_authorization=SimpleNamespace(decision="APPROVED"),
    )

    with patch(
        "ninjatradebuilder.execution_facade.pipeline_module.run_pipeline",
        return_value=mock_pipeline_result,
    ):
        pipeline_result, record = run_pipeline_and_log(
            es_packet,
            "ES",
            _recheck_trigger(),
            model_adapter=object(),
            trigger_family="recheck_at_time",
            log_path=log_path,
        )

    # Verify pipeline result passthrough
    assert pipeline_result is mock_pipeline_result
    assert record.run_type == "full_pipeline"
    assert record.contract == "ES"
    assert record.final_decision == "TRADE_APPROVED"

    # Read back and verify
    stored = read_log_records(log_path)
    assert len(stored) == 1
    assert stored[0].run_id == record.run_id

    # Convert to history row
    rows = log_history_rows_from_records(stored)
    assert len(rows) == 1
    assert rows[0].final_decision == "TRADE_APPROVED"
    assert rows[0].run_type == "full_pipeline"
    assert rows[0].watchman_status in ("ready", "blocked", "caution")
