from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Protocol

from .market_data.stream_events import redact_sensitive_text
from .schwab_reconnect import ReconnectResult, should_attempt_reconnect


class ReceiveThreadSession(Protocol):
    def dispatch_one(self, handler: Callable[[Mapping[str, object]], object]) -> bool: ...


class ReceiveThreadManager(Protocol):
    def ingest_message(self, message: Mapping[str, object]) -> object: ...

    def mark_connection_lost(self, reason: object = "connection_lost") -> object: ...

    def snapshot(self) -> object: ...


class ReceiveThreadReconnectController(Protocol):
    def reconnect(
        self,
        *,
        current_session: object | None = None,
        reason: object = "connection_lost",
    ) -> ReconnectResult: ...


@dataclass(frozen=True)
class ManagedReceiveThreadStatus:
    running: bool
    dispatch_count: int
    message_count: int
    quiet_count: int
    reconnect_count: int
    last_dispatch_status: str
    last_error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "running": self.running,
            "dispatch_count": self.dispatch_count,
            "message_count": self.message_count,
            "quiet_count": self.quiet_count,
            "reconnect_count": self.reconnect_count,
            "last_dispatch_status": self.last_dispatch_status,
            "last_error": self.last_error,
        }


@dataclass
class ManagedSchwabReceiveThread:
    """Explicit operator-owned receive worker for an already-started session.

    Constructing this object does not start a thread. ``start()`` is the only
    method that spawns background work, keeping Marimo refresh and default
    fixture paths read-only.
    """

    session: ReceiveThreadSession
    manager: ReceiveThreadManager
    reconnect_controller: ReceiveThreadReconnectController | None = None
    sleep_seconds: float = 0.05
    daemon: bool = True
    thread_name: str = "ntb-schwab-receive"
    sleep: Callable[[float], None] = time.sleep
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _dispatch_count: int = field(default=0, init=False)
    _message_count: int = field(default=0, init=False)
    _quiet_count: int = field(default=0, init=False)
    _reconnect_count: int = field(default=0, init=False)
    _last_dispatch_status: str = field(default="idle", init=False)
    _last_error: str | None = field(default=None, init=False)

    def start(self) -> ManagedReceiveThreadStatus:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                thread_needed = False
            else:
                thread_needed = True
                self._stop_event.clear()
                self._thread = threading.Thread(
                    target=self.run_until_stopped,
                    name=self.thread_name,
                    daemon=self.daemon,
                )
                self._thread.start()
        if not thread_needed:
            return self.status()
        return self.status()

    def stop(self) -> ManagedReceiveThreadStatus:
        self._stop_event.set()
        return self.status()

    def join(self, timeout: float | None = None) -> ManagedReceiveThreadStatus:
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        return self.status()

    def run_until_stopped(self, *, max_iterations: int | None = None) -> ManagedReceiveThreadStatus:
        iterations = 0
        while not self._stop_event.is_set():
            self.run_once()
            iterations += 1
            if max_iterations is not None and iterations >= max_iterations:
                break
            if self.sleep_seconds > 0:
                self.sleep(self.sleep_seconds)
        return self.status()

    def run_once(self) -> ManagedReceiveThreadStatus:
        messages_seen = 0

        def _handler(message: Mapping[str, object]) -> None:
            nonlocal messages_seen
            messages_seen += 1
            self.manager.ingest_message(message)

        try:
            received = bool(self.session.dispatch_one(_handler))
        except Exception as exc:
            self._mark_connection_lost(f"receive_thread_exception:{type(exc).__name__}")
            self.stop()
            return self.status()

        status = _session_dispatch_status(self.session)
        with self._lock:
            self._dispatch_count += 1
            self._last_dispatch_status = status
            if received:
                self._message_count += messages_seen
            else:
                self._quiet_count += 1

        if received:
            return self.status()

        token_reason = _token_refresh_blocking_reason(self.session)
        if token_reason is not None:
            self._mark_connection_lost(token_reason)
            self.stop()
            return self.status()

        if should_attempt_reconnect(self.session):
            self._attempt_reconnect(reason=status or "connection_lost")
        return self.status()

    def status(self) -> ManagedReceiveThreadStatus:
        thread = self._thread
        with self._lock:
            return ManagedReceiveThreadStatus(
                running=thread is not None and thread.is_alive() and not self._stop_event.is_set(),
                dispatch_count=self._dispatch_count,
                message_count=self._message_count,
                quiet_count=self._quiet_count,
                reconnect_count=self._reconnect_count,
                last_dispatch_status=self._last_dispatch_status,
                last_error=self._last_error,
            )

    def _attempt_reconnect(self, *, reason: object) -> None:
        controller = self.reconnect_controller
        if controller is None:
            self._mark_connection_lost(reason)
            self.stop()
            return

        try:
            result = controller.reconnect(current_session=self.session, reason=reason)
        except Exception as exc:
            self._mark_connection_lost(f"reconnect_controller_exception:{type(exc).__name__}")
            self.stop()
            return

        with self._lock:
            self._reconnect_count += 1

        if result.reconnected and result.session is not None:
            self.session = result.session
            return

        self._mark_connection_lost(result.reason)
        self.stop()

    def _mark_connection_lost(self, reason: object) -> None:
        safe_reason = redact_sensitive_text(reason)
        with self._lock:
            self._last_error = safe_reason
            self._last_dispatch_status = "connection_lost"
        try:
            self.manager.mark_connection_lost(safe_reason)
        except Exception:
            pass


def _session_dispatch_status(session: object) -> str:
    status_func = getattr(session, "dispatch_status", None)
    if not callable(status_func):
        return "unknown"
    try:
        status = status_func()
    except Exception:
        return "unknown"
    return str(status).strip().lower() or "unknown"


def _token_refresh_blocking_reason(session: object) -> str | None:
    reason_func = getattr(session, "token_refresh_blocking_reason", None)
    if not callable(reason_func):
        return None
    try:
        reason = reason_func()
    except Exception as exc:
        return f"token_refresh_status_exception:{type(exc).__name__}"
    if reason is None:
        return None
    text = redact_sensitive_text(reason)
    return text or None
