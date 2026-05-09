from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.live_workstation import (
    CL_LIVE_WORKSTATION_SCHEMA,
    CL_LIVE_WORKSTATION_STATES,
    CLInvalidatorDefinition,
    CLLiveQuoteInput,
    CLLiveWorkstationInput,
    CLPostEIASettlingState,
    CLPremarketArtifact,
    CLPrerequisiteState,
    CLTriggerDefinition,
    CLWorkstationEventLockout,
    evaluate_cl_live_workstation,
)
from ntb_marimo_console.market_data import ChartFuturesBarBuilder
from ntb_marimo_console.market_data.chart_bars import ContractBarState


BASE_TIME = datetime(2026, 5, 6, 14, 0, 0, tzinfo=timezone.utc)
EXPECTED_SYMBOLS = {"CL": "/CLM26"}


def quote_input(
    *,
    contract: str = "CL",
    symbol: str = "/CLM26",
    bid: float | None = 74.99,
    ask: float | None = 75.01,
    last: float | None = 75.0,
    spread_ticks: float | None = 2.0,
    fresh: bool = True,
    symbol_match: bool = True,
    required_fields_present: bool = True,
    blocking_reasons: tuple[str, ...] = (),
) -> CLLiveQuoteInput:
    return CLLiveQuoteInput(
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
    level: float = 75.0,
    approach_threshold_ticks: int = 10,
    requires_volume_prerequisite: bool = True,
    requires_range_expansion_prerequisite: bool = True,
) -> CLTriggerDefinition:
    return CLTriggerDefinition(
        setup_id="cl_premarket_breakout",
        trigger_id="premarket_high_touch",
        level=level,
        direction="at_or_above",
        approach_threshold_ticks=approach_threshold_ticks,
        requires_volume_prerequisite=requires_volume_prerequisite,
        requires_range_expansion_prerequisite=requires_range_expansion_prerequisite,
    )


def artifact() -> CLPremarketArtifact:
    return CLPremarketArtifact(
        artifact_id="fixture_premarket_cl",
        levels={"premarket_high": 75.0, "prior_close": 74.2},
    )


def prerequisite(state: str) -> CLPrerequisiteState:
    return CLPrerequisiteState(available=True, passed=True, state=state)


def payload(**overrides: object) -> CLLiveWorkstationInput:
    values = {
        "contract": "CL",
        "quote": quote_input(),
        "bar_state": completed_bar_state(),
        "premarket_artifact": artifact(),
        "trigger": trigger(),
        "invalidators": (),
        "event_lockout": CLWorkstationEventLockout(),
        "eia_lockout": CLWorkstationEventLockout(),
        "post_eia_settling": CLPostEIASettlingState(),
        "volatility_state": prerequisite("acceptable"),
        "volume_state": prerequisite("accelerating"),
        "range_expansion_state": prerequisite("expanding"),
        "generated_at": "2026-05-06T14:00:00+00:00",
    }
    values.update(overrides)
    return CLLiveWorkstationInput(**values)  # type: ignore[arg-type]


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
        "contract": "CL",
        "symbol": "/CLM26",
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(minutes=1)).isoformat(),
        "open": open_price,
        "high": max(open_price, close) + 0.03,
        "low": min(open_price, close) - 0.03,
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
                open_price=74.95 + minute * 0.01,
                close=75.01 + minute * 0.01,
            )
        )
    return builder.state("CL")


def partial_bar_state() -> ContractBarState:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)
    for minute in range(4):
        builder.ingest(
            bar_message(
                minute=minute,
                open_price=74.95 + minute * 0.01,
                close=75.0 + minute * 0.01,
            )
        )
    builder.ingest(bar_message(minute=4, open_price=75.02, close=75.04, completed=False))
    return builder.state("CL")


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
        assert state in CL_LIVE_WORKSTATION_STATES


def test_price_far_from_trigger_returns_dormant_with_good_quality_inputs() -> None:
    model = evaluate_cl_live_workstation(payload(quote=quote_input(bid=74.49, ask=74.51, last=74.5)))

    assert model.state == "DORMANT"
    assert model.distance_to_trigger_ticks == 50.0
    assert model.blocking_reasons == ("price_outside_approach_threshold",)


def test_price_within_configured_tick_distance_returns_approaching() -> None:
    model = evaluate_cl_live_workstation(payload(quote=quote_input(bid=74.94, ask=74.96, last=74.95)))

    assert model.state == "APPROACHING"
    assert model.distance_to_trigger_ticks == 5.0
    assert model.blocking_reasons == ("awaiting_trigger_touch",)


def test_trigger_touched_without_confirmation_returns_touched() -> None:
    model = evaluate_cl_live_workstation(payload(bar_state=ContractBarState(contract="CL")))

    assert model.state == "TOUCHED"
    assert model.completed_bar_evidence.confirmed is False
    assert "completed_five_minute_confirmation_required" in model.blocking_reasons


def test_partial_confirmation_returns_armed_without_query_gate() -> None:
    model = evaluate_cl_live_workstation(payload(bar_state=partial_bar_state()))

    assert model.state == "ARMED"
    assert model.completed_bar_evidence.confirmed is False
    assert "completed_five_minute_confirmation_required" in model.blocking_reasons
    assert "building_five_minute_bar_not_confirmation" in model.blocking_reasons


def test_query_ready_requires_all_deterministic_cl_prerequisites() -> None:
    model = evaluate_cl_live_workstation(payload())

    assert model.state == "QUERY_READY"
    assert model.completed_bar_evidence.confirmed is True
    assert model.completed_bar_evidence.completed_one_minute_bar_count == 5
    assert model.completed_bar_evidence.completed_five_minute_bar_count == 1
    assert model.pipeline_query_authorized is False
    assert model.authorizations.pipeline_query_authorized is False


def test_eia_lockout_blocks_fail_closed() -> None:
    model = evaluate_cl_live_workstation(
        payload(eia_lockout=CLWorkstationEventLockout(active=True, reason="weekly_eia_release"))
    )

    assert model.state == "LOCKOUT"
    assert model.pipeline_query_authorized is False
    assert model.blocking_reasons == ("eia_lockout_active", "weekly_eia_release")


def test_post_eia_settling_blocks_when_configured_as_blocking() -> None:
    model = evaluate_cl_live_workstation(
        payload(post_eia_settling=CLPostEIASettlingState(active=True, blocking=True, reason="post_eia_settling"))
    )

    assert model.state == "LOCKOUT"
    assert model.pipeline_query_authorized is False
    assert model.blocking_reasons == ("post_eia_settling_active", "post_eia_settling")


def test_missing_volatility_fields_block() -> None:
    model = evaluate_cl_live_workstation(
        payload(
            volatility_state=CLPrerequisiteState(
                available=True,
                passed=False,
                missing_fields=("atr_5m", "realized_range"),
                blocking_reasons=("volatility_regime_unavailable",),
            )
        )
    )

    assert model.state == "BLOCKED"
    assert "volatility_fields_missing:atr_5m,realized_range" in model.blocking_reasons
    assert "volatility.atr_5m" in model.missing_fields
    assert "volatility.realized_range" in model.missing_fields


def test_missing_volume_prerequisite_blocks_volume_dependent_trigger() -> None:
    model = evaluate_cl_live_workstation(payload(volume_state=None))

    assert model.state == "BLOCKED"
    assert "volume_state_required" in model.blocking_reasons
    assert "volume_state" in model.missing_fields


def test_missing_range_expansion_prerequisite_blocks_range_expansion_trigger() -> None:
    model = evaluate_cl_live_workstation(payload(range_expansion_state=None))

    assert model.state == "BLOCKED"
    assert "range_expansion_state_required" in model.blocking_reasons
    assert "range_expansion_state" in model.missing_fields


def test_building_bars_do_not_count_as_completed_confirmation() -> None:
    model = evaluate_cl_live_workstation(payload(bar_state=partial_bar_state()))

    assert model.state == "ARMED"
    assert model.completed_bar_evidence.confirmed is False
    assert model.completed_bar_evidence.completed_five_minute_bar_count == 0


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

    model = evaluate_cl_live_workstation(payload(bar_state=without_one_minute))

    assert model.state == "TOUCHED"
    assert model.completed_bar_evidence.confirmed is False
    assert "completed_one_minute_confirmation_bars_required" in model.blocking_reasons


def test_stale_quote_returns_stale_without_live_credentials() -> None:
    model = evaluate_cl_live_workstation(
        payload(quote=quote_input(fresh=False, blocking_reasons=("stale_or_missing_timestamp:CL",)))
    )

    assert model.state == "STALE"
    assert "quote_stale" in model.blocking_reasons
    assert "stale_or_missing_timestamp:CL" in model.blocking_reasons


def test_missing_required_live_fields_returns_blocked() -> None:
    model = evaluate_cl_live_workstation(
        payload(
            quote=quote_input(
                ask=None,
                spread_ticks=None,
                required_fields_present=False,
                blocking_reasons=("missing_required_fields:CL:ask,spread_ticks",),
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
    model = evaluate_cl_live_workstation(
        payload(
            quote=quote_input(bid=74.79, ask=74.81, last=74.8),
            invalidators=(
                CLInvalidatorDefinition(
                    invalidator_id="premarket_failure",
                    level=74.9,
                    direction="at_or_below",
                ),
            ),
        )
    )

    assert model.state == "INVALIDATED"
    assert model.invalid_reasons == ("invalidator_fired:premarket_failure",)
    assert model.blocking_reasons == ("invalidator_fired:premarket_failure",)


def test_event_lockout_overrides_armed_or_query_ready() -> None:
    armed = evaluate_cl_live_workstation(
        payload(
            bar_state=partial_bar_state(),
            event_lockout=CLWorkstationEventLockout(active=True, reason="operator_event_lockout"),
        )
    )
    query_ready = evaluate_cl_live_workstation(
        payload(event_lockout=CLWorkstationEventLockout(active=True, reason="operator_event_lockout"))
    )

    for model in (armed, query_ready):
        assert model.state == "LOCKOUT"
        assert model.blocking_reasons == ("event_lockout_active", "operator_event_lockout")
        assert model.pipeline_query_authorized is False


def test_cl_outputs_do_not_include_unavailable_evidence_families() -> None:
    payload_dict = evaluate_cl_live_workstation(payload()).to_dict()
    encoded = json.dumps(payload_dict, sort_keys=True).lower()

    for unavailable_family in (
        "footprint",
        "cumulative_delta",
        "sweep",
        "aggressive_order_flow",
        "order_flow",
        "dom",
    ):
        assert unavailable_family not in encoded


@pytest.mark.parametrize(
    ("contract", "expected_reason"),
    (
        ("NQ", "contract_not_onboarded_for_cl_workstation:NQ"),
        ("6E", "contract_not_onboarded_for_cl_workstation:6E"),
        ("MGC", "contract_not_onboarded_for_cl_workstation:MGC"),
    ),
)
def test_cl_implementation_does_not_onboard_other_final_targets(
    contract: str,
    expected_reason: str,
) -> None:
    model = evaluate_cl_live_workstation(
        payload(
            contract=contract,
            quote=quote_input(contract=contract, symbol=f"/{contract}M26"),
        )
    )

    assert model.state == "BLOCKED"
    assert expected_reason in model.blocking_reasons
    assert "cl_workstation_supports_cl_only" in model.blocking_reasons


@pytest.mark.parametrize(
    ("contract", "expected_reason"),
    (
        ("ZN", "excluded_contract:ZN"),
        ("GC", "never_supported_contract:GC"),
    ),
)
def test_cl_implementation_does_not_repromote_zn_or_add_gc(contract: str, expected_reason: str) -> None:
    model = evaluate_cl_live_workstation(
        payload(
            contract=contract,
            quote=quote_input(contract=contract, symbol=f"/{contract}M26"),
        )
    )

    assert model.state == "BLOCKED"
    assert expected_reason in model.blocking_reasons
    assert "GC" not in final_target_contracts()
    assert "MGC" in final_target_contracts()


def test_blocking_reasons_are_stable_visible_and_json_serializable() -> None:
    model = evaluate_cl_live_workstation(payload(quote=quote_input(bid=74.94, ask=74.96, last=74.95)))
    payload_dict = model.to_dict()

    assert payload_dict["schema"] == CL_LIVE_WORKSTATION_SCHEMA
    assert payload_dict["blocking_reasons"] == ["awaiting_trigger_touch"]
    assert payload_dict["pipeline_query_authorized"] is False
    assert json.loads(json.dumps(payload_dict, sort_keys=True))["state"] == "APPROACHING"


def test_no_state_enables_trade_broker_order_fill_account_or_pnl_behavior() -> None:
    models = (
        evaluate_cl_live_workstation(payload(premarket_artifact=None)),
        evaluate_cl_live_workstation(payload(quote=quote_input(fresh=False))),
        evaluate_cl_live_workstation(payload()),
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

    model = evaluate_cl_live_workstation(payload())

    captured = capsys.readouterr()
    assert model.state == "QUERY_READY"
    assert captured.out == ""
    assert captured.err == ""
