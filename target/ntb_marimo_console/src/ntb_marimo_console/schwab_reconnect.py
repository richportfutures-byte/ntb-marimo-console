from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from .market_data.stream_events import redact_sensitive_text
from .market_data.stream_manager import (
    SchwabStreamManagerConfig,
    StreamClientResult,
    StreamSubscriptionRequest,
)


class ReconnectableSession(Protocol):
    def login(self, config: SchwabStreamManagerConfig) -> StreamClientResult: ...

    def subscribe(self, request: StreamSubscriptionRequest) -> StreamClientResult: ...

    def close(self) -> StreamClientResult: ...


SessionFactory = Callable[[SchwabStreamManagerConfig], ReconnectableSession]


@dataclass(frozen=True)
class ReconnectBackoffPolicy:
    initial_delay_seconds: float = 1.0
    multiplier: float = 2.0
    max_delay_seconds: float = 30.0
    jitter_ratio: float = 0.10
    max_attempts: int = 5

    def delay_for_attempt(self, attempt: int, *, random_value: float = 0.5) -> float:
        attempt_index = max(0, int(attempt) - 1)
        base = max(0.0, float(self.initial_delay_seconds)) * (
            max(1.0, float(self.multiplier)) ** attempt_index
        )
        capped = min(max(0.0, float(self.max_delay_seconds)), base)
        jitter = max(0.0, float(self.jitter_ratio))
        if jitter == 0.0:
            return capped
        bounded_random = min(1.0, max(0.0, float(random_value)))
        jitter_factor = 1.0 + ((bounded_random * 2.0) - 1.0) * jitter
        return max(0.0, capped * jitter_factor)

    @property
    def bounded_max_attempts(self) -> int:
        return max(1, int(self.max_attempts))


@dataclass(frozen=True)
class ReconnectResult:
    reconnected: bool
    session: ReconnectableSession | None
    attempts: int
    reason: str


def session_dispatch_status(session: object) -> str:
    status_func = getattr(session, "dispatch_status", None)
    if not callable(status_func):
        return "unknown"
    try:
        status = status_func()
    except Exception:
        return "unknown"
    return str(status).strip().lower() or "unknown"


def should_attempt_reconnect(session: object) -> bool:
    return session_dispatch_status(session) == "connection_lost"


@dataclass
class SchwabReconnectController:
    config: SchwabStreamManagerConfig
    session_factory: SessionFactory
    manager: object
    policy: ReconnectBackoffPolicy = ReconnectBackoffPolicy()
    sleep: Callable[[float], None] = time.sleep
    random_func: Callable[[], float] = random.random
    active_session: ReconnectableSession | None = None

    def reconnect(
        self,
        *,
        current_session: ReconnectableSession | None = None,
        reason: object = "connection_lost",
    ) -> ReconnectResult:
        safe_reason = redact_sensitive_text(reason)
        last_reason = safe_reason
        max_attempts = self.policy.bounded_max_attempts
        for attempt in range(1, max_attempts + 1):
            delay = self.policy.delay_for_attempt(
                attempt,
                random_value=self.random_func(),
            )
            self._record_attempt(attempt=attempt, delay_seconds=delay, reason=safe_reason)
            self.sleep(delay)

            session: ReconnectableSession | None = None
            try:
                session = self.session_factory(self.config)
            except Exception as exc:
                last_reason = f"session_factory_failed:{type(exc).__name__}"
                continue

            login_result = self._login(session)
            if not login_result.succeeded:
                last_reason = login_result.reason or "login_failed"
                self._safe_close(session)
                continue

            subscribe_result = self._subscribe(session)
            if not subscribe_result.succeeded:
                last_reason = subscribe_result.reason or "subscribe_failed"
                self._safe_close(session)
                continue

            self.active_session = session
            if current_session is not None and current_session is not session:
                self._safe_close(current_session)
            self._record_success(attempt=attempt)
            return ReconnectResult(
                reconnected=True,
                session=session,
                attempts=attempt,
                reason="reconnect_succeeded",
            )

        final_reason = f"reconnect_failed:max_attempts_exhausted:{redact_sensitive_text(last_reason)}"
        self._record_exhausted(final_reason)
        return ReconnectResult(
            reconnected=False,
            session=None,
            attempts=max_attempts,
            reason=final_reason,
        )

    def _login(self, session: ReconnectableSession) -> StreamClientResult:
        try:
            return session.login(self.config)
        except Exception as exc:
            return StreamClientResult(
                succeeded=False,
                reason=f"login_exception:{type(exc).__name__}",
            )

    def _subscribe(self, session: ReconnectableSession) -> StreamClientResult:
        request = StreamSubscriptionRequest(
            provider=self.config.provider,
            services=self.config.services_requested,
            symbols=self.config.symbols_requested,
            fields=self.config.fields_requested,
            contracts=self.config.contracts_requested,
        )
        try:
            return session.subscribe(request)
        except Exception as exc:
            return StreamClientResult(
                succeeded=False,
                reason=f"subscribe_exception:{type(exc).__name__}",
            )

    def _record_attempt(self, *, attempt: int, delay_seconds: float, reason: str) -> None:
        marker = getattr(self.manager, "begin_reconnect_attempt", None)
        if callable(marker):
            marker(attempt=attempt, delay_seconds=delay_seconds, reason=reason)

    def _record_success(self, *, attempt: int) -> None:
        marker = getattr(self.manager, "reconnect_succeeded", None)
        if callable(marker):
            marker(attempt=attempt)

    def _record_exhausted(self, reason: str) -> None:
        marker = getattr(self.manager, "reconnect_exhausted", None)
        if callable(marker):
            marker(reason)
            return
        fallback = getattr(self.manager, "mark_connection_lost", None)
        if callable(fallback):
            fallback(reason)

    def _safe_close(self, session: ReconnectableSession) -> None:
        try:
            session.close()
        except Exception:
            pass
