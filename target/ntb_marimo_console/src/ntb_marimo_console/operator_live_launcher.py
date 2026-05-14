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
from .schwab_receive_thread import (
    ManagedSchwabReceiveThread,
)


class OperatorLiveRuntimeOptInRequired(RuntimeError):
    """Raised when the operator launcher is invoked without explicit env opt-in."""


class OperatorLiveRuntimeFactoryError(RuntimeError):
    """Raised when an operator-supplied client factory fails. Message is redacted."""


class OperatorLiveRuntimeStartError(RuntimeError):
    """Raised when the constructed manager fails to reach an active state. Message is redacted."""


ClientFactory = Callable[[SchwabStreamManagerConfig], SchwabStreamClient]
ManagerBuilder = Callable[[SchwabStreamManagerConfig, SchwabStreamClient], object]
ReceiveThreadBuilder = Callable[..., object]


@dataclass(frozen=True)
class OperatorLiveLaunchResult:
    manager: object
    producer: RuntimeSnapshotProducer
    started_snapshot: StreamManagerSnapshot
    receive_worker: object | None = None
    receive_worker_status: object | None = None


_RECEIVE_WORKERS_BY_MANAGER_ID: dict[int, object] = {}


def start_operator_live_runtime(
    *,
    client_factory: ClientFactory,
    config: SchwabStreamManagerConfig | None = None,
    values: dict[str, str] | None = None,
    register: bool = True,
    manager_builder: ManagerBuilder | None = None,
    receive_thread_builder: ReceiveThreadBuilder | None = None,
    start_receive_worker: bool = True,
) -> OperatorLiveLaunchResult:
    """Construct, start, and (optionally) register an operator-owned live runtime.

    The launcher is the only place where ``manager.start()`` (and therefore
    ``client.login`` / ``client.subscribe``) is invoked. When the constructed
    client exposes an operator streamer session, the launcher also starts one
    receive worker to dispatch websocket data into ``manager.ingest_message``.
    The Marimo refresh path remains read-only via
    ``StreamManagerRuntimeSnapshotProducer``.
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

    receive_worker: object | None = None
    receive_worker_status: object | None = None
    if start_receive_worker:
        receive_worker, receive_worker_status = _start_receive_worker_if_supported(
            client=client,
            manager=manager,
            receive_thread_builder=receive_thread_builder,
        )

    producer = StreamManagerRuntimeSnapshotProducer(manager)
    if register:
        register_operator_live_runtime_manager(manager)

    return OperatorLiveLaunchResult(
        manager=manager,
        producer=producer,
        started_snapshot=started_snapshot,
        receive_worker=receive_worker,
        receive_worker_status=receive_worker_status,
    )


def stop_operator_live_runtime(manager: object) -> StreamManagerSnapshot:
    """Shut down an operator-owned manager and clear any matching registration.

    Idempotent: calling on an already-shutdown manager returns its snapshot
    unchanged. Always clears the matching module registration so a subsequent
    Marimo cell evaluation falls back to the safe default.
    """

    _stop_receive_worker_for_manager(manager)
    snapshot = manager.shutdown()
    registered = get_registered_operator_live_runtime_producer()
    if isinstance(registered, StreamManagerRuntimeSnapshotProducer) and registered.manager is manager:
        clear_operator_live_runtime_registration()
    if not isinstance(snapshot, StreamManagerSnapshot):
        raise OperatorLiveRuntimeStartError(
            "operator_live_runtime_shutdown_error:stream_manager_snapshot_required",
        )
    return snapshot


def _start_receive_worker_if_supported(
    *,
    client: object,
    manager: object,
    receive_thread_builder: ReceiveThreadBuilder | None,
) -> tuple[object | None, object | None]:
    session = _receive_session_from_client(client)
    if session is None:
        return None, None
    if not callable(getattr(manager, "ingest_message", None)):
        return None, None
    builder = receive_thread_builder or ManagedSchwabReceiveThread
    try:
        worker = builder(session=session, manager=manager)
        status = worker.start()
    except Exception as exc:
        _safe_shutdown_manager(manager)
        raise OperatorLiveRuntimeStartError(
            f"operator_live_runtime_start_error:receive_thread_start_failed:{redact_sensitive_text(exc)}",
        ) from exc
    _RECEIVE_WORKERS_BY_MANAGER_ID[id(manager)] = worker
    return worker, status


def _receive_session_from_client(client: object) -> object | None:
    direct_dispatch = getattr(client, "dispatch_one", None)
    if callable(direct_dispatch):
        return client
    session = getattr(client, "receive_session", None)
    if session is not None and callable(getattr(session, "dispatch_one", None)):
        return session
    return None


def _stop_receive_worker_for_manager(manager: object) -> None:
    worker = _RECEIVE_WORKERS_BY_MANAGER_ID.pop(id(manager), None)
    if worker is None:
        return
    stop = getattr(worker, "stop", None)
    try:
        if callable(stop):
            stop()
    except Exception:
        pass
    join = getattr(worker, "join", None)
    try:
        if callable(join):
            join(timeout=2.0)
    except Exception:
        pass


def _safe_shutdown_manager(manager: object) -> None:
    shutdown = getattr(manager, "shutdown", None)
    if not callable(shutdown):
        return
    try:
        shutdown()
    except Exception:
        pass
