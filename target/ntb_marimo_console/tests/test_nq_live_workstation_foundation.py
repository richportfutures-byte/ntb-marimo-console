from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.live_workstation import (
    NQ_LIVE_WORKSTATION_SCHEMA,
    NQ_LIVE_WORKSTATION_STATES,
    NQAnchor,
    NQInvalidatorDefinition,
    NQLiveQuoteInput,
    NQLiveWorkstationInput,
    NQPremarketArtifact,
    NQTriggerDefinition,
    NQWorkstationEventLockout,
    evaluate_nq_live_workstation,
)
from ntb_marimo_console.market_data import ChartFuturesBarBuilder
from ntb_marimo_console.market_data.chart_bars import ContractBarState
from ntb_marimo_console.profile_operations import build_profile_operations_snapshot
from ntb_marimo_console.runtime_profiles import default_profile_id_for_mode


BASE_TIME = datetime(2026, 5, 6, 14, 0, 0, tzinfo=timezone.utc)
EXPECTED_SYMBOLS = {"NQ": "/NQM26", "ES": "/ESM26"}


def quote_input(
    *,
    contract: str,
    symbol: str,
    bid: float | None,
    ask: float | None,
    last: float | None,
    spread_ticks: float | None = 2.0,
    fresh: bool = True,
    symbol_match: bool = True,
    required_fields_present: bool = True,
    blocking_reasons: tuple[str, ...] = (),
) -> NQLiveQuoteInput:
    return NQLiveQuoteInput(
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


def nq_quote(
    *,
    bid: float | None = 18179.5,
    ask: float | None = 18180.0,
    last: float | None = 18180.0,
    spread_ticks: float | None = 2.0,
    fresh: bool = True,
    required_fields_present: bool = True,
    blocking_reasons: tuple[str, ...] = (),
) -> NQLiveQuoteInput:
    return quote_input(
        contract="NQ",
        symbol="/NQM26",
        bid=bid,
        ask=ask,
        last=last,
        spread_ticks=spread_ticks,
        fresh=fresh,
        required_fields_present=required_fields_present,
        blocking_reasons=blocking_reasons,
    )


def es_quote(
    *,
    bid: float | None = 5024.75,
    ask: float | None = 5025.25,
    last: float | None = 5025.0,
    spread_ticks: float | None = 2.0,
    fresh: bool = True,
    required_fields_present: bool = True,
    blocking_reasons: tuple[str, ...] = (),
) -> NQLiveQuoteInput:
    return quote_input(
        contract="ES",
        symbol="/ESM26",
        bid=bid,
        ask=ask,
        last=last,
        spread_ticks=spread_ticks,
        fresh=fresh,
        required_fields_present=required_fields_present,
        blocking_reasons=blocking_reasons,
    )


def trigger(
    *,
    level: float = 18175.0,
    approach_threshold_ticks: int = 12,
    relative_strength_threshold: float = 0.001,
    relative_strength_required: bool = True,
) -> NQTriggerDefinition:
    return NQTriggerDefinition(
        setup_id="nq_es_relative_breakout",
        trigger_id="nq_premarket_high_touch",
        level=level,
        direction="at_or_above",
        approach_threshold_ticks=approach_threshold_ticks,
        relative_strength_required=relative_strength_required,
        relative_strength_threshold=relative_strength_threshold,
    )


def artifact() -> NQPremarketArtifact:
    return NQPremarketArtifact(
        artifact_id="fixture_premarket_nq",
        levels={"premarket_high": 18175.0, "prior_close": 18000.0},
    )


def payload(**overrides: object) -> NQLiveWorkstationInput:
    values = {
        "contract": "NQ",
        "nq_quote": nq_quote(),
        "es_quote": es_quote(),
        "nq_bar_state": completed_bar_state("NQ"),
        "es_bar_state": completed_bar_state("ES"),
        "nq_anchor": NQAnchor(kind="prior_close", value=18000.0),
        "es_anchor": NQAnchor(kind="prior_close", value=5000.0),
        "premarket_artifact": artifact(),
        "trigger": trigger(),
        "invalidators": (),
        "event_lockout": NQWorkstationEventLockout(),
        "leadership_proxy_state": None,
        "generated_at": "2026-05-06T14:00:00+00:00",
    }
    values.update(overrides)
    return NQLiveWorkstationInput(**values)  # type: ignore[arg-type]


def bar_message(
    contract: str,
    *,
    minute: int,
    open_price: float,
    close: float,
    completed: bool = True,
) -> dict[str, object]:
    start = BASE_TIME + timedelta(minutes=minute)
    tick = 0.25
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
        "volume": 1000 + minute,
        "completed": completed,
    }


def completed_bar_state(contract: str) -> ContractBarState:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)
    if contract == "NQ":
        for minute in range(5):
            builder.ingest(
                bar_message(
                    contract,
                    minute=minute,
                    open_price=18170.0 + minute,
                    close=18176.0 + minute,
                )
            )
    else:
        for minute in range(5):
            builder.ingest(
                bar_message(
                    contract,
                    minute=minute,
                    open_price=5020.0 + minute * 0.25,
                    close=5021.0 + minute * 0.25,
                )
            )
    return builder.state(contract)


def partial_nq_bar_state() -> ContractBarState:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)
    for minute in range(4):
        builder.ingest(
            bar_message(
                "NQ",
                minute=minute,
                open_price=18170.0 + minute,
                close=18176.0 + minute,
            )
        )
    builder.ingest(bar_message("NQ", minute=4, open_price=18178.0, close=18180.0, completed=False))
    return builder.state("NQ")


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
        assert state in NQ_LIVE_WORKSTATION_STATES


def test_price_far_from_trigger_returns_dormant_with_good_quality_inputs() -> None:
    model = evaluate_nq_live_workstation(payload(nq_quote=nq_quote(bid=18099.5, ask=18100.0, last=18100.0)))

    assert model.state == "DORMANT"
    assert model.distance_to_trigger_ticks == 300.0
    assert model.blocking_reasons == ("price_outside_approach_threshold",)


def test_price_within_configured_tick_distance_returns_approaching() -> None:
    model = evaluate_nq_live_workstation(payload(nq_quote=nq_quote(bid=18172.5, ask=18173.0, last=18173.0)))

    assert model.state == "APPROACHING"
    assert model.distance_to_trigger_ticks == 8.0
    assert model.blocking_reasons == ("awaiting_trigger_touch",)


def test_trigger_touched_without_confirmation_returns_touched() -> None:
    model = evaluate_nq_live_workstation(payload(nq_bar_state=ContractBarState(contract="NQ")))

    assert model.state == "TOUCHED"
    assert model.completed_bar_evidence.nq.confirmed is False
    assert "nq_completed_five_minute_confirmation_required" in model.blocking_reasons


def test_nq_confirmation_without_full_es_relative_gate_returns_armed() -> None:
    model = evaluate_nq_live_workstation(payload(trigger=trigger(relative_strength_threshold=0.02)))

    assert model.state == "ARMED"
    assert model.completed_bar_evidence.nq.confirmed is True
    assert model.completed_bar_evidence.es is not None
    assert model.completed_bar_evidence.es.confirmed is True
    assert model.relative_strength_passed is False
    assert "relative_strength_predicate_failed" in model.blocking_reasons


def test_query_ready_requires_nq_confirmation_and_es_relative_confirmation() -> None:
    model = evaluate_nq_live_workstation(payload())

    assert model.state == "QUERY_READY"
    assert model.completed_bar_evidence.nq.confirmed is True
    assert model.completed_bar_evidence.es is not None
    assert model.completed_bar_evidence.es.confirmed is True
    assert model.relative_strength_passed is True
    assert model.pipeline_query_authorized is False
    assert model.authorizations.pipeline_query_authorized is False


def test_missing_es_live_data_blocks_es_relative_trigger_readiness() -> None:
    model = evaluate_nq_live_workstation(payload(es_quote=None))

    assert model.state == "BLOCKED"
    assert "es_quote_required_for_relative_strength" in model.blocking_reasons
    assert "es_quote.last" in model.missing_fields


def test_missing_nq_anchor_blocks() -> None:
    model = evaluate_nq_live_workstation(payload(nq_anchor=None))

    assert model.state == "BLOCKED"
    assert "nq_anchor_required" in model.blocking_reasons
    assert "nq_anchor" in model.missing_fields


def test_missing_es_anchor_blocks_when_relative_strength_is_required() -> None:
    model = evaluate_nq_live_workstation(payload(es_anchor=None))

    assert model.state == "BLOCKED"
    assert "es_anchor_required" in model.blocking_reasons
    assert "es_anchor" in model.missing_fields


def test_relative_strength_calculation_is_deterministic_and_pinned() -> None:
    model = evaluate_nq_live_workstation(payload())

    assert model.nq_return_since_anchor == 0.01
    assert model.es_return_since_anchor == 0.005
    assert model.relative_strength_vs_es == 0.005
    assert model.relative_strength_passed is True


def test_failed_relative_strength_predicate_blocks_query_ready() -> None:
    model = evaluate_nq_live_workstation(payload(trigger=trigger(relative_strength_threshold=0.006)))

    assert model.state == "ARMED"
    assert model.relative_strength_vs_es == 0.005
    assert model.relative_strength_passed is False
    assert "relative_strength_predicate_failed" in model.blocking_reasons


def test_absolute_breakout_alone_does_not_produce_query_ready_when_es_relative_required() -> None:
    model = evaluate_nq_live_workstation(payload(es_quote=None, es_anchor=None, es_bar_state=None))

    assert model.state == "BLOCKED"
    assert model.completed_bar_evidence.nq.confirmed is True
    assert model.pipeline_query_authorized is False


def test_building_bars_do_not_count_as_completed_confirmation() -> None:
    model = evaluate_nq_live_workstation(payload(nq_bar_state=partial_nq_bar_state()))

    assert model.state == "ARMED"
    assert model.completed_bar_evidence.nq.confirmed is False
    assert model.completed_bar_evidence.nq.completed_five_minute_bar_count == 0
    assert "nq_building_five_minute_bar_not_confirmation" in model.blocking_reasons


def test_completed_five_minute_confirmation_requires_completed_one_minute_support() -> None:
    complete = completed_bar_state("NQ")
    without_one_minute = type(complete)(
        contract=complete.contract,
        completed_one_minute_bars=(),
        completed_five_minute_bars=complete.completed_five_minute_bars,
        building_five_minute_bar=None,
        blocking_reasons=(),
        latest_start_time=complete.latest_start_time,
    )

    model = evaluate_nq_live_workstation(payload(nq_bar_state=without_one_minute))

    assert model.state == "TOUCHED"
    assert model.completed_bar_evidence.nq.confirmed is False
    assert "nq_completed_one_minute_confirmation_bars_required" in model.blocking_reasons


def test_stale_nq_quote_returns_stale_without_live_credentials() -> None:
    model = evaluate_nq_live_workstation(
        payload(nq_quote=nq_quote(fresh=False, blocking_reasons=("stale_or_missing_timestamp:NQ",)))
    )

    assert model.state == "STALE"
    assert "nq_quote_stale" in model.blocking_reasons
    assert "stale_or_missing_timestamp:NQ" in model.blocking_reasons


def test_stale_es_quote_blocks_es_relative_readiness() -> None:
    model = evaluate_nq_live_workstation(
        payload(es_quote=es_quote(fresh=False, blocking_reasons=("stale_or_missing_timestamp:ES",)))
    )

    assert model.state == "BLOCKED"
    assert "es_quote_stale" in model.blocking_reasons
    assert "stale_or_missing_timestamp:ES" in model.blocking_reasons


def test_missing_required_live_fields_returns_blocked() -> None:
    model = evaluate_nq_live_workstation(
        payload(
            nq_quote=nq_quote(
                ask=None,
                spread_ticks=None,
                required_fields_present=False,
                blocking_reasons=("missing_required_fields:NQ:ask,spread_ticks",),
            )
        )
    )

    assert model.state == "BLOCKED"
    assert "nq_missing_required_quote_fields" in model.blocking_reasons
    assert "nq_quote_ask_required" in model.blocking_reasons
    assert "nq_quote_spread_ticks_required" in model.blocking_reasons
    assert "nq_quote.ask" in model.missing_fields
    assert "nq_quote.spread_ticks" in model.missing_fields


def test_invalidator_returns_invalidated() -> None:
    model = evaluate_nq_live_workstation(
        payload(
            nq_quote=nq_quote(bid=18049.5, ask=18050.0, last=18050.0),
            invalidators=(
                NQInvalidatorDefinition(
                    invalidator_id="premarket_failure",
                    level=18060.0,
                    direction="at_or_below",
                ),
            ),
        )
    )

    assert model.state == "INVALIDATED"
    assert model.invalid_reasons == ("invalidator_fired:premarket_failure",)
    assert model.blocking_reasons == ("invalidator_fired:premarket_failure",)


def test_event_lockout_overrides_armed_or_query_ready() -> None:
    armed = evaluate_nq_live_workstation(
        payload(
            nq_bar_state=partial_nq_bar_state(),
            event_lockout=NQWorkstationEventLockout(active=True, reason="operator_event_lockout"),
        )
    )
    query_ready = evaluate_nq_live_workstation(
        payload(event_lockout=NQWorkstationEventLockout(active=True, reason="operator_event_lockout"))
    )

    for model in (armed, query_ready):
        assert model.state == "LOCKOUT"
        assert model.blocking_reasons == ("event_lockout_active", "operator_event_lockout")
        assert model.pipeline_query_authorized is False


def test_leadership_proxy_remains_unavailable_unless_explicitly_sourced() -> None:
    model = evaluate_nq_live_workstation(payload())

    assert model.leadership_proxy_state.available is False
    assert model.leadership_proxy_state.source == "unavailable"
    assert model.leadership_proxy_state.state == "unavailable"


def test_nq_outputs_do_not_include_unavailable_evidence_families() -> None:
    payload_dict = evaluate_nq_live_workstation(payload()).to_dict()
    encoded = json.dumps(payload_dict, sort_keys=True).lower()

    for unavailable_family in (
        "footprint",
        "cumulative_delta",
        "sweep",
        "aggressive_order_flow",
        "order_flow",
        "dom",
        "megacap",
    ):
        assert unavailable_family not in encoded


@pytest.mark.parametrize(
    ("contract", "expected_reason"),
    (
        ("6E", "contract_not_onboarded_for_nq_workstation:6E"),
        ("MGC", "contract_not_onboarded_for_nq_workstation:MGC"),
    ),
)
def test_nq_implementation_does_not_onboard_6e_or_mgc(contract: str, expected_reason: str) -> None:
    model = evaluate_nq_live_workstation(
        payload(
            contract=contract,
            nq_quote=quote_input(
                contract=contract,
                symbol=f"/{contract}M26",
                bid=18179.5,
                ask=18180.0,
                last=18180.0,
            ),
        )
    )

    assert model.state == "BLOCKED"
    assert expected_reason in model.blocking_reasons
    assert "nq_workstation_supports_nq_only" in model.blocking_reasons


@pytest.mark.parametrize(
    ("contract", "expected_reason"),
    (
        ("ZN", "excluded_contract:ZN"),
        ("GC", "never_supported_contract:GC"),
    ),
)
def test_nq_implementation_does_not_repromote_zn_or_add_gc(contract: str, expected_reason: str) -> None:
    model = evaluate_nq_live_workstation(
        payload(
            contract=contract,
            nq_quote=quote_input(
                contract=contract,
                symbol=f"/{contract}M26",
                bid=18179.5,
                ask=18180.0,
                last=18180.0,
            ),
        )
    )

    assert model.state == "BLOCKED"
    assert expected_reason in model.blocking_reasons
    assert "GC" not in final_target_contracts()
    assert "MGC" in final_target_contracts()


def test_blocking_reasons_are_stable_visible_and_json_serializable() -> None:
    model = evaluate_nq_live_workstation(payload(nq_quote=nq_quote(bid=18172.5, ask=18173.0, last=18173.0)))
    payload_dict = model.to_dict()

    assert payload_dict["schema"] == NQ_LIVE_WORKSTATION_SCHEMA
    assert payload_dict["blocking_reasons"] == ["awaiting_trigger_touch"]
    assert payload_dict["pipeline_query_authorized"] is False
    assert json.loads(json.dumps(payload_dict, sort_keys=True))["state"] == "APPROACHING"


def test_no_state_enables_trade_broker_order_fill_account_or_pnl_behavior() -> None:
    models = (
        evaluate_nq_live_workstation(payload(premarket_artifact=None)),
        evaluate_nq_live_workstation(payload(nq_quote=nq_quote(fresh=False))),
        evaluate_nq_live_workstation(payload()),
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

    model = evaluate_nq_live_workstation(payload())

    captured = capsys.readouterr()
    assert model.state == "QUERY_READY"
    assert captured.out == ""
    assert captured.err == ""


def test_runtime_profile_defaults_remain_fixture_safe_and_non_live() -> None:
    snapshot = build_profile_operations_snapshot(current_profile_id="preserved_es_phase1")
    supported = {profile.profile_id: profile for profile in snapshot.supported_profiles}

    assert "NQ" in final_target_contracts()
    assert supported["preserved_nq_phase1"].contract == "NQ"
    assert supported["preserved_nq_phase1"].operator_selectable is True
    assert default_profile_id_for_mode("fixture_demo") == "fixture_es_demo"
    assert default_profile_id_for_mode("preserved_engine") == "preserved_es_phase1"
    assert {candidate.contract for candidate in snapshot.candidate_profiles if candidate.status == "blocked"} == {"MGC"}
