from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.live_workstation import (
    SIXE_LIVE_WORKSTATION_SCHEMA,
    SIXE_LIVE_WORKSTATION_STATES,
    SixEDXYState,
    SixEInvalidatorDefinition,
    SixELiveQuoteInput,
    SixELiveWorkstationInput,
    SixEPremarketArtifact,
    SixESessionRangeState,
    SixESessionSequenceState,
    SixEThinLiquidityState,
    SixETriggerDefinition,
    SixEWorkstationEventLockout,
    evaluate_sixe_live_workstation,
)
from ntb_marimo_console.market_data import ChartFuturesBarBuilder
from ntb_marimo_console.market_data.chart_bars import ContractBarState
from ntb_marimo_console.profile_operations import build_profile_operations_snapshot
from ntb_marimo_console.runtime_profiles import default_profile_id_for_mode, get_runtime_profile


BASE_TIME = datetime(2026, 5, 6, 14, 0, 0, tzinfo=timezone.utc)
EXPECTED_SYMBOLS = {"6E": "/6EM26"}


def quote_input(
    *,
    contract: str = "6E",
    symbol: str = "/6EM26",
    bid: float | None = 1.09115,
    ask: float | None = 1.09125,
    last: float | None = 1.09125,
    spread_ticks: float | None = 2.0,
    fresh: bool = True,
    symbol_match: bool = True,
    required_fields_present: bool = True,
    blocking_reasons: tuple[str, ...] = (),
) -> SixELiveQuoteInput:
    return SixELiveQuoteInput(
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
    level: float = 1.0912,
    approach_threshold_ticks: int = 8,
    dxy_change_threshold: float = 0.0,
) -> SixETriggerDefinition:
    return SixETriggerDefinition(
        setup_id="sixe_dxy_session_breakout",
        trigger_id="sixe_london_high_touch",
        level=level,
        direction="at_or_above",
        approach_threshold_ticks=approach_threshold_ticks,
        dxy_required=True,
        dxy_change_threshold=dxy_change_threshold,
        dxy_change_predicate="at_or_below",
        session_sequence_required=True,
        range_context_required=True,
        thin_liquidity_state_required=True,
    )


def artifact() -> SixEPremarketArtifact:
    return SixEPremarketArtifact(
        artifact_id="fixture_premarket_6e",
        levels={"london_high": 1.0912, "prior_close": 1.0889},
    )


def dxy_state(*, change: float | None = -0.12, source_label: str | None = "fixture_dxy") -> SixEDXYState:
    return SixEDXYState(
        available=True,
        source_label=source_label,
        value=101.85,
        change=change,
    )


def session_sequence(
    *,
    asia_complete: bool | None = True,
    london_complete: bool | None = True,
    ny_active: bool | None = True,
    ny_pending: bool | None = False,
) -> SixESessionSequenceState:
    return SixESessionSequenceState(
        available=True,
        asia_complete=asia_complete,
        london_complete=london_complete,
        ny_active=ny_active,
        ny_pending=ny_pending,
        source_label="fixture_session_sequence",
        state="ny_active_after_london_completion",
    )


def range_state(high: float | None, low: float | None, *, complete: bool | None = True) -> SixESessionRangeState:
    return SixESessionRangeState(
        high=high,
        low=low,
        complete=complete,
        source_label="fixture_session_range",
    )


def thin_liquidity(*, active: bool | None = False, blocking: bool = True) -> SixEThinLiquidityState:
    return SixEThinLiquidityState(
        available=True,
        active=active,
        blocking=blocking,
        reason="post_london_close_thin_liquidity" if active else None,
        source_label="fixture_thin_liquidity",
    )


def payload(**overrides: object) -> SixELiveWorkstationInput:
    values = {
        "contract": "6E",
        "quote": quote_input(),
        "bar_state": completed_bar_state(),
        "premarket_artifact": artifact(),
        "trigger": trigger(),
        "invalidators": (),
        "event_lockout": SixEWorkstationEventLockout(),
        "dxy_state": dxy_state(),
        "session_sequence_state": session_sequence(),
        "asia_range_state": range_state(1.0892, 1.0876),
        "london_range_state": range_state(1.0914, 1.0886),
        "ny_range_state": range_state(1.0916, 1.0898, complete=None),
        "thin_liquidity_state": thin_liquidity(),
        "generated_at": "2026-05-06T14:00:00+00:00",
    }
    values.update(overrides)
    return SixELiveWorkstationInput(**values)  # type: ignore[arg-type]


def bar_message(
    *,
    minute: int,
    open_price: float,
    close: float,
    completed: bool = True,
) -> dict[str, object]:
    start = BASE_TIME + timedelta(minutes=minute)
    tick = 0.00005
    return {
        "service": "CHART_FUTURES",
        "contract": "6E",
        "symbol": "/6EM26",
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(minutes=1)).isoformat(),
        "open": open_price,
        "high": max(open_price, close) + tick,
        "low": min(open_price, close) - tick,
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
                open_price=1.0910 + minute * 0.00002,
                close=1.09122 + minute * 0.00003,
            )
        )
    return builder.state("6E")


def partial_bar_state() -> ContractBarState:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)
    for minute in range(4):
        builder.ingest(
            bar_message(
                minute=minute,
                open_price=1.0910 + minute * 0.00002,
                close=1.09122 + minute * 0.00003,
            )
        )
    builder.ingest(bar_message(minute=4, open_price=1.09118, close=1.09125, completed=False))
    return builder.state("6E")


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
        assert state in SIXE_LIVE_WORKSTATION_STATES


def test_price_far_from_trigger_returns_dormant_with_good_quality_inputs() -> None:
    model = evaluate_sixe_live_workstation(
        payload(quote=quote_input(bid=1.08995, ask=1.09005, last=1.09))
    )

    assert model.state == "DORMANT"
    assert model.distance_to_trigger_ticks == 24.0
    assert model.blocking_reasons == ("price_outside_approach_threshold",)


def test_price_within_configured_tick_distance_returns_approaching() -> None:
    model = evaluate_sixe_live_workstation(
        payload(quote=quote_input(bid=1.0909, ask=1.0910, last=1.09095))
    )

    assert model.state == "APPROACHING"
    assert model.distance_to_trigger_ticks == 5.0
    assert model.blocking_reasons == ("awaiting_trigger_touch",)


def test_trigger_touched_without_confirmation_returns_touched() -> None:
    model = evaluate_sixe_live_workstation(payload(bar_state=ContractBarState(contract="6E")))

    assert model.state == "TOUCHED"
    assert model.completed_bar_evidence.confirmed is False
    assert "completed_five_minute_confirmation_required" in model.blocking_reasons


def test_sixe_confirmation_without_full_dxy_session_gate_returns_armed() -> None:
    model = evaluate_sixe_live_workstation(
        payload(session_sequence_state=session_sequence(london_complete=False))
    )

    assert model.state == "ARMED"
    assert model.completed_bar_evidence.confirmed is True
    assert model.session_sequence_passed is False
    assert "session_sequence_predicate_failed" in model.blocking_reasons


def test_query_ready_requires_completed_confirmation_numeric_dxy_session_and_lockout_gates() -> None:
    model = evaluate_sixe_live_workstation(payload())

    assert model.state == "QUERY_READY"
    assert model.completed_bar_evidence.confirmed is True
    assert model.dxy_passed is True
    assert model.session_sequence_passed is True
    assert model.pipeline_query_authorized is False
    assert model.authorizations.pipeline_query_authorized is False


def test_missing_numeric_dxy_blocks_when_dxy_is_required() -> None:
    model = evaluate_sixe_live_workstation(payload(dxy_state=SixEDXYState(available=True, source_label="fixture")))

    assert model.state == "BLOCKED"
    assert "dxy_numeric_change_required" in model.blocking_reasons
    assert "dxy_state.change" in model.missing_fields


def test_textual_dxy_alone_blocks_when_dxy_is_required() -> None:
    model = evaluate_sixe_live_workstation(
        payload(
            dxy_state=SixEDXYState(
                available=True,
                source_label="fixture_text",
                textual_context="weakening",
            )
        )
    )

    assert model.state == "BLOCKED"
    assert "dxy_numeric_change_required" in model.blocking_reasons
    assert "dxy_textual_context_not_sufficient" in model.blocking_reasons
    assert model.dxy_change is None


def test_missing_dxy_source_label_blocks_when_dxy_is_required() -> None:
    model = evaluate_sixe_live_workstation(payload(dxy_state=dxy_state(source_label=None)))

    assert model.state == "BLOCKED"
    assert "dxy_source_label_required" in model.blocking_reasons
    assert "dxy_state.source_label" in model.missing_fields


def test_failed_dxy_predicate_blocks_query_ready() -> None:
    model = evaluate_sixe_live_workstation(payload(dxy_state=dxy_state(change=0.18)))

    assert model.state == "ARMED"
    assert model.dxy_passed is False
    assert "dxy_predicate_failed" in model.blocking_reasons


def test_missing_session_sequence_blocks_when_required() -> None:
    model = evaluate_sixe_live_workstation(payload(session_sequence_state=None))

    assert model.state == "BLOCKED"
    assert "session_sequence_state_required" in model.blocking_reasons
    assert "session_sequence_state" in model.missing_fields


def test_missing_asia_london_or_ny_range_fields_block_when_required() -> None:
    model = evaluate_sixe_live_workstation(
        payload(
            asia_range_state=range_state(None, 1.0876),
            london_range_state=range_state(1.0914, None),
            ny_range_state=range_state(None, None, complete=None),
        )
    )

    assert model.state == "BLOCKED"
    assert "asia_range_high_required" in model.blocking_reasons
    assert "london_range_low_required" in model.blocking_reasons
    assert "ny_range_high_required" in model.blocking_reasons
    assert "ny_range_low_required" in model.blocking_reasons


def test_thin_liquidity_after_london_close_lockout_when_configured_as_blocking() -> None:
    model = evaluate_sixe_live_workstation(payload(thin_liquidity_state=thin_liquidity(active=True)))

    assert model.state == "LOCKOUT"
    assert "thin_liquidity_after_london_close_active" in model.blocking_reasons
    assert model.pipeline_query_authorized is False


def test_absolute_breakout_alone_does_not_produce_query_ready_when_context_is_required() -> None:
    model = evaluate_sixe_live_workstation(
        payload(
            dxy_state=None,
            session_sequence_state=None,
            asia_range_state=None,
            london_range_state=None,
            ny_range_state=None,
        )
    )

    assert model.state == "BLOCKED"
    assert model.completed_bar_evidence.confirmed is True
    assert model.pipeline_query_authorized is False


def test_building_bars_do_not_count_as_completed_confirmation() -> None:
    model = evaluate_sixe_live_workstation(payload(bar_state=partial_bar_state()))

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

    model = evaluate_sixe_live_workstation(payload(bar_state=without_one_minute))

    assert model.state == "TOUCHED"
    assert model.completed_bar_evidence.confirmed is False
    assert "completed_one_minute_confirmation_bars_required" in model.blocking_reasons


def test_stale_quote_returns_stale_without_live_credentials() -> None:
    model = evaluate_sixe_live_workstation(
        payload(quote=quote_input(fresh=False, blocking_reasons=("stale_or_missing_timestamp:6E",)))
    )

    assert model.state == "STALE"
    assert "quote_stale" in model.blocking_reasons
    assert "stale_or_missing_timestamp:6E" in model.blocking_reasons


def test_missing_required_live_fields_returns_blocked() -> None:
    model = evaluate_sixe_live_workstation(
        payload(
            quote=quote_input(
                ask=None,
                spread_ticks=None,
                required_fields_present=False,
                blocking_reasons=("missing_required_fields:6E:ask,spread_ticks",),
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
    model = evaluate_sixe_live_workstation(
        payload(
            quote=quote_input(bid=1.08995, ask=1.09005, last=1.09),
            invalidators=(
                SixEInvalidatorDefinition(
                    invalidator_id="london_acceptance_failure",
                    level=1.0905,
                    direction="at_or_below",
                ),
            ),
        )
    )

    assert model.state == "INVALIDATED"
    assert model.invalid_reasons == ("invalidator_fired:london_acceptance_failure",)
    assert model.blocking_reasons == ("invalidator_fired:london_acceptance_failure",)


def test_event_lockout_overrides_armed_or_query_ready() -> None:
    armed = evaluate_sixe_live_workstation(
        payload(
            bar_state=partial_bar_state(),
            event_lockout=SixEWorkstationEventLockout(active=True, reason="operator_event_lockout"),
        )
    )
    query_ready = evaluate_sixe_live_workstation(
        payload(event_lockout=SixEWorkstationEventLockout(active=True, reason="operator_event_lockout"))
    )

    for model in (armed, query_ready):
        assert model.state == "LOCKOUT"
        assert model.blocking_reasons == ("event_lockout_active", "operator_event_lockout")
        assert model.pipeline_query_authorized is False


def test_unavailable_dxy_session_range_and_thin_liquidity_are_not_inferred() -> None:
    model = evaluate_sixe_live_workstation(
        payload(
            dxy_state=None,
            session_sequence_state=None,
            asia_range_state=None,
            london_range_state=None,
            ny_range_state=None,
            thin_liquidity_state=None,
        )
    )

    assert model.state == "BLOCKED"
    assert model.dxy_numeric_value is None
    assert model.dxy_change is None
    assert model.session_sequence_state is None
    assert model.thin_liquidity_state is None
    assert "dxy_state_required" in model.blocking_reasons


def test_sixe_outputs_do_not_include_unavailable_evidence_families() -> None:
    payload_dict = evaluate_sixe_live_workstation(payload()).to_dict()
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
        ("ES", "contract_not_onboarded_for_sixe_workstation:ES"),
        ("NQ", "contract_not_onboarded_for_sixe_workstation:NQ"),
        ("CL", "contract_not_onboarded_for_sixe_workstation:CL"),
        ("MGC", "contract_not_onboarded_for_sixe_workstation:MGC"),
    ),
)
def test_sixe_implementation_does_not_onboard_other_final_targets(
    contract: str,
    expected_reason: str,
) -> None:
    model = evaluate_sixe_live_workstation(
        payload(
            contract=contract,
            quote=quote_input(contract=contract, symbol=f"/{contract}M26"),
        )
    )

    assert model.state == "BLOCKED"
    assert expected_reason in model.blocking_reasons
    assert "sixe_workstation_supports_6e_only" in model.blocking_reasons


@pytest.mark.parametrize(
    ("contract", "expected_reason"),
    (
        ("ZN", "excluded_contract:ZN"),
        ("GC", "never_supported_contract:GC"),
    ),
)
def test_sixe_implementation_does_not_repromote_zn_or_add_gc(contract: str, expected_reason: str) -> None:
    model = evaluate_sixe_live_workstation(
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
    model = evaluate_sixe_live_workstation(
        payload(quote=quote_input(bid=1.0909, ask=1.0910, last=1.09095))
    )
    payload_dict = model.to_dict()

    assert payload_dict["schema"] == SIXE_LIVE_WORKSTATION_SCHEMA
    assert payload_dict["blocking_reasons"] == ["awaiting_trigger_touch"]
    assert payload_dict["pipeline_query_authorized"] is False
    assert json.loads(json.dumps(payload_dict, sort_keys=True))["state"] == "APPROACHING"


def test_no_state_enables_trade_broker_order_fill_account_or_pnl_behavior() -> None:
    models = (
        evaluate_sixe_live_workstation(payload(premarket_artifact=None)),
        evaluate_sixe_live_workstation(payload(quote=quote_input(fresh=False))),
        evaluate_sixe_live_workstation(payload()),
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

    model = evaluate_sixe_live_workstation(payload())

    captured = capsys.readouterr()
    assert model.state == "QUERY_READY"
    assert captured.out == ""
    assert captured.err == ""


def test_runtime_profile_defaults_remain_fixture_safe_and_non_live_after_6e_onboarding() -> None:
    profile = get_runtime_profile("preserved_6e_phase1")
    snapshot = build_profile_operations_snapshot(current_profile_id="preserved_es_phase1")
    supported = {item.profile_id: item for item in snapshot.supported_profiles}

    assert profile.contract == "6E"
    assert supported["preserved_6e_phase1"].operator_selectable is True
    assert default_profile_id_for_mode("fixture_demo") == "fixture_es_demo"
    assert default_profile_id_for_mode("preserved_engine") == "preserved_es_phase1"
    assert tuple(snapshot.candidate_profiles) == ()
