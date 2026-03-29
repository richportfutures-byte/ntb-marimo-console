from __future__ import annotations

import unittest

from ntb_marimo_console.state.session_state import OperatorSessionMachine, SessionState


class SessionStateTests(unittest.TestCase):
    def test_query_enabled_only_when_live_query_eligible(self) -> None:
        machine = OperatorSessionMachine()
        machine.mark_startup_ready()
        machine.mark_live_query_blocked()
        self.assertFalse(machine.query_enabled)
        machine.mark_live_query_eligible()
        self.assertTrue(machine.query_enabled)

    def test_illegal_transition_rejected(self) -> None:
        machine = OperatorSessionMachine()
        with self.assertRaises(ValueError):
            machine.transition(SessionState.DECISION_REVIEW_READY)

    def test_state_history_tracks_real_operator_workflow(self) -> None:
        machine = OperatorSessionMachine()
        machine.mark_startup_ready()
        machine.mark_live_query_eligible()
        machine.mark_query_action_requested()
        machine.mark_query_action_completed()
        machine.mark_decision_review_ready()
        machine.mark_audit_replay_ready()

        self.assertEqual(
            machine.state_history,
            (
                SessionState.BOOTSTRAP,
                SessionState.STARTUP_READY,
                SessionState.LIVE_QUERY_ELIGIBLE,
                SessionState.QUERY_ACTION_REQUESTED,
                SessionState.QUERY_ACTION_COMPLETED,
                SessionState.DECISION_REVIEW_READY,
                SessionState.AUDIT_REPLAY_READY,
            ),
        )

    def test_query_action_failure_transition_is_explicit(self) -> None:
        machine = OperatorSessionMachine()
        machine.mark_startup_ready()
        machine.mark_live_query_eligible()
        machine.mark_query_action_requested()
        machine.mark_query_action_failed()

        self.assertEqual(machine.state, SessionState.QUERY_ACTION_FAILED)
        self.assertIn(SessionState.QUERY_ACTION_FAILED, machine.state_history)

    def test_refresh_and_reset_transitions_are_explicit(self) -> None:
        machine = OperatorSessionMachine()
        machine.mark_startup_ready()
        machine.mark_live_query_eligible()
        machine.mark_query_action_requested()
        machine.mark_query_action_completed()
        machine.mark_decision_review_ready()
        machine.mark_audit_replay_ready()
        machine.mark_session_reset_requested()
        machine.mark_session_reset_completed()
        machine.mark_startup_ready()
        machine.mark_live_query_eligible()
        machine.mark_refresh_requested()
        machine.mark_refresh_completed()
        machine.mark_startup_ready()
        machine.mark_live_query_eligible()

        self.assertEqual(machine.state, SessionState.LIVE_QUERY_ELIGIBLE)
        self.assertIn(SessionState.SESSION_RESET_REQUESTED, machine.state_history)
        self.assertIn(SessionState.SESSION_RESET_COMPLETED, machine.state_history)
        self.assertIn(SessionState.REFRESH_REQUESTED, machine.state_history)
        self.assertIn(SessionState.REFRESH_COMPLETED, machine.state_history)

    def test_profile_switch_transitions_are_explicit(self) -> None:
        machine = OperatorSessionMachine()
        machine.mark_startup_ready()
        machine.mark_live_query_eligible()
        machine.mark_query_action_requested()
        machine.mark_query_action_completed()
        machine.mark_decision_review_ready()
        machine.mark_audit_replay_ready()
        machine.mark_profile_switch_requested()
        machine.mark_profile_switch_validating()
        machine.mark_profile_switch_completed()
        machine.mark_startup_ready()
        machine.mark_live_query_eligible()

        self.assertEqual(machine.state, SessionState.LIVE_QUERY_ELIGIBLE)
        self.assertIn(SessionState.PROFILE_SWITCH_REQUESTED, machine.state_history)
        self.assertIn(SessionState.PROFILE_SWITCH_VALIDATING, machine.state_history)
        self.assertIn(SessionState.PROFILE_SWITCH_COMPLETED, machine.state_history)

    def test_machine_can_resume_from_existing_history(self) -> None:
        machine = OperatorSessionMachine()
        machine.mark_startup_ready()
        machine.mark_live_query_eligible()

        resumed = OperatorSessionMachine.from_history(machine.state_history)
        resumed.mark_query_action_requested()

        self.assertEqual(resumed.state, SessionState.QUERY_ACTION_REQUESTED)
        self.assertEqual(
            resumed.state_history,
            (
                SessionState.BOOTSTRAP,
                SessionState.STARTUP_READY,
                SessionState.LIVE_QUERY_ELIGIBLE,
                SessionState.QUERY_ACTION_REQUESTED,
            ),
        )

    def test_manual_override_state_not_present(self) -> None:
        self.assertFalse(hasattr(SessionState, "MANUAL_OVERRIDE"))


if __name__ == "__main__":
    unittest.main()
