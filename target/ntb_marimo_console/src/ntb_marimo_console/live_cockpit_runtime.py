"""Explicit opt-in live cockpit runtime bootstrap.

Wires the operator live runtime start/register primitives
(:func:`start_operator_live_runtime`) into the Marimo cockpit session
lifecycle. The bootstrap is invoked at most once per explicit live cockpit
session — the caller owns the once-per-session guard (the Marimo app guards
via ``mo.state``) — and never from the refresh/render path. Refresh reads the
already-started runtime's cache through the registered read-only
``RuntimeSnapshotProducer``; it never re-logs-in or re-subscribes.

Fail-closed by construction: if the live opt-in is missing, no client-factory
builder is available, the builder errors, or the runtime fails to start, the
bootstrap returns an :class:`UnavailableRuntimeSnapshotProducer` so the cockpit
surfaces a fail-closed live-unavailable/error state. It never falls back to
fixture data.

Import-time inert: importing this module performs no env reads, file opens,
network calls, websocket imports, or runtime starts. All such work happens only
when :func:`start_live_cockpit_runtime` is explicitly invoked under live opt-in.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from .market_data.stream_events import redact_sensitive_text
from .market_data.stream_manager import SchwabStreamManagerConfig
from .operator_live_launcher import (
    OperatorLiveLaunchResult,
    OperatorLiveRuntimeFactoryError,
    OperatorLiveRuntimeOptInRequired,
    OperatorLiveRuntimeStartError,
    start_operator_live_runtime,
    stop_operator_live_runtime,
)
from .operator_live_runtime import (
    OPERATOR_LIVE_RUNTIME,
    RuntimeSnapshotProducer,
    UnavailableRuntimeSnapshotProducer,
    operator_runtime_mode_from_env,
)
from .schwab_stream_client import ClientFactory


LiveCockpitClientFactoryBuilder = Callable[
    [dict[str, str]], "tuple[ClientFactory, SchwabStreamManagerConfig]"
]
RuntimeStarter = Callable[..., OperatorLiveLaunchResult]

LIVE_COCKPIT_STATUS_STARTED = "started"
LIVE_COCKPIT_STATUS_OPT_IN_REQUIRED = "opt_in_required"
LIVE_COCKPIT_STATUS_CLIENT_FACTORY_UNAVAILABLE = "client_factory_unavailable"
LIVE_COCKPIT_STATUS_CLIENT_FACTORY_ERROR = "client_factory_error"
LIVE_COCKPIT_STATUS_START_FAILED = "start_failed"


@dataclass(frozen=True)
class LiveCockpitRuntimeBootstrap:
    """Result of one explicit live cockpit runtime start attempt.

    ``producer`` is always a usable read-only :class:`RuntimeSnapshotProducer`:
    the registered live producer on success, or an
    :class:`UnavailableRuntimeSnapshotProducer` (fail-closed) otherwise. It is
    never a fixture producer.
    """

    producer: RuntimeSnapshotProducer
    started: bool
    status: str
    blocking_reason: str | None = None
    manager: object | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "started": self.started,
            "status": self.status,
            "blocking_reason": self.blocking_reason,
        }


_REGISTERED_CLIENT_FACTORY_BUILDER: LiveCockpitClientFactoryBuilder | None = None


def register_live_cockpit_client_factory_builder(
    builder: LiveCockpitClientFactoryBuilder,
) -> None:
    """Register the default live cockpit client-factory builder.

    Replaces any prior registration. The builder is invoked only inside
    :func:`start_live_cockpit_runtime` under explicit live opt-in.
    """

    global _REGISTERED_CLIENT_FACTORY_BUILDER
    _REGISTERED_CLIENT_FACTORY_BUILDER = builder


def clear_live_cockpit_client_factory_builder() -> None:
    """Drop any registered client-factory builder. Safe to call when empty."""

    global _REGISTERED_CLIENT_FACTORY_BUILDER
    _REGISTERED_CLIENT_FACTORY_BUILDER = None


def get_live_cockpit_client_factory_builder() -> LiveCockpitClientFactoryBuilder | None:
    """Return the currently registered client-factory builder, if any."""

    return _REGISTERED_CLIENT_FACTORY_BUILDER


def _fail_closed(status: str, reason: str) -> LiveCockpitRuntimeBootstrap:
    return LiveCockpitRuntimeBootstrap(
        producer=UnavailableRuntimeSnapshotProducer(reason=reason),
        started=False,
        status=status,
        blocking_reason=reason,
        manager=None,
    )


def _resolve_default_builder() -> LiveCockpitClientFactoryBuilder | None:
    """Lazy-import the app-owned default builder if available.

    Import-time inert: the ``schwab_client_factory_builder`` module is only
    imported here — never at module level — and only when no injected or
    registered builder is available. Returns ``None`` (preserving
    fail-closed behavior) if the module is unavailable.
    """

    try:
        from .schwab_client_factory_builder import build_default_live_client_factory

        return build_default_live_client_factory
    except ImportError:
        return None


def start_live_cockpit_runtime(
    values: dict[str, str] | None = None,
    *,
    client_factory_builder: LiveCockpitClientFactoryBuilder | None = None,
    runtime_starter: RuntimeStarter = start_operator_live_runtime,
) -> LiveCockpitRuntimeBootstrap:
    """Start and register the operator-owned live runtime for a live cockpit session.

    Must be called at most once per explicit live cockpit session; the caller
    owns the once-per-session guard. This function performs a fresh start each
    time it is invoked and is never called from the refresh/render path.

    Fail-closed: returns an :class:`UnavailableRuntimeSnapshotProducer` (never a
    fixture producer) when live opt-in is missing, no client-factory builder is
    available, the builder errors, or the runtime fails to start.
    """

    if operator_runtime_mode_from_env(values) != OPERATOR_LIVE_RUNTIME:
        return _fail_closed(
            LIVE_COCKPIT_STATUS_OPT_IN_REQUIRED,
            "operator_live_runtime_opt_in_required",
        )
    resolved_values = dict(values) if values is not None else dict(os.environ)

    builder = client_factory_builder or _REGISTERED_CLIENT_FACTORY_BUILDER
    if builder is None:
        builder = _resolve_default_builder()
    if builder is None:
        return _fail_closed(
            LIVE_COCKPIT_STATUS_CLIENT_FACTORY_UNAVAILABLE,
            "live_cockpit_client_factory_unavailable",
        )

    try:
        client_factory, config = builder(resolved_values or {})
    except Exception as exc:
        return _fail_closed(
            LIVE_COCKPIT_STATUS_CLIENT_FACTORY_ERROR,
            f"live_cockpit_client_factory_error:{redact_sensitive_text(exc)}",
        )

    try:
        result = runtime_starter(
            client_factory=client_factory,
            config=config,
            values=resolved_values,
            register=True,
        )
    except (
        OperatorLiveRuntimeOptInRequired,
        OperatorLiveRuntimeFactoryError,
        OperatorLiveRuntimeStartError,
    ) as exc:
        return _fail_closed(
            LIVE_COCKPIT_STATUS_START_FAILED,
            f"live_cockpit_runtime_start_failed:{redact_sensitive_text(exc)}",
        )

    return LiveCockpitRuntimeBootstrap(
        producer=result.producer,
        started=True,
        status=LIVE_COCKPIT_STATUS_STARTED,
        blocking_reason=None,
        manager=result.manager,
    )


def stop_live_cockpit_runtime(bootstrap: LiveCockpitRuntimeBootstrap) -> bool:
    """Best-effort shutdown of a started live cockpit runtime.

    Returns ``True`` when a started manager was shut down, ``False`` for a
    fail-closed bootstrap (no-op). Safe to call regardless of bootstrap state.
    """

    if not bootstrap.started or bootstrap.manager is None:
        return False
    stop_operator_live_runtime(bootstrap.manager)
    return True
