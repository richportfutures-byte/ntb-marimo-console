from __future__ import annotations

import json
from pathlib import Path

import pytest

from ntb_marimo_console.adapters.contracts import TriggerEvaluation
from ntb_marimo_console.app import build_phase1_payload
from ntb_marimo_console.demo_fixture_runtime import (
    FixturePipelineBackend,
    build_phase1_dependencies,
    build_runtime_inputs_for_profile,
    default_fixtures_root,
)
from ntb_marimo_console.runtime_profiles import get_runtime_profile
from ntb_marimo_console.trigger_state import TriggerState, TriggerStateResult
from ntb_marimo_console.trigger_state_result_producer import (
    TriggerStateResultProducerRequest,
    build_trigger_state_results,
)
from ntb_marimo_console.viewmodels.models import TriggerStatusVM


FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "golden" / "phase1"
NOW = "2026-05-06T14:00:00+00:00"


def test_producer_builds_real_trigger_state_results_from_brief_and_snapshot() -> None:
    results = build_trigger_state_results(
        TriggerStateResultProducerRequest(
            contract="ES",
            premarket_brief=_brief("ES"),
            live_snapshot=_observable("ES"),
            last_updated=NOW,
        )
    )

    assert len(results) == 1
    result = results[0]
    assert isinstance(result, TriggerStateResult)
    assert result.contract == "ES"
    assert result.setup_id == "es_setup_1"
    assert result.trigger_id == "es_trigger_acceptance"
    assert result.state == TriggerState.TOUCHED
    assert result.blocking_reasons == ("bar_state_required_for_confirmation",)
    assert result.last_updated == NOW
    assert result.pipeline_query_authorized is False


def test_producer_missing_brief_fails_closed_without_display_fallback() -> None:
    results = build_trigger_state_results(
        TriggerStateResultProducerRequest(
            contract="ES",
            premarket_brief=None,
            live_snapshot=_observable("ES"),
            last_updated=NOW,
        )
    )

    assert len(results) == 1
    result = results[0]
    assert result.contract == "ES"
    assert result.setup_id is None
    assert result.trigger_id is None
    assert result.state == TriggerState.UNAVAILABLE
    assert result.blocking_reasons == ("artifact_unavailable",)
    assert result.pipeline_query_authorized is False


def test_producer_missing_snapshot_fails_closed_with_trigger_attribution() -> None:
    results = build_trigger_state_results(
        TriggerStateResultProducerRequest(
            contract="ES",
            premarket_brief=_brief("ES"),
            live_snapshot=None,
            last_updated=NOW,
        )
    )

    assert len(results) == 1
    result = results[0]
    assert result.contract == "ES"
    assert result.setup_id == "es_setup_1"
    assert result.trigger_id == "es_trigger_acceptance"
    assert result.state == TriggerState.UNAVAILABLE
    assert result.blocking_reasons == ("live_snapshot_unavailable",)
    assert result.pipeline_query_authorized is False


def test_producer_mismatched_contract_fails_closed_without_cross_contract_bleed() -> None:
    results = build_trigger_state_results(
        TriggerStateResultProducerRequest(
            contract="NQ",
            premarket_brief=_brief("ES"),
            live_snapshot=_observable("ES"),
            last_updated=NOW,
        )
    )

    assert len(results) == 1
    result = results[0]
    assert result.contract == "NQ"
    assert result.setup_id is None
    assert result.trigger_id is None
    assert result.state == TriggerState.UNAVAILABLE
    assert result.blocking_reasons == ("artifact_unavailable",)


def test_producer_rejects_display_layer_inputs_at_boundary() -> None:
    display_only_inputs = (
        {"contract": "ES", "state": "TOUCHED"},
        TriggerEvaluation(
            trigger_id="es_trigger_acceptance",
            is_valid=True,
            is_true=True,
            missing_fields=(),
            invalid_reasons=(),
        ),
        TriggerStatusVM(
            trigger_id="es_trigger_acceptance",
            is_valid=True,
            is_true=True,
            missing_fields=(),
            invalid_reasons=(),
        ),
    )

    for display_only_input in display_only_inputs:
        with pytest.raises(TypeError):
            build_trigger_state_results(display_only_input)  # type: ignore[arg-type]


def test_producer_rejects_display_objects_inside_request() -> None:
    status_vm = TriggerStatusVM(
        trigger_id="es_trigger_acceptance",
        is_valid=True,
        is_true=True,
        missing_fields=(),
        invalid_reasons=(),
    )

    with pytest.raises(TypeError):
        build_trigger_state_results(
            TriggerStateResultProducerRequest(
                contract="ES",
                premarket_brief=status_vm,  # type: ignore[arg-type]
                live_snapshot=_observable("ES"),
            )
        )


def test_phase1_payload_produces_trigger_state_results_before_display_conversion() -> None:
    profile = get_runtime_profile("fixture_es_demo")
    fixtures_root = default_fixtures_root()
    backend = FixturePipelineBackend(fixtures_root, profile=profile)
    inputs = build_runtime_inputs_for_profile(fixtures_root, profile=profile)
    dependencies = build_phase1_dependencies(fixtures_root, profile=profile)

    artifacts = build_phase1_payload(
        backend=backend,
        inputs=inputs,
        dependencies=dependencies,
        query_action_requested=False,
    )

    assert tuple(type(item) for item in artifacts.trigger_state_results) == (TriggerStateResult,)
    assert artifacts.trigger_state_results[0].contract == "ES"
    assert artifacts.trigger_state_results[0].setup_id == "es_setup_1"
    assert artifacts.trigger_state_results[0].trigger_id == "es_trigger_acceptance"
    assert artifacts.payload.trigger_rows


def _brief(contract: str) -> dict[str, object]:
    return _load_json(FIXTURES_ROOT / "premarket" / contract / "2026-03-25" / "premarket_brief.ready.json")


def _observable(contract: str) -> dict[str, object]:
    return _load_json(FIXTURES_ROOT / "observables" / contract / "trigger_true.json")


def _load_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        parsed = json.load(handle)
    assert isinstance(parsed, dict)
    return parsed
