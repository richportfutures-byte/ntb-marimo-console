from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from ntb_marimo_console.adapters.schwab_futures_market_data import (
    DEFAULT_LEVELONE_FUTURES_FIELD_IDS,
    SchwabFuturesMarketDataResult,
    SchwabFuturesQuoteSnapshot,
)
from ntb_marimo_console.market_data.config import FuturesQuoteServiceConfig
from ntb_marimo_console.market_data.factory import (
    FuturesQuoteProviderFactoryError,
    build_futures_quote_provider,
    build_futures_quote_service,
)
from ntb_marimo_console.market_data.futures_quote_service import (
    FixtureFuturesQuoteProvider,
    FuturesQuote,
    FuturesQuoteService,
    NullFuturesQuoteProvider,
    SchwabAdapterFuturesQuoteProvider,
)


NOW = datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc)


class FakeSchwabAdapter:
    def __init__(self, result: SchwabFuturesMarketDataResult) -> None:
        self.result = result
        self.requests: list[object] = []

    def fetch_once(self, request: object) -> SchwabFuturesMarketDataResult:
        self.requests.append(request)
        return self.result


@pytest.fixture
def target_root(tmp_path: Path) -> Path:
    root = tmp_path / "target" / "ntb_marimo_console"
    (root / ".state" / "schwab").mkdir(parents=True)
    return root


def config(
    target_root: Path,
    *,
    provider: str,
    failure_reason: str | None = None,
) -> FuturesQuoteServiceConfig:
    return FuturesQuoteServiceConfig(
        provider=provider,  # type: ignore[arg-type]
        symbol="/ESM26",
        field_ids=DEFAULT_LEVELONE_FUTURES_FIELD_IDS,
        max_quote_age_seconds=5.0,
        token_path=(target_root / ".state" / "schwab" / "token.json").resolve(),
        timeout_seconds=10.0,
        failure_reason=failure_reason,
    )


def quote() -> FuturesQuote:
    return FuturesQuote(
        symbol="/ESM26",
        bid_price=7175,
        ask_price=7175.5,
        last_price=7175.25,
        bid_size=19,
        ask_size=14,
        received_at="2026-04-30T11:59:58+00:00",
    )


def adapter_result() -> SchwabFuturesMarketDataResult:
    return SchwabFuturesMarketDataResult(
        status="success",
        symbol="/ESM26",
        field_ids=DEFAULT_LEVELONE_FUTURES_FIELD_IDS,
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


def test_disabled_config_returns_null_provider(target_root: Path) -> None:
    provider = build_futures_quote_provider(config(target_root, provider="disabled"))

    assert isinstance(provider, NullFuturesQuoteProvider)


def test_failure_reason_forces_null_provider(target_root: Path) -> None:
    fixture_provider = build_futures_quote_provider(
        config(target_root, provider="fixture", failure_reason="invalid_field_ids"),
        fixture_quote=quote(),
    )
    schwab_provider = build_futures_quote_provider(
        config(target_root, provider="schwab", failure_reason="invalid_timeout_seconds"),
        schwab_adapter=FakeSchwabAdapter(adapter_result()),
    )

    assert isinstance(fixture_provider, NullFuturesQuoteProvider)
    assert isinstance(schwab_provider, NullFuturesQuoteProvider)


def test_fixture_config_uses_explicit_fixture_quote(target_root: Path) -> None:
    provider = build_futures_quote_provider(
        config(target_root, provider="fixture"),
        fixture_quote=quote(),
    )

    assert isinstance(provider, FixtureFuturesQuoteProvider)
    assert provider.fetch_quote("/ESM26") == quote()


def test_fixture_config_uses_explicit_fixture_quote_factory(target_root: Path) -> None:
    seen_configs: list[FuturesQuoteServiceConfig] = []

    provider = build_futures_quote_provider(
        config(target_root, provider="fixture"),
        fixture_quote_factory=lambda cfg: seen_configs.append(cfg) or quote(),
    )

    assert isinstance(provider, FixtureFuturesQuoteProvider)
    assert seen_configs and seen_configs[0].provider == "fixture"
    assert provider.fetch_quote("/ESM26") == quote()


def test_fixture_config_without_injection_raises_controlled_error(target_root: Path) -> None:
    with pytest.raises(FuturesQuoteProviderFactoryError, match="fixture_quote_required"):
        build_futures_quote_provider(config(target_root, provider="fixture"))


def test_schwab_config_uses_explicit_prebuilt_adapter(target_root: Path) -> None:
    adapter = FakeSchwabAdapter(adapter_result())

    provider = build_futures_quote_provider(
        config(target_root, provider="schwab"),
        schwab_adapter=adapter,
    )

    assert isinstance(provider, SchwabAdapterFuturesQuoteProvider)
    assert provider.token_path == (target_root / ".state" / "schwab" / "token.json").resolve()
    assert provider.field_ids == DEFAULT_LEVELONE_FUTURES_FIELD_IDS
    assert provider.fetch_quote("/ESM26") is not None
    assert len(adapter.requests) == 1


def test_schwab_config_uses_explicit_adapter_factory(target_root: Path) -> None:
    seen_configs: list[FuturesQuoteServiceConfig] = []
    adapter = FakeSchwabAdapter(adapter_result())

    provider = build_futures_quote_provider(
        config(target_root, provider="schwab"),
        schwab_adapter_factory=lambda cfg: seen_configs.append(cfg) or adapter,
    )

    assert isinstance(provider, SchwabAdapterFuturesQuoteProvider)
    assert seen_configs and seen_configs[0].provider == "schwab"
    assert provider.fetch_quote("/ESM26") is not None
    assert len(adapter.requests) == 1


def test_schwab_config_without_adapter_injection_raises_controlled_error(target_root: Path) -> None:
    with pytest.raises(FuturesQuoteProviderFactoryError, match="schwab_adapter_required"):
        build_futures_quote_provider(config(target_root, provider="schwab"))


def test_build_futures_quote_service_wraps_selected_provider(target_root: Path) -> None:
    service = build_futures_quote_service(
        config(target_root, provider="fixture"),
        fixture_quote=quote(),
        clock=lambda: NOW,
    )

    assert isinstance(service, FuturesQuoteService)
    result = service.get_quote("/ESM26")
    assert result.status == "connected"
    assert result.provider_name == "fixture"
    assert result.quote_age_seconds == 2.0


def test_factory_module_does_not_import_live_smoke_probe() -> None:
    factory_source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "ntb_marimo_console"
        / "market_data"
        / "factory.py"
    ).read_text(encoding="utf-8")

    assert "probe_schwab_futures_market_data_adapter" not in factory_source
    assert ".env" not in factory_source
    assert "os.environ" not in factory_source

