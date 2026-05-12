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
    SchwabReconnectController,
    should_attempt_reconnect,
)


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
