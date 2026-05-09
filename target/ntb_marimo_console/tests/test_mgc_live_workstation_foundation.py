from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.live_workstation import (
    MGC_LIVE_WORKSTATION_SCHEMA,
    MGC_LIVE_WORKSTATION_STATES,
    MGCDXYState,
    MGCFearCatalystState,
    MGCInvalidatorDefinition,
    MGCLiveQuoteInput,
    MGCLiveWorkstationInput,
    MGCPremarketArtifact,
    MGCTriggerDefinition,
    MGCUnsupportedOrderFlowEvidence,
    MGCWorkstationEventLockout,
    MGCYieldState,
    evaluate_mgc_live_workstation,
)
from ntb_marimo_console.market_data import ChartFuturesBarBuilder
from ntb_marimo_console.market_data.chart_bars import ContractBarState
from ntb_marimo_console.profile_operations import build_profile_operations_snapshot
from ntb_marimo_console.runtime_profiles import default_profile_id_for_mode, get_runtime_profile


BASE_TIME = datetime(2026, 5, 6, 14, 0, 0, tzinfo=timezone.utc)
EXPECTED_SYMBOLS = {"MGC": "/MGCM26"}


def quote_input(
    *,
    contract: str = "MGC",
    symbol: str = "/MGCM26",
    bid: float | None = 2054.2,
    ask: float | None = 2054.4,
    last: float | None = 2054.4,
    spread_ticks: float | None = 2.0,
    fresh: bool = True,
    symbol_match: bool = True,
    required_fields_present: bool = True,
    blocking_reasons: tuple[str, ...] = (),
) -> MGCLiveQuoteInput:
    return MGCLiveQuoteInput(
        contract=contract,
        symbol=symbol,
        bid=bid,
        ask=ask,
        last=last,
        spread_ticks=spread_ticks,
        fresh=fresh,
        symbol_match=symbol_match,
        required_fields_present=required_fields_present,
        blocking_reasons=blocking_reasons,
        quote_time="2026-05-06T13:59:58+00:00",
        trade_time="2026-05-06T13:59:58+00:00",
        quote_age_seconds=2.0,
        trade_age_seconds=2.0,
    )


def trigger(
    *,
    level: float = 2054.2,
    approach_threshold_ticks: int = 20,
    dxy_change_threshold: float = 0.0,
    yield_change_bps_threshold: float = 0.0,
    fear_catalyst_required: bool = False,
    unsupported_order_flow_required: bool = False,
) -> MGCTriggerDefinition:
    return MGCTriggerDefinition(
        setup_id="mgc_dxy_yield_alignment",
        trigger_id="mgc_micro_gold_pivot_touch",
        level=level,
        direction="at_or_above",
        approach_threshold_ticks=approach_threshold_ticks,
        price_confirmation_required=True,
        dxy_required=True,
        dxy_change_threshold=dxy_change_threshold,
        dxy_change_predicate="at_or_below",
        yield_required=True,
        yield_change_bps_threshold=yield_change_bps_threshold,
        yield_change_bps_predicate="at_or_below",
        fear_catalyst_required=fear_catalyst_required,
        unsupported_order_flow_required=unsupported_order_flow_required,
    )


def artifact() -> MGCPremarketArtifact:
    return MGCPremarketArtifact(
        artifact_id="fixture_premarket_mgc",
        levels={"micro_gold_pivot": 2054.2, "prior_close": 2044.2},
    )


def dxy_state(
    *,
    value: float | None = 101.85,
    change: float | None = -0.18,
    source_label: str | None = "fixture_numeric_dxy",
    textual_context: str | None = None,
) -> MGCDXYState:
    return MGCDXYState(
        available=True,
        source_label=source_label,
        value=value,
        change=change,
        textual_context=textual_context,
    )


def yield_state(
    *,
    value: float | None = 4.12,
    change_bps: float | None = -3.0,
    source_label: str | None = "fixture_numeric_cash_10y_yield",
    textual_context: str | None = None,
) -> MGCYieldState:
    return MGCYieldState(
        available=True,
        source_label=source_label,
        value=value,
        change_bps=change_bps,
        textual_context=textual_context,
    )


def fear_catalyst(*, active: bool | None = False, state: str | None = "none") -> MGCFearCatalystState:
    return MGCFearCatalystState(
        available=True,
        source_label="fixture_fear_catalyst",
        state=state,
        active=active,
    )


def payload(**overrides: object) -> MGCLiveWorkstationInput:
    values = {
        "contract": "MGC",
        "quote": quote_input(),
        "bar_state": completed_bar_state(),
        "premarket_artifact": artifact(),
        "trigger": trigger(),
        "invalidators": (),
        "event_lockout": MGCWorkstationEventLockout(),
        "dxy_state": dxy_state(),
        "yield_state": yield_state(),
        "fear_catalyst_state": fear_catalyst(),
        "generated_at": "2026-05-06T14:00:00+00:00",
    }
    values.update(overrides)
    return MGCLiveWorkstationInput(**values)  # type: ignore[arg-type]


def bar_message(
    *,
    minute: int,
    open_price: float,
    close: float,
    completed: bool = True,
) -> dict[str, object]:
    start = BASE_TIME + timedelta(minutes=minute)
    return {
        "service": "CHART_FUTURES",
        "contract": "MGC",
        "symbol": "/MGCM26",
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(minutes=1)).isoformat(),
        "open": open_price,
        "high": max(open_price, close) + 0.2,
        "low": min(open_price, close) - 0.2,
        "close": close,
        "volume": 1000 + minute,
        "completed": completed,
    }


def completed_bar_state() -> ContractBarState:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)
    for minute in range(5):
        builder.ingest(
            bar_message(
                minute=minute,
                open_price=2053.8 + minute * 0.1,
                close=2054.2 + minute * 0.1,
            )
        )
    return builder.state("MGC")


def partial_bar_state() -> ContractBarState:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)
    for minute in range(4):
        builder.ingest(
            bar_message(
                minute=minute,
                open_price=2053.8 + minute * 0.1,
                close=2054.2 + minute * 0.1,
            )
        )
    builder.ingest(bar_message(minute=4, open_price=2054.2, close=2054.4, completed=False))
    return builder.state("MGC")


def test_declared_states_include_required_fail_closed_read_model_states() -> None:
    for state in (
        "UNAVAILABLE",
        "DORMANT",
        "APPROACHING",
        "TOUCHED",
        "ARMED",
        "QUERY_READY",
        "INVALIDATED",
        "BLOCKED",
        "STALE",
        "LOCKOUT",
        "ERROR",
    ):
        assert state in MGC_LIVE_WORKSTATION_STATES


def test_price_far_from_trigger_returns_dormant_with_good_quality_inputs() -> None:
    model = evaluate_mgc_live_workstation(payload(quote=quote_input(bid=2051.9, ask=2052.1, last=2052.0)))

    assert model.state == "DORMANT"
    assert model.distance_to_trigger_ticks == 22.0
    assert model.blocking_reasons == ("price_outside_approach_threshold",)


def test_price_within_configured_tick_distance_returns_approaching() -> None:
    model = evaluate_mgc_live_workstation(payload(quote=quote_input(bid=2053.2, ask=2053.4, last=2053.3)))

    assert model.state == "APPROACHING"
    assert model.distance_to_trigger_ticks == 9.0
    assert model.blocking_reasons == ("awaiting_trigger_touch",)


def test_trigger_touched_without_confirmation_returns_touched() -> None:
    model = evaluate_mgc_live_workstation(payload(bar_state=ContractBarState(contract="MGC")))

    assert model.state == "TOUCHED"
    assert model.completed_bar_evidence.confirmed is False
    assert "completed_five_minute_confirmation_required" in model.blocking_reasons


def test_query_ready_requires_completed_confirmation_numeric_dxy_and_numeric_yield() -> None:
    model = evaluate_mgc_live_workstation(payload())

    assert model.state == "QUERY_READY"
    assert model.completed_bar_evidence.confirmed is True
    assert model.dxy_passed is True
    assert model.yield_passed is True
    assert model.pipeline_query_authorized is False
    assert model.authorizations.pipeline_query_authorized is False


def test_absolute_price_action_alone_cannot_produce_query_ready_when_macro_context_is_required() -> None:
    model = evaluate_mgc_live_workstation(payload(dxy_state=None, yield_state=None, fear_catalyst_state=None))

    assert model.state == "BLOCKED"
    assert model.completed_bar_evidence.confirmed is True
    assert "dxy_state_required" in model.blocking_reasons
    assert "yield_state_required" in model.blocking_reasons
    assert "fear_catalyst_state_required" not in model.blocking_reasons
    assert model.pipeline_query_authorized is False


def test_missing_numeric_dxy_blocks_when_dxy_is_required() -> None:
    model = evaluate_mgc_live_workstation(payload(dxy_state=dxy_state(value=None, change=None)))

    assert model.state == "BLOCKED"
    assert "dxy_numeric_value_required" in model.blocking_reasons
    assert "dxy_numeric_change_required" in model.blocking_reasons
    assert "dxy_state.value" in model.missing_fields
    assert "dxy_state.change" in model.missing_fields


def test_textual_dxy_alone_blocks_when_dxy_is_required() -> None:
    model = evaluate_mgc_live_workstation(
        payload(dxy_state=dxy_state(value=None, change=None, textual_context="weakening"))
    )

    assert model.state == "BLOCKED"
    assert "dxy_textual_context_not_sufficient" in model.blocking_reasons
    assert model.dxy_numeric_value is None


def test_missing_numeric_yield_blocks_when_yield_is_required() -> None:
    model = evaluate_mgc_live_workstation(payload(yield_state=yield_state(value=None, change_bps=None)))

    assert model.state == "BLOCKED"
    assert "yield_numeric_value_required" in model.blocking_reasons
    assert "yield_numeric_change_bps_required" in model.blocking_reasons
    assert "yield_state.value" in model.missing_fields
    assert "yield_state.change_bps" in model.missing_fields


def test_textual_yield_alone_blocks_when_yield_is_required() -> None:
    model = evaluate_mgc_live_workstation(
        payload(yield_state=yield_state(value=None, change_bps=None, textual_context="falling"))
    )

    assert model.state == "BLOCKED"
    assert "yield_textual_context_not_sufficient" in model.blocking_reasons
    assert model.yield_numeric_value is None


def test_failed_dxy_or_yield_predicate_blocks_query_ready() -> None:
    failed_dxy = evaluate_mgc_live_workstation(payload(dxy_state=dxy_state(change=0.2)))
    failed_yield = evaluate_mgc_live_workstation(payload(yield_state=yield_state(change_bps=4.0)))

    assert failed_dxy.state == "ARMED"
    assert failed_dxy.dxy_passed is False
    assert "dxy_predicate_failed" in failed_dxy.blocking_reasons
    assert failed_yield.state == "ARMED"
    assert failed_yield.yield_passed is False
    assert "yield_predicate_failed" in failed_yield.blocking_reasons


def test_fear_catalyst_state_blocks_only_when_trigger_requires_it() -> None:
    not_required = evaluate_mgc_live_workstation(payload(fear_catalyst_state=None))
    required_missing = evaluate_mgc_live_workstation(
        payload(trigger=trigger(fear_catalyst_required=True), fear_catalyst_state=None)
    )
    required_inactive = evaluate_mgc_live_workstation(
        payload(trigger=trigger(fear_catalyst_required=True), fear_catalyst_state=fear_catalyst(active=False))
    )
    required_active = evaluate_mgc_live_workstation(
        payload(trigger=trigger(fear_catalyst_required=True), fear_catalyst_state=fear_catalyst(active=True, state="active_risk_off"))
    )

    assert not_required.state == "QUERY_READY"
    assert required_missing.state == "BLOCKED"
    assert "fear_catalyst_state_required" in required_missing.blocking_reasons
    assert required_inactive.state == "ARMED"
    assert "fear_catalyst_predicate_failed" in required_inactive.blocking_reasons
    assert required_active.state == "QUERY_READY"


def test_building_bars_do_not_count_as_completed_confirmation() -> None:
    model = evaluate_mgc_live_workstation(payload(bar_state=partial_bar_state()))

    assert model.state == "ARMED"
    assert model.completed_bar_evidence.confirmed is False
    assert model.completed_bar_evidence.completed_five_minute_bar_count == 0
    assert "building_five_minute_bar_not_confirmation" in model.blocking_reasons


def test_completed_five_minute_confirmation_requires_completed_one_minute_support() -> None:
    complete = completed_bar_state()
    without_one_minute = type(complete)(
        contract=complete.contract,
        completed_one_minute_bars=(),
        completed_five_minute_bars=complete.completed_five_minute_bars,
        building_five_minute_bar=None,
        blocking_reasons=(),
        latest_start_time=complete.latest_start_time,
    )

    model = evaluate_mgc_live_workstation(payload(bar_state=without_one_minute))

    assert model.state == "TOUCHED"
    assert model.completed_bar_evidence.confirmed is False
    assert "completed_one_minute_confirmation_bars_required" in model.blocking_reasons


def test_stale_quote_returns_stale_without_live_credentials() -> None:
    model = evaluate_mgc_live_workstation(
        payload(quote=quote_input(fresh=False, blocking_reasons=("stale_or_missing_timestamp:MGC",)))
    )

    assert model.state == "STALE"
    assert "quote_stale" in model.blocking_reasons
    assert "stale_or_missing_timestamp:MGC" in model.blocking_reasons


def test_missing_required_live_fields_returns_blocked() -> None:
    model = evaluate_mgc_live_workstation(
        payload(
            quote=quote_input(
                ask=None,
                spread_ticks=None,
                required_fields_present=False,
                blocking_reasons=("missing_required_fields:MGC:ask,spread_ticks",),
            )
        )
    )

    assert model.state == "BLOCKED"
    assert "missing_required_quote_fields" in model.blocking_reasons
    assert "quote_ask_required" in model.blocking_reasons
    assert "quote_spread_ticks_required" in model.blocking_reasons
    assert "quote.ask" in model.missing_fields
    assert "quote.spread_ticks" in model.missing_fields


def test_invalidator_returns_invalidated() -> None:
    model = evaluate_mgc_live_workstation(
        payload(
            quote=quote_input(bid=2051.9, ask=2052.1, last=2052.0),
            invalidators=(
                MGCInvalidatorDefinition(
                    invalidator_id="micro_gold_acceptance_failure",
                    level=2052.5,
                    direction="at_or_below",
                ),
            ),
        )
    )

    assert model.state == "INVALIDATED"
    assert model.invalid_reasons == ("invalidator_fired:micro_gold_acceptance_failure",)
    assert model.blocking_reasons == ("invalidator_fired:micro_gold_acceptance_failure",)


def test_event_lockout_overrides_armed_or_query_ready() -> None:
    armed = evaluate_mgc_live_workstation(
        payload(
            bar_state=partial_bar_state(),
            event_lockout=MGCWorkstationEventLockout(active=True, reason="operator_event_lockout"),
        )
    )
    query_ready = evaluate_mgc_live_workstation(
        payload(event_lockout=MGCWorkstationEventLockout(active=True, reason="operator_event_lockout"))
    )

    for model in (armed, query_ready):
        assert model.state == "LOCKOUT"
        assert model.blocking_reasons == ("event_lockout_active", "operator_event_lockout")
        assert model.pipeline_query_authorized is False


def test_unsupported_order_flow_fields_are_unavailable_not_inferred() -> None:
    model = evaluate_mgc_live_workstation(payload())
    payload_dict = model.to_dict()

    assert model.state == "QUERY_READY"
    assert payload_dict["unsupported_order_flow_evidence"] == {
        "footprint": "unavailable",
        "dom": "unavailable",
        "sweep": "unavailable",
        "cumulative_delta": "unavailable",
        "aggressive_order_flow": "unavailable",
        "source": "unavailable",
    }


def test_unsupported_order_flow_requirement_blocks_because_foundation_cannot_infer_it() -> None:
    model = evaluate_mgc_live_workstation(
        payload(
            trigger=trigger(unsupported_order_flow_required=True),
            unsupported_order_flow_evidence=MGCUnsupportedOrderFlowEvidence(),
        )
    )

    assert model.state == "BLOCKED"
    assert "unsupported_order_flow_evidence_unavailable" in model.blocking_reasons


def test_mgc_implementation_never_accepts_gc_symbol_mapping() -> None:
    model = evaluate_mgc_live_workstation(
        payload(
            contract="GC",
            quote=quote_input(contract="GC", symbol="/GCM26"),
        )
    )

    assert model.state == "BLOCKED"
    assert "never_supported_contract:GC" in model.blocking_reasons
    assert "mgc_workstation_supports_mgc_only" in model.blocking_reasons
    assert "GC" not in final_target_contracts()
    assert "MGC" in final_target_contracts()


@pytest.mark.parametrize(
    ("contract", "expected_reason"),
    (
        ("ES", "contract_not_onboarded_for_mgc_workstation:ES"),
        ("NQ", "contract_not_onboarded_for_mgc_workstation:NQ"),
        ("CL", "contract_not_onboarded_for_mgc_workstation:CL"),
        ("6E", "contract_not_onboarded_for_mgc_workstation:6E"),
    ),
)
def test_mgc_implementation_does_not_onboard_other_final_targets(
    contract: str,
    expected_reason: str,
) -> None:
    model = evaluate_mgc_live_workstation(
        payload(
            contract=contract,
            quote=quote_input(contract=contract, symbol=f"/{contract}M26"),
        )
    )

    assert model.state == "BLOCKED"
    assert expected_reason in model.blocking_reasons
    assert "mgc_workstation_supports_mgc_only" in model.blocking_reasons


def test_mgc_quote_symbol_must_be_micro_gold_not_full_size_gold() -> None:
    model = evaluate_mgc_live_workstation(payload(quote=quote_input(symbol="/GCM26")))

    assert model.state == "BLOCKED"
    assert "quote_symbol_must_be_mgc_not_gc" in model.blocking_reasons


def test_blocking_reasons_are_stable_visible_and_json_serializable() -> None:
    model = evaluate_mgc_live_workstation(payload(quote=quote_input(bid=2053.2, ask=2053.4, last=2053.3)))
    payload_dict = model.to_dict()

    assert payload_dict["schema"] == MGC_LIVE_WORKSTATION_SCHEMA
    assert payload_dict["blocking_reasons"] == ["awaiting_trigger_touch"]
    assert payload_dict["pipeline_query_authorized"] is False
    assert json.loads(json.dumps(payload_dict, sort_keys=True))["state"] == "APPROACHING"


def test_no_state_enables_trade_broker_order_fill_account_or_pnl_behavior() -> None:
    models = (
        evaluate_mgc_live_workstation(payload(premarket_artifact=None)),
        evaluate_mgc_live_workstation(payload(quote=quote_input(fresh=False))),
        evaluate_mgc_live_workstation(payload()),
    )

    for model in models:
        authorizations = model.authorizations.to_dict()
        assert set(authorizations.values()) == {False}
        assert model.decision_authority == "preserved_engine_only"
        assert model.read_model_only is True


def test_default_pytest_path_uses_no_credentials_and_prints_no_sensitive_values(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SCHWAB_APP_KEY", raising=False)
    monkeypatch.delenv("SCHWAB_APP_SECRET", raising=False)
    monkeypatch.delenv("SCHWAB_TOKEN_PATH", raising=False)

    model = evaluate_mgc_live_workstation(payload())

    captured = capsys.readouterr()
    assert model.state == "QUERY_READY"
    assert captured.out == ""
    assert captured.err == ""


def test_runtime_profile_defaults_remain_fixture_safe_and_non_live_after_mgc_onboarding() -> None:
    profile = get_runtime_profile("preserved_mgc_phase1")
    snapshot = build_profile_operations_snapshot(current_profile_id="preserved_es_phase1")
    supported = {item.profile_id: item for item in snapshot.supported_profiles}

    assert profile.contract == "MGC"
    assert supported["preserved_mgc_phase1"].operator_selectable is True
    assert default_profile_id_for_mode("fixture_demo") == "fixture_es_demo"
    assert default_profile_id_for_mode("preserved_engine") == "preserved_es_phase1"
    assert tuple(snapshot.candidate_profiles) == ()
