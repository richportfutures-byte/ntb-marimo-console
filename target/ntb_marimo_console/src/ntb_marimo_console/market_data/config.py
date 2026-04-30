from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Literal, Mapping

from ntb_marimo_console.adapters.schwab_futures_market_data import (
    DEFAULT_LEVELONE_FUTURES_FIELD_IDS,
    LEVELONE_FUTURES_FIELD_NAMES,
)


MarketDataProviderName = Literal["disabled", "fixture", "schwab"]

DEFAULT_MARKET_DATA_PROVIDER = "disabled"
DEFAULT_MARKET_DATA_SYMBOL = "/ESM26"
DEFAULT_MAX_QUOTE_AGE_SECONDS = 5.0
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_SCHWAB_TOKEN_PATH = ".state/schwab/token.json"


@dataclass(frozen=True)
class FuturesQuoteServiceConfig:
    provider: MarketDataProviderName
    symbol: str
    field_ids: tuple[int, ...]
    max_quote_age_seconds: float
    token_path: Path
    timeout_seconds: float
    failure_reason: str | None = None


def resolve_futures_quote_service_config(
    values: Mapping[str, str],
    *,
    target_root: Path | None = None,
) -> FuturesQuoteServiceConfig:
    resolved_target_root = (target_root or _default_target_root()).resolve()
    provider_name = values.get("NTB_MARKET_DATA_PROVIDER", DEFAULT_MARKET_DATA_PROVIDER).strip().lower()
    if provider_name not in {"disabled", "fixture", "schwab"}:
        return _failure_config(resolved_target_root, failure_reason="invalid_provider")

    symbol = _resolve_symbol(values.get("NTB_MARKET_DATA_SYMBOL", ""), provider=provider_name)
    field_ids = _parse_field_ids(values.get("NTB_MARKET_DATA_FIELD_IDS", ""))
    if field_ids is None:
        return _failure_config(resolved_target_root, failure_reason="invalid_field_ids")

    max_quote_age_seconds = _parse_positive_float(
        values.get("NTB_MARKET_DATA_MAX_QUOTE_AGE_SECONDS", ""),
        default=DEFAULT_MAX_QUOTE_AGE_SECONDS,
    )
    if max_quote_age_seconds is None:
        return _failure_config(resolved_target_root, failure_reason="invalid_max_quote_age_seconds")

    timeout_seconds = _parse_positive_float(
        values.get("NTB_MARKET_DATA_TIMEOUT_SECONDS", ""),
        default=DEFAULT_TIMEOUT_SECONDS,
    )
    if timeout_seconds is None:
        return _failure_config(resolved_target_root, failure_reason="invalid_timeout_seconds")

    token_path = _resolve_safe_token_path(
        values.get("SCHWAB_TOKEN_PATH", DEFAULT_SCHWAB_TOKEN_PATH),
        target_root=resolved_target_root,
    )
    if token_path is None:
        return _failure_config(resolved_target_root, failure_reason="token_path_outside_target_state")

    return FuturesQuoteServiceConfig(
        provider=provider_name,
        symbol=symbol,
        field_ids=field_ids,
        max_quote_age_seconds=max_quote_age_seconds,
        token_path=token_path,
        timeout_seconds=timeout_seconds,
        failure_reason=None,
    )


def _failure_config(target_root: Path, *, failure_reason: str) -> FuturesQuoteServiceConfig:
    return FuturesQuoteServiceConfig(
        provider="disabled",
        symbol="",
        field_ids=DEFAULT_LEVELONE_FUTURES_FIELD_IDS,
        max_quote_age_seconds=DEFAULT_MAX_QUOTE_AGE_SECONDS,
        token_path=_resolve_safe_token_path(DEFAULT_SCHWAB_TOKEN_PATH, target_root=target_root) or target_root / ".state",
        timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        failure_reason=failure_reason,
    )


def _resolve_symbol(raw_value: str, *, provider: str) -> str:
    symbol = raw_value.strip().upper()
    if symbol:
        return symbol
    if provider in {"fixture", "schwab"}:
        return DEFAULT_MARKET_DATA_SYMBOL
    return ""


def _parse_field_ids(raw_value: str) -> tuple[int, ...] | None:
    text = raw_value.strip()
    if not text:
        return DEFAULT_LEVELONE_FUTURES_FIELD_IDS
    parts = [part.strip() for part in text.split(",")]
    if not parts or any(not part for part in parts):
        return None
    field_ids: list[int] = []
    for part in parts:
        if not part.isdigit():
            return None
        field_id = int(part)
        if field_id not in LEVELONE_FUTURES_FIELD_NAMES:
            return None
        field_ids.append(field_id)
    return tuple(field_ids)


def _parse_positive_float(raw_value: str, *, default: float) -> float | None:
    text = raw_value.strip()
    if not text:
        return default
    try:
        value = float(text)
    except ValueError:
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return value


def _resolve_safe_token_path(raw_value: str, *, target_root: Path) -> Path | None:
    raw_path = Path(raw_value).expanduser()
    if not raw_path.is_absolute() and raw_path.parts[:2] == ("target", "ntb_marimo_console"):
        raw_path = target_root.parents[1] / raw_path
    candidate = raw_path if raw_path.is_absolute() else target_root / raw_path
    resolved = candidate.resolve()
    state_root = (target_root / ".state").resolve()
    if resolved != state_root and state_root not in resolved.parents:
        return None
    return resolved


def _default_target_root() -> Path:
    return Path(__file__).resolve().parents[3]
