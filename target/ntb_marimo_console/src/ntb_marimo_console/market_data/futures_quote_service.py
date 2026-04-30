from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Protocol

from ntb_marimo_console.adapters.schwab_futures_market_data import (
    DEFAULT_LEVELONE_FUTURES_FIELD_IDS,
    SchwabFuturesMarketDataAdapter,
    SchwabFuturesMarketDataRequest,
    SchwabFuturesMarketDataResult,
)


FuturesQuoteStatus = Literal["disabled", "connected", "no_data", "stale", "error", "blocked"]


@dataclass(frozen=True)
class FuturesQuote:
    symbol: str
    bid_price: float | int | None
    ask_price: float | int | None
    last_price: float | int | None
    bid_size: float | int | None
    ask_size: float | int | None
    received_at: str


@dataclass(frozen=True)
class FuturesQuoteServiceResult:
    status: FuturesQuoteStatus
    provider_name: str
    requested_symbol: str
    quote: FuturesQuote | None
    quote_age_seconds: float | None
    failure_reason: str | None


class FuturesQuoteProvider(Protocol):
    provider_name: str
    enabled: bool

    def fetch_quote(self, requested_symbol: str) -> FuturesQuote | None: ...


class FuturesQuoteProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class NullFuturesQuoteProvider:
    provider_name: str = "disabled"
    enabled: bool = False

    def fetch_quote(self, requested_symbol: str) -> FuturesQuote | None:
        return None


@dataclass(frozen=True)
class FixtureFuturesQuoteProvider:
    quote: FuturesQuote | None
    provider_name: str = "fixture"
    enabled: bool = True

    def fetch_quote(self, requested_symbol: str) -> FuturesQuote | None:
        return self.quote


@dataclass(frozen=True)
class SchwabAdapterFuturesQuoteProvider:
    adapter: SchwabFuturesMarketDataAdapter
    token_path: Path | str = ".state/schwab/token.json"
    field_ids: tuple[int, ...] = DEFAULT_LEVELONE_FUTURES_FIELD_IDS
    timeout_seconds: float = 10.0
    provider_name: str = "schwab"
    enabled: bool = True

    def fetch_quote(self, requested_symbol: str) -> FuturesQuote | None:
        result = self.adapter.fetch_once(
            SchwabFuturesMarketDataRequest(
                symbol=requested_symbol,
                token_path=self.token_path,
                field_ids=self.field_ids,
                timeout_seconds=self.timeout_seconds,
            )
        )
        return _quote_from_schwab_result(result)


class FuturesQuoteService:
    def __init__(
        self,
        provider: FuturesQuoteProvider,
        *,
        max_quote_age_seconds: float = 5.0,
        clock: object | None = None,
    ) -> None:
        self._provider = provider
        self._max_quote_age_seconds = max_quote_age_seconds
        self._clock = clock or _utc_now

    def get_quote(self, requested_symbol: str) -> FuturesQuoteServiceResult:
        provider_name = _safe_provider_name(getattr(self._provider, "provider_name", "unknown"))
        symbol = requested_symbol.strip().upper()
        if not getattr(self._provider, "enabled", False):
            return FuturesQuoteServiceResult(
                status="disabled",
                provider_name=provider_name,
                requested_symbol=symbol,
                quote=None,
                quote_age_seconds=None,
                failure_reason="provider_disabled",
            )
        try:
            quote = self._provider.fetch_quote(symbol)
        except Exception as exc:
            return FuturesQuoteServiceResult(
                status="error",
                provider_name=provider_name,
                requested_symbol=symbol,
                quote=None,
                quote_age_seconds=None,
                failure_reason=_sanitize_failure_reason(exc),
            )
        if quote is None:
            return FuturesQuoteServiceResult(
                status="no_data",
                provider_name=provider_name,
                requested_symbol=symbol,
                quote=None,
                quote_age_seconds=None,
                failure_reason="provider_returned_no_quote",
            )
        if quote.symbol.strip().upper() != symbol:
            return FuturesQuoteServiceResult(
                status="blocked",
                provider_name=provider_name,
                requested_symbol=symbol,
                quote=None,
                quote_age_seconds=None,
                failure_reason="quote_symbol_mismatch",
            )
        if not _quote_values_are_valid(quote):
            return FuturesQuoteServiceResult(
                status="error",
                provider_name=provider_name,
                requested_symbol=symbol,
                quote=None,
                quote_age_seconds=None,
                failure_reason="malformed_quote_values",
            )
        age_seconds = _quote_age_seconds(quote.received_at, now=self._clock())
        if age_seconds is None:
            return FuturesQuoteServiceResult(
                status="error",
                provider_name=provider_name,
                requested_symbol=symbol,
                quote=None,
                quote_age_seconds=None,
                failure_reason="malformed_quote_timestamp",
            )
        if age_seconds > self._max_quote_age_seconds:
            return FuturesQuoteServiceResult(
                status="stale",
                provider_name=provider_name,
                requested_symbol=symbol,
                quote=quote,
                quote_age_seconds=age_seconds,
                failure_reason="quote_stale",
            )
        return FuturesQuoteServiceResult(
            status="connected",
            provider_name=provider_name,
            requested_symbol=symbol,
            quote=quote,
            quote_age_seconds=age_seconds,
            failure_reason=None,
        )


def _quote_from_schwab_result(result: SchwabFuturesMarketDataResult) -> FuturesQuote | None:
    snapshot = result.last_quote_snapshot
    if result.status != "success" or not result.market_data_received or snapshot is None or result.received_at is None:
        return None
    return FuturesQuote(
        symbol=snapshot.symbol or result.symbol,
        bid_price=snapshot.bid_price,
        ask_price=snapshot.ask_price,
        last_price=snapshot.last_price,
        bid_size=snapshot.bid_size,
        ask_size=snapshot.ask_size,
        received_at=result.received_at,
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _quote_age_seconds(received_at: str, *, now: datetime) -> float | None:
    parsed = _parse_timestamp(received_at)
    if parsed is None:
        return None
    current = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    return max(0.0, (current.astimezone(timezone.utc) - parsed).total_seconds())


def _quote_values_are_valid(quote: FuturesQuote) -> bool:
    values = (quote.bid_price, quote.ask_price, quote.last_price, quote.bid_size, quote.ask_size)
    return all(value is None or _is_number(value) for value in values)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _safe_provider_name(value: object) -> str:
    text = str(value).strip() or "unknown"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", text)[:64]


def _sanitize_failure_reason(value: object) -> str:
    text = f"{value.__class__.__name__}: {value}"
    text = re.sub(r"(?i)(access_token|refresh_token|authorization|secret)=([^&\s,}]+)", r"\1=[REDACTED]", text)
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"(?i)(customer|correl|account)[A-Za-z_]*=([^&\s,}]+)", r"\1=[REDACTED]", text)
    text = re.sub(r"wss?://[^\s,}]+", "[REDACTED_URL]", text)
    text = re.sub(r"\b[A-Za-z0-9._~+/=-]{24,}\b", "[REDACTED_TOKEN_LIKE]", text)
    return text[:240]
