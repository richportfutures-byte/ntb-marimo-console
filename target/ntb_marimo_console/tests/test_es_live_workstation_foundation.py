from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from ntb_marimo_console.live_observables.schema_v2 import (
    ContractObservableV2,
    QualityObservableV2,
    QuoteObservableV2,
)
from ntb_marimo_console.live_workstation import (
    ES_LIVE_WORKSTATION_SCHEMA,
    ES_LIVE_WORKSTATION_STATES,
    ESInvalidatorDefinition,
    ESLiveQuoteInput,
    ESLiveWorkstationInput,
    ESPremarketArtifact,
    ESTriggerDefinition,
    ESWorkstationEventLockout,
    evaluate_es_live_workstation,
)
from ntb_marimo_console.market_data import ChartFuturesBarBuilder


BASE_TIME = datetime(2026, 5, 6, 14, 0, 0, tzinfo=timezone.utc)
EXPECTED_SYMBOLS = {"ES": "/ESM26"}


def quote_input(
    *,
    contract: str = "ES",
    symbol: str = "/ESM26",
    bid: float | None = 99.75,
    ask: float | None = 100.25,
    last: float | None = 100.0,
    fresh: bool = True,
    symbol_match: bool = True,
    required_fields_present: bool = True,
    blocking_reasons: tuple[str, ...] = (),
) -> ESLiveQuoteInput:
    return ESLiveQuoteInput(
        contract=contract,
        symbol=symbol,
        bid=bid,
        ask=ask,
        last=last,
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
    level: float = 100.0,
    approach_threshold_ticks: int = 4,
) -> ESTriggerDefinition:
    return ESTriggerDefinition(
        trigger_id="premarket_high_touch",
        level=level,
        direction="at_or_above",
        approach_threshold_ticks=approach_threshold_ticks,
    )


def artifact() -> ESPremarketArtifact:
    return ESPremarketArtifact(
        artifact_id="fixture_premarket_es",
        levels={"premarket_high": 100.0, "prior_close": 98.75},
    )


def payload(**overrides: object) -> ESLiveWorkstationInput:
    values = {
        "contract": "ES",
        "quote": quote_input(),
        "bar_state": None,
        "premarket_artifact": artifact(),
        "trigger": trigger(),
        "invalidators": (),
        "event_lockout": ESWorkstationEventLockout(),
    }
    values.update(overrides)
    return ESLiveWorkstationInput(**values)  # type: ignore[arg-type]


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
        "contract": "ES",
        "symbol": "/ESM26",
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(minutes=1)).isoformat(),
        "open": open_price,
        "high": max(open_price, close) + 0.25,
        "low": min(open_price, close) - 0.25,
        "close": close,
        "volume": 100 + minute,
        "completed": completed,
    }


def completed_bar_state() -> object:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)
    for minute in range(5):
        builder.ingest(bar_message(minute=minute, open_price=100.0 + minute * 0.25, close=100.5 + minute * 0.25))
    return builder.state("ES")


def partial_bar_state() -> object:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)
    for minute in range(4):
        builder.ingest(bar_message(minute=minute, open_price=100.0 + minute * 0.25, close=100.25 + minute * 0.25))
    builder.ingest(bar_message(minute=4, open_price=101.0, close=101.25, completed=False))
    return builder.state("ES")


def test_missing_premarket_trigger_or_artifact_fails_closed() -> None:
    missing_artifact = evaluate_es_live_workstation(payload(premarket_artifact=None))
    missing_trigger = evaluate_es_live_workstation(payload(trigger=None))

    assert missing_artifact.state == "BLOCKED"
    assert "premarket_artifact_required" in missing_artifact.blocking_reasons
    assert missing_trigger.state == "BLOCKED"
    assert "premarket_trigger_required" in missing_trigger.blocking_reasons


def test_stale_quote_returns_stale_without_live_credentials() -> None:
    model = evaluate_es_live_workstation(
        payload(quote=quote_input(fresh=False, blocking_reasons=("stale_or_missing_timestamp:ES",)))
    )

    assert model.state == "STALE"
    assert "quote_stale" in model.blocking_reasons
    assert "stale_or_missing_timestamp:ES" in model.blocking_reasons


def test_event_lockout_returns_lockout() -> None:
    model = evaluate_es_live_workstation(
        payload(event_lockout=ESWorkstationEventLockout(active=True, reason="fomc_lockout"))
    )

    assert model.state == "LOCKOUT"
    assert model.blocking_reasons == ("event_lockout_active", "fomc_lockout")


def test_missing_required_quote_fields_blocks() -> None:
    model = evaluate_es_live_workstation(
        payload(
            quote=quote_input(
                ask=None,
                required_fields_present=False,
                blocking_reasons=("missing_required_fields:ES:ask",),
            )
        )
    )

    assert model.state == "BLOCKED"
    assert "missing_required_quote_fields" in model.blocking_reasons
    assert "quote_ask_required" in model.blocking_reasons
    assert "missing_required_fields:ES:ask" in model.blocking_reasons


@pytest.mark.parametrize(
    ("contract", "expected_reason"),
    (
        ("NQ", "contract_not_onboarded_for_es_workstation:NQ"),
        ("6E", "contract_not_onboarded_for_es_workstation:6E"),
        ("MGC", "contract_not_onboarded_for_es_workstation:MGC"),
        ("ZN", "excluded_contract:ZN"),
        ("GC", "never_supported_contract:GC"),
    ),
)
def test_contract_mismatch_unsupported_and_excluded_contracts_block(
    contract: str,
    expected_reason: str,
) -> None:
    model = evaluate_es_live_workstation(
        payload(
            contract=contract,
            quote=quote_input(contract=contract, symbol=f"/{contract}M26"),
        )
    )

    assert model.state == "BLOCKED"
    assert expected_reason in model.blocking_reasons
    assert "es_workstation_supports_es_only" in model.blocking_reasons


def test_quote_contract_mismatch_blocks() -> None:
    model = evaluate_es_live_workstation(payload(quote=quote_input(contract="NQ", symbol="/NQM26")))

    assert model.state == "BLOCKED"
    assert "quote_contract_mismatch:NQ" in model.blocking_reasons


def test_price_away_from_trigger_returns_dormant() -> None:
    model = evaluate_es_live_workstation(payload(quote=quote_input(bid=97.75, ask=98.25, last=98.0)))

    assert model.state == "DORMANT"
    assert model.distance_to_trigger_ticks == 8.0
    assert model.blocking_reasons == ("price_outside_approach_threshold",)


def test_price_within_configured_tick_distance_returns_approaching() -> None:
    model = evaluate_es_live_workstation(payload(quote=quote_input(bid=99.0, ask=99.5, last=99.25)))

    assert model.state == "APPROACHING"
    assert model.distance_to_trigger_ticks == 3.0
    assert model.blocking_reasons == ("awaiting_trigger_touch",)


def test_touched_trigger_with_partial_confirmation_returns_armed_not_query_ready() -> None:
    model = evaluate_es_live_workstation(payload(bar_state=partial_bar_state()))

    assert model.state == "ARMED"
    assert model.confirmation.confirmed is False
    assert "completed_five_minute_confirmation_required" in model.blocking_reasons
    assert "building_five_minute_bar_not_confirmation" in model.blocking_reasons


def test_query_ready_read_model_requires_completed_five_minute_confirmation() -> None:
    partial = evaluate_es_live_workstation(payload(bar_state=partial_bar_state()))
    completed = evaluate_es_live_workstation(payload(bar_state=completed_bar_state()))

    assert partial.state == "ARMED"
    assert partial.confirmation.confirmed is False
    assert completed.state == "QUERY_READY"
    assert completed.confirmation.confirmed is True
    assert completed.confirmation.completed_one_minute_bar_count == 5
    assert completed.confirmation.completed_five_minute_bar_count == 1
    assert completed.authorizations.pipeline_query_authorized is False


def test_completed_five_minute_without_underlying_one_minute_support_does_not_confirm() -> None:
    complete = completed_bar_state()
    without_one_minute = type(complete)(
        contract=complete.contract,
        completed_one_minute_bars=(),
        completed_five_minute_bars=complete.completed_five_minute_bars,
        building_five_minute_bar=None,
        blocking_reasons=(),
        latest_start_time=complete.latest_start_time,
    )

    model = evaluate_es_live_workstation(payload(bar_state=without_one_minute))

    assert model.state == "TOUCHED"
    assert model.confirmation.confirmed is False
    assert "completed_one_minute_confirmation_bars_required" in model.blocking_reasons


def test_invalidator_firing_returns_invalidated() -> None:
    model = evaluate_es_live_workstation(
        payload(
            quote=quote_input(bid=98.25, ask=98.75, last=98.5),
            invalidators=(
                ESInvalidatorDefinition(
                    invalidator_id="premarket_failure",
                    level=99.0,
                    direction="at_or_below",
                ),
            ),
        )
    )

    assert model.state == "INVALIDATED"
    assert model.blocking_reasons == ("invalidator_fired:premarket_failure",)


def test_blocking_reasons_are_stable_visible_and_json_serializable() -> None:
    model = evaluate_es_live_workstation(payload(quote=quote_input(bid=99.0, ask=99.5, last=99.25)))
    payload_dict = model.to_dict()

    assert payload_dict["schema"] == ES_LIVE_WORKSTATION_SCHEMA
    assert payload_dict["blocking_reasons"] == ["awaiting_trigger_touch"]
    assert json.loads(json.dumps(payload_dict, sort_keys=True))["state"] == "APPROACHING"


def test_source_classification_from_live_observable_contract() -> None:
    observable = ContractObservableV2(
        contract="ES",
        symbol="/ESM26",
        quote=QuoteObservableV2(bid=99.75, ask=100.25, last=100.0),
        quality=QualityObservableV2(
            fresh=True,
            symbol_match=True,
            required_fields_present=True,
        ),
    )

    model = evaluate_es_live_workstation(payload(quote=ESLiveQuoteInput.from_live_observable(observable)))

    assert model.source_classification["quote"] == "observed_from_schwab"
    assert model.source_classification["quote_quality"] == "derived_from_schwab"
    assert model.source_classification["premarket_artifact"] == "preserved_artifact"
    assert model.source_classification["event_lockout"] == "manual_operator_input"
    assert model.source_classification["bar_confirmation"] == "unavailable"


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
        assert state in ES_LIVE_WORKSTATION_STATES


def test_no_state_enables_trade_broker_order_fill_account_or_pnl_behavior() -> None:
    models = (
        evaluate_es_live_workstation(payload(premarket_artifact=None)),
        evaluate_es_live_workstation(payload(quote=quote_input(fresh=False))),
        evaluate_es_live_workstation(payload(bar_state=completed_bar_state())),
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

    model = evaluate_es_live_workstation(payload(bar_state=completed_bar_state()))

    captured = capsys.readouterr()
    assert model.state == "QUERY_READY"
    assert captured.out == ""
    assert captured.err == ""
