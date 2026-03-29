from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SessionState(str, Enum):
    """Operator-facing workflow states for the Phase 1 integration slice."""

    BOOTSTRAP = "BOOTSTRAP"
    STARTUP_BLOCKED = "STARTUP_BLOCKED"
    STARTUP_READY = "STARTUP_READY"
    LIVE_QUERY_BLOCKED = "LIVE_QUERY_BLOCKED"
    LIVE_QUERY_ELIGIBLE = "LIVE_QUERY_ELIGIBLE"
    QUERY_ACTION_REQUESTED = "QUERY_ACTION_REQUESTED"
    QUERY_ACTION_COMPLETED = "QUERY_ACTION_COMPLETED"
    QUERY_ACTION_FAILED = "QUERY_ACTION_FAILED"
    DECISION_REVIEW_READY = "DECISION_REVIEW_READY"
    AUDIT_REPLAY_READY = "AUDIT_REPLAY_READY"
    REFRESH_REQUESTED = "REFRESH_REQUESTED"
    REFRESH_COMPLETED = "REFRESH_COMPLETED"
    REFRESH_FAILED = "REFRESH_FAILED"
    SESSION_RESET_REQUESTED = "SESSION_RESET_REQUESTED"
    SESSION_RESET_COMPLETED = "SESSION_RESET_COMPLETED"
    PROFILE_SWITCH_REQUESTED = "PROFILE_SWITCH_REQUESTED"
    PROFILE_SWITCH_VALIDATING = "PROFILE_SWITCH_VALIDATING"
    PROFILE_SWITCH_COMPLETED = "PROFILE_SWITCH_COMPLETED"
    PROFILE_SWITCH_BLOCKED = "PROFILE_SWITCH_BLOCKED"
    PROFILE_SWITCH_FAILED = "PROFILE_SWITCH_FAILED"
    ERROR = "ERROR"


_ALLOWED_TRANSITIONS: dict[SessionState, set[SessionState]] = {
    SessionState.BOOTSTRAP: {
        SessionState.STARTUP_BLOCKED,
        SessionState.STARTUP_READY,
        SessionState.ERROR,
    },
    SessionState.STARTUP_BLOCKED: {
        SessionState.REFRESH_REQUESTED,
        SessionState.PROFILE_SWITCH_REQUESTED,
        SessionState.ERROR,
    },
    SessionState.STARTUP_READY: {
        SessionState.LIVE_QUERY_BLOCKED,
        SessionState.LIVE_QUERY_ELIGIBLE,
        SessionState.REFRESH_REQUESTED,
        SessionState.SESSION_RESET_REQUESTED,
        SessionState.PROFILE_SWITCH_REQUESTED,
        SessionState.ERROR,
    },
    SessionState.LIVE_QUERY_BLOCKED: {
        SessionState.LIVE_QUERY_ELIGIBLE,
        SessionState.QUERY_ACTION_FAILED,
        SessionState.REFRESH_REQUESTED,
        SessionState.SESSION_RESET_REQUESTED,
        SessionState.PROFILE_SWITCH_REQUESTED,
        SessionState.ERROR,
    },
    SessionState.LIVE_QUERY_ELIGIBLE: {
        SessionState.QUERY_ACTION_REQUESTED,
        SessionState.QUERY_ACTION_FAILED,
        SessionState.REFRESH_REQUESTED,
        SessionState.SESSION_RESET_REQUESTED,
        SessionState.PROFILE_SWITCH_REQUESTED,
        SessionState.ERROR,
    },
    SessionState.QUERY_ACTION_REQUESTED: {
        SessionState.QUERY_ACTION_COMPLETED,
        SessionState.QUERY_ACTION_FAILED,
        SessionState.ERROR,
    },
    SessionState.QUERY_ACTION_COMPLETED: {
        SessionState.DECISION_REVIEW_READY,
        SessionState.REFRESH_REQUESTED,
        SessionState.SESSION_RESET_REQUESTED,
        SessionState.PROFILE_SWITCH_REQUESTED,
        SessionState.ERROR,
    },
    SessionState.QUERY_ACTION_FAILED: {
        SessionState.REFRESH_REQUESTED,
        SessionState.SESSION_RESET_REQUESTED,
        SessionState.PROFILE_SWITCH_REQUESTED,
        SessionState.ERROR,
    },
    SessionState.DECISION_REVIEW_READY: {
        SessionState.AUDIT_REPLAY_READY,
        SessionState.REFRESH_REQUESTED,
        SessionState.SESSION_RESET_REQUESTED,
        SessionState.PROFILE_SWITCH_REQUESTED,
        SessionState.ERROR,
    },
    SessionState.AUDIT_REPLAY_READY: {
        SessionState.REFRESH_REQUESTED,
        SessionState.SESSION_RESET_REQUESTED,
        SessionState.LIVE_QUERY_BLOCKED,
        SessionState.LIVE_QUERY_ELIGIBLE,
        SessionState.PROFILE_SWITCH_REQUESTED,
        SessionState.ERROR,
    },
    SessionState.REFRESH_REQUESTED: {
        SessionState.REFRESH_COMPLETED,
        SessionState.REFRESH_FAILED,
        SessionState.ERROR,
    },
    SessionState.REFRESH_COMPLETED: {
        SessionState.STARTUP_READY,
        SessionState.LIVE_QUERY_BLOCKED,
        SessionState.LIVE_QUERY_ELIGIBLE,
        SessionState.PROFILE_SWITCH_REQUESTED,
        SessionState.ERROR,
    },
    SessionState.REFRESH_FAILED: {
        SessionState.REFRESH_REQUESTED,
        SessionState.PROFILE_SWITCH_REQUESTED,
        SessionState.ERROR,
    },
    SessionState.SESSION_RESET_REQUESTED: {
        SessionState.SESSION_RESET_COMPLETED,
        SessionState.ERROR,
    },
    SessionState.SESSION_RESET_COMPLETED: {
        SessionState.STARTUP_READY,
        SessionState.LIVE_QUERY_BLOCKED,
        SessionState.LIVE_QUERY_ELIGIBLE,
        SessionState.PROFILE_SWITCH_REQUESTED,
        SessionState.ERROR,
    },
    SessionState.PROFILE_SWITCH_REQUESTED: {
        SessionState.PROFILE_SWITCH_VALIDATING,
        SessionState.ERROR,
    },
    SessionState.PROFILE_SWITCH_VALIDATING: {
        SessionState.PROFILE_SWITCH_COMPLETED,
        SessionState.PROFILE_SWITCH_BLOCKED,
        SessionState.PROFILE_SWITCH_FAILED,
        SessionState.ERROR,
    },
    SessionState.PROFILE_SWITCH_COMPLETED: {
        SessionState.STARTUP_READY,
        SessionState.LIVE_QUERY_BLOCKED,
        SessionState.LIVE_QUERY_ELIGIBLE,
        SessionState.ERROR,
    },
    SessionState.PROFILE_SWITCH_BLOCKED: {
        SessionState.PROFILE_SWITCH_REQUESTED,
        SessionState.REFRESH_REQUESTED,
        SessionState.SESSION_RESET_REQUESTED,
        SessionState.ERROR,
    },
    SessionState.PROFILE_SWITCH_FAILED: {
        SessionState.PROFILE_SWITCH_REQUESTED,
        SessionState.REFRESH_REQUESTED,
        SessionState.ERROR,
    },
    SessionState.ERROR: {
        SessionState.REFRESH_REQUESTED,
        SessionState.SESSION_RESET_REQUESTED,
        SessionState.PROFILE_SWITCH_REQUESTED,
    },
}


@dataclass
class OperatorSessionMachine:
    """Phase 1 transition guard for session-state wiring.

    No manual override state exists in this machine.
    """

    state: SessionState = SessionState.BOOTSTRAP
    _history: list[SessionState] = field(default_factory=lambda: [SessionState.BOOTSTRAP], init=False, repr=False)

    @classmethod
    def from_history(cls, history: tuple[SessionState, ...]) -> OperatorSessionMachine:
        if not history:
            raise ValueError("Session history must contain at least one state.")
        machine = cls()
        first_state = history[0]
        if first_state != SessionState.BOOTSTRAP:
            raise ValueError("Session history must begin with BOOTSTRAP.")
        for state in history[1:]:
            machine.transition(state)
        return machine

    def transition(self, next_state: SessionState) -> None:
        allowed = _ALLOWED_TRANSITIONS[self.state]
        if next_state not in allowed:
            raise ValueError(f"Illegal transition {self.state.value} -> {next_state.value}.")
        self.state = next_state
        self._history.append(next_state)

    def mark_startup_blocked(self) -> None:
        self.transition(SessionState.STARTUP_BLOCKED)

    def mark_startup_ready(self) -> None:
        self.transition(SessionState.STARTUP_READY)

    def mark_live_query_blocked(self) -> None:
        self.transition(SessionState.LIVE_QUERY_BLOCKED)

    def mark_live_query_eligible(self) -> None:
        self.transition(SessionState.LIVE_QUERY_ELIGIBLE)

    def mark_query_action_requested(self) -> None:
        self.transition(SessionState.QUERY_ACTION_REQUESTED)

    def mark_query_action_completed(self) -> None:
        self.transition(SessionState.QUERY_ACTION_COMPLETED)

    def mark_query_action_failed(self) -> None:
        self.transition(SessionState.QUERY_ACTION_FAILED)

    def mark_decision_review_ready(self) -> None:
        self.transition(SessionState.DECISION_REVIEW_READY)

    def mark_audit_replay_ready(self) -> None:
        self.transition(SessionState.AUDIT_REPLAY_READY)

    def mark_refresh_requested(self) -> None:
        self.transition(SessionState.REFRESH_REQUESTED)

    def mark_refresh_completed(self) -> None:
        self.transition(SessionState.REFRESH_COMPLETED)

    def mark_refresh_failed(self) -> None:
        self.transition(SessionState.REFRESH_FAILED)

    def mark_session_reset_requested(self) -> None:
        self.transition(SessionState.SESSION_RESET_REQUESTED)

    def mark_session_reset_completed(self) -> None:
        self.transition(SessionState.SESSION_RESET_COMPLETED)

    def mark_profile_switch_requested(self) -> None:
        self.transition(SessionState.PROFILE_SWITCH_REQUESTED)

    def mark_profile_switch_validating(self) -> None:
        self.transition(SessionState.PROFILE_SWITCH_VALIDATING)

    def mark_profile_switch_completed(self) -> None:
        self.transition(SessionState.PROFILE_SWITCH_COMPLETED)

    def mark_profile_switch_blocked(self) -> None:
        self.transition(SessionState.PROFILE_SWITCH_BLOCKED)

    def mark_profile_switch_failed(self) -> None:
        self.transition(SessionState.PROFILE_SWITCH_FAILED)

    def mark_error(self) -> None:
        if self.state == SessionState.ERROR:
            return
        if SessionState.ERROR in _ALLOWED_TRANSITIONS[self.state]:
            self.transition(SessionState.ERROR)
            return
        self.state = SessionState.ERROR
        self._history.append(SessionState.ERROR)

    @property
    def query_enabled(self) -> bool:
        return self.state == SessionState.LIVE_QUERY_ELIGIBLE

    @property
    def state_history(self) -> tuple[SessionState, ...]:
        return tuple(self._history)
