from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .market_data.stream_events import redact_sensitive_text
from .market_data.stream_manager import (
    SchwabStreamClient,
    SchwabStreamManager,
    SchwabStreamManagerConfig,
    StreamManagerSnapshot,
)
from .operator_live_runtime import (
    OPERATOR_LIVE_RUNTIME,
    RuntimeSnapshotProducer,
    StreamManagerRuntimeSnapshotProducer,
    clear_operator_live_runtime_registration,
    get_registered_operator_live_runtime_producer,
    operator_runtime_mode_from_env,
    register_operator_live_runtime_manager,
)


class OperatorLiveRuntimeOptInRequired(RuntimeError):
    """Raised when the operator launcher is invoked without explicit env opt-in."""


class OperatorLiveRuntimeFactoryError(RuntimeError):
    """Raised when an operator-supplied client factory fails. Message is redacted."""


class OperatorLiveRuntimeStartError(RuntimeError):
    """Raised when the constructed manager fails to reach an active state. Message is redacted."""


ClientFactory = Callable[[SchwabStreamManagerConfig], SchwabStreamClient]
ManagerBuilder = Callable[[SchwabStreamManagerConfig, SchwabStreamClient], object]


@dataclass(frozen=True)
class OperatorLiveLaunchResult:
    manager: object
    producer: RuntimeSnapshotProducer
    started_snapshot: StreamManagerSnapshot


def start_operator_live_runtime(
    *,
    client_factory: ClientFactory,
    config: SchwabStreamManagerConfig | None = None,
    values: dict[str, str] | None = None,
    register: bool = True,
    manager_builder: ManagerBuilder | None = None,
) -> OperatorLiveLaunchResult:
    """Construct, start, and (optionally) register an operator-owned live runtime.

    The launcher is the only place where ``manager.start()`` (and therefore
    ``client.login`` / ``client.subscribe``) is invoked. The Marimo refresh
    path remains read-only via ``StreamManagerRuntimeSnapshotProducer``.
    """

    if operator_runtime_mode_from_env(values) != OPERATOR_LIVE_RUNTIME:
        raise OperatorLiveRuntimeOptInRequired(
            "operator_live_runtime_opt_in_required",
        )

    resolved_config = config if config is not None else SchwabStreamManagerConfig(
        provider="schwab",
        explicit_live_opt_in=True,
    )

    try:
        client = client_factory(resolved_config)
    except Exception as exc:
        raise OperatorLiveRuntimeFactoryError(
            f"operator_live_runtime_factory_error:{redact_sensitive_text(exc)}",
        ) from exc

    if manager_builder is None:
        manager: object = SchwabStreamManager(resolved_config, client=client)
    else:
        manager = manager_builder(resolved_config, client)

    try:
        started_snapshot = manager.start()
    except Exception as exc:
        raise OperatorLiveRuntimeStartError(
            f"operator_live_runtime_start_error:{redact_sensitive_text(exc)}",
        ) from exc

    if not isinstance(started_snapshot, StreamManagerSnapshot):
        raise OperatorLiveRuntimeStartError(
            "operator_live_runtime_start_error:stream_manager_snapshot_required",
        )

    if started_snapshot.state != "active" or started_snapshot.blocking_reasons:
        reasons = "; ".join(redact_sensitive_text(reason) for reason in started_snapshot.blocking_reasons)
        detail = reasons or f"state={started_snapshot.state}"
        raise OperatorLiveRuntimeStartError(
            f"operator_live_runtime_start_error:{detail}",
        )

    producer = StreamManagerRuntimeSnapshotProducer(manager)
    if register:
        register_operator_live_runtime_manager(manager)

    return OperatorLiveLaunchResult(
        manager=manager,
        producer=producer,
        started_snapshot=started_snapshot,
    )


def stop_operator_live_runtime(manager: object) -> StreamManagerSnapshot:
    """Shut down an operator-owned manager and clear any matching registration.

    Idempotent: calling on an already-shutdown manager returns its snapshot
    unchanged. Always clears the matching module registration so a subsequent
    Marimo cell evaluation falls back to the safe default.
    """

    snapshot = manager.shutdown()
    registered = get_registered_operator_live_runtime_producer()
    if isinstance(registered, StreamManagerRuntimeSnapshotProducer) and registered.manager is manager:
        clear_operator_live_runtime_registration()
    if not isinstance(snapshot, StreamManagerSnapshot):
        raise OperatorLiveRuntimeStartError(
            "operator_live_runtime_shutdown_error:stream_manager_snapshot_required",
        )
    return snapshot
