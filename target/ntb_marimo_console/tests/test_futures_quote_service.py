from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from ntb_marimo_console.adapters.schwab_futures_market_data import (
    SchwabFuturesMarketDataResult,
    SchwabFuturesQuoteSnapshot,
)
from ntb_marimo_console.market_data.futures_quote_service import (
    FixtureFuturesQuoteProvider,
    FuturesQuote,
    FuturesQuoteProviderError,
    FuturesQuoteService,
    NullFuturesQuoteProvider,
    SchwabAdapterFuturesQuoteProvider,
)


NOW = datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc)


class RaisingProvider:
    provider_name = "raising"
    enabled = True

    def fetch_quote(self, requested_symbol: str) -> FuturesQuote | None:
        raise FuturesQuoteProviderError(
            "failed access_token=secret-access-token customerId=raw-customer "
            "wss://streamer-api.schwab.com/ws?credential=hidden"
        )


class FakeSchwabAdapter:
    def __init__(self, result: SchwabFuturesMarketDataResult) -> None:
        self.result = result
        self.requests: list[object] = []

    def fetch_once(self, request: object) -> SchwabFuturesMarketDataResult:
        self.requests.append(request)
        return self.result


def quote(*, symbol: str = "/ESM26", received_at: str = "2026-04-30T11:59:58+00:00") -> FuturesQuote:
    return FuturesQuote(
        symbol=symbol,
        bid_price=7175,
        ask_price=7175.5,
        last_price=7175.25,
        bid_size=19,
        ask_size=14,
        received_at=received_at,
    )


def service(provider: object, *, max_quote_age_seconds: float = 5.0) -> FuturesQuoteService:
    return FuturesQuoteService(
        provider,
        max_quote_age_seconds=max_quote_age_seconds,
        clock=lambda: NOW,
    )


def test_disabled_provider_returns_disabled_and_no_quote() -> None:
    result = service(NullFuturesQuoteProvider()).get_quote("/ESM26")

    assert result.status == "disabled"
    assert result.provider_name == "disabled"
    assert result.requested_symbol == "/ESM26"
    assert result.quote is None
    assert result.quote_age_seconds is None
    assert result.failure_reason == "provider_disabled"


def test_fixture_provider_returns_connected_with_safe_quote_fields() -> None:
    result = service(FixtureFuturesQuoteProvider(quote())).get_quote("/ESM26")

    assert result.status == "connected"
    assert result.provider_name == "fixture"
    assert result.quote is not None
    assert result.quote.symbol == "/ESM26"
    assert result.quote.bid_price == 7175
    assert result.quote.ask_price == 7175.5
    assert result.quote.last_price == 7175.25
    assert result.quote.bid_size == 19
    assert result.quote.ask_size == 14
    assert result.quote.received_at == "2026-04-30T11:59:58+00:00"
    assert result.quote_age_seconds == 2.0
    assert result.failure_reason is None


def test_fixture_provider_stale_quote_returns_stale() -> None:
    result = service(
        FixtureFuturesQuoteProvider(quote(received_at="2026-04-30T11:59:00+00:00")),
        max_quote_age_seconds=5.0,
    ).get_quote("/ESM26")

    assert result.status == "stale"
    assert result.quote is not None
    assert result.quote_age_seconds == 60.0
    assert result.failure_reason == "quote_stale"


def test_symbol_mismatch_fails_closed() -> None:
    result = service(FixtureFuturesQuoteProvider(quote(symbol="/NQM26"))).get_quote("/ESM26")

    assert result.status == "blocked"
    assert result.quote is None
    assert result.failure_reason == "quote_symbol_mismatch"


def test_provider_exception_returns_sanitized_error() -> None:
    result = service(RaisingProvider()).get_quote("/ESM26")

    assert result.status == "error"
    assert result.quote is None
    assert result.failure_reason is not None
    assert "access_token=[REDACTED]" in result.failure_reason
    assert "customer=[REDACTED]" in result.failure_reason
    assert "wss://" not in result.failure_reason
    assert "secret-access-token" not in result.failure_reason
    assert "raw-customer" not in result.failure_reason


def test_schwab_adapter_provider_maps_success_to_connected_quote_state() -> None:
    adapter = FakeSchwabAdapter(
        SchwabFuturesMarketDataResult(
            status="success",
            symbol="/ESM26",
            field_ids=(0, 1, 2, 3, 4, 5),
            streamer_socket_host="streamer-api.schwab.com",
            login_response_code=0,
            subscription_response_code=0,
            market_data_received=True,
            last_quote_snapshot=SchwabFuturesQuoteSnapshot(
                raw_fields=((0, "/ESM26"), (1, 7175), (2, 7175.5), (3, 7175.25), (4, 19), (5, 14)),
                symbol="/ESM26",
                bid_price=7175,
                ask_price=7175.5,
                last_price=7175.25,
                bid_size=19,
                ask_size=14,
            ),
            received_at="2026-04-30T11:59:58+00:00",
            failure_reason=None,
        )
    )
    provider = SchwabAdapterFuturesQuoteProvider(adapter=adapter)

    result = service(provider).get_quote("/ESM26")

    assert result.status == "connected"
    assert result.provider_name == "schwab"
    assert result.quote is not None
    assert result.quote.bid_price == 7175
    assert result.quote.ask_price == 7175.5
    assert result.quote.last_price == 7175.25
    assert len(adapter.requests) == 1


def test_schwab_adapter_provider_maps_no_data_failure_without_unsafe_fields() -> None:
    adapter = FakeSchwabAdapter(
        SchwabFuturesMarketDataResult(
            status="timeout",
            symbol="/ESM26",
            field_ids=(0, 1, 2),
            streamer_socket_host="streamer-api.schwab.com",
            login_response_code=0,
            subscription_response_code=0,
            market_data_received=False,
            last_quote_snapshot=None,
            received_at=None,
            failure_reason="market_data_not_received",
        )
    )
    provider = SchwabAdapterFuturesQuoteProvider(adapter=adapter, field_ids=(0, 1, 2))

    result = service(provider).get_quote("/ESM26")

    assert result.status == "no_data"
    assert result.quote is None
    assert result.failure_reason == "provider_returned_no_quote"
    assert "streamer-api.schwab.com" not in repr(result)
    assert "access_token" not in repr(result)
    assert "refresh_token" not in repr(result)


def test_service_result_and_quote_are_immutable() -> None:
    result = service(FixtureFuturesQuoteProvider(quote())).get_quote("/ESM26")

    with pytest.raises(FrozenInstanceError):
        result.status = "error"  # type: ignore[misc]
    assert result.quote is not None
    with pytest.raises(FrozenInstanceError):
        result.quote.bid_price = 1  # type: ignore[misc]


def test_malformed_quote_values_fail_closed() -> None:
    malformed = FuturesQuote(
        symbol="/ESM26",
        bid_price="7175",  # type: ignore[arg-type]
        ask_price=7175.5,
        last_price=7175.25,
        bid_size=19,
        ask_size=14,
        received_at="2026-04-30T11:59:58+00:00",
    )

    result = service(FixtureFuturesQuoteProvider(malformed)).get_quote("/ESM26")

    assert result.status == "error"
    assert result.quote is None
    assert result.failure_reason == "malformed_quote_values"
