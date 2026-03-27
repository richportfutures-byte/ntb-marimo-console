from __future__ import annotations

import io
import json
from pathlib import Path

from ninjatradebuilder.cli import run_cli

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _valid_contract_analysis(contract: str, outcome: str = "NO_TRADE") -> dict:
    return {
        "$schema": "contract_analysis_v1",
        "stage": "contract_market_read",
        "contract": contract,
        "timestamp": "2026-01-14T14:06:00Z",
        "market_regime": "range_bound",
        "directional_bias": "bullish",
        "key_levels": {
            "support_levels": [4485.0],
            "resistance_levels": [4495.0],
            "pivot_level": 4490.0,
        },
        "evidence_score": 6,
        "confidence_band": "MEDIUM",
        "value_context": {
            "relative_to_prior_value_area": "inside",
            "relative_to_current_developing_value": "inside_value",
            "relative_to_vwap": "above",
            "relative_to_prior_day_range": "inside",
        },
        "structural_notes": "Price is holding above pivot with one conflicting signal.",
        "outcome": outcome,
        "conflicting_signals": ["delta mixed"] if outcome == "ANALYSIS_COMPLETE" else ["conflict"],
        "assumptions": [],
    }


def test_cli_fails_fast_when_gemini_api_key_is_missing(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = run_cli(
        [
            "--packet",
            str(FIXTURES_DIR / "packets.valid.json"),
            "--contract",
            "ES",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert "GEMINI_API_KEY is required for CLI execution." in stderr.getvalue()


def test_cli_runs_bundle_packet_and_prints_pipeline_json(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    stdout = io.StringIO()
    stderr = io.StringIO()
    captured: dict[str, object] = {}

    class FakeGeminiAdapter:
        def __init__(self, *, client, model, timeout_seconds=None, max_retries=0):
            captured["client"] = client
            captured["model"] = model
            captured["timeout_seconds"] = timeout_seconds
            captured["max_retries"] = max_retries

        def generate_structured(self, request):
            captured["prompt_id"] = request.prompt_id
            return _valid_contract_analysis("ES", outcome="NO_TRADE")

    monkeypatch.setattr("ninjatradebuilder.cli.GeminiResponsesAdapter", FakeGeminiAdapter)

    exit_code = run_cli(
        [
            "--packet",
            str(FIXTURES_DIR / "packets.valid.json"),
            "--contract",
            "ES",
            "--model",
            "gemini-test-model",
        ],
        stdout=stdout,
        stderr=stderr,
        client_factory=lambda config: config,
    )

    output = stdout.getvalue()
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert '"termination_stage": "contract_market_read"' in output
    assert '"final_decision": "NO_TRADE"' in output
    assert '"contract": "ES"' in output
    assert captured["client"].api_key == "test-key"
    assert captured["client"].timeout_seconds == 20
    assert captured["client"].max_retries == 1
    assert captured["model"] == "gemini-test-model"
    assert captured["timeout_seconds"] == 20
    assert captured["max_retries"] == 1
    assert captured["prompt_id"] == 2


def test_cli_writes_success_audit_record(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    audit_path = tmp_path / "audit.jsonl"
    stdout = io.StringIO()
    stderr = io.StringIO()

    class FakeGeminiAdapter:
        def __init__(self, *, client, model, timeout_seconds=None, max_retries=0):
            self.client = client

        def generate_structured(self, request):
            return _valid_contract_analysis("ES", outcome="NO_TRADE")

    monkeypatch.setattr("ninjatradebuilder.cli.GeminiResponsesAdapter", FakeGeminiAdapter)

    exit_code = run_cli(
        [
            "--packet",
            str(FIXTURES_DIR / "packets.valid.json"),
            "--contract",
            "ES",
            "--audit-log",
            str(audit_path),
        ],
        stdout=stdout,
        stderr=stderr,
        client_factory=lambda config: config,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    record = json.loads(audit_path.read_text().strip())
    assert record["audit_schema"] == "operator_cli_run_v1"
    assert record["contract"] == "ES"
    assert record["model"] == "gemini-3.1-pro-preview"
    assert record["timeout_seconds"] == 20
    assert record["max_retries"] == 1
    assert record["termination_stage"] == "contract_market_read"
    assert record["final_decision"] == "NO_TRADE"
    assert record["status"] == "success"
    assert record["success"] is True
    assert record["error_message"] is None


def test_cli_rejects_bundle_packet_without_contract(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = run_cli(
        [
            "--packet",
            str(FIXTURES_DIR / "packets.valid.json"),
        ],
        stdout=stdout,
        stderr=stderr,
        client_factory=lambda api_key: {"api_key": api_key},
    )

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert "Bundle packet files require --contract." in stderr.getvalue()


def test_cli_rejects_invalid_timeout_configuration(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("NINJATRADEBUILDER_GEMINI_TIMEOUT_SECONDS", "9")
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = run_cli(
        [
            "--packet",
            str(FIXTURES_DIR / "packets.valid.json"),
            "--contract",
            "ES",
        ],
        stdout=stdout,
        stderr=stderr,
        client_factory=lambda config: config,
    )

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert "NINJATRADEBUILDER_GEMINI_TIMEOUT_SECONDS must be >= 10." in stderr.getvalue()


def test_cli_writes_failure_audit_record(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    audit_path = tmp_path / "audit.jsonl"
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = run_cli(
        [
            "--packet",
            str(FIXTURES_DIR / "packets.valid.json"),
            "--contract",
            "ES",
            "--audit-log",
            str(audit_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert "GEMINI_API_KEY is required for CLI execution." in stderr.getvalue()
    record = json.loads(audit_path.read_text().strip())
    assert record["contract"] == "ES"
    assert record["status"] == "failure"
    assert record["success"] is False
    assert record["termination_stage"] is None
    assert record["final_decision"] is None
    assert record["error_category"] == "config_error"
    assert record["error_type"] == "ConfigError"
    assert "GEMINI_API_KEY is required for CLI execution." in record["error_message"]
