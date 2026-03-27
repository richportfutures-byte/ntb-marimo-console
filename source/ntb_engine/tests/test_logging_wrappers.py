from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ninjatradebuilder.execution_facade import (
    DEFAULT_LOG_PATH,
    run_pipeline_and_log,
    sweep_watchman_and_log,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_packet(contract: str) -> dict:
    payload = json.loads((FIXTURES_DIR / "packets.valid.json").read_text())
    return {
        "$schema": "historical_packet_v1",
        "challenge_state": copy.deepcopy(payload["shared"]["challenge_state"]),
        "attached_visuals": copy.deepcopy(payload["shared"]["attached_visuals"]),
        "contract_metadata": copy.deepcopy(payload["contracts"][contract]["contract_metadata"]),
        "market_packet": copy.deepcopy(payload["contracts"][contract]["market_packet"]),
        "contract_specific_extension": copy.deepcopy(
            payload["contracts"][contract]["contract_specific_extension"]
        ),
    }


def _load_packet_bundle() -> dict:
    return json.loads((FIXTURES_DIR / "packets.valid.json").read_text())


def _recheck_trigger() -> dict[str, str]:
    return {
        "trigger_family": "recheck_at_time",
        "recheck_at_time": "2026-01-14T15:15:00Z",
    }


def test_sweep_watchman_and_log_creates_records(tmp_path: Path) -> None:
    log_path = tmp_path / "test.jsonl"

    sweep_results, records = sweep_watchman_and_log(
        _load_packet_bundle(),
        _recheck_trigger(),
        trigger_family="recheck_at_time",
        log_path=log_path,
    )

    assert isinstance(sweep_results, dict)
    assert sweep_results
    assert len(records) == len(sweep_results)
    assert all(record.run_type == "watchman_only" for record in records)
    assert all(record.trigger_family == "recheck_at_time" for record in records)
    assert log_path.exists()
    assert len(log_path.read_text(encoding="utf-8").splitlines()) == len(records)


def test_sweep_watchman_and_log_records_match_contracts(tmp_path: Path) -> None:
    sweep_results, records = sweep_watchman_and_log(
        _load_packet_bundle(),
        _recheck_trigger(),
        trigger_family="recheck_at_time",
        log_path=tmp_path / "test.jsonl",
    )

    assert {record.contract for record in records} == set(sweep_results)


def test_sweep_watchman_and_log_uses_default_path_when_not_specified() -> None:
    append_mock = MagicMock()

    with patch.dict(
        sweep_watchman_and_log.__globals__,
        {"append_log_record": append_mock},
    ):
        sweep_results, records = sweep_watchman_and_log(
            _load_packet_bundle(),
            _recheck_trigger(),
            trigger_family="recheck_at_time",
        )

    assert len(records) == len(sweep_results)
    assert append_mock.call_count == len(records)
    assert all(call.args[1] == DEFAULT_LOG_PATH for call in append_mock.call_args_list)


def test_run_pipeline_and_log_returns_result_and_record(tmp_path: Path) -> None:
    packet = _load_packet("ES")
    expected_result = SimpleNamespace(
        contract="ES",
        final_decision="GO",
        termination_stage="risk_authorization",
        sufficiency_gate_output=SimpleNamespace(status="SUFFICIENT"),
        contract_analysis=SimpleNamespace(outcome="ALIGNED"),
        proposed_setup=SimpleNamespace(outcome="PROPOSED"),
        risk_authorization=SimpleNamespace(decision="AUTHORIZED"),
    )

    with patch(
        "ninjatradebuilder.execution_facade.pipeline_module.run_pipeline",
        return_value=expected_result,
    ):
        pipeline_result, record = run_pipeline_and_log(
            packet,
            "ES",
            _recheck_trigger(),
            model_adapter=object(),
            trigger_family="recheck_at_time",
            log_path=tmp_path / "test.jsonl",
        )

    assert pipeline_result is expected_result
    assert record.run_type == "full_pipeline"
    assert record.final_decision == "GO"
    assert record.contract == "ES"
    assert (tmp_path / "test.jsonl").exists()
    assert len((tmp_path / "test.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_run_pipeline_and_log_persists_watchman_fields(tmp_path: Path) -> None:
    packet = _load_packet("ES")
    expected_result = SimpleNamespace(
        contract="ES",
        final_decision="GO",
        termination_stage="risk_authorization",
        sufficiency_gate_output=SimpleNamespace(status="SUFFICIENT"),
        contract_analysis=SimpleNamespace(outcome="ALIGNED"),
        proposed_setup=SimpleNamespace(outcome="PROPOSED"),
        risk_authorization=SimpleNamespace(decision="AUTHORIZED"),
    )

    with patch(
        "ninjatradebuilder.execution_facade.pipeline_module.run_pipeline",
        return_value=expected_result,
    ):
        _, record = run_pipeline_and_log(
            packet,
            "ES",
            _recheck_trigger(),
            model_adapter=object(),
            trigger_family="recheck_at_time",
            log_path=tmp_path / "test.jsonl",
        )

    assert record.watchman_status in {"ready", "blocked", "caution"}
    assert isinstance(record.vwap_posture, str)
    assert record.vwap_posture
    assert isinstance(record.evaluation_timestamp_iso, str)
    assert record.evaluation_timestamp_iso


def test_sweep_watchman_and_log_with_notes(tmp_path: Path) -> None:
    _, records = sweep_watchman_and_log(
        _load_packet_bundle(),
        _recheck_trigger(),
        trigger_family="recheck_at_time",
        log_path=tmp_path / "test.jsonl",
        notes="test note",
    )

    assert all(record.notes == "test note" for record in records)
