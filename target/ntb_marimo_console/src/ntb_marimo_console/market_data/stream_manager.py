from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Protocol

from ntb_marimo_console.contract_universe import (
    final_target_contracts,
    is_excluded_final_target_contract,
    is_final_target_contract,
    is_never_supported_contract,
)

from .stream_cache import NormalizedStreamMessage, StreamCache, StreamCacheSnapshot
from .stream_events import StreamEvent, redact_sensitive_text
from .stream_lifecycle import StreamLifecycleState


MIN_STREAM_REFRESH_FLOOR_SECONDS = 15.0
StreamProvider = Literal["disabled", "schwab"]
StreamStartupMode = Literal["default_non_live", "explicit_live"]


@dataclass(frozen=True)
class SchwabStreamManagerConfig:
    provider: StreamProvider = "disabled"
    services_requested: tuple[str, ...] = ()
    symbols_requested: tuple[str, ...] = ()
    fields_requested: tuple[int, ...] = ()
    explicit_live_opt_in: bool = False
    refresh_floor_seconds: float = MIN_STREAM_REFRESH_FLOOR_SECONDS
    cache_max_age_seconds: float = MIN_STREAM_REFRESH_FLOOR_SECONDS
    startup_mode: StreamStartupMode = "default_non_live"
    contracts_requested: tuple[str, ...] = final_target_contracts()

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", self.provider.strip().lower())
        object.__setattr__(
            self,
            "services_requested",
            tuple(service.strip().upper() for service in self.services_requested if service.strip()),
        )
        object.__setattr__(
            self,
            "symbols_requested",
            tuple(symbol.strip().upper() for symbol in self.symbols_requested if symbol.strip()),
        )
        object.__setattr__(
            self,
            "contracts_requested",
            tuple(contract.strip().upper() for contract in self.contracts_requested if contract.strip()),
        )
        object.__setattr__(self, "fields_requested", tuple(int(field) for field in self.fields_requested))
        object.__setattr__(
            self,
            "refresh_floor_seconds",
            max(float(self.refresh_floor_seconds), MIN_STREAM_REFRESH_FLOOR_SECONDS),
        )
        object.__setattr__(
            self,
            "cache_max_age_seconds",
            max(float(self.cache_max_age_seconds), MIN_STREAM_REFRESH_FLOOR_SECONDS),
        )
        startup_mode: StreamStartupMode = "explicit_live" if self.explicit_live_opt_in else "default_non_live"
        object.__setattr__(self, "startup_mode", startup_mode)


@dataclass(frozen=True)
class StreamClientResult:
    succeeded: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.reason is not None:
            object.__setattr__(self, "reason", redact_sensitive_text(self.reason))

    def to_dict(self) -> dict[str, object]:
        return {
            "succeeded": self.succeeded,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class StreamSubscriptionRequest:
    provider: str
    services: tuple[str, ...]
    symbols: tuple[str, ...]
    fields: tuple[int, ...]
    contracts: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "services": list(self.services),
            "symbols": list(self.symbols),
            "fields": list(self.fields),
            "contracts": list(self.contracts),
        }


class SchwabStreamClient(Protocol):
    def login(self, config: SchwabStreamManagerConfig) -> StreamClientResult: ...

    def subscribe(self, request: StreamSubscriptionRequest) -> StreamClientResult: ...

    def close(self) -> StreamClientResult: ...


@dataclass(frozen=True)
class StreamManagerSnapshot:
    state: StreamLifecycleState
    config: SchwabStreamManagerConfig
    cache: StreamCacheSnapshot
    events: tuple[StreamEvent, ...]
    blocking_reasons: tuple[str, ...]
    login_count: int
    subscription_count: int
    last_subscription_request: StreamSubscriptionRequest | None = None
    last_subscription_result: StreamClientResult | None = None
    last_heartbeat_at: str | None = None
    heartbeat_age_seconds: float | None = None

    @property
    def operator_state(self) -> StreamLifecycleState:
        return self.state

    @property
    def ready(self) -> bool:
        return self.state == "active" and self.cache.ready and not self.blocking_reasons

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "provider": self.config.provider,
            "startup_mode": self.config.startup_mode,
            "services_requested": list(self.config.services_requested),
            "symbols_requested": list(self.config.symbols_requested),
            "fields_requested": list(self.config.fields_requested),
            "contracts_requested": list(self.config.contracts_requested),
            "explicit_live_opt_in": self.config.explicit_live_opt_in,
            "refresh_floor_seconds": self.config.refresh_floor_seconds,
            "cache": self.cache.to_dict(),
            "events": [event.to_dict() for event in self.events],
            "blocking_reasons": list(self.blocking_reasons),
            "login_count": self.login_count,
            "subscription_count": self.subscription_count,
            "last_subscription_request": (
                self.last_subscription_request.to_dict()
                if self.last_subscription_request is not None
                else None
            ),
            "last_subscription_result": (
                self.last_subscription_result.to_dict()
                if self.last_subscription_result is not None
                else None
            ),
            "last_heartbeat_at": self.last_heartbeat_at,
            "heartbeat_age_seconds": self.heartbeat_age_seconds,
            "ready": self.ready,
        }


class SchwabStreamManager:
    def __init__(
        self,
        config: SchwabStreamManagerConfig | None = None,
        *,
        client: SchwabStreamClient | None = None,
        clock: object | None = None,
    ) -> None:
        self._config = config or SchwabStreamManagerConfig()
        self._client = client
        self._clock = clock or _utc_now
        self._state: StreamLifecycleState = "disabled" if self._config.provider == "disabled" else "initialized"
        self._cache = StreamCache(
            provider=self._config.provider,
            cache_max_age_seconds=self._config.cache_max_age_seconds,
            clock=self._clock,
        )
        self._cache.set_provider_status("disabled" if self._state == "disabled" else "connected")
        self._events: list[StreamEvent] = []
        self._blocking_reasons: list[str] = []
        self._login_count = 0
        self._subscription_count = 0
        self._last_heartbeat_at: datetime | None = None
        self._last_subscription_request: StreamSubscriptionRequest | None = None
        self._last_subscription_result: StreamClientResult | None = None

    @property
    def state(self) -> StreamLifecycleState:
        return self._state

    @property
    def events(self) -> tuple[StreamEvent, ...]:
        return tuple(self._events)

    def start(self) -> StreamManagerSnapshot:
        if self._state in {"active", "stale", "blocked", "error", "shutdown"}:
            return self.snapshot()

        if self._config.provider == "disabled":
            self._state = "disabled"
            self._cache.set_provider_status("disabled")
            return self.snapshot()

        blocking_reasons = self._startup_blocking_reasons()
        if blocking_reasons:
            reason = "; ".join(blocking_reasons)
            self._block(
                event_type="login_denied",
                summary=reason,
                blocking_reason=reason,
            )
            return self.snapshot()

        if self._client is None:
            self._block(
                event_type="login_denied",
                summary="stream_client_required",
                blocking_reason="stream_client_required",
            )
            return self.snapshot()

        self._state = "connecting"
        self._cache.set_provider_status("connected")
        self._state = "login_pending"
        self._record_event(
            "login_requested",
            summary="login_requested_for_explicit_live_session",
            state=self._state,
        )
        try:
            self._login_count += 1
            login_result = self._client.login(self._config)
        except Exception as exc:
            self._block(
                event_type="login_denied",
                summary=f"login_exception:{exc}",
                blocking_reason=f"login_exception:{exc}",
            )
            return self.snapshot()
        if not login_result.succeeded:
            reason = login_result.reason or "login_denied"
            self._block(event_type="login_denied", summary=reason, blocking_reason=reason)
            return self.snapshot()

        self._state = "connected"
        self._record_event("login_succeeded", summary="login_succeeded", state=self._state)

        self._state = "subscribing"
        self._record_event(
            "subscription_requested",
            summary="subscription_requested_for_configured_futures_services",
            state=self._state,
        )
        subscription_request = StreamSubscriptionRequest(
            provider=self._config.provider,
            services=self._config.services_requested,
            symbols=self._config.symbols_requested,
            fields=self._config.fields_requested,
            contracts=self._config.contracts_requested,
        )
        self._last_subscription_request = subscription_request
        try:
            self._subscription_count += 1
            subscription_result = self._client.subscribe(subscription_request)
        except Exception as exc:
            self._last_subscription_result = StreamClientResult(
                succeeded=False,
                reason=f"subscription_exception:{exc}",
            )
            self._block(
                event_type="subscription_failed",
                summary=self._last_subscription_result.reason or "subscription_exception",
                blocking_reason=self._last_subscription_result.reason or "subscription_exception",
            )
            return self.snapshot()
        self._last_subscription_result = subscription_result
        if not subscription_result.succeeded:
            reason = subscription_result.reason or "subscription_failed"
            self._block(event_type="subscription_failed", summary=reason, blocking_reason=reason)
            return self.snapshot()

        self._state = "active"
        self._cache.set_provider_status("active")
        self._record_event("subscription_succeeded", summary="subscription_succeeded", state=self._state)
        return self.snapshot()

    def read_cache_snapshot(self) -> StreamCacheSnapshot:
        return self._cache.snapshot()

    def ingest_message(self, message: Mapping[str, object]) -> StreamManagerSnapshot:
        normalized = self._normalize_message(message)
        if normalized is None:
            return self.snapshot()

        if self._state != "active":
            self._block(
                event_type="malformed_message",
                summary="stream_not_active",
                blocking_reason="stream_not_active",
                symbol=normalized.symbol,
            )
            return self.snapshot()

        if normalized.contract not in self._config.contracts_requested:
            self._block(
                event_type="malformed_message",
                summary="symbol_mismatch",
                blocking_reason=f"symbol_mismatch:{normalized.contract}:{normalized.symbol}",
                symbol=normalized.symbol,
            )
            return self.snapshot()
        if normalized.symbol not in self._config.symbols_requested:
            self._block(
                event_type="malformed_message",
                summary="symbol_mismatch",
                blocking_reason=f"symbol_mismatch:{normalized.contract}:{normalized.symbol}",
                symbol=normalized.symbol,
            )
            return self.snapshot()
        if not normalized.fields:
            self._block(
                event_type="malformed_message",
                summary="missing_required_data",
                blocking_reason=f"missing_required_data:{normalized.contract}:{normalized.symbol}",
                symbol=normalized.symbol,
            )
            return self.snapshot()

        self._cache.put_message(normalized)
        self._record_event("data_received", summary="data_received", state=self._state, symbol=normalized.symbol)
        return self.snapshot()

    def record_heartbeat(self) -> StreamManagerSnapshot:
        self._last_heartbeat_at = self._clock()
        if self._state == "stale":
            self._state = "active"
            self._cache.set_provider_status("active")
        self._record_event("heartbeat_seen", summary="heartbeat_seen", state=self._state)
        return self.snapshot()

    def check_heartbeat(self) -> StreamManagerSnapshot:
        if self._state not in {"connected", "subscribing", "active", "stale"}:
            return self.snapshot()
        if self._last_heartbeat_at is None:
            return self._mark_stale("heartbeat_missing")
        heartbeat_age = (self._clock().astimezone(timezone.utc) - self._last_heartbeat_at.astimezone(timezone.utc))
        if heartbeat_age.total_seconds() > self._config.refresh_floor_seconds:
            return self._mark_stale("heartbeat_stale")
        return self.snapshot()

    def mark_connection_lost(self, reason: object = "connection_lost") -> StreamManagerSnapshot:
        safe_reason = redact_sensitive_text(reason)
        self._state = "disconnected"
        self._cache.set_provider_status("blocked")
        self._add_blocking_reason(safe_reason)
        self._record_event(
            "connection_lost",
            summary=safe_reason,
            state=self._state,
            blocking_reason=safe_reason,
        )
        return self.snapshot()

    def shutdown(self) -> StreamManagerSnapshot:
        if self._state == "shutdown":
            return self.snapshot()
        self._record_event("shutdown_requested", summary="shutdown_requested", state=self._state)
        if self._client is not None:
            try:
                self._client.close()
            except Exception as exc:
                self._add_blocking_reason(f"shutdown_exception:{exc}")
        self._state = "shutdown"
        self._cache.set_provider_status("shutdown")
        self._record_event("shutdown_completed", summary="shutdown_completed", state=self._state)
        return self.snapshot()

    def snapshot(self) -> StreamManagerSnapshot:
        return StreamManagerSnapshot(
            state=self._state,
            config=self._config,
            cache=self._cache.snapshot(),
            events=tuple(self._events),
            blocking_reasons=tuple(self._blocking_reasons),
            login_count=self._login_count,
            subscription_count=self._subscription_count,
            last_subscription_request=self._last_subscription_request,
            last_subscription_result=self._last_subscription_result,
            last_heartbeat_at=(
                _isoformat(self._last_heartbeat_at)
                if self._last_heartbeat_at is not None
                else None
            ),
            heartbeat_age_seconds=(
                _age_seconds_since(self._last_heartbeat_at, now=self._clock())
                if self._last_heartbeat_at is not None
                else None
            ),
        )

    def _startup_blocking_reasons(self) -> tuple[str, ...]:
        reasons: list[str] = []
        if self._config.provider != "schwab":
            reasons.append("provider_not_supported_for_stream_manager")
        if not self._config.explicit_live_opt_in:
            reasons.append("explicit_live_opt_in_required")
        if not self._config.services_requested:
            reasons.append("services_required")
        if not self._config.symbols_requested:
            reasons.append("symbols_required")
        if not self._config.fields_requested:
            reasons.append("fields_required")
        if not self._config.contracts_requested:
            reasons.append("contracts_required")
        for contract in self._config.contracts_requested:
            if is_never_supported_contract(contract):
                reasons.append(f"never_supported_contract_requested:{contract}")
            elif is_excluded_final_target_contract(contract):
                reasons.append(f"excluded_contract_requested:{contract}")
            elif not is_final_target_contract(contract):
                reasons.append(f"non_final_target_contract_requested:{contract}")
        return tuple(reasons)

    def _normalize_message(self, message: Mapping[str, object]) -> NormalizedStreamMessage | None:
        try:
            service = _required_string(message, "service").upper()
            symbol = _required_string(message, "symbol").upper()
            contract = _required_string(message, "contract").upper()
            message_type = _message_type(_required_string(message, "message_type"))
            fields = message.get("fields")
            if not isinstance(fields, Mapping):
                raise ValueError("fields_required")
            received_at = message.get("received_at")
            timestamp = received_at if isinstance(received_at, str) and received_at.strip() else _isoformat(self._clock())
        except Exception as exc:
            self._block(
                event_type="malformed_message",
                summary=f"malformed_message:{exc}",
                blocking_reason=f"malformed_message:{exc}",
            )
            return None
        return NormalizedStreamMessage(
            provider=self._config.provider,
            service=service,
            symbol=symbol,
            contract=contract,
            message_type=message_type,
            fields=fields,
            received_at=timestamp,
        )

    def _mark_stale(self, reason: str) -> StreamManagerSnapshot:
        self._state = "stale"
        self._cache.set_provider_status("stale")
        self._add_blocking_reason(reason)
        self._record_event(
            "heartbeat_stale",
            summary=reason,
            state=self._state,
            blocking_reason=reason,
        )
        return self.snapshot()

    def _block(
        self,
        *,
        event_type: Literal["login_denied", "subscription_failed", "malformed_message"],
        summary: object,
        blocking_reason: object,
        symbol: str | None = None,
    ) -> None:
        safe_reason = redact_sensitive_text(blocking_reason)
        self._state = "blocked"
        self._cache.set_provider_status("blocked")
        self._add_blocking_reason(safe_reason, symbol=symbol)
        self._record_event(
            event_type,
            summary=summary,
            state=self._state,
            blocking_reason=safe_reason,
            symbol=symbol,
        )

    def _add_blocking_reason(self, reason: object, *, symbol: str | None = None) -> None:
        safe_reason = redact_sensitive_text(reason)
        if safe_reason not in self._blocking_reasons:
            self._blocking_reasons.append(safe_reason)
        self._cache.add_blocking_reason(safe_reason, symbol=symbol)

    def _record_event(
        self,
        event_type: Literal[
            "login_requested",
            "login_succeeded",
            "login_denied",
            "subscription_requested",
            "subscription_succeeded",
            "subscription_failed",
            "data_received",
            "heartbeat_seen",
            "heartbeat_stale",
            "malformed_message",
            "connection_lost",
            "shutdown_requested",
            "shutdown_completed",
        ],
        *,
        summary: object,
        state: StreamLifecycleState,
        blocking_reason: object | None = None,
        symbol: str | None = None,
    ) -> None:
        self._events.append(
            StreamEvent(
                event_type=event_type,
                state=state,
                provider=self._config.provider,
                summary=redact_sensitive_text(summary),
                generated_at=_isoformat(self._clock()),
                symbols=(symbol,) if symbol else self._config.symbols_requested,
                services=self._config.services_requested,
                blocking_reason=redact_sensitive_text(blocking_reason) if blocking_reason is not None else None,
            )
        )


def _required_string(message: Mapping[str, object], key: str) -> str:
    value = message.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key}_required")
    return value.strip()


def _message_type(value: str) -> Literal["quote", "bar"]:
    normalized = value.strip().lower()
    if normalized not in {"quote", "bar"}:
        raise ValueError("unsupported_message_type")
    return normalized  # type: ignore[return-value]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    current = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat()


def _age_seconds_since(value: datetime, *, now: datetime) -> float:
    current = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    observed = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return max(0.0, (current.astimezone(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds())
