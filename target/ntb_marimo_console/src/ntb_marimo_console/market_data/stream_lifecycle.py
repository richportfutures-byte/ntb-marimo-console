from __future__ import annotations

from typing import Final, Literal


StreamLifecycleState = Literal[
    "disabled",
    "initialized",
    "connecting",
    "login_pending",
    "connected",
    "subscribing",
    "active",
    "reconnecting",
    "stale",
    "disconnected",
    "error",
    "blocked",
    "shutdown",
]

STREAM_LIFECYCLE_STATES: Final[tuple[StreamLifecycleState, ...]] = (
    "disabled",
    "initialized",
    "connecting",
    "login_pending",
    "connected",
    "subscribing",
    "active",
    "reconnecting",
    "stale",
    "disconnected",
    "error",
    "blocked",
    "shutdown",
)

FAIL_CLOSED_STATES: Final[tuple[StreamLifecycleState, ...]] = (
    "disabled",
    "reconnecting",
    "stale",
    "disconnected",
    "error",
    "blocked",
    "shutdown",
)


def is_fail_closed_state(state: StreamLifecycleState) -> bool:
    return state in FAIL_CLOSED_STATES
