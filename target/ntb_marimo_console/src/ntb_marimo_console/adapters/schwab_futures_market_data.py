from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol
from urllib.parse import urlparse


DEFAULT_LEVELONE_FUTURES_FIELD_IDS: tuple[int, ...] = (0, 1, 2, 3, 4, 5)

LEVELONE_FUTURES_FIELD_NAMES: dict[int, str] = {
    0: "Symbol",
    1: "Bid Price",
    2: "Ask Price",
    3: "Last Price",
    4: "Bid Size",
    5: "Ask Size",
    8: "Total Volume",
    9: "Last Size",
    10: "Quote Time",
    11: "Trade Time",
    12: "High Price",
    13: "Low Price",
    14: "Close Price",
    18: "Open Price",
    19: "Net Change",
    20: "Future Percent Change",
    22: "Security Status",
    23: "Open Interest",
    24: "Mark",
    25: "Tick",
    26: "Tick Amount",
    27: "Product",
    28: "Future Price Format",
    29: "Future Trading Hours",
    30: "Future Is Tradable",
    31: "Future Multiplier",
    32: "Future Is Active",
    33: "Future Settlement Price",
    34: "Future Active Symbol",
    35: "Future Expiration Date",
    37: "Ask Time",
    38: "Bid Time",
    39: "Quoted In Session",
}


@dataclass(frozen=True)
class SchwabFuturesMarketDataRequest:
    symbol: str
    token_path: Path | str = ".state/schwab/token.json"
    field_ids: tuple[int, ...] = DEFAULT_LEVELONE_FUTURES_FIELD_IDS
    timeout_seconds: float = 10.0


@dataclass(frozen=True)
class SchwabStreamerMetadata:
    streamer_socket_url: str
    schwab_client_customer_id: str
    schwab_client_correl_id: str
    schwab_client_channel: str
    schwab_client_function_id: str


@dataclass(frozen=True)
class SchwabLevelOneFuturesSubscription:
    response_code: int
    market_data: Mapping[int | str, object] | None = None


@dataclass(frozen=True)
class SchwabFuturesQuoteSnapshot:
    raw_fields: tuple[tuple[int, object], ...]
    symbol: str | None
    bid_price: object | None
    ask_price: object | None
    last_price: object | None
    bid_size: object | None
    ask_size: object | None


@dataclass(frozen=True)
class SchwabFuturesMarketDataResult:
    status: str
    symbol: str
    field_ids: tuple[int, ...]
    streamer_socket_host: str | None
    login_response_code: int | None
    subscription_response_code: int | None
    market_data_received: bool
    last_quote_snapshot: SchwabFuturesQuoteSnapshot | None
    received_at: str | None
    failure_reason: str | None


class SchwabUserPreferenceProvider(Protocol):
    def load_streamer_metadata(self, token_path: Path) -> SchwabStreamerMetadata: ...


class SchwabFuturesStreamerClient(Protocol):
    def login(
        self,
        metadata: SchwabStreamerMetadata,
        *,
        timeout_seconds: float,
    ) -> int: ...

    def subscribe_levelone_futures(
        self,
        metadata: SchwabStreamerMetadata,
        *,
        symbol: str,
        field_ids: tuple[int, ...],
        timeout_seconds: float,
    ) -> SchwabLevelOneFuturesSubscription: ...


class SchwabAdapterTimeoutError(RuntimeError):
    pass


class SchwabFuturesMarketDataAdapter:
    def __init__(
        self,
        *,
        user_preference_provider: SchwabUserPreferenceProvider,
        streamer_client: SchwabFuturesStreamerClient,
        target_root: Path | None = None,
        clock: object | None = None,
    ) -> None:
        self._user_preference_provider = user_preference_provider
        self._streamer_client = streamer_client
        self._target_root = target_root or _target_root()
        self._clock = clock or _utc_iso_now

    def fetch_once(self, request: SchwabFuturesMarketDataRequest) -> SchwabFuturesMarketDataResult:
        token_path_result = _resolve_token_path(request.token_path, target_root=self._target_root)
        if token_path_result.failure_reason is not None:
            return _failure_result(
                request,
                status="error",
                failure_reason=token_path_result.failure_reason,
            )

        try:
            field_ids = _validate_field_ids(request.field_ids)
        except Exception:
            return _failure_result(
                request,
                status="error",
                field_ids=_safe_field_ids(request.field_ids),
                failure_reason="field_validation_error",
            )

        try:
            metadata = self._user_preference_provider.load_streamer_metadata(token_path_result.path)
        except Exception as exc:
            return _failure_result(
                request,
                status="error",
                field_ids=field_ids,
                failure_reason=_safe_failure_reason("user_preference_error", exc),
            )

        streamer_socket_host = _streamer_socket_host(metadata.streamer_socket_url)
        if not streamer_socket_host:
            return _failure_result(
                request,
                status="error",
                field_ids=field_ids,
                failure_reason="invalid_streamer_socket_url",
            )

        try:
            login_response_code = self._streamer_client.login(
                metadata,
                timeout_seconds=request.timeout_seconds,
            )
        except SchwabAdapterTimeoutError:
            return _failure_result(
                request,
                status="timeout",
                field_ids=field_ids,
                streamer_socket_host=streamer_socket_host,
                failure_reason="login_timeout",
            )
        except Exception as exc:
            return _failure_result(
                request,
                status="error",
                field_ids=field_ids,
                streamer_socket_host=streamer_socket_host,
                failure_reason=_safe_failure_reason("login_error", exc),
            )
        if login_response_code != 0:
            return _failure_result(
                request,
                status="login_failed",
                field_ids=field_ids,
                streamer_socket_host=streamer_socket_host,
                login_response_code=login_response_code,
                failure_reason="login_response_code_nonzero",
            )

        try:
            subscription = self._streamer_client.subscribe_levelone_futures(
                metadata,
                symbol=request.symbol,
                field_ids=field_ids,
                timeout_seconds=request.timeout_seconds,
            )
        except SchwabAdapterTimeoutError:
            return _failure_result(
                request,
                status="timeout",
                field_ids=field_ids,
                streamer_socket_host=streamer_socket_host,
                login_response_code=login_response_code,
                failure_reason="subscription_timeout",
            )
        except Exception as exc:
            return _failure_result(
                request,
                status="error",
                field_ids=field_ids,
                streamer_socket_host=streamer_socket_host,
                login_response_code=login_response_code,
                failure_reason=_safe_failure_reason("subscription_error", exc),
            )
        if subscription.response_code != 0:
            return _failure_result(
                request,
                status="subscription_failed",
                field_ids=field_ids,
                streamer_socket_host=streamer_socket_host,
                login_response_code=login_response_code,
                subscription_response_code=subscription.response_code,
                failure_reason="subscription_response_code_nonzero",
            )
        if not subscription.market_data:
            return _failure_result(
                request,
                status="timeout",
                field_ids=field_ids,
                streamer_socket_host=streamer_socket_host,
                login_response_code=login_response_code,
                subscription_response_code=subscription.response_code,
                failure_reason="market_data_not_received",
            )

        try:
            snapshot = _quote_snapshot(subscription.market_data)
        except Exception as exc:
            return _failure_result(
                request,
                status="error",
                field_ids=field_ids,
                streamer_socket_host=streamer_socket_host,
                login_response_code=login_response_code,
                subscription_response_code=subscription.response_code,
                failure_reason=_safe_failure_reason("result_mapping_error", exc),
            )
        return SchwabFuturesMarketDataResult(
            status="success",
            symbol=snapshot.symbol or request.symbol,
            field_ids=field_ids,
            streamer_socket_host=streamer_socket_host,
            login_response_code=login_response_code,
            subscription_response_code=subscription.response_code,
            market_data_received=True,
            last_quote_snapshot=snapshot,
            received_at=self._clock(),
            failure_reason=None,
        )


@dataclass(frozen=True)
class _TokenPathResult:
    path: Path
    failure_reason: str | None = None


def _target_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _utc_iso_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _resolve_token_path(token_path: Path | str, *, target_root: Path) -> _TokenPathResult:
    raw_path = Path(token_path).expanduser()
    candidate = raw_path if raw_path.is_absolute() else target_root / raw_path
    resolved = candidate.resolve(strict=False)
    state_root = (target_root / ".state").resolve(strict=False)
    try:
        resolved.relative_to(state_root)
    except ValueError:
        return _TokenPathResult(path=resolved, failure_reason="token_path_outside_target_state")
    return _TokenPathResult(path=resolved)


def _validate_field_ids(field_ids: tuple[int, ...]) -> tuple[int, ...]:
    if not field_ids:
        raise ValueError("field_ids_required")
    normalized = tuple(int(field_id) for field_id in field_ids)
    unsupported = tuple(field_id for field_id in normalized if field_id not in LEVELONE_FUTURES_FIELD_NAMES)
    if unsupported:
        raise ValueError("unsupported_field_id")
    return normalized


def _safe_field_ids(field_ids: tuple[int, ...]) -> tuple[int, ...]:
    try:
        return tuple(int(field_id) for field_id in field_ids)
    except Exception:
        return ()


def _safe_failure_reason(stage: str, exc: Exception) -> str:
    return f"{stage}:{exc.__class__.__name__}"


def _streamer_socket_host(streamer_socket_url: str) -> str:
    parsed = urlparse(streamer_socket_url.strip())
    return parsed.netloc


def _field_value(market_data: Mapping[int | str, object], field_id: int) -> object | None:
    if field_id in market_data:
        return market_data[field_id]
    text_field_id = str(field_id)
    if text_field_id in market_data:
        return market_data[text_field_id]
    return None


def _quote_snapshot(market_data: Mapping[int | str, object]) -> SchwabFuturesQuoteSnapshot:
    raw_fields = tuple(
        sorted(
            (
                (int(field_id), value)
                for field_id, value in market_data.items()
                if isinstance(field_id, int) or (isinstance(field_id, str) and field_id.isdigit())
            ),
            key=lambda item: item[0],
        )
    )
    symbol_value = _field_value(market_data, 0)
    return SchwabFuturesQuoteSnapshot(
        raw_fields=raw_fields,
        symbol=symbol_value if isinstance(symbol_value, str) else None,
        bid_price=_field_value(market_data, 1),
        ask_price=_field_value(market_data, 2),
        last_price=_field_value(market_data, 3),
        bid_size=_field_value(market_data, 4),
        ask_size=_field_value(market_data, 5),
    )


def _failure_result(
    request: SchwabFuturesMarketDataRequest,
    *,
    status: str,
    failure_reason: str,
    field_ids: tuple[int, ...] | None = None,
    streamer_socket_host: str | None = None,
    login_response_code: int | None = None,
    subscription_response_code: int | None = None,
) -> SchwabFuturesMarketDataResult:
    return SchwabFuturesMarketDataResult(
        status=status,
        symbol=request.symbol,
        field_ids=field_ids or _safe_field_ids(request.field_ids),
        streamer_socket_host=streamer_socket_host,
        login_response_code=login_response_code,
        subscription_response_code=subscription_response_code,
        market_data_received=False,
        last_quote_snapshot=None,
        received_at=None,
        failure_reason=failure_reason,
    )
