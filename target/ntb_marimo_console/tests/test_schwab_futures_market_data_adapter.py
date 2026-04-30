from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from ntb_marimo_console.adapters.schwab_futures_market_data import (
    DEFAULT_LEVELONE_FUTURES_FIELD_IDS,
    SchwabAdapterTimeoutError,
    SchwabFuturesMarketDataAdapter,
    SchwabFuturesMarketDataRequest,
    SchwabLevelOneFuturesSubscription,
    SchwabStreamerMetadata,
)


SAFE_SOCKET_URL = "wss://streamer-api.schwab.com/ws?credential=hidden"


class FakeUserPreferenceProvider:
    def __init__(self, metadata: SchwabStreamerMetadata | None = None) -> None:
        self.metadata = metadata or SchwabStreamerMetadata(
            streamer_socket_url=SAFE_SOCKET_URL,
            schwab_client_customer_id="raw-customer-id",
            schwab_client_correl_id="raw-correl-id",
            schwab_client_channel="raw-channel",
            schwab_client_function_id="raw-function",
        )
        self.loaded_paths: list[Path] = []

    def load_streamer_metadata(self, token_path: Path) -> SchwabStreamerMetadata:
        self.loaded_paths.append(token_path)
        return self.metadata


class FakeStreamerClient:
    def __init__(
        self,
        *,
        login_code: int = 0,
        subscription_code: int = 0,
        market_data: dict[int | str, object] | None = None,
        timeout: bool = False,
    ) -> None:
        self.login_code = login_code
        self.subscription_code = subscription_code
        self.market_data = market_data
        self.timeout = timeout
        self.calls: list[str] = []
        self.subscribed_symbol: str | None = None
        self.subscribed_field_ids: tuple[int, ...] | None = None

    def login(self, metadata: SchwabStreamerMetadata, *, timeout_seconds: float) -> int:
        self.calls.append("login")
        if self.timeout:
            raise SchwabAdapterTimeoutError("timeout")
        return self.login_code

    def subscribe_levelone_futures(
        self,
        metadata: SchwabStreamerMetadata,
        *,
        symbol: str,
        field_ids: tuple[int, ...],
        timeout_seconds: float,
    ) -> SchwabLevelOneFuturesSubscription:
        self.calls.append("subscribe")
        self.subscribed_symbol = symbol
        self.subscribed_field_ids = field_ids
        if self.timeout:
            raise SchwabAdapterTimeoutError("timeout")
        return SchwabLevelOneFuturesSubscription(
            response_code=self.subscription_code,
            market_data=self.market_data,
        )


@pytest.fixture
def target_root(tmp_path: Path) -> Path:
    root = tmp_path / "target" / "ntb_marimo_console"
    (root / ".state" / "schwab").mkdir(parents=True)
    return root


def adapter(
    target_root: Path,
    *,
    provider: FakeUserPreferenceProvider | None = None,
    client: FakeStreamerClient | None = None,
) -> SchwabFuturesMarketDataAdapter:
    return SchwabFuturesMarketDataAdapter(
        user_preference_provider=provider or FakeUserPreferenceProvider(),
        streamer_client=client or FakeStreamerClient(),
        target_root=target_root,
        clock=lambda: "2026-04-30T12:00:00+00:00",
    )


def request(**overrides: object) -> SchwabFuturesMarketDataRequest:
    values = {
        "symbol": "/ESM26",
        "token_path": ".state/schwab/token.json",
    }
    values.update(overrides)
    return SchwabFuturesMarketDataRequest(**values)


def test_happy_path_success_with_default_field_ids(target_root: Path) -> None:
    client = FakeStreamerClient(
        market_data={
            0: "/ESM26",
            1: 7175,
            2: 7175.5,
            3: 7175.25,
            4: 19,
            5: 14,
        }
    )

    result = adapter(target_root, client=client).fetch_once(request())

    assert result.status == "success"
    assert result.symbol == "/ESM26"
    assert result.field_ids == DEFAULT_LEVELONE_FUTURES_FIELD_IDS
    assert result.streamer_socket_host == "streamer-api.schwab.com"
    assert result.login_response_code == 0
    assert result.subscription_response_code == 0
    assert result.market_data_received is True
    assert result.received_at == "2026-04-30T12:00:00+00:00"
    assert result.failure_reason is None
    assert result.last_quote_snapshot is not None
    assert result.last_quote_snapshot.bid_price == 7175
    assert result.last_quote_snapshot.ask_price == 7175.5
    assert result.last_quote_snapshot.last_price == 7175.25
    assert result.last_quote_snapshot.bid_size == 19
    assert result.last_quote_snapshot.ask_size == 14
    assert client.calls == ["login", "subscribe"]
    with pytest.raises(FrozenInstanceError):
        result.status = "mutated"  # type: ignore[misc]


def test_success_with_custom_field_ids_preserves_effective_field_set(target_root: Path) -> None:
    client = FakeStreamerClient(market_data={0: "/ESM26", 1: 7175, 8: 12345})

    result = adapter(target_root, client=client).fetch_once(
        request(field_ids=(0, 1, 8))
    )

    assert result.status == "success"
    assert result.field_ids == (0, 1, 8)
    assert client.subscribed_field_ids == (0, 1, 8)
    assert client.subscribed_symbol == "/ESM26"


def test_login_failure_fails_closed_before_subscription(target_root: Path) -> None:
    client = FakeStreamerClient(login_code=7, market_data={0: "/ESM26"})

    result = adapter(target_root, client=client).fetch_once(request())

    assert result.status == "login_failed"
    assert result.login_response_code == 7
    assert result.subscription_response_code is None
    assert result.market_data_received is False
    assert result.failure_reason == "login_response_code_nonzero"
    assert client.calls == ["login"]


def test_subscription_failure_fails_closed(target_root: Path) -> None:
    client = FakeStreamerClient(subscription_code=9, market_data={0: "/ESM26"})

    result = adapter(target_root, client=client).fetch_once(request())

    assert result.status == "subscription_failed"
    assert result.login_response_code == 0
    assert result.subscription_response_code == 9
    assert result.market_data_received is False
    assert result.failure_reason == "subscription_response_code_nonzero"


def test_timeout_after_successful_login_and_subscription_has_no_received_at(target_root: Path) -> None:
    client = FakeStreamerClient(subscription_code=0, market_data=None)

    result = adapter(target_root, client=client).fetch_once(request())

    assert result.status == "timeout"
    assert result.login_response_code == 0
    assert result.subscription_response_code == 0
    assert result.market_data_received is False
    assert result.received_at is None
    assert result.last_quote_snapshot is None
    assert result.failure_reason == "market_data_not_received"


def test_sanitization_guard_exposes_host_only(target_root: Path) -> None:
    client = FakeStreamerClient(market_data={0: "/ESM26", 1: 7175})

    result = adapter(target_root, client=client).fetch_once(request())

    rendered = repr(result)
    assert result.streamer_socket_host == "streamer-api.schwab.com"
    assert "wss://streamer-api.schwab.com/ws?credential=hidden" not in rendered
    assert "raw-customer-id" not in rendered
    assert "raw-correl-id" not in rendered


def test_token_path_guard_rejects_paths_outside_target_state(target_root: Path) -> None:
    provider = FakeUserPreferenceProvider()
    client = FakeStreamerClient(market_data={0: "/ESM26"})

    result = adapter(target_root, provider=provider, client=client).fetch_once(
        request(token_path="../token.json")
    )

    assert result.status == "error"
    assert result.market_data_received is False
    assert result.failure_reason == "token_path_outside_target_state"
    assert provider.loaded_paths == []
    assert client.calls == []


def test_missing_or_malformed_quote_fields_degrade_safely(target_root: Path) -> None:
    client = FakeStreamerClient(market_data={0: "/ESM26", 1: 7175, "8": 1000, "bad": "ignored"})

    result = adapter(target_root, client=client).fetch_once(request())

    assert result.status == "success"
    assert result.last_quote_snapshot is not None
    assert result.last_quote_snapshot.bid_price == 7175
    assert result.last_quote_snapshot.ask_price is None
    assert result.last_quote_snapshot.last_price is None
    assert result.last_quote_snapshot.bid_size is None
    assert result.last_quote_snapshot.ask_size is None
    assert dict(result.last_quote_snapshot.raw_fields) == {0: "/ESM26", 1: 7175, 8: 1000}
