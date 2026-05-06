from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.market_data.stream_cache import StreamCacheSnapshot

from .quality import contract_tick_size, normalize_provider_status, provider_blocking_reason
from .schema_v2 import (
    ContractObservableV2,
    DerivedObservableV2,
    LiveObservableSnapshotV2,
    QualityObservableV2,
    QuoteObservableV2,
    SessionObservableV2,
)


class StreamCacheSnapshotLike(Protocol):
    generated_at: str
    provider: str
    provider_status: str
    records: tuple[object, ...]
    blocking_reasons: tuple[str, ...]
    stale_symbols: tuple[str, ...]


@dataclass(frozen=True)
class LiveObservableSnapshotBuilder:
    expected_symbols: Mapping[str, str] | None = None
    clock: object | None = None

    def build(self, cache_snapshot: StreamCacheSnapshotLike | None = None) -> LiveObservableSnapshotV2:
        generated_at = _generated_at(cache_snapshot, clock=self.clock)
        provider = _provider(cache_snapshot)
        provider_status = normalize_provider_status(getattr(cache_snapshot, "provider_status", "disabled"))
        provider_reason = provider_blocking_reason(provider_status)
        cache_blocking_reasons = _cache_blocking_reasons(cache_snapshot)
        records_by_contract = _records_by_contract(cache_snapshot)

        contracts: dict[str, ContractObservableV2] = {}
        for contract in final_target_contracts():
            record = records_by_contract.get(contract)
            contracts[contract] = _contract_observable(
                contract,
                record=record,
                expected_symbol=_expected_symbol(contract, self.expected_symbols, record),
                generated_at=generated_at,
                provider_reason=provider_reason,
                cache_blocking_reasons=cache_blocking_reasons,
            )

        all_blocking_reasons = _dedupe(
            tuple(cache_blocking_reasons)
            + tuple(reason for reason in (provider_reason,) if reason is not None)
            + tuple(
                f"{contract}:{reason}"
                for contract, observable in contracts.items()
                for reason in observable.quality.blocking_reasons
            )
        )
        ready_contracts = tuple(
            contract
            for contract, observable in contracts.items()
            if (
                observable.quality.fresh
                and observable.quality.symbol_match
                and observable.quality.required_fields_present
                and not observable.quality.blocking_reasons
            )
        )
        return LiveObservableSnapshotV2(
            generated_at=generated_at,
            provider=provider,
            provider_status=provider_status,
            contracts=contracts,
            cross_asset={
                "dxy": {"source": "unavailable", "value": None},
                "yield_context": {"source": "unavailable", "value": None},
                "es_relative_strength": {"source": "unavailable", "value": None},
            },
            macro_context={
                "event_lockout": {"source": "unavailable", "value": None},
            },
            session_context={
                "session_sequence": {"source": "unavailable", "value": None},
            },
            data_quality={
                "ready": provider_status == "connected" and len(ready_contracts) == len(final_target_contracts()),
                "state": "blocked" if all_blocking_reasons else "ready",
                "ready_contracts": list(ready_contracts),
                "blocking_reasons": list(all_blocking_reasons),
            },
        )


def build_live_observable_snapshot_v2(
    cache_snapshot: StreamCacheSnapshot | None = None,
    *,
    expected_symbols: Mapping[str, str] | None = None,
    clock: object | None = None,
) -> LiveObservableSnapshotV2:
    return LiveObservableSnapshotBuilder(expected_symbols=expected_symbols, clock=clock).build(cache_snapshot)


def _contract_observable(
    contract: str,
    *,
    record: object | None,
    expected_symbol: str | None,
    generated_at: str,
    provider_reason: str | None,
    cache_blocking_reasons: tuple[str, ...],
) -> ContractObservableV2:
    if record is None:
        reasons = _dedupe(
            tuple(reason for reason in (provider_reason,) if reason is not None)
            + cache_blocking_reasons
            + (f"missing_cache_record:{contract}",)
        )
        return ContractObservableV2(
            contract=contract,
            symbol=expected_symbol,
            quality=QualityObservableV2(blocking_reasons=reasons),
            label=_contract_label(contract),
        )

    fields = _record_fields(record)
    symbol = _record_symbol(record)
    quote_time = _timestamp_field(fields, "quote_time") or _record_updated_at(record)
    trade_time = _timestamp_field(fields, "trade_time") or _record_updated_at(record)
    quote_age_seconds = _age_seconds(quote_time, generated_at=generated_at)
    trade_age_seconds = _age_seconds(trade_time, generated_at=generated_at)
    quote = QuoteObservableV2(
        bid=_number_field(fields, "bid", "bid_price"),
        ask=_number_field(fields, "ask", "ask_price"),
        last=_number_field(fields, "last", "last_price"),
        bid_size=_number_field(fields, "bid_size"),
        ask_size=_number_field(fields, "ask_size"),
        last_size=_number_field(fields, "last_size"),
        quote_time=quote_time,
        trade_time=trade_time,
        quote_age_seconds=quote_age_seconds,
        trade_age_seconds=trade_age_seconds,
    )
    session = SessionObservableV2(
        open=_number_field(fields, "open"),
        high=_number_field(fields, "high"),
        low=_number_field(fields, "low"),
        prior_close=_number_field(fields, "prior_close", "close", "close_price"),
        net_change=_number_field(fields, "net_change"),
        percent_change=_number_field(fields, "percent_change"),
        volume=_number_field(fields, "volume", "total_volume"),
        security_status=_string_field(fields, "security_status"),
        tradable=_bool_field(fields, "tradable", "future_is_tradable"),
        active=_bool_field(fields, "active", "future_is_active"),
    )
    tick_size = contract_tick_size(contract)
    derived = DerivedObservableV2(
        spread_ticks=_spread_ticks(quote.bid, quote.ask, tick_size),
        mid=_mid(quote.bid, quote.ask),
    )
    required_reasons = _required_field_reasons(contract, quote)
    symbol_match = bool(expected_symbol and symbol == expected_symbol)
    symbol_reasons = () if symbol_match else (f"symbol_mismatch:{contract}:{symbol or 'missing'}",)
    fresh = _record_fresh(record) and quote_age_seconds is not None and trade_age_seconds is not None
    freshness_reasons = () if fresh else (f"stale_or_missing_timestamp:{contract}",)
    record_reasons = tuple(_record_blocking_reasons(record))
    reasons = _dedupe(
        tuple(reason for reason in (provider_reason,) if reason is not None)
        + cache_blocking_reasons
        + record_reasons
        + required_reasons
        + symbol_reasons
        + freshness_reasons
    )

    return ContractObservableV2(
        contract=contract,
        symbol=symbol,
        quote=quote,
        session=session,
        derived=derived,
        quality=QualityObservableV2(
            fresh=fresh,
            delayed=None,
            symbol_match=symbol_match,
            required_fields_present=not required_reasons,
            blocking_reasons=reasons,
        ),
        label=_contract_label(contract),
    )


def _records_by_contract(cache_snapshot: StreamCacheSnapshotLike | None) -> dict[str, object]:
    records: dict[str, object] = {}
    if cache_snapshot is None:
        return records
    for record in getattr(cache_snapshot, "records", ()):
        contract = _record_contract(record)
        if contract in final_target_contracts():
            records.setdefault(contract, record)
    return records


def _record_fields(record: object) -> dict[str, object]:
    fields = getattr(record, "fields", ())
    if isinstance(fields, Mapping):
        raw_items = fields.items()
    else:
        raw_items = fields
    normalized: dict[str, object] = {}
    for key, value in raw_items:
        normalized[str(key).strip().lower()] = value
    return normalized


def _record_contract(record: object) -> str:
    return str(getattr(record, "contract", "")).strip().upper()


def _record_symbol(record: object) -> str | None:
    symbol = str(getattr(record, "symbol", "")).strip().upper()
    return symbol or None


def _record_updated_at(record: object) -> str | None:
    value = getattr(record, "updated_at", None)
    return value if isinstance(value, str) and value.strip() else None


def _record_fresh(record: object) -> bool:
    return bool(getattr(record, "fresh", False))


def _record_blocking_reasons(record: object) -> tuple[str, ...]:
    return tuple(str(reason) for reason in getattr(record, "blocking_reasons", ()) if str(reason).strip())


def _cache_blocking_reasons(cache_snapshot: StreamCacheSnapshotLike | None) -> tuple[str, ...]:
    if cache_snapshot is None:
        return ("cache_snapshot_missing",)
    reasons = tuple(str(reason) for reason in getattr(cache_snapshot, "blocking_reasons", ()) if str(reason).strip())
    stale_symbols = tuple(str(symbol) for symbol in getattr(cache_snapshot, "stale_symbols", ()) if str(symbol).strip())
    return _dedupe(reasons + tuple(f"cache_stale_symbol:{symbol}" for symbol in stale_symbols))


def _provider(cache_snapshot: StreamCacheSnapshotLike | None) -> str:
    provider = str(getattr(cache_snapshot, "provider", "disabled")).strip().lower()
    return provider or "disabled"


def _generated_at(cache_snapshot: StreamCacheSnapshotLike | None, *, clock: object | None) -> str:
    if cache_snapshot is not None:
        generated_at = getattr(cache_snapshot, "generated_at", None)
        if isinstance(generated_at, str) and generated_at.strip():
            return _isoformat(_parse_timestamp(generated_at) or _utc_now())
    current_clock = clock or _utc_now
    return _isoformat(current_clock())


def _expected_symbol(contract: str, expected_symbols: Mapping[str, str] | None, record: object | None) -> str | None:
    if expected_symbols and contract in expected_symbols:
        return expected_symbols[contract].strip().upper()
    return _record_symbol(record) if record is not None else None


def _number_field(fields: Mapping[str, object], *names: str) -> float | int | None:
    for name in names:
        value = fields.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
    return None


def _string_field(fields: Mapping[str, object], *names: str) -> str | None:
    for name in names:
        value = fields.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _timestamp_field(fields: Mapping[str, object], name: str) -> str | None:
    value = _string_field(fields, name)
    return value if value and _parse_timestamp(value) is not None else None


def _bool_field(fields: Mapping[str, object], *names: str) -> bool | None:
    for name in names:
        value = fields.get(name)
        if isinstance(value, bool):
            return value
    return None


def _required_field_reasons(contract: str, quote: QuoteObservableV2) -> tuple[str, ...]:
    missing: list[str] = []
    for field_name in ("bid", "ask", "last"):
        if getattr(quote, field_name) is None:
            missing.append(field_name)
    if quote.quote_time is None and quote.trade_time is None:
        missing.append("quote_or_trade_timestamp")
    if missing:
        return (f"missing_required_fields:{contract}:{','.join(missing)}",)
    return ()


def _mid(bid: float | int | None, ask: float | int | None) -> float | None:
    if bid is None or ask is None:
        return None
    return (float(bid) + float(ask)) / 2.0


def _spread_ticks(bid: float | int | None, ask: float | int | None, tick_size: float | None) -> float | None:
    if bid is None or ask is None or tick_size is None:
        return None
    return round((float(ask) - float(bid)) / tick_size, 10)


def _age_seconds(value: str | None, *, generated_at: str) -> float | None:
    if value is None:
        return None
    parsed_value = _parse_timestamp(value)
    parsed_generated_at = _parse_timestamp(generated_at)
    if parsed_value is None or parsed_generated_at is None:
        return None
    return max(0.0, (parsed_generated_at - parsed_value).total_seconds())


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    current = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat()


def _dedupe(reasons: tuple[str, ...]) -> tuple[str, ...]:
    deduped: list[str] = []
    for reason in reasons:
        normalized = str(reason).strip()
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return tuple(deduped)


def _contract_label(contract: str) -> str | None:
    if contract == "MGC":
        return "Micro Gold"
    return None
