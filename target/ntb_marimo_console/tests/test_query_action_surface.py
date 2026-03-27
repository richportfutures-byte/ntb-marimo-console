from __future__ import annotations

import unittest

from ntb_marimo_console.ui.surfaces.query_action import render_query_action_panel
from ntb_marimo_console.viewmodels.models import ReadinessCardVM, TriggerStatusVM


class QueryActionSurfaceTests(unittest.TestCase):
    def test_query_disabled_when_readiness_blocked(self) -> None:
        trigger_rows = (
            TriggerStatusVM(
                trigger_id="t1",
                is_valid=True,
                is_true=True,
                missing_fields=(),
                invalid_reasons=(),
            ),
        )
        readiness_cards = (
            ReadinessCardVM(
                contract="ES",
                status="blocked",
                event_risk="lockout_active",
                vwap_posture="price_below_vwap",
                value_location="below_value",
                level_proximity="near_prior_day_level",
                hard_lockouts=("event_lockout",),
                awareness_items=(),
                missing_context=(),
            ),
        )

        panel = render_query_action_panel(
            trigger_rows=trigger_rows,
            readiness_cards=readiness_cards,
        )

        self.assertFalse(panel["query_enabled"])
        self.assertFalse(panel["manual_override_available"])


if __name__ == "__main__":
    unittest.main()
