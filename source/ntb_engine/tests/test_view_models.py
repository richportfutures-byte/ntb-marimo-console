from __future__ import annotations

import builtins
import importlib
import sys
from types import SimpleNamespace

from ninjatradebuilder.pipeline import PipelineExecutionResult
from ninjatradebuilder.watchman import TriggerProximity

MODULE_NAME = "ninjatradebuilder.view_models"


def _load_module():
    return importlib.import_module(MODULE_NAME)


def _make_context(
    *,
    contract: str = "ES",
    hard_lockout_flags: list[str] | None = None,
    awareness_flags: list[str] | None = None,
    missing_inputs: list[str] | None = None,
    trigger_proximity: TriggerProximity | None = None,
):
    return SimpleNamespace(
        contract=contract,
        hard_lockout_flags=hard_lockout_flags or [],
        awareness_flags=awareness_flags or [],
        missing_inputs=missing_inputs or [],
        session_state="RTH",
        vwap_posture_state="price_above_vwap",
        value_location_state="above_value",
        level_proximity_state="near_overnight_level",
        trigger_context_state="scheduled_recheck_pending",
        trigger_proximity=trigger_proximity
        or TriggerProximity(
            trigger_family="recheck_at_time",
            time_distance_minutes=10.0,
        ),
        contract_specific_macro_state="breadth_cash_delta_aligned",
        event_risk_state="clear",
    )


def test_view_models_imports_without_marimo(monkeypatch) -> None:
    original_import = builtins.__import__
    sys.modules.pop(MODULE_NAME, None)

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "marimo":
            raise AssertionError("view_models should not import marimo")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    module = importlib.import_module(MODULE_NAME)

    assert module.__name__ == MODULE_NAME


def test_readiness_card_status_blocked_when_hard_lockouts_present() -> None:
    view_models = _load_module()

    card = view_models.readiness_card_from_context(
        _make_context(hard_lockout_flags=["stale_market_packet"])
    )

    assert card.status == "blocked"


def test_readiness_card_status_caution_when_awareness_flags_present() -> None:
    view_models = _load_module()

    card = view_models.readiness_card_from_context(
        _make_context(awareness_flags=["yield_headwind"])
    )

    assert card.status == "caution"


def test_readiness_card_status_caution_when_missing_inputs_present() -> None:
    view_models = _load_module()

    card = view_models.readiness_card_from_context(
        _make_context(missing_inputs=["cross_market_context"])
    )

    assert card.status == "caution"


def test_readiness_card_status_ready_when_clean() -> None:
    view_models = _load_module()

    card = view_models.readiness_card_from_context(_make_context())

    assert card.status == "ready"


def test_readiness_card_trigger_proximity_summary_for_time() -> None:
    view_models = _load_module()
    context = _make_context(
        trigger_proximity=TriggerProximity(
            trigger_family="recheck_at_time",
            time_distance_minutes=10.0,
        )
    )

    card = view_models.readiness_card_from_context(context)

    assert "10" in card.trigger_proximity_summary
    assert "min" in card.trigger_proximity_summary


def test_readiness_card_trigger_proximity_summary_for_price() -> None:
    view_models = _load_module()
    context = _make_context(
        trigger_proximity=TriggerProximity(
            trigger_family="price_level_touch",
            price_distance_ticks=5.0,
        )
    )

    card = view_models.readiness_card_from_context(context)

    assert "5" in card.trigger_proximity_summary
    assert "tick" in card.trigger_proximity_summary


def test_readiness_cards_from_sweep_returns_sorted_list() -> None:
    view_models = _load_module()
    sweep_result = {
        "NQ": _make_context(contract="NQ"),
        "ES": _make_context(contract="ES"),
        "CL": _make_context(contract="CL"),
    }

    cards = view_models.readiness_cards_from_sweep(sweep_result)

    assert [card.contract for card in cards] == ["CL", "ES", "NQ"]


def test_pipeline_result_view_full_pipeline() -> None:
    view_models = _load_module()
    result = PipelineExecutionResult(
        contract="ES",
        termination_stage="risk_authorization",
        final_decision="TRADE_APPROVED",
        sufficiency_gate_output=SimpleNamespace(status="READY"),
        contract_analysis=SimpleNamespace(outcome="ANALYSIS_COMPLETE"),
        proposed_setup=SimpleNamespace(outcome="SETUP_PROPOSED"),
        risk_authorization=SimpleNamespace(decision="APPROVED"),
    )

    view = view_models.pipeline_result_view(result)

    assert view.contract == "ES"
    assert view.final_decision == "TRADE_APPROVED"
    assert view.termination_stage == "risk_authorization"
    assert tuple(row.reached for row in view.stages) == (True, True, True, True)
    assert tuple(row.outcome for row in view.stages) == (
        "READY",
        "ANALYSIS_COMPLETE",
        "SETUP_PROPOSED",
        "APPROVED",
    )


def test_pipeline_result_view_early_termination() -> None:
    view_models = _load_module()
    result = PipelineExecutionResult(
        contract="CL",
        termination_stage="sufficiency_gate",
        final_decision="INSUFFICIENT_DATA",
        sufficiency_gate_output=SimpleNamespace(status="INSUFFICIENT_DATA"),
    )

    view = view_models.pipeline_result_view(result)

    assert tuple(row.reached for row in view.stages) == (True, False, False, False)
    assert tuple(row.outcome for row in view.stages) == (
        "INSUFFICIENT_DATA",
        None,
        None,
        None,
    )
