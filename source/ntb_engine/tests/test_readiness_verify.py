from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from ninjatradebuilder.readiness_verify import (
    _classify_failure,
    build_parser,
    run_cli,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
READINESS_FIXTURES_DIR = FIXTURES_DIR / "readiness"


class FakeGeminiAdapter:
    def __init__(self, *, client, model, timeout_seconds=None, max_retries=0):
        self.client = client
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.calls: list[Any] = []

    def generate_structured(self, request):
        self.calls.append(request)
        return json.loads((READINESS_FIXTURES_DIR / "zn_wait_for_trigger.expected.json").read_text())


class MultiContractFakeGeminiAdapter(FakeGeminiAdapter):
    def generate_structured(self, request):
        self.calls.append(request)
        rendered = request.rendered_prompt
        marker = '"contract": '
        start = rendered.index(marker) + len(marker)
        contract = rendered[start:].split('"', 2)[1]
        timestamp = "2026-01-14T15:05:00Z"
        return {
            "$schema": "readiness_engine_output_v1",
            "stage": "readiness_engine",
            "authority": "ESCALATE_ONLY",
            "contract": contract,
            "timestamp": timestamp,
            "status": "WAIT_FOR_TRIGGER",
            "doctrine_gates": [
                {"gate": "data_sufficiency_gate", "state": "PASS", "rationale": "Inputs complete."},
                {"gate": "context_alignment_gate", "state": "PASS", "rationale": "Context aligned."},
                {"gate": "structure_quality_gate", "state": "PASS", "rationale": "Structure acceptable."},
                {"gate": "trigger_gate", "state": "WAIT", "rationale": "Awaiting trigger."},
                {"gate": "risk_window_gate", "state": "PASS", "rationale": "Risk window open."},
                {"gate": "lockout_gate", "state": "PASS", "rationale": "No lockout."},
            ],
            "trigger_data": {
                "family": "recheck_at_time",
                "recheck_at_time": "2026-01-14T15:15:00Z",
                "price_level": None,
            },
            "wait_for_trigger_reason": "timing_window_not_open",
            "lockout_reason": None,
            "insufficient_data_reasons": [],
            "missing_inputs": [],
        }


def test_readiness_verify_help_text_describes_modes() -> None:
    help_text = build_parser().format_help()

    assert "--fixture" in help_text
    assert "--packet-file" in help_text
    assert "--runtime-input-file" in help_text
    assert "--all-contracts" in help_text
    assert "--packet-contract" in help_text


def test_readiness_verify_returns_zero_and_writes_artifact_for_runtime_input(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("ninjatradebuilder.readiness_verify.GeminiResponsesAdapter", FakeGeminiAdapter)
    stdout = io.StringIO()
    stderr = io.StringIO()
    artifact_path = tmp_path / "artifact.json"

    exit_code = run_cli(
        [
            "--runtime-input-file",
            str(READINESS_FIXTURES_DIR / "zn_runtime_inputs.valid.json"),
            "--trigger-file",
            str(READINESS_FIXTURES_DIR / "zn_recheck_trigger.valid.json"),
            "--contract",
            "ZN",
            "--artifact-file",
            str(artifact_path),
        ],
        stdout=stdout,
        stderr=stderr,
        client_factory=lambda config: config,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    artifact = json.loads(artifact_path.read_text())
    assert artifact["artifact_schema"] == "readiness_verification_run_v1"
    assert artifact["run"]["success"] is True
    assert artifact["run"]["invocation_mode"] == "single_contract"
    assert artifact["results"][0]["contract"] == "ZN"
    assert artifact["results"][0]["validation"]["outcome"] == "validated"
    assert artifact["results"][0]["failure_classification"] is None
    assert artifact["results"][0]["prompt"]["rendered_prompt_sha256"]
    assert artifact["results"][0]["summary"] == "ZN: PASS (validated)."


def test_readiness_verify_returns_nonzero_for_contract_mismatch(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("ninjatradebuilder.readiness_verify.GeminiResponsesAdapter", FakeGeminiAdapter)
    stdout = io.StringIO()
    stderr = io.StringIO()
    artifact_path = tmp_path / "artifact.json"

    exit_code = run_cli(
        [
            "--runtime-input-file",
            str(READINESS_FIXTURES_DIR / "zn_runtime_inputs.valid.json"),
            "--trigger-file",
            str(READINESS_FIXTURES_DIR / "zn_recheck_trigger.valid.json"),
            "--contract",
            "ES",
            "--artifact-file",
            str(artifact_path),
        ],
        stdout=stdout,
        stderr=stderr,
        client_factory=lambda config: config,
    )

    assert exit_code == 1
    artifact = json.loads(artifact_path.read_text())
    assert artifact["run"]["success"] is False
    assert artifact["results"][0]["failure_classification"] == "contract_mismatch_error"
    assert artifact["results"][0]["summary"] == "ES: FAIL (contract_mismatch_error)."


def test_readiness_verify_all_contracts_formats_summary(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        "ninjatradebuilder.readiness_verify.GeminiResponsesAdapter",
        MultiContractFakeGeminiAdapter,
    )
    stdout = io.StringIO()
    stderr = io.StringIO()
    artifact_path = tmp_path / "artifact.json"
    packets_fixture = FIXTURES_DIR / "packets.valid.json"
    trigger_file = READINESS_FIXTURES_DIR / "zn_recheck_trigger.valid.json"

    exit_code = run_cli(
        [
            "--packet-file",
            str(packets_fixture),
            "--trigger-file",
            str(trigger_file),
            "--all-contracts",
            "--artifact-file",
            str(artifact_path),
        ],
        stdout=stdout,
        stderr=stderr,
        client_factory=lambda config: config,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    artifact = json.loads(artifact_path.read_text())
    assert artifact["run"]["invocation_mode"] == "contract_sweep"
    assert artifact["run"]["summary"] == "Readiness verification passed for 6/6 contract(s)."
    assert len(artifact["results"]) == 6
    assert all(result["summary"].endswith("PASS (validated).") for result in artifact["results"])


def test_readiness_verify_invalid_mode_returns_operator_error(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = run_cli(
        [
            "--packet-file",
            str(FIXTURES_DIR / "packets.valid.json"),
            "--contract",
            "ES",
        ],
        stdout=stdout,
        stderr=stderr,
        client_factory=lambda config: config,
    )

    assert exit_code == 2
    assert "--trigger-file is required with --packet-file." in stderr.getvalue()


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (ValueError("Model output failed schema validation for prompt 10"), "schema_validation_error"),
        (ValueError("Contract mismatch across runtime inputs"), "contract_mismatch_error"),
        (RuntimeError("boom"), "unexpected_runtime_error"),
    ],
)
def test_failure_classification_mapping(message: Exception, expected: str) -> None:
    assert _classify_failure(message) == expected
