from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.market_data.chart_bars import ContractBarState
from ntb_marimo_console.market_data.stream_cache import StreamCacheSnapshot

from .quality import contract_tick_size, normalize_provider_status, provider_blocking_reason
from .schema_v2 import (
    ChartBarObservableV2,
    ContractObservableV2,
    DependencyObservableV2,
    DependencyStatusV2,
    DerivedObservableV2,
    LiveObservableSnapshotV2,
    QualityObservableV2,
    QuoteObservableV2,
    SessionObservableV2,
)


QUOTE_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "bid": ("bid", "bid_price", "bid price", "1"),
    "ask": ("ask", "ask_price", "ask price", "2"),
    "last": ("last", "last_price", "last price", "3"),
    "bid_size": ("bid_size", "bid size", "4"),
    "ask_size": ("ask_size", "ask size", "5"),
    "last_size": ("last_size", "last size", "9"),
    "quote_time": ("quote_time", "quote time", "10"),
    "trade_time": ("trade_time", "trade time", "11"),
}

SESSION_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "open": ("open", "open_price", "open price", "18"),
    "high": ("high", "high_price", "high price", "12"),
    "low": ("low", "low_price", "low price", "13"),
    "prior_close": ("prior_close", "close", "close_price", "close price", "14"),
    "net_change": ("net_change", "net change", "19"),
    "percent_change": ("percent_change", "future_percent_change", "future percent change", "20"),
    "volume": ("volume", "total_volume", "total volume", "8"),
    "security_status": ("security_status", "security status", "22"),
    "tradable": ("tradable", "future_is_tradable", "future is tradable", "30"),
    "active": ("active", "future_is_active", "future is active", "32"),
}

REQUIRED_QUOTE_FIELDS: tuple[str, ...] = (
    "bid",
    "ask",
    "last",
    "bid_size",
    "ask_size",
    "quote_time",
    "trade_time",
)
REQUIRED_SESSION_FIELDS: tuple[str, ...] = (
    "volume",
    "open",
    "high",
    "low",
    "prior_close",
    "tradable",
    "active",
    "security_status",
)
REQUIRED_CONTRACT_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "ES": ("cumulative_delta", "breadth"),
    "NQ": ("relative_strength_vs_es",),
    "CL": ("eia_lockout", "cumulative_delta", "current_volume_vs_average"),
    "6E": ("dxy", "session_sequence"),
    "MGC": ("dxy", "cash_10y_yield", "fear_catalyst_state"),
}


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
    bar_states: Mapping[str, ContractBarState] | None = None
    dependency_states: Mapping[str, Mapping[str, object]] | None = None
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
                bar_state=_bar_state(contract, self.bar_states),
                dependencies=_contract_dependencies(contract, self.dependency_states),
            )

        all_blocking_reasons = _dedupe(
            tuple(cache_blocking_reasons)
            + tuple(reason for reason in (provider_reason,) if reason is not None)
            + tuple(
                f"{contract}:{reason}"
                for contract, observable in contracts.items()
                for reason in observable.quality.blocking_reasons
            )
            + tuple(
                f"{contract}:{reason}"
                for contract, observable in contracts.items()
                for reason in observable.chart_bar.blocking_reasons
            )
            + tuple(
                f"{contract}:{reason}"
                for contract, observable in contracts.items()
                for reason in observable.quality.dependency_blocking_reasons
            )
        )
        quote_ready_contracts = tuple(
            contract
            for contract, observable in contracts.items()
            if (
                observable.quality.fresh
                and observable.quality.symbol_match
                and observable.quality.required_fields_present
                and not observable.quality.blocking_reasons
            )
        )
        ready_contracts = tuple(
            contract
            for contract, observable in contracts.items()
            if (
                contract in quote_ready_contracts
                and observable.chart_bar.available
                and not observable.quality.dependency_blocking_reasons
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
                "quote_ready_contracts": list(quote_ready_contracts),
                "blocking_reasons": list(all_blocking_reasons),
            },
        )


def build_live_observable_snapshot_v2(
    cache_snapshot: StreamCacheSnapshot | None = None,
    *,
    expected_symbols: Mapping[str, str] | None = None,
    bar_states: Mapping[str, ContractBarState] | None = None,
    dependency_states: Mapping[str, Mapping[str, object]] | None = None,
    clock: object | None = None,
) -> LiveObservableSnapshotV2:
    return LiveObservableSnapshotBuilder(
        expected_symbols=expected_symbols,
        bar_states=bar_states,
        dependency_states=dependency_states,
        clock=clock,
    ).build(cache_snapshot)


def _contract_observable(
    contract: str,
    *,
    record: object | None,
    expected_symbol: str | None,
    generated_at: str,
    provider_reason: str | None,
    cache_blocking_reasons: tuple[str, ...],
    bar_state: ContractBarState | None,
    dependencies: dict[str, DependencyObservableV2],
) -> ContractObservableV2:
    chart_bar = _chart_bar_observable(contract, bar_state)
    dependency_reasons = _dependency_blocking_reasons(contract, dependencies)
    if record is None:
        reasons = _dedupe(
            tuple(reason for reason in (provider_reason,) if reason is not None)
            + cache_blocking_reasons
            + (f"missing_cache_record:{contract}",)
        )
        return ContractObservableV2(
            contract=contract,
            symbol=expected_symbol,
            chart_bar=chart_bar,
            dependencies=dependencies,
            quality=QualityObservableV2(
                chart_bars_ready=chart_bar.available,
                dependency_blocking_reasons=dependency_reasons,
                blocking_reasons=reasons,
            ),
            label=_contract_label(contract),
            sources=_empty_sources(chart_bar=chart_bar, dependencies=dependencies),
        )

    fields = _record_fields(record)
    symbol = _record_symbol(record)
    quote_time = _timestamp_field(fields, *QUOTE_FIELD_ALIASES["quote_time"])
    trade_time = _timestamp_field(fields, *QUOTE_FIELD_ALIASES["trade_time"])
    quote_age_seconds = _age_seconds(quote_time, generated_at=generated_at)
    trade_age_seconds = _age_seconds(trade_time, generated_at=generated_at)
    quote = QuoteObservableV2(
        bid=_number_field(fields, *QUOTE_FIELD_ALIASES["bid"]),
        ask=_number_field(fields, *QUOTE_FIELD_ALIASES["ask"]),
        last=_number_field(fields, *QUOTE_FIELD_ALIASES["last"]),
        bid_size=_number_field(fields, *QUOTE_FIELD_ALIASES["bid_size"]),
        ask_size=_number_field(fields, *QUOTE_FIELD_ALIASES["ask_size"]),
        last_size=_number_field(fields, *QUOTE_FIELD_ALIASES["last_size"]),
        quote_time=quote_time,
        trade_time=trade_time,
        quote_age_seconds=quote_age_seconds,
        trade_age_seconds=trade_age_seconds,
    )
    session = SessionObservableV2(
        open=_number_field(fields, *SESSION_FIELD_ALIASES["open"]),
        high=_number_field(fields, *SESSION_FIELD_ALIASES["high"]),
        low=_number_field(fields, *SESSION_FIELD_ALIASES["low"]),
        prior_close=_number_field(fields, *SESSION_FIELD_ALIASES["prior_close"]),
        net_change=_number_field(fields, *SESSION_FIELD_ALIASES["net_change"]),
        percent_change=_number_field(fields, *SESSION_FIELD_ALIASES["percent_change"]),
        volume=_number_field(fields, *SESSION_FIELD_ALIASES["volume"]),
        security_status=_string_field(fields, *SESSION_FIELD_ALIASES["security_status"]),
        tradable=_bool_field(fields, *SESSION_FIELD_ALIASES["tradable"]),
        active=_bool_field(fields, *SESSION_FIELD_ALIASES["active"]),
    )
    tick_size = contract_tick_size(contract)
    derived = DerivedObservableV2(
        spread_ticks=_spread_ticks(quote.bid, quote.ask, tick_size),
        mid=_mid(quote.bid, quote.ask),
        bar_5m_close=_latest_completed_bar_close(bar_state),
    )
    required_reasons = _required_field_reasons(contract, quote, session)
    missing_fields = _missing_required_fields(quote, session)
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
        chart_bar=chart_bar,
        dependencies=dependencies,
        quality=QualityObservableV2(
            fresh=fresh,
            delayed=None,
            symbol_match=symbol_match,
            required_fields_present=not required_reasons,
            missing_fields=missing_fields,
            chart_bars_ready=chart_bar.available,
            dependency_blocking_reasons=dependency_reasons,
            blocking_reasons=reasons,
        ),
        label=_contract_label(contract),
        sources=_sources_for_observable(quote, session, derived, chart_bar, dependencies),
    )


def _bar_state(contract: str, bar_states: Mapping[str, ContractBarState] | None) -> ContractBarState | None:
    if not bar_states:
        return None
    candidate = bar_states.get(contract)
    return candidate if isinstance(candidate, ContractBarState) else None


def _chart_bar_observable(contract: str, bar_state: ContractBarState | None) -> ChartBarObservableV2:
    if bar_state is None:
        return ChartBarObservableV2(
            state="unavailable",
            available=False,
            fresh=False,
            source="unavailable_until_chart_futures",
            source_status="unavailable",
            blocking_reasons=(f"chart_bars_missing:{contract}",),
        )
    readiness = bar_state.readiness()
    return ChartBarObservableV2(
        state=readiness.state,
        available=readiness.available,
        fresh=readiness.fresh,
        source=readiness.source,
        source_status="derived_with_source" if readiness.available else readiness.state,
        completed_one_minute_available=readiness.completed_one_minute_available,
        completed_five_minute_available=readiness.completed_five_minute_available,
        building=readiness.building,
        completed_one_minute_count=len(bar_state.completed_one_minute_bars),
        completed_five_minute_count=len(bar_state.completed_five_minute_bars),
        latest_completed_one_minute_end_time=readiness.latest_completed_one_minute_end_time,
        latest_completed_five_minute_end_time=readiness.latest_completed_five_minute_end_time,
        blocking_reasons=readiness.blocking_reasons,
    )


def _contract_dependencies(
    contract: str,
    dependency_states: Mapping[str, Mapping[str, object]] | None,
) -> dict[str, DependencyObservableV2]:
    supplied = dependency_states.get(contract, {}) if dependency_states else {}
    dependencies: dict[str, DependencyObservableV2] = {}
    for name in REQUIRED_CONTRACT_DEPENDENCIES.get(contract, ()):
        dependencies[name] = _dependency_from_input(contract, name, supplied.get(name))
    return dependencies


def _dependency_from_input(contract: str, name: str, value: object) -> DependencyObservableV2:
    if isinstance(value, DependencyObservableV2):
        return _normalize_dependency(contract, value)
    if isinstance(value, Mapping):
        status = _dependency_status(value.get("status"))
        source = _source_text(value.get("source"))
        source_status = _source_text(value.get("source_status")) or status
        fresh = value.get("fresh")
        fresh_bool = fresh if isinstance(fresh, bool) else status in {"available", "derived_with_source"}
        dependency = DependencyObservableV2(
            name=name,
            status=status,
            required=True,
            source=source or ("derived" if status.startswith("derived") else "provided"),
            source_status=source_status or status,
            value=_json_scalar(value.get("value")),
            fields=_json_fields(value.get("fields")),
            fresh=fresh_bool,
            blocking_reasons=tuple(str(reason) for reason in value.get("blocking_reasons", ()) if str(reason).strip())
            if isinstance(value.get("blocking_reasons"), (list, tuple))
            else (),
        )
        return _normalize_dependency(contract, dependency)
    return DependencyObservableV2(
        name=name,
        status="unavailable",
        required=True,
        source="unavailable",
        source_status="unavailable",
        fresh=False,
        blocking_reasons=(f"dependency_unavailable:{contract}:{name}",),
    )


def _normalize_dependency(contract: str, dependency: DependencyObservableV2) -> DependencyObservableV2:
    reasons = list(dependency.blocking_reasons)
    if dependency.status == "derived_without_source":
        reasons.append(f"derived_without_source:{contract}:{dependency.name}")
    elif dependency.status == "lockout":
        reasons.append(f"dependency_lockout:{contract}:{dependency.name}")
    elif dependency.status == "unavailable":
        reasons.append(f"dependency_unavailable:{contract}:{dependency.name}")
    elif not dependency.fresh:
        reasons.append(f"dependency_stale:{contract}:{dependency.name}")
    return DependencyObservableV2(
        name=dependency.name,
        status=dependency.status,
        required=dependency.required,
        source=dependency.source,
        source_status=dependency.source_status,
        value=dependency.value,
        fields=dependency.fields,
        fresh=dependency.fresh,
        blocking_reasons=_dedupe(tuple(reasons)),
    )


def _dependency_status(value: object) -> DependencyStatusV2:
    normalized = str(value).strip().lower()
    if normalized in {"available", "lockout", "derived_with_source", "derived_without_source"}:
        return normalized  # type: ignore[return-value]
    return "unavailable"


def _dependency_blocking_reasons(
    contract: str,
    dependencies: Mapping[str, DependencyObservableV2],
) -> tuple[str, ...]:
    reasons: list[str] = []
    for name, dependency in dependencies.items():
        if dependency.required and not dependency.available:
            reasons.extend(dependency.blocking_reasons or (f"dependency_unavailable:{contract}:{name}",))
    return _dedupe(tuple(reasons))


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


def _timestamp_field(fields: Mapping[str, object], *names: str) -> str | None:
    for name in names:
        if name not in fields:
            continue
        timestamp = _timestamp_value(fields[name])
        if timestamp is not None:
            return timestamp
    return None


def _bool_field(fields: Mapping[str, object], *names: str) -> bool | None:
    for name in names:
        value = fields.get(name)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value in {0, 1}:
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "yes", "y", "1"}:
                return True
            if normalized in {"false", "no", "n", "0"}:
                return False
    return None


def _required_field_reasons(
    contract: str,
    quote: QuoteObservableV2,
    session: SessionObservableV2,
) -> tuple[str, ...]:
    missing = _missing_required_fields(quote, session)
    if missing:
        return (f"missing_required_fields:{contract}:{','.join(missing)}",)
    return ()


def _missing_required_fields(
    quote: QuoteObservableV2,
    session: SessionObservableV2,
) -> tuple[str, ...]:
    missing: list[str] = []
    for field_name in REQUIRED_QUOTE_FIELDS:
        if getattr(quote, field_name) is None:
            missing.append(field_name)
    for field_name in REQUIRED_SESSION_FIELDS:
        if getattr(session, field_name) is None:
            missing.append(field_name)
    return tuple(missing)


def _mid(bid: float | int | None, ask: float | int | None) -> float | None:
    if bid is None or ask is None:
        return None
    return (float(bid) + float(ask)) / 2.0


def _spread_ticks(bid: float | int | None, ask: float | int | None, tick_size: float | None) -> float | None:
    if bid is None or ask is None or tick_size is None:
        return None
    return round((float(ask) - float(bid)) / tick_size, 10)


def _latest_completed_bar_close(bar_state: ContractBarState | None) -> float | int | None:
    if bar_state is None or not bar_state.readiness().available or not bar_state.completed_five_minute_bars:
        return None
    latest = bar_state.completed_five_minute_bars[-1]
    return latest.close if latest.completed else None


def _age_seconds(value: str | None, *, generated_at: str) -> float | None:
    if value is None:
        return None
    parsed_value = _parse_timestamp(value)
    parsed_generated_at = _parse_timestamp(generated_at)
    if parsed_value is None or parsed_generated_at is None:
        return None
    return max(0.0, (parsed_generated_at - parsed_value).total_seconds())


def _timestamp_value(value: object) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        numeric = _numeric_timestamp(text)
        if numeric is not None:
            return _isoformat(numeric)
        parsed = _parse_timestamp(text)
        return _isoformat(parsed) if parsed is not None else None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        parsed = _numeric_timestamp(value)
        return _isoformat(parsed) if parsed is not None else None
    return None


def _json_scalar(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return None


def _json_fields(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): _json_scalar(item)
        for key, item in value.items()
        if str(key).strip() and _json_scalar(item) is not None
    }


def _source_text(value: object) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _numeric_timestamp(value: object) -> datetime | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    # Schwab Level One time fields are commonly epoch milliseconds. Accept
    # epoch seconds as well for deterministic fixtures.
    seconds = numeric / 1000.0 if numeric > 10_000_000_000 else numeric
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


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


def _sources_for_observable(
    quote: QuoteObservableV2,
    session: SessionObservableV2,
    derived: DerivedObservableV2,
    chart_bar: ChartBarObservableV2,
    dependencies: Mapping[str, DependencyObservableV2],
) -> dict[str, object]:
    bar_source = "chart_futures_bar_contract" if chart_bar.available else "unavailable_until_chart_futures"
    return {
        "quote": {
            field_name: _observed_source(getattr(quote, field_name))
            for field_name in QuoteObservableV2().to_dict()
        },
        "session": {
            field_name: _observed_source(getattr(session, field_name))
            for field_name in SessionObservableV2().to_dict()
        },
        "derived": {
            "mid": _derived_source(derived.mid),
            "spread_ticks": _derived_source(derived.spread_ticks),
            "distance_to_primary_trigger_ticks": "unavailable_until_trigger_context",
            "bar_5m_close": _bar_derived_source(derived.bar_5m_close, bar_source),
            "bar_5m_close_count_at_or_beyond_level": "unavailable_until_chart_futures",
            "range_expansion_state": "unavailable_until_chart_futures",
            "volume_velocity_state": "unavailable_until_chart_futures",
        },
        "derived_source_status": {
            "bar_5m_close": chart_bar.source_status if derived.bar_5m_close is not None else "unavailable",
            "mid": "derived_from_level_one_quote" if derived.mid is not None else "unavailable",
            "spread_ticks": "derived_from_level_one_quote" if derived.spread_ticks is not None else "unavailable",
        },
        "dependencies": {
            name: {
                "source": dependency.source,
                "source_status": dependency.source_status,
                "status": dependency.status,
            }
            for name, dependency in dependencies.items()
        },
        "quality": {
            "fresh": "stream_cache_record",
            "symbol_match": "expected_symbol_comparison",
            "required_fields_present": "level_one_required_field_check",
            "blocking_reasons": "builder_fail_closed_contract",
        },
    }


def _empty_sources(
    *,
    chart_bar: ChartBarObservableV2 | None = None,
    dependencies: Mapping[str, DependencyObservableV2] | None = None,
) -> dict[str, object]:
    return {
        "quote": {field_name: "unavailable" for field_name in QuoteObservableV2().to_dict()},
        "session": {field_name: "unavailable" for field_name in SessionObservableV2().to_dict()},
        "derived": {
            "mid": "unavailable",
            "spread_ticks": "unavailable",
            "distance_to_primary_trigger_ticks": "unavailable_until_trigger_context",
            "bar_5m_close": "unavailable_until_chart_futures",
            "bar_5m_close_count_at_or_beyond_level": "unavailable_until_chart_futures",
            "range_expansion_state": "unavailable_until_chart_futures",
            "volume_velocity_state": "unavailable_until_chart_futures",
        },
        "derived_source_status": {
            "bar_5m_close": chart_bar.source_status if chart_bar is not None else "unavailable",
            "mid": "unavailable",
            "spread_ticks": "unavailable",
        },
        "dependencies": {
            name: {
                "source": dependency.source,
                "source_status": dependency.source_status,
                "status": dependency.status,
            }
            for name, dependency in (dependencies or {}).items()
        },
        "quality": {
            "fresh": "stream_cache_record_missing",
            "symbol_match": "expected_symbol_comparison",
            "required_fields_present": "level_one_required_field_check",
            "blocking_reasons": "builder_fail_closed_contract",
        },
    }


def _observed_source(value: object) -> str:
    return "stream_cache_level_one" if value is not None else "unavailable"


def _derived_source(value: object) -> str:
    return "derived_from_level_one_quote" if value is not None else "unavailable"


def _bar_derived_source(value: object, bar_source: str) -> str:
    return bar_source if value is not None else "unavailable_until_chart_futures"
