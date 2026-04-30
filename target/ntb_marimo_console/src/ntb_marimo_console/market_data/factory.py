from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ntb_marimo_console.adapters.schwab_futures_market_data import SchwabFuturesMarketDataAdapter

from .config import FuturesQuoteServiceConfig
from .futures_quote_service import (
    FixtureFuturesQuoteProvider,
    FuturesQuote,
    FuturesQuoteProvider,
    FuturesQuoteService,
    NullFuturesQuoteProvider,
    SchwabAdapterFuturesQuoteProvider,
)


class FuturesQuoteProviderFactoryError(RuntimeError):
    pass


FixtureQuoteFactory = Callable[[FuturesQuoteServiceConfig], FuturesQuote | None]
SchwabAdapterFactory = Callable[[FuturesQuoteServiceConfig], SchwabFuturesMarketDataAdapter]


def build_futures_quote_provider(
    config: FuturesQuoteServiceConfig,
    *,
    fixture_quote: FuturesQuote | None = None,
    fixture_quote_factory: FixtureQuoteFactory | None = None,
    schwab_adapter: SchwabFuturesMarketDataAdapter | None = None,
    schwab_adapter_factory: SchwabAdapterFactory | None = None,
) -> FuturesQuoteProvider:
    if config.provider == "disabled" or config.failure_reason is not None:
        return NullFuturesQuoteProvider()

    if config.provider == "fixture":
        quote = fixture_quote
        if quote is None and fixture_quote_factory is not None:
            quote = fixture_quote_factory(config)
        if quote is None:
            raise FuturesQuoteProviderFactoryError("fixture_quote_required")
        return FixtureFuturesQuoteProvider(quote=quote)

    if config.provider == "schwab":
        adapter = schwab_adapter
        if adapter is None and schwab_adapter_factory is not None:
            adapter = schwab_adapter_factory(config)
        if adapter is None:
            raise FuturesQuoteProviderFactoryError("schwab_adapter_required")
        return SchwabAdapterFuturesQuoteProvider(
            adapter=adapter,
            token_path=config.token_path,
            field_ids=config.field_ids,
            timeout_seconds=config.timeout_seconds,
        )

    raise FuturesQuoteProviderFactoryError("unsupported_provider")


def build_futures_quote_service(
    config: FuturesQuoteServiceConfig,
    *,
    fixture_quote: FuturesQuote | None = None,
    fixture_quote_factory: FixtureQuoteFactory | None = None,
    schwab_adapter: SchwabFuturesMarketDataAdapter | None = None,
    schwab_adapter_factory: SchwabAdapterFactory | None = None,
    clock: object | None = None,
) -> FuturesQuoteService:
    provider = build_futures_quote_provider(
        config,
        fixture_quote=fixture_quote,
        fixture_quote_factory=fixture_quote_factory,
        schwab_adapter=schwab_adapter,
        schwab_adapter_factory=schwab_adapter_factory,
    )
    return FuturesQuoteService(
        provider,
        max_quote_age_seconds=config.max_quote_age_seconds,
        clock=clock,
    )
