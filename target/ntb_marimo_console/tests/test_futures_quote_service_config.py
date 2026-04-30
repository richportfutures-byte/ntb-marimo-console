from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from ntb_marimo_console.adapters.schwab_futures_market_data import DEFAULT_LEVELONE_FUTURES_FIELD_IDS
from ntb_marimo_console.market_data.config import (
    DEFAULT_MARKET_DATA_SYMBOL,
    DEFAULT_MAX_QUOTE_AGE_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    FuturesQuoteServiceConfig,
    resolve_futures_quote_service_config,
)


@pytest.fixture
def target_root(tmp_path: Path) -> Path:
    root = tmp_path / "target" / "ntb_marimo_console"
    (root / ".state" / "schwab").mkdir(parents=True)
    return root


def test_empty_config_defaults_to_disabled_provider(target_root: Path) -> None:
    config = resolve_futures_quote_service_config({}, target_root=target_root)

    assert config.provider == "disabled"
    assert config.symbol == ""
    assert config.field_ids == DEFAULT_LEVELONE_FUTURES_FIELD_IDS
    assert config.max_quote_age_seconds == DEFAULT_MAX_QUOTE_AGE_SECONDS
    assert config.timeout_seconds == DEFAULT_TIMEOUT_SECONDS
    assert config.failure_reason is None


def test_fixture_provider_resolves_safe_defaults(target_root: Path) -> None:
    config = resolve_futures_quote_service_config(
        {"NTB_MARKET_DATA_PROVIDER": "fixture"},
        target_root=target_root,
    )

    assert config.provider == "fixture"
    assert config.symbol == DEFAULT_MARKET_DATA_SYMBOL
    assert config.field_ids == DEFAULT_LEVELONE_FUTURES_FIELD_IDS
    assert config.failure_reason is None


def test_schwab_provider_resolves_defaults_and_state_token_path(target_root: Path) -> None:
    config = resolve_futures_quote_service_config(
        {"NTB_MARKET_DATA_PROVIDER": "schwab"},
        target_root=target_root,
    )

    assert config.provider == "schwab"
    assert config.symbol == DEFAULT_MARKET_DATA_SYMBOL
    assert config.field_ids == DEFAULT_LEVELONE_FUTURES_FIELD_IDS
    assert config.timeout_seconds == DEFAULT_TIMEOUT_SECONDS
    assert config.token_path == (target_root / ".state" / "schwab" / "token.json").resolve()
    assert config.failure_reason is None


def test_invalid_provider_fails_closed(target_root: Path) -> None:
    config = resolve_futures_quote_service_config(
        {"NTB_MARKET_DATA_PROVIDER": "live_wire"},
        target_root=target_root,
    )

    assert config.provider == "disabled"
    assert config.failure_reason == "invalid_provider"


def test_token_path_outside_state_fails_closed(target_root: Path) -> None:
    config = resolve_futures_quote_service_config(
        {
            "NTB_MARKET_DATA_PROVIDER": "schwab",
            "SCHWAB_TOKEN_PATH": "../token.json",
        },
        target_root=target_root,
    )

    assert config.provider == "disabled"
    assert config.failure_reason == "token_path_outside_target_state"


def test_malformed_field_ids_fail_closed(target_root: Path) -> None:
    config = resolve_futures_quote_service_config(
        {
            "NTB_MARKET_DATA_PROVIDER": "fixture",
            "NTB_MARKET_DATA_FIELD_IDS": "0,1,bad,5",
        },
        target_root=target_root,
    )

    assert config.provider == "disabled"
    assert config.failure_reason == "invalid_field_ids"


def test_shell_style_field_ids_parse_correctly(target_root: Path) -> None:
    config = resolve_futures_quote_service_config(
        {
            "NTB_MARKET_DATA_PROVIDER": "fixture",
            "NTB_MARKET_DATA_FIELD_IDS": "0,1,2,3,4,5",
        },
        target_root=target_root,
    )

    assert config.provider == "fixture"
    assert config.field_ids == (0, 1, 2, 3, 4, 5)


def test_invalid_max_quote_age_fails_closed(target_root: Path) -> None:
    config = resolve_futures_quote_service_config(
        {
            "NTB_MARKET_DATA_PROVIDER": "fixture",
            "NTB_MARKET_DATA_MAX_QUOTE_AGE_SECONDS": "0",
        },
        target_root=target_root,
    )

    assert config.provider == "disabled"
    assert config.failure_reason == "invalid_max_quote_age_seconds"


def test_nonfinite_max_quote_age_fails_closed(target_root: Path) -> None:
    config = resolve_futures_quote_service_config(
        {
            "NTB_MARKET_DATA_PROVIDER": "fixture",
            "NTB_MARKET_DATA_MAX_QUOTE_AGE_SECONDS": "nan",
        },
        target_root=target_root,
    )

    assert config.provider == "disabled"
    assert config.failure_reason == "invalid_max_quote_age_seconds"


def test_invalid_timeout_fails_closed(target_root: Path) -> None:
    config = resolve_futures_quote_service_config(
        {
            "NTB_MARKET_DATA_PROVIDER": "schwab",
            "NTB_MARKET_DATA_TIMEOUT_SECONDS": "-1",
        },
        target_root=target_root,
    )

    assert config.provider == "disabled"
    assert config.failure_reason == "invalid_timeout_seconds"


def test_nonfinite_timeout_fails_closed(target_root: Path) -> None:
    config = resolve_futures_quote_service_config(
        {
            "NTB_MARKET_DATA_PROVIDER": "schwab",
            "NTB_MARKET_DATA_TIMEOUT_SECONDS": "inf",
        },
        target_root=target_root,
    )

    assert config.provider == "disabled"
    assert config.failure_reason == "invalid_timeout_seconds"


def test_absolute_token_path_outside_state_fails_closed(target_root: Path) -> None:
    config = resolve_futures_quote_service_config(
        {
            "NTB_MARKET_DATA_PROVIDER": "schwab",
            "SCHWAB_TOKEN_PATH": str((target_root.parent / "outside-token.json").resolve()),
        },
        target_root=target_root,
    )

    assert config.provider == "disabled"
    assert config.failure_reason == "token_path_outside_target_state"


def test_config_object_is_immutable(target_root: Path) -> None:
    config = resolve_futures_quote_service_config({}, target_root=target_root)

    with pytest.raises(FrozenInstanceError):
        config.provider = "fixture"  # type: ignore[misc]


def test_resolver_has_no_network_side_effects(target_root: Path) -> None:
    config = resolve_futures_quote_service_config(
        {
            "NTB_MARKET_DATA_PROVIDER": "schwab",
            "NTB_MARKET_DATA_SYMBOL": "/esm26",
            "SCHWAB_TOKEN_PATH": ".state/schwab/token.json",
        },
        target_root=target_root,
    )

    assert isinstance(config, FuturesQuoteServiceConfig)
    assert config.symbol == DEFAULT_MARKET_DATA_SYMBOL
