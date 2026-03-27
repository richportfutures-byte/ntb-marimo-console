from __future__ import annotations

import copy
import json
from pathlib import Path

from ninjatradebuilder.logging_record import build_logging_record_from_watchman
from ninjatradebuilder.readiness_adapter import (
    build_readiness_runtime_inputs_from_packet,
)
from ninjatradebuilder.view_models import log_history_rows_from_records
from ninjatradebuilder.watchman import build_watchman_context_from_runtime_inputs

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _packet_payload(contract: str) -> dict[str, object]:
    bundle = json.loads((FIXTURES_DIR / "packets.valid.json").read_text(encoding="utf-8"))
    return {
        "$schema": "historical_packet_v1",
        "challenge_state": copy.deepcopy(bundle["shared"]["challenge_state"]),
        "attached_visuals": copy.deepcopy(bundle["shared"]["attached_visuals"]),
        "contract_metadata": copy.deepcopy(bundle["contracts"][contract]["contract_metadata"]),
        "market_packet": copy.deepcopy(bundle["contracts"][contract]["market_packet"]),
        "contract_specific_extension": copy.deepcopy(
            bundle["contracts"][contract]["contract_specific_extension"]
        ),
    }


def _recheck_trigger() -> dict[str, str]:
    return {
        "trigger_family": "recheck_at_time",
        "recheck_at_time": "2026-01-14T15:15:00Z",
    }


def _build_context(contract: str):
    runtime_inputs = build_readiness_runtime_inputs_from_packet(_packet_payload(contract))
    return build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())


def test_log_history_row_from_watchman_record() -> None:
    record = build_logging_record_from_watchman(_build_context("ES"), "recheck_at_time")

    rows = log_history_rows_from_records([record])

    assert len(rows) == 1
    assert rows[0].contract == "ES"
    assert rows[0].run_type == "watchman_only"
    assert rows[0].final_decision == "—"
    assert rows[0].notes == "—"
    assert isinstance(rows[0].logged_at, str)
    assert rows[0].logged_at


def test_log_history_row_from_watchman_record_with_notes() -> None:
    record = build_logging_record_from_watchman(
        _build_context("ES"),
        "recheck_at_time",
        notes="operator note",
    )

    rows = log_history_rows_from_records([record])

    assert rows[0].notes == "operator note"


def test_log_history_rows_contract_filter() -> None:
    es_record = build_logging_record_from_watchman(_build_context("ES"), "recheck_at_time")
    nq_record = build_logging_record_from_watchman(_build_context("NQ"), "recheck_at_time")

    rows = log_history_rows_from_records([es_record, nq_record], contract_filter="ES")

    assert len(rows) == 1
    assert rows[0].contract == "ES"


def test_log_history_rows_contract_filter_none_returns_all() -> None:
    es_record = build_logging_record_from_watchman(_build_context("ES"), "recheck_at_time")
    nq_record = build_logging_record_from_watchman(_build_context("NQ"), "recheck_at_time")

    rows = log_history_rows_from_records([es_record, nq_record])

    assert len(rows) == 2


def test_log_history_rows_preserves_order() -> None:
    es_record = build_logging_record_from_watchman(_build_context("ES"), "recheck_at_time")
    nq_record = build_logging_record_from_watchman(_build_context("NQ"), "recheck_at_time")
    cl_record = build_logging_record_from_watchman(_build_context("CL"), "recheck_at_time")

    rows = log_history_rows_from_records([es_record, nq_record, cl_record])

    assert [row.contract for row in rows] == ["ES", "NQ", "CL"]


def test_log_history_rows_empty_input() -> None:
    assert log_history_rows_from_records([]) == []
