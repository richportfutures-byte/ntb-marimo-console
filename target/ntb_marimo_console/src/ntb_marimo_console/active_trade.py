from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Final, Literal
from uuid import uuid4

from ntb_marimo_console.contract_universe import is_final_target_contract, normalize_contract_symbol


ACTIVE_TRADE_SCHEMA_VERSION: Final[int] = 1
ACTIVE_TRADE_PAYLOAD_TYPE: Final[str] = "ntb_marimo_console.active_trades"

TradeDirection = Literal["long", "short"]
TradeStatus = Literal["open", "closed", "stopped"]

_TRADE_DIRECTIONS: Final[frozenset[str]] = frozenset({"long", "short"})
_TRADE_STATUSES: Final[frozenset[str]] = frozenset({"open", "closed", "stopped"})
_CLOSING_STATUSES: Final[frozenset[str]] = frozenset({"closed", "stopped"})
_ROOT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "payload_type",
        "schema_version",
        "saved_at_utc",
        "trades",
    }
)
_THESIS_KEYS: Final[frozenset[str]] = frozenset(
    {
        "pipeline_result_id",
        "trigger_name",
        "trigger_state",
        "query_session_id",
    }
)
_TRADE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "trade_id",
        "contract",
        "direction",
        "entry_price",
        "entry_time_utc",
        "thesis_reference",
        "stop_loss",
        "target",
        "status",
        "operator_notes",
        "closed_at_utc",
        "close_reason",
    }
)


@dataclass(frozen=True)
class ThesisReference:
    pipeline_result_id: str
    trigger_name: str
    trigger_state: str
    query_session_id: str | None = None

    def __post_init__(self) -> None:
        pipeline_result_id = self.pipeline_result_id.strip()
        trigger_name = self.trigger_name.strip()
        trigger_state = self.trigger_state.strip()
        query_session_id = self.query_session_id.strip() if self.query_session_id else None
        if not pipeline_result_id:
            raise ValueError("Thesis reference pipeline_result_id is required.")
        if not trigger_name:
            raise ValueError("Thesis reference trigger_name is required.")
        if not trigger_state:
            raise ValueError("Thesis reference trigger_state is required.")
        object.__setattr__(self, "pipeline_result_id", pipeline_result_id)
        object.__setattr__(self, "trigger_name", trigger_name)
        object.__setattr__(self, "trigger_state", trigger_state)
        object.__setattr__(self, "query_session_id", query_session_id)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: object) -> ThesisReference:
        if not isinstance(payload, Mapping):
            raise ValueError("Thesis reference payload must be a mapping.")
        if frozenset(str(key) for key in payload.keys()) != _THESIS_KEYS:
            raise ValueError("Thesis reference payload keys are invalid.")
        return cls(
            pipeline_result_id=_required_string(payload, "pipeline_result_id"),
            trigger_name=_required_string(payload, "trigger_name"),
            trigger_state=_required_string(payload, "trigger_state"),
            query_session_id=_optional_string(payload, "query_session_id"),
        )


@dataclass(frozen=True)
class ActiveTradePnlState:
    trade_id: str
    contract: str
    status: TradeStatus
    direction: TradeDirection
    entry_price: float
    live_price: float
    price_delta: float
    direction_adjusted_points: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ActiveTrade:
    trade_id: str
    contract: str
    direction: TradeDirection
    entry_price: float
    entry_time_utc: str
    thesis_reference: ThesisReference | None = None
    stop_loss: float | None = None
    target: float | None = None
    status: TradeStatus = "open"
    operator_notes: str = ""
    closed_at_utc: str | None = None
    close_reason: str | None = None

    def __post_init__(self) -> None:
        trade_id = self.trade_id.strip()
        contract = normalize_contract_symbol(self.contract)
        direction = self.direction.strip().lower()
        status = self.status.strip().lower()
        operator_notes = self.operator_notes.strip()
        close_reason = self.close_reason.strip() if self.close_reason else None

        if not trade_id:
            raise ValueError("Active trade trade_id is required.")
        if not is_final_target_contract(contract):
            raise ValueError(f"Active trade contract is not in the final target universe: {contract}.")
        if direction not in _TRADE_DIRECTIONS:
            raise ValueError("Active trade direction must be long or short.")
        if status not in _TRADE_STATUSES:
            raise ValueError("Active trade status must be open, closed, or stopped.")
        _validate_iso_datetime(self.entry_time_utc, field_name="entry_time_utc")
        if self.closed_at_utc is not None:
            _validate_iso_datetime(self.closed_at_utc, field_name="closed_at_utc")
        if status == "open" and self.closed_at_utc is not None:
            raise ValueError("Open active trades cannot have closed_at_utc.")
        if status != "open" and self.closed_at_utc is None:
            raise ValueError("Closed or stopped active trades require closed_at_utc.")

        object.__setattr__(self, "trade_id", trade_id)
        object.__setattr__(self, "contract", contract)
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "entry_price", _positive_float(self.entry_price, "entry_price"))
        object.__setattr__(self, "stop_loss", _optional_positive_float(self.stop_loss, "stop_loss"))
        object.__setattr__(self, "target", _optional_positive_float(self.target, "target"))
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "operator_notes", operator_notes)
        object.__setattr__(self, "close_reason", close_reason)

    def pnl_state(self, live_price: float) -> ActiveTradePnlState:
        live_price_value = _positive_float(live_price, "live_price")
        price_delta = live_price_value - self.entry_price
        direction_adjusted_points = price_delta if self.direction == "long" else -price_delta
        return ActiveTradePnlState(
            trade_id=self.trade_id,
            contract=self.contract,
            status=self.status,
            direction=self.direction,
            entry_price=self.entry_price,
            live_price=live_price_value,
            price_delta=price_delta,
            direction_adjusted_points=direction_adjusted_points,
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["thesis_reference"] = (
            None if self.thesis_reference is None else self.thesis_reference.to_dict()
        )
        return payload

    @classmethod
    def from_payload(cls, payload: object) -> ActiveTrade:
        if not isinstance(payload, Mapping):
            raise ValueError("Active trade payload must be a mapping.")
        if frozenset(str(key) for key in payload.keys()) != _TRADE_KEYS:
            raise ValueError("Active trade payload keys are invalid.")
        return cls(
            trade_id=_required_string(payload, "trade_id"),
            contract=_required_string(payload, "contract"),
            direction=_required_string(payload, "direction"),  # type: ignore[arg-type]
            entry_price=_required_float(payload, "entry_price"),
            entry_time_utc=_required_string(payload, "entry_time_utc"),
            thesis_reference=(
                None
                if payload.get("thesis_reference") is None
                else ThesisReference.from_payload(payload.get("thesis_reference"))
            ),
            stop_loss=_optional_float(payload, "stop_loss"),
            target=_optional_float(payload, "target"),
            status=_required_string(payload, "status"),  # type: ignore[arg-type]
            operator_notes=_required_string(payload, "operator_notes"),
            closed_at_utc=_optional_string(payload, "closed_at_utc"),
            close_reason=_optional_string(payload, "close_reason"),
        )


class ActiveTradeRegistry:
    def __init__(
        self,
        trades: Iterable[ActiveTrade] = (),
        *,
        clock: object | None = None,
    ) -> None:
        self._clock = clock or _utc_now
        self._trades: dict[str, ActiveTrade] = {}
        for trade in trades:
            if trade.trade_id in self._trades:
                raise ValueError(f"Duplicate active trade id: {trade.trade_id}.")
            self._trades[trade.trade_id] = trade

    def add(
        self,
        *,
        contract: str,
        direction: TradeDirection,
        entry_price: float,
        thesis_reference: ThesisReference | None = None,
        entry_time_utc: str | None = None,
        stop_loss: float | None = None,
        target: float | None = None,
        operator_notes: str = "",
        trade_id: str | None = None,
    ) -> ActiveTrade:
        active_trade = ActiveTrade(
            trade_id=trade_id or uuid4().hex,
            contract=contract,
            direction=direction,
            entry_price=entry_price,
            entry_time_utc=entry_time_utc or _isoformat_utc(self._clock()),
            thesis_reference=thesis_reference,
            stop_loss=stop_loss,
            target=target,
            operator_notes=operator_notes,
        )
        if active_trade.trade_id in self._trades:
            raise ValueError(f"Duplicate active trade id: {active_trade.trade_id}.")
        self._trades[active_trade.trade_id] = active_trade
        return active_trade

    def update(
        self,
        trade_id: str,
        *,
        stop_loss: float | None = None,
        target: float | None = None,
        operator_notes: str | None = None,
        thesis_reference: ThesisReference | None = None,
    ) -> ActiveTrade:
        trade = self.get(trade_id)
        updated = replace(
            trade,
            stop_loss=trade.stop_loss if stop_loss is None else stop_loss,
            target=trade.target if target is None else target,
            operator_notes=trade.operator_notes if operator_notes is None else operator_notes,
            thesis_reference=trade.thesis_reference if thesis_reference is None else thesis_reference,
        )
        self._trades[updated.trade_id] = updated
        return updated

    def close(
        self,
        trade_id: str,
        *,
        status: TradeStatus = "closed",
        closed_at_utc: str | None = None,
        close_reason: str | None = None,
    ) -> ActiveTrade:
        if status not in _CLOSING_STATUSES:
            raise ValueError("Active trade close status must be closed or stopped.")
        trade = self.get(trade_id)
        closed = replace(
            trade,
            status=status,
            closed_at_utc=closed_at_utc or _isoformat_utc(self._clock()),
            close_reason=close_reason,
        )
        self._trades[closed.trade_id] = closed
        return closed

    def get(self, trade_id: str) -> ActiveTrade:
        normalized = trade_id.strip()
        try:
            return self._trades[normalized]
        except KeyError as exc:
            raise KeyError(f"Unknown active trade id: {normalized}.") from exc

    def list(
        self,
        *,
        status: TradeStatus | None = None,
        contract: str | None = None,
    ) -> tuple[ActiveTrade, ...]:
        trades = tuple(self._trades.values())
        if status is not None:
            status_key = status.strip().lower()
            if status_key not in _TRADE_STATUSES:
                raise ValueError("Active trade status filter must be open, closed, or stopped.")
            trades = tuple(trade for trade in trades if trade.status == status_key)
        if contract is not None:
            contract_key = normalize_contract_symbol(contract)
            trades = tuple(trade for trade in trades if trade.contract == contract_key)
        return trades

    def to_payload(self) -> dict[str, object]:
        return {
            "payload_type": ACTIVE_TRADE_PAYLOAD_TYPE,
            "schema_version": ACTIVE_TRADE_SCHEMA_VERSION,
            "saved_at_utc": _isoformat_utc(self._clock()),
            "trades": [trade.to_dict() for trade in self.list()],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True)

    @classmethod
    def from_payload(cls, payload: object, *, clock: object | None = None) -> ActiveTradeRegistry:
        if not isinstance(payload, Mapping):
            raise ValueError("Active trade registry payload must be a mapping.")
        if frozenset(str(key) for key in payload.keys()) != _ROOT_KEYS:
            raise ValueError("Active trade registry payload keys are invalid.")
        if payload.get("payload_type") != ACTIVE_TRADE_PAYLOAD_TYPE:
            raise ValueError("Active trade registry payload type is unsupported.")
        if payload.get("schema_version") != ACTIVE_TRADE_SCHEMA_VERSION:
            raise ValueError("Active trade registry schema version is unsupported.")
        saved_at_utc = payload.get("saved_at_utc")
        if not isinstance(saved_at_utc, str) or not saved_at_utc:
            raise ValueError("Active trade registry saved_at_utc is invalid.")
        _validate_iso_datetime(saved_at_utc, field_name="saved_at_utc")
        trades = payload.get("trades")
        if not isinstance(trades, list):
            raise ValueError("Active trade registry trades must be a list.")
        return cls((ActiveTrade.from_payload(item) for item in trades), clock=clock)

    @classmethod
    def from_json(cls, payload: str, *, clock: object | None = None) -> ActiveTradeRegistry:
        return cls.from_payload(json.loads(payload), clock=clock)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat_utc(value: object) -> str:
    if not isinstance(value, datetime):
        raise TypeError("Clock must return a datetime.")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _validate_iso_datetime(value: str, *, field_name: str) -> None:
    if not value:
        raise ValueError(f"Active trade {field_name} is required.")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Active trade {field_name} must be an ISO datetime.") from exc


def _positive_float(value: float, field_name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"Active trade {field_name} must be a positive finite number.")
    return result


def _optional_positive_float(value: float | None, field_name: str) -> float | None:
    if value is None:
        return None
    return _positive_float(value, field_name)


def _required_string(payload: Mapping[object, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Active trade {key} must be a string.")
    return value


def _optional_string(payload: Mapping[object, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Active trade {key} must be a string or null.")
    return value


def _required_float(payload: Mapping[object, object], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, int | float):
        raise ValueError(f"Active trade {key} must be numeric.")
    return float(value)


def _optional_float(payload: Mapping[object, object], key: str) -> float | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, int | float):
        raise ValueError(f"Active trade {key} must be numeric or null.")
    return float(value)
