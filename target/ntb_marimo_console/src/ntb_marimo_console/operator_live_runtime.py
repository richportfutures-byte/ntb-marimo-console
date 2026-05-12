from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Protocol

from .market_data.stream_cache import ProviderStatus, StreamCacheSnapshot
from .market_data.stream_events import redact_sensitive_text
from .market_data.stream_manager import (
    MIN_STREAM_REFRESH_FLOOR_SECONDS,
    StreamManagerSnapshot,
)
from .readiness_summary import RuntimeReadinessSnapshot


OperatorRuntimeMode = Literal["SAFE_NON_LIVE", "OPERATOR_LIVE_RUNTIME"]
OperatorRuntimeStatus = Literal[
    "SAFE_NON_LIVE",
    "OPERATOR_LIVE_RUNTIME",
    "LIVE_RUNTIME_UNAVAILABLE",
    "LIVE_RUNTIME_STALE",
    "LIVE_RUNTIME_ERROR",
    "LIVE_RUNTIME_DISABLED",
]

SAFE_NON_LIVE: OperatorRuntimeMode = "SAFE_NON_LIVE"
OPERATOR_LIVE_RUNTIME: OperatorRuntimeMode = "OPERATOR_LIVE_RUNTIME"
LIVE_RUNTIME_UNAVAILABLE: OperatorRuntimeStatus = "LIVE_RUNTIME_UNAVAILABLE"
LIVE_RUNTIME_STALE: OperatorRuntimeStatus = "LIVE_RUNTIME_STALE"
LIVE_RUNTIME_ERROR: OperatorRuntimeStatus = "LIVE_RUNTIME_ERROR"
LIVE_RUNTIME_DISABLED: OperatorRuntimeStatus = "LIVE_RUNTIME_DISABLED"
ENV_OPERATOR_RUNTIME_MODE = "NTB_OPERATOR_RUNTIME_MODE"
ENV_OPERATOR_LIVE_RUNTIME = "NTB_OPERATOR_LIVE_RUNTIME"


class RuntimeSnapshotProducer(Protocol):
    """Read the latest local runtime/cache snapshot without starting live network work."""

    def read_snapshot(self) -> RuntimeReadinessSnapshot | None: ...


@dataclass(frozen=True)
class OperatorRuntimeSnapshotResult:
    mode: OperatorRuntimeMode
    status: OperatorRuntimeStatus
    source: str
    snapshot: RuntimeReadinessSnapshot | None
    requested_live_runtime: bool
    runtime_cache_derived: bool
    refresh_floor_seconds: float
    blocking_reasons: tuple[str, ...]
    cache_provider_status: str | None = None
    cache_generated_at: str | None = None
    cache_snapshot_ready: bool = False
    producer_error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "status": self.status,
            "source": self.source,
            "requested_live_runtime": self.requested_live_runtime,
            "runtime_cache_derived": self.runtime_cache_derived,
            "refresh_floor_seconds": self.refresh_floor_seconds,
            "blocking_reasons": list(self.blocking_reasons),
            "cache_provider_status": self.cache_provider_status,
            "cache_generated_at": self.cache_generated_at,
            "cache_snapshot_ready": self.cache_snapshot_ready,
            "producer_error": self.producer_error,
        }


@dataclass(frozen=True)
class StaticRuntimeSnapshotProducer:
    snapshot: RuntimeReadinessSnapshot | None

    def read_snapshot(self) -> RuntimeReadinessSnapshot | None:
        return self.snapshot


@dataclass(frozen=True)
class UnavailableRuntimeSnapshotProducer:
    reason: str = "operator_live_runtime_snapshot_unavailable"

    def read_snapshot(self) -> RuntimeReadinessSnapshot | None:
        return None


@dataclass(frozen=True)
class StreamManagerRuntimeSnapshotProducer:
    """Cache-first producer for an existing manager instance.

    The producer only reads the manager's current snapshot. It deliberately does
    not call ``start()``, ``login()``, or ``subscribe()`` from the Marimo refresh
    path.
    """

    manager: object

    def read_snapshot(self) -> RuntimeReadinessSnapshot | None:
        snapshot = self.manager.snapshot()
        if not isinstance(snapshot, StreamManagerSnapshot):
            raise TypeError("stream_manager_snapshot_required")
        return snapshot


def operator_runtime_mode_from_env(values: dict[str, str] | None = None) -> OperatorRuntimeMode:
    env = values if values is not None else os.environ
    raw_mode = env.get(ENV_OPERATOR_RUNTIME_MODE)
    if raw_mode:
        normalized = raw_mode.strip().upper()
        if normalized in {"SAFE_NON_LIVE", "NON_LIVE", "FIXTURE", "FIXTURE_SAFE"}:
            return SAFE_NON_LIVE
        if normalized in {"OPERATOR_LIVE_RUNTIME", "LIVE_RUNTIME", "LIVE"}:
            return OPERATOR_LIVE_RUNTIME
    raw_enabled = env.get(ENV_OPERATOR_LIVE_RUNTIME)
    if raw_enabled and raw_enabled.strip().lower() in {"1", "true", "yes", "on"}:
        return OPERATOR_LIVE_RUNTIME
    return SAFE_NON_LIVE


_REGISTERED_OPERATOR_LIVE_PRODUCER: RuntimeSnapshotProducer | None = None


def register_operator_live_runtime_manager(manager: object) -> None:
    """Register an operator-owned, already-started stream manager.

    Replaces any prior registration. The caller owns the manager lifecycle
    (``start``/``shutdown``); the registered producer only invokes
    ``manager.snapshot()``.
    """

    global _REGISTERED_OPERATOR_LIVE_PRODUCER
    _REGISTERED_OPERATOR_LIVE_PRODUCER = StreamManagerRuntimeSnapshotProducer(manager)


def register_operator_live_runtime_producer(producer: RuntimeSnapshotProducer) -> None:
    """Register a custom producer directly.

    Mutually exclusive with ``register_operator_live_runtime_manager`` —
    last write wins.
    """

    global _REGISTERED_OPERATOR_LIVE_PRODUCER
    _REGISTERED_OPERATOR_LIVE_PRODUCER = producer


def clear_operator_live_runtime_registration() -> None:
    """Drop any registered manager/producer. Safe to call when empty."""

    global _REGISTERED_OPERATOR_LIVE_PRODUCER
    _REGISTERED_OPERATOR_LIVE_PRODUCER = None


def get_registered_operator_live_runtime_producer() -> RuntimeSnapshotProducer | None:
    """Return the currently registered producer, if any."""

    return _REGISTERED_OPERATOR_LIVE_PRODUCER


def build_operator_runtime_snapshot_producer_from_env(
    values: dict[str, str] | None = None,
    *,
    manager: object | None = None,
    manager_factory: Callable[[], object] | None = None,
    producer: RuntimeSnapshotProducer | None = None,
) -> RuntimeSnapshotProducer | None:
    """Build the app-owned producer without touching Schwab or secrets.

    Resolution order when mode is ``OPERATOR_LIVE_RUNTIME``:

    1. explicit ``producer=`` kwarg → returned as-is.
    2. explicit ``manager=`` kwarg → wrapped via ``StreamManagerRuntimeSnapshotProducer``.
    3. explicit ``manager_factory=`` → invoked exactly once, wrapped.
    4. registered producer from the module-level registry → returned.
    5. ``UnavailableRuntimeSnapshotProducer`` (preserves the safe default).

    ``SAFE_NON_LIVE`` returns ``None`` regardless of kwargs; the kwargs do not
    silently flip the mode. The real live manager is never constructed from
    environment values here — operator code or tests must supply it.
    """

    if operator_runtime_mode_from_env(values) != OPERATOR_LIVE_RUNTIME:
        return None
    if producer is not None:
        return producer
    if manager is not None:
        return StreamManagerRuntimeSnapshotProducer(manager)
    if manager_factory is not None:
        return StreamManagerRuntimeSnapshotProducer(manager_factory())
    registered = _REGISTERED_OPERATOR_LIVE_PRODUCER
    if registered is not None:
        return registered
    return UnavailableRuntimeSnapshotProducer()


def resolve_operator_runtime_snapshot(
    *,
    mode: OperatorRuntimeMode | str | None = None,
    producer: RuntimeSnapshotProducer | None = None,
    runtime_snapshot: RuntimeReadinessSnapshot | None = None,
) -> OperatorRuntimeSnapshotResult:
    resolved_mode = _normalize_mode(mode, producer=producer, runtime_snapshot=runtime_snapshot)
    if resolved_mode == SAFE_NON_LIVE:
        return OperatorRuntimeSnapshotResult(
            mode=SAFE_NON_LIVE,
            status=SAFE_NON_LIVE,
            source="fixture_preserved_shell",
            snapshot=None,
            requested_live_runtime=False,
            runtime_cache_derived=False,
            refresh_floor_seconds=MIN_STREAM_REFRESH_FLOOR_SECONDS,
            blocking_reasons=("live_runtime_snapshot_not_requested",),
        )

    active_producer = producer
    if active_producer is None and runtime_snapshot is not None:
        active_producer = StaticRuntimeSnapshotProducer(runtime_snapshot)

    if active_producer is None:
        return _blocking_result(
            status=LIVE_RUNTIME_UNAVAILABLE,
            source="operator_live_runtime_unavailable",
            provider_status="blocked",
            reason="operator_live_runtime_snapshot_unavailable",
        )

    try:
        snapshot = active_producer.read_snapshot()
    except Exception as exc:
        safe_error = redact_sensitive_text(exc)
        return _blocking_result(
            status=LIVE_RUNTIME_ERROR,
            source="operator_live_runtime_producer_error",
            provider_status="error",
            reason=f"operator_live_runtime_producer_error:{type(exc).__name__}",
            producer_error=safe_error,
        )

    if snapshot is None:
        return _blocking_result(
            status=LIVE_RUNTIME_UNAVAILABLE,
            source="operator_live_runtime_unavailable",
            provider_status="blocked",
            reason="operator_live_runtime_snapshot_unavailable",
        )

    return _result_from_snapshot(snapshot)


def _normalize_mode(
    mode: OperatorRuntimeMode | str | None,
    *,
    producer: RuntimeSnapshotProducer | None,
    runtime_snapshot: RuntimeReadinessSnapshot | None,
) -> OperatorRuntimeMode:
    if mode is None:
        return OPERATOR_LIVE_RUNTIME if producer is not None or runtime_snapshot is not None else SAFE_NON_LIVE
    normalized = str(mode).strip().upper()
    if normalized in {"SAFE_NON_LIVE", "NON_LIVE", "FIXTURE", "FIXTURE_SAFE"}:
        return SAFE_NON_LIVE
    if normalized in {"OPERATOR_LIVE_RUNTIME", "LIVE_RUNTIME", "LIVE"}:
        return OPERATOR_LIVE_RUNTIME
    return SAFE_NON_LIVE


def _result_from_snapshot(snapshot: RuntimeReadinessSnapshot) -> OperatorRuntimeSnapshotResult:
    cache = snapshot.cache if isinstance(snapshot, StreamManagerSnapshot) else snapshot
    manager_reasons: tuple[str, ...] = ()
    manager_state: str | None = None
    if isinstance(snapshot, StreamManagerSnapshot):
        manager_reasons = tuple(_safe_reason(reason) for reason in snapshot.blocking_reasons)
        manager_state = str(snapshot.state)

    cache_reasons = tuple(_safe_reason(reason) for reason in cache.blocking_reasons)
    reasons = _dedupe(manager_reasons + cache_reasons)
    provider_status = str(cache.provider_status)
    status: OperatorRuntimeStatus = OPERATOR_LIVE_RUNTIME
    if provider_status == "disabled" or manager_state == "disabled":
        status = LIVE_RUNTIME_DISABLED
    elif manager_state == "reconnecting":
        status = LIVE_RUNTIME_UNAVAILABLE
        reasons = _dedupe(reasons + ("operator_live_runtime_reconnecting",))
    elif provider_status == "stale" or cache.stale_symbols or manager_state == "stale":
        status = LIVE_RUNTIME_STALE
    elif provider_status in {"blocked", "error", "shutdown"} or manager_state in {"blocked", "error", "shutdown"}:
        status = LIVE_RUNTIME_ERROR
    elif not cache.records:
        status = LIVE_RUNTIME_UNAVAILABLE
        reasons = _dedupe(reasons + ("operator_live_runtime_snapshot_unavailable",))
    elif reasons:
        status = LIVE_RUNTIME_ERROR

    return OperatorRuntimeSnapshotResult(
        mode=OPERATOR_LIVE_RUNTIME,
        status=status,
        source="runtime_cache_derived",
        snapshot=snapshot,
        requested_live_runtime=True,
        runtime_cache_derived=True,
        refresh_floor_seconds=MIN_STREAM_REFRESH_FLOOR_SECONDS,
        blocking_reasons=reasons,
        cache_provider_status=provider_status,
        cache_generated_at=cache.generated_at,
        cache_snapshot_ready=cache.ready and not reasons,
    )


def _blocking_result(
    *,
    status: OperatorRuntimeStatus,
    source: str,
    provider_status: ProviderStatus,
    reason: str,
    producer_error: str | None = None,
) -> OperatorRuntimeSnapshotResult:
    blocking_reason = _safe_reason(reason)
    snapshot = _blocking_cache_snapshot(provider_status=provider_status, reason=blocking_reason)
    return OperatorRuntimeSnapshotResult(
        mode=OPERATOR_LIVE_RUNTIME,
        status=status,
        source=source,
        snapshot=snapshot,
        requested_live_runtime=True,
        runtime_cache_derived=True,
        refresh_floor_seconds=MIN_STREAM_REFRESH_FLOOR_SECONDS,
        blocking_reasons=(blocking_reason,),
        cache_provider_status=snapshot.provider_status,
        cache_generated_at=snapshot.generated_at,
        cache_snapshot_ready=False,
        producer_error=producer_error,
    )


def _blocking_cache_snapshot(*, provider_status: ProviderStatus, reason: str) -> StreamCacheSnapshot:
    return StreamCacheSnapshot(
        generated_at=_utc_now_iso(),
        provider="operator_live_runtime",
        provider_status=provider_status,
        cache_max_age_seconds=MIN_STREAM_REFRESH_FLOOR_SECONDS,
        records=(),
        blocking_reasons=(_safe_reason(reason),),
        stale_symbols=(),
    )


def _safe_reason(value: object) -> str:
    return redact_sensitive_text(value).strip() or "operator_live_runtime_blocked"


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = _safe_reason(value)
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return tuple(result)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
