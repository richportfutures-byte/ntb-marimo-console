from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ntb_marimo_console.adapters.contracts import TriggerSpec
from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.live_observables.quality import contract_tick_size
from ntb_marimo_console.live_observables.schema_v2 import (
    ContractObservableV2,
    LiveObservableSnapshotV2,
    QualityObservableV2,
    QuoteObservableV2,
)
from ntb_marimo_console.market_data import ChartFuturesBarBuilder
from ntb_marimo_console.market_data.chart_bars import ContractBarState
from ntb_marimo_console.trigger_state import (
    TRIGGER_STATES,
    TriggerInvalidatorState,
    TriggerLockoutState,
    TriggerState,
    TriggerStateRequest,
    evaluate_trigger_state,
    evaluate_trigger_state_from_brief,
)


FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "golden" / "phase1"
BRIEF_PATHS = {
    "ES": FIXTURES_ROOT / "premarket" / "ES" / "2026-03-25" / "premarket_brief.ready.json",
    "NQ": FIXTURES_ROOT / "premarket" / "NQ" / "2026-01-14" / "premarket_brief.ready.json",
    "CL": FIXTURES_ROOT / "premarket" / "CL" / "2026-01-14" / "premarket_brief.ready.json",
    "6E": FIXTURES_ROOT / "premarket" / "6E" / "2026-01-14" / "premarket_brief.ready.json",
    "MGC": FIXTURES_ROOT / "premarket" / "MGC" / "2026-01-14" / "premarket_brief.ready.json",
    "ZN": FIXTURES_ROOT / "premarket" / "ZN" / "2026-01-14" / "premarket_brief.ready.json",
}
OBSERVABLE_PATHS = {
    contract: FIXTURES_ROOT / "observables" / contract / "trigger_true.json"
    for contract in ("ES", "NQ", "CL", "6E", "MGC", "ZN")
}
LEVELS = {
    "ES": 5604.0,
    "NQ": 18142.0,
    "CL": 73.35,
    "6E": 1.0912,
    "MGC": 2054.2,
}
EXPECTED_SYMBOLS = {
    "ES": "/ESM26",
    "NQ": "/NQM26",
    "CL": "/CLM26",
    "6E": "/6EM26",
    "MGC": "/MGCM26",
}
BASE_TIME = datetime(2026, 5, 6, 14, 0, 0, tzinfo=timezone.utc)


def test_declared_trigger_states_are_stable() -> None:
    assert tuple(state.value for state in TRIGGER_STATES) == (
        "UNAVAILABLE",
        "DORMANT",
        "APPROACHING",
        "TOUCHED",
        "ARMED",
        "QUERY_READY",
        "INVALIDATED",
        "BLOCKED",
        "LOCKOUT",
        "STALE",
        "ERROR",
    )


def test_same_input_snapshot_returns_same_state_and_payload() -> None:
    brief = _brief("ES")
    snapshot = _observable("ES")
    bar_state = completed_bar_state("ES")

    first = evaluate_trigger_state_from_brief(brief, snapshot, bar_state=bar_state)
    second = evaluate_trigger_state_from_brief(brief, snapshot, bar_state=bar_state)

    assert first.state == TriggerState.QUERY_READY
    assert second.state == TriggerState.QUERY_READY
    assert first.to_dict() == second.to_dict()


def test_core_fail_closed_state_transitions_are_deterministic() -> None:
    brief = _brief("ES")
    ready_snapshot = _observable("ES")
    covered = [
        evaluate_trigger_state_from_brief(None, ready_snapshot, bar_state=completed_bar_state("ES")),
        evaluate_trigger_state_from_brief(brief, _es_snapshot(current_price=5598.0), bar_state=completed_bar_state("ES")),
        evaluate_trigger_state_from_brief(brief, _es_snapshot(current_price=5603.5), bar_state=completed_bar_state("ES")),
        evaluate_trigger_state_from_brief(brief, ready_snapshot, bar_state=ContractBarState(contract="ES")),
        evaluate_trigger_state_from_brief(brief, ready_snapshot, bar_state=partial_bar_state("ES")),
        evaluate_trigger_state_from_brief(brief, ready_snapshot, bar_state=completed_bar_state("ES")),
        evaluate_trigger_state_from_brief(
            brief,
            ready_snapshot,
            bar_state=completed_bar_state("ES"),
            invalidators=(TriggerInvalidatorState("es_delta_failure", active=True),),
        ),
        evaluate_trigger_state_from_brief(brief, _missing_breadth_snapshot(), bar_state=completed_bar_state("ES")),
        evaluate_trigger_state_from_brief(
            brief,
            ready_snapshot,
            bar_state=completed_bar_state("ES"),
            event_lockout=TriggerLockoutState(active=True, reason="operator_event_lockout"),
        ),
        evaluate_trigger_state_from_brief(
            brief,
            ready_snapshot,
            bar_state=completed_bar_state("ES"),
            quote_fresh=False,
            quote_blocking_reasons=("stale_or_missing_timestamp:ES",),
        ),
    ]

    assert {result.state for result in covered} == {
        TriggerState.UNAVAILABLE,
        TriggerState.DORMANT,
        TriggerState.APPROACHING,
        TriggerState.TOUCHED,
        TriggerState.ARMED,
        TriggerState.QUERY_READY,
        TriggerState.INVALIDATED,
        TriggerState.BLOCKED,
        TriggerState.LOCKOUT,
        TriggerState.STALE,
    }
    for result in covered:
        assert result.pipeline_query_authorized is False
        assert set(result.authorizations.to_dict().values()) == {False}


def test_missing_required_field_never_returns_query_ready() -> None:
    result = evaluate_trigger_state_from_brief(
        _brief("ES"),
        _missing_breadth_snapshot(),
        bar_state=completed_bar_state("ES"),
    )

    assert result.state == TriggerState.BLOCKED
    assert result.pipeline_query_authorized is False
    assert "cross_asset.breadth.current_advancers_pct" in result.missing_fields
    assert "missing_required_live_fields" in result.blocking_reasons


def test_quote_only_snapshot_v2_does_not_infer_missing_trigger_evidence() -> None:
    es_result = evaluate_trigger_state_from_brief(
        _brief("ES"),
        quote_only_snapshot_v2("ES", last=5605.0),
        bar_state=completed_bar_state("ES"),
    )
    mgc_result = evaluate_trigger_state_from_brief(
        _brief("MGC"),
        quote_only_snapshot_v2("MGC", last=2054.3),
        bar_state=completed_bar_state("MGC"),
    )

    assert es_result.state == TriggerState.BLOCKED
    assert "market.cumulative_delta" in es_result.missing_fields
    assert "cross_asset.breadth.current_advancers_pct" in es_result.missing_fields
    assert mgc_result.state == TriggerState.BLOCKED
    assert "cross_asset.dxy" in mgc_result.missing_fields
    assert "cross_asset.cash_10y_yield" in mgc_result.missing_fields
    assert "macro_context.fear_catalyst_state" in mgc_result.missing_fields


def test_stale_quote_returns_stale_not_query_ready() -> None:
    result = evaluate_trigger_state_from_brief(
        _brief("ES"),
        _observable("ES"),
        bar_state=completed_bar_state("ES"),
        quote_fresh=False,
        quote_blocking_reasons=("stale_or_missing_timestamp:ES",),
    )

    assert result.state == TriggerState.STALE
    assert "quote_stale" in result.blocking_reasons
    assert result.pipeline_query_authorized is False


def test_stale_required_bar_data_returns_stale_not_query_ready() -> None:
    result = evaluate_trigger_state_from_brief(
        _brief("NQ"),
        _observable("NQ"),
        bar_state=stale_bar_state("NQ"),
    )

    assert result.state == TriggerState.STALE
    assert any(reason.startswith("bar_state_stale:stale_bar_data:") for reason in result.blocking_reasons)
    assert result.pipeline_query_authorized is False


def test_event_lockout_overrides_armed_and_query_ready() -> None:
    brief = _brief("ES")
    snapshot = _observable("ES")
    lockout = TriggerLockoutState(active=True, reason="operator_event_lockout")

    armed = evaluate_trigger_state_from_brief(
        brief,
        snapshot,
        bar_state=partial_bar_state("ES"),
        event_lockout=lockout,
    )
    query_ready = evaluate_trigger_state_from_brief(
        brief,
        snapshot,
        bar_state=completed_bar_state("ES"),
        event_lockout=lockout,
    )

    for result in (armed, query_ready):
        assert result.state == TriggerState.LOCKOUT
        assert result.blocking_reasons == ("event_lockout_active", "operator_event_lockout")
        assert result.pipeline_query_authorized is False


def test_invalidated_setup_cannot_be_query_ready_without_explicit_reset() -> None:
    brief = _brief("ES")
    snapshot = _observable("ES")

    invalidated = evaluate_trigger_state_from_brief(
        brief,
        snapshot,
        bar_state=completed_bar_state("ES"),
        invalidators=(TriggerInvalidatorState("acceptance_failure", active=True),),
    )
    reset = evaluate_trigger_state_from_brief(
        brief,
        snapshot,
        bar_state=completed_bar_state("ES"),
        invalidators=(TriggerInvalidatorState("acceptance_failure", active=True, reset_condition_met=True),),
    )

    assert invalidated.state == TriggerState.INVALIDATED
    assert invalidated.invalid_reasons == ("invalidator_fired:acceptance_failure",)
    assert reset.state == TriggerState.QUERY_READY
    assert reset.pipeline_query_authorized is False


def test_partial_bars_are_not_treated_as_completed_confirmation() -> None:
    result = evaluate_trigger_state_from_brief(
        _brief("ES"),
        _observable("ES"),
        bar_state=partial_bar_state("ES"),
    )

    assert result.state == TriggerState.ARMED
    assert "completed_five_minute_confirmation_required" in result.blocking_reasons
    assert "building_five_minute_bar_not_confirmation" in result.blocking_reasons
    assert result.pipeline_query_authorized is False


def test_display_bar_object_cannot_provide_query_ready_provenance() -> None:
    class DisplayBarState:
        completed_five_minute_bars = completed_bar_state("ES").completed_five_minute_bars
        completed_one_minute_bars = completed_bar_state("ES").completed_one_minute_bars
        building_five_minute_bar = None
        blocking_reasons: tuple[str, ...] = ()

    result = evaluate_trigger_state_from_brief(
        _brief("ES"),
        _observable("ES"),
        bar_state=DisplayBarState(),  # type: ignore[arg-type]
    )

    assert result.state == TriggerState.BLOCKED
    assert "bar_state_provenance_not_verified" in result.blocking_reasons
    assert result.pipeline_query_authorized is False


def test_completed_five_minute_confirmation_requires_every_quality_gate() -> None:
    ready = evaluate_trigger_state_from_brief(
        _brief("ES"),
        _observable("ES"),
        bar_state=completed_bar_state("ES"),
    )
    missing = evaluate_trigger_state_from_brief(
        _brief("ES"),
        _missing_breadth_snapshot(),
        bar_state=completed_bar_state("ES"),
    )
    stale = evaluate_trigger_state_from_brief(
        _brief("ES"),
        _observable("ES"),
        bar_state=completed_bar_state("ES"),
        quote_fresh=False,
    )

    assert ready.state == TriggerState.QUERY_READY
    assert ready.pipeline_query_authorized is False
    assert missing.state == TriggerState.BLOCKED
    assert stale.state == TriggerState.STALE


@pytest.mark.parametrize("contract", ("ES", "NQ", "CL", "6E", "MGC"))
def test_final_target_fixtures_evaluate_through_trigger_state_engine(contract: str) -> None:
    result = evaluate_trigger_state_from_brief(
        _brief(contract),
        _observable(contract),
        bar_state=completed_bar_state(contract),
    )

    assert result.state == TriggerState.QUERY_READY
    assert result.contract == contract
    assert result.required_fields
    assert result.pipeline_query_authorized is False


def test_mgc_remains_micro_gold_only_and_does_not_depend_on_gc() -> None:
    result = evaluate_trigger_state_from_brief(
        _brief("MGC"),
        _observable("MGC"),
        bar_state=completed_bar_state("MGC"),
    )
    encoded = json.dumps(result.to_dict(), sort_keys=True)

    assert result.contract == "MGC"
    assert result.state == TriggerState.QUERY_READY
    assert "GC" not in result.required_fields
    assert '"contract": "GC"' not in encoded
    assert '"trigger_id": "gc' not in encoded.lower()
    assert "MGC" in final_target_contracts()
    assert "GC" not in final_target_contracts()


def test_gc_and_zn_remain_excluded_from_trigger_state_eligibility() -> None:
    zn = evaluate_trigger_state_from_brief(
        _brief("ZN"),
        _observable("ZN"),
        bar_state=None,
    )
    gc = evaluate_trigger_state(
        TriggerStateRequest(
            contract="GC",
            trigger_spec=TriggerSpec(
                id="gc_unsupported",
                predicate="market.current_price >= 1",
                required_live_field_paths=("market.current_price",),
                source_brief_trigger_id="gc_unsupported",
            ),
            live_snapshot={"contract": "GC", "market": {"current_price": 1.0}},
        )
    )

    assert zn.state == TriggerState.BLOCKED
    assert "excluded_contract:ZN" in zn.blocking_reasons
    assert gc.state == TriggerState.BLOCKED
    assert "never_supported_contract:GC" in gc.blocking_reasons
    assert "ZN" not in final_target_contracts()
    assert "GC" not in final_target_contracts()


def test_invalid_predicate_errors_fail_closed() -> None:
    result = evaluate_trigger_state(
        TriggerStateRequest(
            contract="ES",
            trigger_spec=TriggerSpec(
                id="bad_predicate",
                predicate="market.current_price >=",
                required_live_field_paths=("market.current_price",),
                source_brief_trigger_id="bad_predicate",
            ),
            live_snapshot={"contract": "ES", "market": {"current_price": 5605.0}},
            bar_state=completed_bar_state("ES"),
            trigger_level=5604.0,
            trigger_direction="at_or_above",
        )
    )

    assert result.state == TriggerState.ERROR
    assert "invalid_predicate_syntax" in result.invalid_reasons
    assert result.pipeline_query_authorized is False


def test_trigger_state_has_no_trade_or_preserved_engine_bypass_authority(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SCHWAB_APP_KEY", raising=False)
    monkeypatch.delenv("SCHWAB_APP_SECRET", raising=False)
    monkeypatch.delenv("SCHWAB_TOKEN_PATH", raising=False)

    result = evaluate_trigger_state_from_brief(
        _brief("ES"),
        _observable("ES"),
        bar_state=completed_bar_state("ES"),
    )

    captured = capsys.readouterr()
    assert result.state == TriggerState.QUERY_READY
    assert set(result.authorizations.to_dict().values()) == {False}
    assert result.decision_authority == "preserved_engine_only"
    assert result.read_model_only is True
    assert captured.out == ""
    assert captured.err == ""


def completed_bar_state(contract: str) -> ContractBarState:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)
    level = LEVELS[contract]
    tick = contract_tick_size(contract) or 0.25
    for minute in range(5):
        close = level + tick * (minute + 1)
        builder.ingest(bar_message(contract, minute=minute, open_price=close - tick, close=close))
    return builder.state(contract)


def partial_bar_state(contract: str) -> ContractBarState:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)
    level = LEVELS[contract]
    tick = contract_tick_size(contract) or 0.25
    for minute in range(4):
        close = level + tick * (minute + 1)
        builder.ingest(bar_message(contract, minute=minute, open_price=close - tick, close=close))
    builder.ingest(
        bar_message(
            contract,
            minute=4,
            open_price=level + tick,
            close=level + tick * 2,
            completed=False,
        )
    )
    return builder.state(contract)


def stale_bar_state(contract: str) -> ContractBarState:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)
    level = LEVELS[contract]
    tick = contract_tick_size(contract) or 0.25
    for minute in range(5):
        close = level + tick * (minute + 1)
        builder.ingest(bar_message(contract, minute=minute, open_price=close - tick, close=close))
    return builder.state(
        contract,
        now=BASE_TIME + timedelta(minutes=30),
        max_completed_bar_age_seconds=60.0,
    )


def bar_message(
    contract: str,
    *,
    minute: int,
    open_price: float,
    close: float,
    completed: bool = True,
) -> dict[str, object]:
    tick = contract_tick_size(contract) or 0.25
    start = BASE_TIME + timedelta(minutes=minute)
    return {
        "service": "CHART_FUTURES",
        "contract": contract,
        "symbol": EXPECTED_SYMBOLS[contract],
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(minutes=1)).isoformat(),
        "open": open_price,
        "high": max(open_price, close) + tick,
        "low": min(open_price, close) - tick,
        "close": close,
        "volume": 100 + minute,
        "completed": completed,
    }


def quote_only_snapshot_v2(contract: str, *, last: float) -> LiveObservableSnapshotV2:
    return LiveObservableSnapshotV2(
        generated_at="2026-05-06T14:00:00+00:00",
        provider="fixture",
        provider_status="connected",
        contracts={
            contract: ContractObservableV2(
                contract=contract,
                symbol=EXPECTED_SYMBOLS[contract],
                quote=QuoteObservableV2(
                    bid=last - (contract_tick_size(contract) or 0.25),
                    ask=last + (contract_tick_size(contract) or 0.25),
                    last=last,
                    quote_time="2026-05-06T13:59:58+00:00",
                    trade_time="2026-05-06T13:59:58+00:00",
                    quote_age_seconds=2.0,
                    trade_age_seconds=2.0,
                ),
                quality=QualityObservableV2(
                    fresh=True,
                    symbol_match=True,
                    required_fields_present=True,
                ),
            )
        },
        cross_asset={},
        macro_context={},
        session_context={},
        data_quality={"ready": True},
    )


def _es_snapshot(*, current_price: float) -> dict[str, object]:
    snapshot = copy.deepcopy(_observable("ES"))
    market = snapshot["market"]
    assert isinstance(market, dict)
    market["current_price"] = current_price
    market["cumulative_delta"] = 1200.0
    breadth = snapshot["cross_asset"]
    assert isinstance(breadth, dict)
    breadth["breadth"] = {"current_advancers_pct": 0.61}
    return snapshot


def _missing_breadth_snapshot() -> dict[str, object]:
    snapshot = copy.deepcopy(_observable("ES"))
    cross_asset = snapshot["cross_asset"]
    assert isinstance(cross_asset, dict)
    cross_asset.pop("breadth")
    return snapshot


def _brief(contract: str) -> dict[str, object]:
    with BRIEF_PATHS[contract].open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    assert isinstance(payload, dict)
    return payload


def _observable(contract: str) -> dict[str, object]:
    with OBSERVABLE_PATHS[contract].open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    assert isinstance(payload, dict)
    return payload
