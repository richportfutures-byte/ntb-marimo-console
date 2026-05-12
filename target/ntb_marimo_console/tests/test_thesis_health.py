from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from ntb_marimo_console.active_trade import ActiveTrade, ActiveTradeRegistry, ThesisReference
from ntb_marimo_console.market_data.stream_cache import StreamCacheRecord, StreamCacheSnapshot
from ntb_marimo_console.thesis_health import assess_all_open_trades, assess_trade_thesis


FIXTURE_NOW = "2026-05-12T15:00:00+00:00"


def thesis_reference() -> ThesisReference:
    return ThesisReference(
        pipeline_result_id="pipeline-result-fixture-001",
        trigger_name="fixture-trigger",
        trigger_state="QUERY_READY",
        query_session_id="query-session-fixture-001",
    )


def active_trade_registry() -> ActiveTradeRegistry:
    return ActiveTradeRegistry(clock=lambda: datetime(2026, 5, 12, 14, 30, tzinfo=timezone.utc))


def open_trade(
    *,
    trade_id: str = "trade-es-fixture-001",
    contract: str = "ES",
    direction: str = "long",
    entry_price: float = 5325.0,
    stop_loss: float | None = 5315.0,
    target: float | None = 5345.0,
) -> ActiveTrade:
    return active_trade_registry().add(
        trade_id=trade_id,
        contract=contract,
        direction=direction,  # type: ignore[arg-type]
        entry_price=entry_price,
        thesis_reference=thesis_reference(),
        stop_loss=stop_loss,
        target=target,
    )


def stream_cache_snapshot(
    *,
    contract: str = "ES",
    last: float | None = 5330.0,
    fresh: bool = True,
) -> StreamCacheSnapshot:
    records: tuple[StreamCacheRecord, ...] = ()
    stale_symbols: tuple[str, ...] = ()
    if last is not None:
        stale_symbols = () if fresh else (f"{contract}_TEST",)
        records = (
            StreamCacheRecord(
                provider="fixture",
                service="LEVELONE_FUTURES",
                symbol=f"{contract}_TEST",
                contract=contract,
                message_type="quote",
                fields=(("ask", last + 0.25), ("bid", last - 0.25), ("last", last)),
                updated_at=FIXTURE_NOW,
                age_seconds=2.0 if fresh else 90.0,
                fresh=fresh,
                blocking_reasons=(),
            ),
        )
    return StreamCacheSnapshot(
        generated_at=FIXTURE_NOW,
        provider="fixture",
        provider_status="active" if fresh else "stale",
        cache_max_age_seconds=15.0,
        records=records,
        blocking_reasons=(),
        stale_symbols=stale_symbols,
    )


def test_trade_with_no_thesis_reference_returns_no_thesis() -> None:
    trade = replace(open_trade(), thesis_reference=None)

    assessment = assess_trade_thesis(trade, stream_cache_snapshot())

    assert assessment.status == "no_thesis"
    assert assessment.reasons == ("no_thesis_reference",)
    assert assessment.live_price is None


def test_trade_with_no_live_data_returns_unknown() -> None:
    assessment = assess_trade_thesis(open_trade(), stream_cache_snapshot(last=None))

    assert assessment.status == "unknown"
    assert assessment.reasons == ("no_live_data",)
    assert assessment.distance_from_stop is None
    assert assessment.distance_from_target is None


def test_trade_with_stale_data_returns_degraded() -> None:
    assessment = assess_trade_thesis(open_trade(), stream_cache_snapshot(last=5322.0, fresh=False))

    assert assessment.status == "degraded"
    assert assessment.reasons == ("stale_data",)
    assert assessment.live_price == 5322.0


def test_long_trade_where_price_crossed_stop_returns_invalidated() -> None:
    assessment = assess_trade_thesis(open_trade(), stream_cache_snapshot(last=5314.75))

    assert assessment.status == "invalidated"
    assert assessment.reasons == ("stop_crossed",)


def test_short_trade_where_price_crossed_stop_returns_invalidated() -> None:
    trade = open_trade(
        trade_id="trade-nq-fixture-001",
        contract="NQ",
        direction="short",
        entry_price=18650.0,
        stop_loss=18680.0,
        target=18580.0,
    )

    assessment = assess_trade_thesis(trade, stream_cache_snapshot(contract="NQ", last=18681.0))

    assert assessment.status == "invalidated"
    assert assessment.reasons == ("stop_crossed",)


def test_long_trade_with_adverse_movement_returns_degraded() -> None:
    assessment = assess_trade_thesis(open_trade(), stream_cache_snapshot(last=5319.0))

    assert assessment.status == "degraded"
    assert assessment.reasons == ("adverse_movement",)


def test_long_trade_moving_toward_target_returns_healthy() -> None:
    assessment = assess_trade_thesis(open_trade(), stream_cache_snapshot(last=5338.0))

    assert assessment.status == "healthy"
    assert assessment.reasons == ("thesis_holding",)
    assert assessment.to_dict()["reasons"] == ["thesis_holding"]


def test_distance_calculations_are_correct_for_long_and_short_trades() -> None:
    long_assessment = assess_trade_thesis(open_trade(), stream_cache_snapshot(last=5330.0))
    short_trade = open_trade(
        trade_id="trade-cl-fixture-001",
        contract="CL",
        direction="short",
        entry_price=78.4,
        stop_loss=79.1,
        target=77.2,
    )
    short_assessment = assess_trade_thesis(
        short_trade,
        stream_cache_snapshot(contract="CL", last=77.7),
    )

    assert long_assessment.distance_from_stop == 15.0
    assert long_assessment.distance_from_target == 15.0
    assert round(short_assessment.distance_from_stop or 0.0, 10) == 1.4
    assert round(short_assessment.distance_from_target or 0.0, 10) == 0.5


def test_assess_all_open_trades_returns_correct_mapping() -> None:
    registry = active_trade_registry()
    es_trade = registry.add(
        trade_id="trade-es-fixture-001",
        contract="ES",
        direction="long",
        entry_price=5325.0,
        thesis_reference=thesis_reference(),
        stop_loss=5315.0,
        target=5345.0,
    )
    nq_trade = registry.add(
        trade_id="trade-nq-fixture-001",
        contract="NQ",
        direction="short",
        entry_price=18650.0,
        thesis_reference=thesis_reference(),
        stop_loss=18680.0,
        target=18580.0,
    )
    snapshot = StreamCacheSnapshot(
        generated_at=FIXTURE_NOW,
        provider="fixture",
        provider_status="active",
        cache_max_age_seconds=15.0,
        records=(
            stream_cache_snapshot(contract="ES", last=5335.0).records[0],
            stream_cache_snapshot(contract="NQ", last=18670.0).records[0],
        ),
        blocking_reasons=(),
        stale_symbols=(),
    )

    assessments = assess_all_open_trades(registry, snapshot)

    assert tuple(assessments) == (es_trade.trade_id, nq_trade.trade_id)
    assert assessments[es_trade.trade_id].status == "healthy"
    assert assessments[nq_trade.trade_id].status == "degraded"
    assert assessments[nq_trade.trade_id].reasons == ("adverse_movement",)


def test_closed_trades_are_excluded_from_assessment() -> None:
    registry = active_trade_registry()
    open_item = registry.add(
        trade_id="trade-es-open",
        contract="ES",
        direction="long",
        entry_price=5325.0,
        thesis_reference=thesis_reference(),
        stop_loss=5315.0,
        target=5345.0,
    )
    closed_item = registry.add(
        trade_id="trade-es-closed",
        contract="ES",
        direction="long",
        entry_price=5320.0,
        thesis_reference=thesis_reference(),
        stop_loss=5310.0,
        target=5340.0,
    )
    registry.close(closed_item.trade_id, status="closed", close_reason="fixture_close")

    assessments = assess_all_open_trades(registry, stream_cache_snapshot(last=5330.0))

    assert tuple(assessments) == (open_item.trade_id,)
