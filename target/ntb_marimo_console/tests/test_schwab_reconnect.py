from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from ntb_marimo_console.market_data.stream_manager import (
    SchwabStreamManager,
    SchwabStreamManagerConfig,
    StreamClientResult,
    StreamSubscriptionRequest,
)
from ntb_marimo_console.schwab_reconnect import (
    ReconnectBackoffPolicy,
    ReconnectResult,
    SchwabReconnectController,
    should_attempt_reconnect,
)
from ntb_marimo_console.schwab_receive_thread import ManagedSchwabReceiveThread


@dataclass
class FakeClock:
    current: datetime = datetime(2026, 5, 12, 14, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)


class FakeStartClient:
    def __init__(self) -> None:
        self.login_calls = 0
        self.subscription_calls = 0

    def login(self, config: SchwabStreamManagerConfig) -> StreamClientResult:
        self.login_calls += 1
        return StreamClientResult(succeeded=True)

    def subscribe(self, request: StreamSubscriptionRequest) -> StreamClientResult:
        self.subscription_calls += 1
        return StreamClientResult(succeeded=True)

    def close(self) -> StreamClientResult:
        return StreamClientResult(succeeded=True)


class FakeTokenProvider:
    def __init__(self) -> None:
        self.call_count = 0
        self.values: list[str] = []

    def load_access_token(self) -> str:
        self.call_count += 1
        token = f"token-{self.call_count}"
        self.values.append(token)
        return token


@dataclass
class FakeSession:
    login_result: StreamClientResult = field(default_factory=lambda: StreamClientResult(succeeded=True))
    subscribe_result: StreamClientResult = field(default_factory=lambda: StreamClientResult(succeeded=True))
    token_provider: FakeTokenProvider | None = None
    dispatch_status_value: str = "idle"
    login_calls: int = 0
    subscribe_calls: int = 0
    close_calls: int = 0
    tokens_used: list[str] = field(default_factory=list)

    def login(self, config: SchwabStreamManagerConfig) -> StreamClientResult:
        self.login_calls += 1
        if self.token_provider is not None:
            self.tokens_used.append(self.token_provider.load_access_token())
        return self.login_result

    def subscribe(self, request: StreamSubscriptionRequest) -> StreamClientResult:
        self.subscribe_calls += 1
        return self.subscribe_result

    def close(self) -> StreamClientResult:
        self.close_calls += 1
        return StreamClientResult(succeeded=True)

    def dispatch_status(self) -> str:
        return self.dispatch_status_value


class FakeSessionFactory:
    def __init__(
        self,
        *,
        login_results: list[StreamClientResult] | None = None,
        subscribe_results: list[StreamClientResult] | None = None,
        token_provider: FakeTokenProvider | None = None,
    ) -> None:
        self.login_results = list(login_results or [])
        self.subscribe_results = list(subscribe_results or [])
        self.token_provider = token_provider
        self.sessions: list[FakeSession] = []

    def __call__(self, config: SchwabStreamManagerConfig) -> FakeSession:
        login_result = (
            self.login_results.pop(0)
            if self.login_results
            else StreamClientResult(succeeded=True)
        )
        subscribe_result = (
            self.subscribe_results.pop(0)
            if self.subscribe_results
            else StreamClientResult(succeeded=True)
        )
        session = FakeSession(
            login_result=login_result,
            subscribe_result=subscribe_result,
            token_provider=self.token_provider,
        )
        self.sessions.append(session)
        return session


def live_config() -> SchwabStreamManagerConfig:
    return SchwabStreamManagerConfig(
        provider="schwab",
        services_requested=("LEVELONE_FUTURES",),
        symbols_requested=("/ESM26",),
        fields_requested=(0, 1, 2, 3, 4, 5),
        explicit_live_opt_in=True,
        contracts_requested=("ES",),
    )


def active_manager(clock: FakeClock | None = None) -> SchwabStreamManager:
    manager = SchwabStreamManager(live_config(), client=FakeStartClient(), clock=clock or FakeClock())
    snapshot = manager.start()
    assert snapshot.state == "active"
    return manager


def test_successful_reconnect_after_first_connection_drop() -> None:
    manager = active_manager()
    factory = FakeSessionFactory()
    old_session = FakeSession(dispatch_status_value="connection_lost")
    sleeps: list[float] = []
    controller = SchwabReconnectController(
        config=live_config(),
        session_factory=factory,
        manager=manager,
        policy=ReconnectBackoffPolicy(jitter_ratio=0.0),
        sleep=sleeps.append,
    )

    result = controller.reconnect(current_session=old_session, reason="connection_lost")

    assert result.reconnected is True
    assert result.session is factory.sessions[0]
    assert old_session.close_calls == 1
    assert factory.sessions[0].login_calls == 1
    assert factory.sessions[0].subscribe_calls == 1
    assert manager.snapshot().state == "active"
    assert sleeps == [1.0]


def test_exponential_backoff_timing_with_mock_sleep() -> None:
    manager = active_manager()
    factory = FakeSessionFactory(
        login_results=[
            StreamClientResult(succeeded=False, reason="login_failed"),
            StreamClientResult(succeeded=False, reason="login_failed"),
            StreamClientResult(succeeded=True),
        ]
    )
    sleeps: list[float] = []
    controller = SchwabReconnectController(
        config=live_config(),
        session_factory=factory,
        manager=manager,
        policy=ReconnectBackoffPolicy(
            initial_delay_seconds=1.0,
            multiplier=2.0,
            max_delay_seconds=30.0,
            jitter_ratio=0.0,
            max_attempts=3,
        ),
        sleep=sleeps.append,
    )

    result = controller.reconnect(current_session=FakeSession(), reason="connection_lost")

    assert result.reconnected is True
    assert sleeps == [1.0, 2.0, 4.0]
    assert manager.snapshot().reconnect_attempts == 3


def test_max_retries_exhausted_transitions_to_blocked_state() -> None:
    manager = active_manager()
    factory = FakeSessionFactory(
        login_results=[
            StreamClientResult(succeeded=False, reason="login_failed"),
            StreamClientResult(succeeded=False, reason="login_failed"),
        ]
    )
    controller = SchwabReconnectController(
        config=live_config(),
        session_factory=factory,
        manager=manager,
        policy=ReconnectBackoffPolicy(jitter_ratio=0.0, max_attempts=2),
        sleep=lambda delay: None,
    )

    result = controller.reconnect(current_session=FakeSession(), reason="connection_lost")
    snapshot = manager.snapshot()

    assert result.reconnected is False
    assert result.attempts == 2
    assert snapshot.state == "blocked"
    assert snapshot.cache.provider_status == "blocked"
    assert any("reconnect_failed:max_attempts_exhausted" in reason for reason in snapshot.blocking_reasons)


def test_fresh_token_is_obtained_on_each_reconnect_attempt() -> None:
    manager = active_manager()
    token_provider = FakeTokenProvider()
    factory = FakeSessionFactory(
        login_results=[
            StreamClientResult(succeeded=False, reason="login_failed"),
            StreamClientResult(succeeded=False, reason="login_failed"),
            StreamClientResult(succeeded=False, reason="login_failed"),
        ],
        token_provider=token_provider,
    )
    controller = SchwabReconnectController(
        config=live_config(),
        session_factory=factory,
        manager=manager,
        policy=ReconnectBackoffPolicy(jitter_ratio=0.0, max_attempts=3),
        sleep=lambda delay: None,
    )

    controller.reconnect(current_session=FakeSession(), reason="connection_lost")

    assert token_provider.call_count == 3
    assert token_provider.values == ["token-1", "token-2", "token-3"]
    assert [session.tokens_used for session in factory.sessions] == [["token-1"], ["token-2"], ["token-3"]]


def test_reconnect_creates_new_session_instance_not_reusing_old_one() -> None:
    manager = active_manager()
    factory = FakeSessionFactory()
    old_session = FakeSession(dispatch_status_value="connection_lost")
    controller = SchwabReconnectController(
        config=live_config(),
        session_factory=factory,
        manager=manager,
        policy=ReconnectBackoffPolicy(jitter_ratio=0.0),
        sleep=lambda delay: None,
    )

    result = controller.reconnect(current_session=old_session, reason="connection_lost")

    assert result.session is not old_session
    assert controller.active_session is factory.sessions[0]
    assert len(factory.sessions) == 1


def test_reconnect_events_are_recorded_in_stream_manager() -> None:
    clock = FakeClock()
    manager = active_manager(clock)
    factory = FakeSessionFactory()
    controller = SchwabReconnectController(
        config=live_config(),
        session_factory=factory,
        manager=manager,
        policy=ReconnectBackoffPolicy(jitter_ratio=0.0),
        sleep=lambda delay: clock.advance(delay),
    )

    controller.reconnect(current_session=FakeSession(), reason="connection_lost")
    snapshot = manager.snapshot()
    event_types = [event.event_type for event in snapshot.events]

    assert "reconnect_attempt" in event_types
    assert "reconnect_succeeded" in event_types
    assert snapshot.reconnect_attempts == 1
    assert snapshot.last_reconnect_at is not None
    assert snapshot.current_backoff_delay is None


def test_reconnect_is_not_triggered_by_recv_timeout() -> None:
    timeout_session = FakeSession(dispatch_status_value="timeout")
    lost_session = FakeSession(dispatch_status_value="connection_lost")

    assert should_attempt_reconnect(timeout_session) is False
    assert should_attempt_reconnect(lost_session) is True


class FakeReceiveManager:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []
        self.connection_lost_reasons: list[str] = []
        self.check_heartbeat_calls = 0
        self.check_contract_heartbeats_calls = 0
        self.last_heartbeat_at: str | None = None

    def ingest_message(self, message: dict[str, object]) -> None:
        self.messages.append(dict(message))

    def mark_connection_lost(self, reason: object = "connection_lost") -> None:
        self.connection_lost_reasons.append(str(reason))

    def snapshot(self) -> object:
        return type("Snapshot", (), {"last_heartbeat_at": self.last_heartbeat_at})()

    def check_heartbeat(self) -> None:
        self.check_heartbeat_calls += 1

    def check_contract_heartbeats(self) -> None:
        self.check_contract_heartbeats_calls += 1


class FakeReceiveSession:
    def __init__(
        self,
        *,
        outcomes: list[tuple[bool, str, dict[str, object] | None]] | None = None,
        token_reason: str | None = None,
    ) -> None:
        self.outcomes = list(outcomes or [])
        self.token_reason = token_reason
        self.dispatch_calls = 0
        self.last_status = "idle"

    def dispatch_one(self, handler) -> bool:
        self.dispatch_calls += 1
        if not self.outcomes:
            self.last_status = "timeout"
            return False
        received, _status, message = self.outcomes.pop(0)
        self.last_status = _status
        if message is not None:
            handler(message)
        return received

    def dispatch_status(self) -> str:
        return self.last_status

    def token_refresh_blocking_reason(self) -> str | None:
        return self.token_reason


class FakeReceiveReconnectController:
    def __init__(self, result: ReconnectResult) -> None:
        self.result = result
        self.calls = 0
        self.current_sessions: list[object | None] = []

    def reconnect(
        self,
        *,
        current_session: object | None = None,
        reason: object = "connection_lost",
    ) -> ReconnectResult:
        self.calls += 1
        self.current_sessions.append(current_session)
        return self.result


def test_managed_receive_thread_dispatches_messages_without_starting_live_by_construction() -> None:
    manager = FakeReceiveManager()
    session = FakeReceiveSession(
        outcomes=[
            (
                True,
                "message",
                {
                    "service": "LEVELONE_FUTURES",
                    "symbol": "/ESM26",
                    "contract": "ES",
                    "message_type": "quote",
                    "fields": {"1": 10.0},
                    "received_at": "2026-05-12T14:00:00+00:00",
                },
            )
        ]
    )
    worker = ManagedSchwabReceiveThread(
        session=session,
        manager=manager,
        sleep_seconds=0,
    )

    status = worker.run_until_stopped(max_iterations=1)

    assert status.dispatch_count == 1
    assert status.message_count == 1
    assert manager.messages[0]["contract"] == "ES"
    assert manager.connection_lost_reasons == []


def test_managed_receive_thread_treats_timeout_as_quiet_not_reconnect() -> None:
    manager = FakeReceiveManager()
    session = FakeReceiveSession(outcomes=[(False, "timeout", None)])
    worker = ManagedSchwabReceiveThread(
        session=session,
        manager=manager,
        sleep_seconds=0,
    )

    status = worker.run_until_stopped(max_iterations=1)

    assert status.quiet_count == 1
    assert status.reconnect_count == 0
    assert manager.connection_lost_reasons == []


def test_managed_receive_thread_marks_token_refresh_failure_fail_closed() -> None:
    manager = FakeReceiveManager()
    session = FakeReceiveSession(
        outcomes=[(False, "token_refresh_failed", None)],
        token_reason="token_refresh_failed:SchwabTokenError",
    )
    worker = ManagedSchwabReceiveThread(
        session=session,
        manager=manager,
        sleep_seconds=0,
    )

    status = worker.run_until_stopped(max_iterations=1)

    assert status.last_error == "token_refresh_failed:SchwabTokenError"
    assert manager.connection_lost_reasons == ["token_refresh_failed:SchwabTokenError"]


def test_managed_receive_thread_swaps_to_reconnected_session() -> None:
    manager = FakeReceiveManager()
    old_session = FakeReceiveSession(outcomes=[(False, "connection_lost", None)])
    new_session = FakeReceiveSession()
    controller = FakeReceiveReconnectController(
        ReconnectResult(
            reconnected=True,
            session=new_session,
            attempts=1,
            reason="reconnect_succeeded",
        )
    )
    worker = ManagedSchwabReceiveThread(
        session=old_session,
        manager=manager,
        reconnect_controller=controller,
        sleep_seconds=0,
    )

    status = worker.run_until_stopped(max_iterations=1)

    assert status.reconnect_count == 1
    assert worker.session is new_session
    assert controller.current_sessions == [old_session]
    assert manager.connection_lost_reasons == []


def test_managed_receive_thread_runs_watchdog_checks_after_dispatch() -> None:
    manager = FakeReceiveManager()
    manager.last_heartbeat_at = "2026-05-12T14:00:00+00:00"
    session = FakeReceiveSession(
        outcomes=[
            (
                True,
                "message",
                {
                    "service": "LEVELONE_FUTURES",
                    "symbol": "/ESM26",
                    "contract": "ES",
                    "message_type": "quote",
                    "fields": {"1": 10.0},
                    "received_at": "2026-05-12T14:00:00+00:00",
                },
            )
        ]
    )
    worker = ManagedSchwabReceiveThread(
        session=session,
        manager=manager,
        sleep_seconds=0,
    )

    worker.run_until_stopped(max_iterations=1)

    assert manager.check_heartbeat_calls == 1
    assert manager.check_contract_heartbeats_calls == 1
