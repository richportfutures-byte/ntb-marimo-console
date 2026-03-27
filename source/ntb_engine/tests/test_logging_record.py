from __future__ import annotations

import copy
import json
from pathlib import Path

from ninjatradebuilder.logging_record import (
    DEFAULT_LOG_PATH,
    append_log_record,
    build_logging_record_from_watchman,
    read_log_records,
)
from ninjatradebuilder.readiness_adapter import (
    build_readiness_runtime_inputs_from_packet,
)
from ninjatradebuilder.watchman import build_watchman_context_from_runtime_inputs


def _packet_payload(contract: str) -> dict[str, object]:
    fixture_path = Path(__file__).parent / "fixtures" / "packets.valid.json"
    bundle = json.loads(fixture_path.read_text(encoding="utf-8"))
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


def _build_context(contract: str = "ES"):
    runtime_inputs = build_readiness_runtime_inputs_from_packet(_packet_payload(contract))
    return build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())


def test_build_logging_record_from_watchman_ready():
    context = _build_context("ES")

    record = build_logging_record_from_watchman(context, "recheck_at_time")

    assert record.run_type == "watchman_only"
    assert record.watchman_status in {"ready", "blocked", "caution"}
    assert record.final_decision is None
    assert isinstance(record.run_id, str)
    assert record.run_id
    assert record.logged_at.tzinfo is not None
    assert record.logged_at.utcoffset() is not None


def test_build_logging_record_from_watchman_blocked():
    context = _build_context("ES").model_copy(
        update={"hard_lockout_flags": ["stale_market_packet"]}
    )

    record = build_logging_record_from_watchman(context, "recheck_at_time")

    assert record.watchman_status == "blocked"


def test_build_logging_record_from_watchman_caution():
    context = _build_context("ES").model_copy(
        update={"hard_lockout_flags": [], "awareness_flags": ["yield_headwind"]}
    )

    record = build_logging_record_from_watchman(context, "recheck_at_time")

    assert record.watchman_status == "caution"


def test_append_and_read_log_record(tmp_path: Path):
    record = build_logging_record_from_watchman(_build_context("ES"), "recheck_at_time")
    log_path = tmp_path / "test_log.jsonl"

    append_log_record(record, log_path)
    records = read_log_records(log_path)

    assert len(records) == 1
    assert records[0].run_id == record.run_id
    assert records[0].contract == record.contract


def test_append_multiple_records(tmp_path: Path):
    log_path = tmp_path / "test_log.jsonl"
    records = [
        build_logging_record_from_watchman(_build_context("ES"), "recheck_at_time"),
        build_logging_record_from_watchman(_build_context("NQ"), "recheck_at_time"),
        build_logging_record_from_watchman(_build_context("CL"), "recheck_at_time"),
    ]

    for record in records:
        append_log_record(record, log_path)

    stored_records = read_log_records(log_path)

    assert [record.run_id for record in stored_records] == [
        record.run_id for record in records
    ]


def test_read_log_records_returns_empty_for_missing_file(tmp_path: Path):
    assert read_log_records(tmp_path / "missing.jsonl") == []


def test_read_log_records_skips_malformed_lines(tmp_path: Path):
    record = build_logging_record_from_watchman(_build_context("ES"), "recheck_at_time")
    log_path = tmp_path / "test_log.jsonl"
    valid_line = json.dumps(record.model_dump(mode="json"))
    log_path.write_text(valid_line + "\n{not valid json\n", encoding="utf-8")

    records = read_log_records(log_path)

    assert len(records) == 1
    assert records[0].run_id == record.run_id


def test_default_log_path_is_stable():
    assert DEFAULT_LOG_PATH == Path("logs") / "run_history.jsonl"
