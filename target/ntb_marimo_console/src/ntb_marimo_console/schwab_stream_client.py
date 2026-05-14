from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .market_data.stream_manager import (
    SchwabStreamClient,
    SchwabStreamManagerConfig,
    StreamClientResult,
    StreamSubscriptionRequest,
)


class StreamerSession(Protocol):
    """Operator-supplied collaborator that performs the Schwab websocket round trip.

    The session is invoked exclusively from the explicit operator live launcher
    (and the manager's ``start()``); never from Marimo refresh, readiness summary,
    renderer, or any default/CI/import path.
    """

    def login(self, config: SchwabStreamManagerConfig) -> StreamClientResult: ...

    def subscribe(self, request: StreamSubscriptionRequest) -> StreamClientResult: ...

    def close(self) -> StreamClientResult: ...


StreamerSessionFactory = Callable[[SchwabStreamManagerConfig], StreamerSession]
ClientFactory = Callable[[SchwabStreamManagerConfig], SchwabStreamClient]


class OperatorSchwabStreamClient:
    """Concrete ``SchwabStreamClient`` that delegates to a ``StreamerSession``.

    Each method catches any exception from the session and returns a
    ``StreamClientResult`` whose ``reason`` field is auto-redacted by
    ``StreamClientResult.__post_init__``. Session-returned results pass through
    unchanged (the dataclass also redacts their ``reason`` on construction).
    """

    def __init__(self, session: StreamerSession) -> None:
        self._session = session

    @property
    def receive_session(self) -> object:
        """Return the underlying streamer session for the operator receive loop."""

        return self._session

    def login(self, config: SchwabStreamManagerConfig) -> StreamClientResult:
        try:
            return self._session.login(config)
        except Exception as exc:
            return StreamClientResult(
                succeeded=False,
                reason=f"login_exception:{exc}",
            )

    def subscribe(self, request: StreamSubscriptionRequest) -> StreamClientResult:
        try:
            return self._session.subscribe(request)
        except Exception as exc:
            return StreamClientResult(
                succeeded=False,
                reason=f"subscribe_exception:{exc}",
            )

    def close(self) -> StreamClientResult:
        try:
            return self._session.close()
        except Exception as exc:
            return StreamClientResult(
                succeeded=False,
                reason=f"close_exception:{exc}",
            )


def build_operator_schwab_stream_client_factory(
    *,
    streamer_session_factory: StreamerSessionFactory,
) -> ClientFactory:
    """Construct a ``ClientFactory`` consumable by ``start_operator_live_runtime``.

    Lazy: invoking this builder does NOT call ``streamer_session_factory``. The
    returned factory only invokes ``streamer_session_factory`` when the launcher
    invokes the factory under explicit ``OPERATOR_LIVE_RUNTIME`` opt-in.

    No credential, token, streamer-metadata, or network work is performed at
    import time, at builder time, or by the returned factory until the launcher
    actually invokes it.
    """

    if not callable(streamer_session_factory):
        raise TypeError("streamer_session_factory_must_be_callable")

    def _factory(config: SchwabStreamManagerConfig) -> SchwabStreamClient:
        session = streamer_session_factory(config)
        return OperatorSchwabStreamClient(session)

    return _factory
