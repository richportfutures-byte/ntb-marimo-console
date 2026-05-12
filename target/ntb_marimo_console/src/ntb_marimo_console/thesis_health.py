from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Final, Literal

from ntb_marimo_console.active_trade import ActiveTrade, ActiveTradeRegistry
from ntb_marimo_console.market_data.stream_cache import StreamCacheRecord, StreamCacheSnapshot


ThesisHealthStatus = Literal["healthy", "degraded", "invalidated", "unknown", "no_thesis"]

_PRICE_FIELD_PRIORITY: Final[tuple[str, ...]] = (
    "last",
    "last_price",
    "current_price",
    "mark",
    "mid",
)


@dataclass(frozen=True)
class ThesisHealthAssessment:
    status: ThesisHealthStatus
    contract: str
    trade_id: str
    reasons: tuple[str, ...]
    assessed_at: str
    live_price: float | None
    entry_price: float
    distance_from_stop: float | None
    distance_from_target: float | None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


def assess_trade_thesis(
    trade: ActiveTrade,
    cache_snapshot: StreamCacheSnapshot,
    *,
    assessed_at: str | None = None,
) -> ThesisHealthAssessment:
    assessed_at_value = assessed_at or cache_snapshot.generated_at or _utc_now_iso()
    if trade.thesis_reference is None:
        return _assessment(
            trade,
            status="no_thesis",
            reasons=("no_thesis_reference",),
            assessed_at=assessed_at_value,
            live_price=None,
        )

    record = _record_for_contract(cache_snapshot, trade.contract)
    if record is None:
        return _assessment(
            trade,
            status="unknown",
            reasons=("no_live_data",),
            assessed_at=assessed_at_value,
            live_price=None,
        )

    live_price = _live_price_from_record(record)
    if live_price is None:
        return _assessment(
            trade,
            status="unknown",
            reasons=("no_live_data",),
            assessed_at=assessed_at_value,
            live_price=None,
        )

    if not record.fresh:
        return _assessment(
            trade,
            status="degraded",
            reasons=("stale_data",),
            assessed_at=assessed_at_value,
            live_price=live_price,
        )

    if _stop_crossed(trade, live_price):
        return _assessment(
            trade,
            status="invalidated",
            reasons=("stop_crossed",),
            assessed_at=assessed_at_value,
            live_price=live_price,
        )

    if _adverse_movement(trade, live_price):
        return _assessment(
            trade,
            status="degraded",
            reasons=("adverse_movement",),
            assessed_at=assessed_at_value,
            live_price=live_price,
        )

    return _assessment(
        trade,
        status="healthy",
        reasons=("thesis_holding",),
        assessed_at=assessed_at_value,
        live_price=live_price,
    )


def assess_all_open_trades(
    registry: ActiveTradeRegistry,
    cache_snapshot: StreamCacheSnapshot,
    *,
    assessed_at: str | None = None,
) -> dict[str, ThesisHealthAssessment]:
    return {
        trade.trade_id: assess_trade_thesis(trade, cache_snapshot, assessed_at=assessed_at)
        for trade in registry.list(status="open")
    }


def _assessment(
    trade: ActiveTrade,
    *,
    status: ThesisHealthStatus,
    reasons: tuple[str, ...],
    assessed_at: str,
    live_price: float | None,
) -> ThesisHealthAssessment:
    return ThesisHealthAssessment(
        status=status,
        contract=trade.contract,
        trade_id=trade.trade_id,
        reasons=reasons,
        assessed_at=assessed_at,
        live_price=live_price,
        entry_price=trade.entry_price,
        distance_from_stop=_distance(live_price, trade.stop_loss),
        distance_from_target=_distance(live_price, trade.target),
    )


def _record_for_contract(
    cache_snapshot: StreamCacheSnapshot,
    contract: str,
) -> StreamCacheRecord | None:
    matching = tuple(record for record in cache_snapshot.records if record.contract == contract)
    if not matching:
        return None
    quote_records = tuple(record for record in matching if record.message_type == "quote")
    candidates = quote_records or matching
    return max(candidates, key=lambda record: record.updated_at)


def _live_price_from_record(record: StreamCacheRecord) -> float | None:
    fields = dict(record.fields)
    for field_name in _PRICE_FIELD_PRIORITY:
        value = fields.get(field_name)
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            return float(value)
    return None


def _stop_crossed(trade: ActiveTrade, live_price: float) -> bool:
    if trade.stop_loss is None:
        return False
    if trade.direction == "long":
        return live_price <= trade.stop_loss
    return live_price >= trade.stop_loss


def _adverse_movement(trade: ActiveTrade, live_price: float) -> bool:
    if trade.target is None or trade.stop_loss is None:
        return False
    if trade.direction == "long":
        return trade.stop_loss < live_price < trade.entry_price < trade.target
    return trade.target < trade.entry_price < live_price < trade.stop_loss


def _distance(live_price: float | None, level: float | None) -> float | None:
    if live_price is None or level is None:
        return None
    return abs(live_price - level)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
