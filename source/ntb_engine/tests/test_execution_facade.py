from __future__ import annotations

import builtins
import copy
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ninjatradebuilder.pipeline import PipelineExecutionResult
from ninjatradebuilder.watchman import WatchmanReadinessContext

FIXTURES_DIR = Path(__file__).parent / "fixtures"
MODULE_NAME = "ninjatradebuilder.execution_facade"


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


def _load_module():
    return importlib.import_module(MODULE_NAME)


def test_execution_facade_imports_without_marimo(monkeypatch) -> None:
    original_import = builtins.__import__
    sys.modules.pop(MODULE_NAME, None)

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "marimo":
            raise AssertionError("execution_facade should not import marimo")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    module = importlib.import_module(MODULE_NAME)

    assert module.__name__ == MODULE_NAME


def test_run_pipeline_delegates_to_pipeline_entrypoint_for_bundle_packet(monkeypatch) -> None:
    execution_facade = _load_module()
    captured: dict[str, object] = {}
    expected_result = object()

    def fake_run_pipeline(*, packet, evaluation_timestamp_iso, model_adapter):
        captured["packet"] = packet
        captured["evaluation_timestamp_iso"] = evaluation_timestamp_iso
        captured["model_adapter"] = model_adapter
        return expected_result

    monkeypatch.setattr(execution_facade.pipeline_module, "run_pipeline", fake_run_pipeline)
    adapter = object()

    result = execution_facade.run_pipeline(
        _load_packet_bundle(),
        "ES",
        model_adapter=adapter,
    )

    assert result is expected_result
    assert captured["packet"]["$schema"] == "historical_packet_v1"
    assert captured["packet"]["market_packet"]["contract"] == "ES"
    assert captured["evaluation_timestamp_iso"] == "2026-01-14T15:05:00Z"
    assert captured["model_adapter"] is adapter


def test_run_readiness_for_contract_builds_runtime_inputs_from_packet(monkeypatch) -> None:
    execution_facade = _load_module()
    captured: dict[str, object] = {}
    runtime_inputs = {"contract_metadata_json": {"contract": "ZN"}}
    expected_result = object()

    def fake_build(packet_payload):
        captured["packet_payload"] = packet_payload
        return runtime_inputs

    def fake_run_readiness(*, runtime_inputs, readiness_trigger, model_adapter):
        captured["runtime_inputs"] = runtime_inputs
        captured["readiness_trigger"] = readiness_trigger
        captured["model_adapter"] = model_adapter
        return expected_result

    monkeypatch.setattr(
        execution_facade.readiness_adapter_module,
        "build_readiness_runtime_inputs_from_packet",
        fake_build,
    )
    monkeypatch.setattr(execution_facade.runtime_module, "run_readiness", fake_run_readiness)
    adapter = object()
    trigger = {"trigger_family": "recheck_at_time", "recheck_at_time": "2026-01-14T15:15:00Z"}

    result = execution_facade.run_readiness_for_contract(
        _load_packet("ZN"),
        trigger,
        model_adapter=adapter,
    )

    assert result is expected_result
    assert captured["packet_payload"]["market_packet"]["contract"] == "ZN"
    assert captured["runtime_inputs"] == runtime_inputs
    assert captured["readiness_trigger"] == trigger
    assert captured["model_adapter"] is adapter


def test_run_readiness_for_contract_uses_runtime_inputs_path_without_packet_conversion(
    monkeypatch,
) -> None:
    execution_facade = _load_module()
    runtime_inputs = {
        "master_doctrine_text": "MASTER DOCTRINE",
        "evaluation_timestamp_iso": "2026-01-14T15:05:00Z",
        "challenge_state_json": {},
        "contract_metadata_json": {"contract": "ZN"},
        "market_packet_json": {"contract": "ZN"},
        "contract_specific_extension_json": {"contract": "ZN"},
        "attached_visuals_json": {},
    }
    captured: dict[str, object] = {}
    expected_result = object()

    def fail_build(packet_payload):
        raise AssertionError("packet conversion should not run for readiness runtime inputs")

    def fake_run_readiness(*, runtime_inputs, readiness_trigger, model_adapter):
        captured["runtime_inputs"] = runtime_inputs
        captured["readiness_trigger"] = readiness_trigger
        captured["model_adapter"] = model_adapter
        return expected_result

    monkeypatch.setattr(
        execution_facade.readiness_adapter_module,
        "build_readiness_runtime_inputs_from_packet",
        fail_build,
    )
    monkeypatch.setattr(execution_facade.runtime_module, "run_readiness", fake_run_readiness)
    adapter = object()
    trigger = {"trigger_family": "price_level_touch", "price_level": 110.40625}

    result = execution_facade.run_readiness_for_contract(
        runtime_inputs,
        trigger,
        model_adapter=adapter,
    )

    assert result is expected_result
    assert captured["runtime_inputs"] == runtime_inputs
    assert captured["readiness_trigger"] == trigger
    assert captured["model_adapter"] is adapter


def test_sweep_watchman_returns_watchman_context_for_all_bundle_contracts() -> None:
    execution_facade = _load_module()
    trigger = {"trigger_family": "recheck_at_time", "recheck_at_time": "2026-01-14T15:15:00Z"}

    result = execution_facade.sweep_watchman(_load_packet_bundle(), trigger)

    assert isinstance(result, dict)
    assert set(result) == {"ES", "NQ", "CL", "ZN", "6E", "MGC"}
    for contract, context in result.items():
        assert isinstance(context, WatchmanReadinessContext)
        assert context.contract == contract


def test_sweep_watchman_rejects_non_mapping_input() -> None:
    execution_facade = _load_module()
    trigger = {"trigger_family": "recheck_at_time", "recheck_at_time": "2026-01-14T15:15:00Z"}

    with pytest.raises(TypeError):
        execution_facade.sweep_watchman("not-a-bundle", trigger)


def test_sweep_watchman_rejects_malformed_bundle() -> None:
    execution_facade = _load_module()
    trigger = {"trigger_family": "recheck_at_time", "recheck_at_time": "2026-01-14T15:15:00Z"}

    with pytest.raises(ValueError) as exc_info:
        execution_facade.sweep_watchman({"bundle": "missing-sections"}, trigger)

    assert "shared and contracts sections" in str(exc_info.value)


def test_sweep_watchman_skips_unsupported_contracts() -> None:
    execution_facade = _load_module()
    trigger = {"trigger_family": "recheck_at_time", "recheck_at_time": "2026-01-14T15:15:00Z"}
    bundle = _load_packet_bundle()
    bundle["contracts"]["XX"] = {"bogus": True}

    result = execution_facade.sweep_watchman(bundle, trigger)

    assert "XX" not in result
    assert set(result) == {"ES", "NQ", "CL", "ZN", "6E", "MGC"}


def test_summarize_pipeline_result_returns_deterministic_concise_summary() -> None:
    execution_facade = _load_module()
    result = PipelineExecutionResult(
        contract="ES",
        termination_stage="risk_authorization",
        final_decision="TRADE_REDUCED",
        contract_analysis=SimpleNamespace(outcome="ANALYSIS_COMPLETE"),
        proposed_setup=SimpleNamespace(outcome="SETUP_PROPOSED"),
        risk_authorization=SimpleNamespace(decision="REDUCED"),
    )

    summary = execution_facade.summarize_pipeline_result(result)

    assert summary == {
        "contract": "ES",
        "termination_stage": "risk_authorization",
        "final_decision": "TRADE_REDUCED",
        "sufficiency_gate_status": None,
        "contract_analysis_outcome": "ANALYSIS_COMPLETE",
        "proposed_setup_outcome": "SETUP_PROPOSED",
        "risk_authorization_decision": "REDUCED",
    }
