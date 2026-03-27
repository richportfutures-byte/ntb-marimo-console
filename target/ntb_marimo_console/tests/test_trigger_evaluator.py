from __future__ import annotations

import unittest

from ntb_marimo_console.adapters.contracts import TriggerSpec
from ntb_marimo_console.adapters.trigger_evaluator import TriggerEvaluator


class TriggerEvaluatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluator = TriggerEvaluator()

    def test_evaluates_declared_dotted_dependencies(self) -> None:
        spec = TriggerSpec(
            id="t1",
            predicate="market.current_price >= 5604 AND market.cumulative_delta > 0",
            required_live_field_paths=("market.current_price", "market.cumulative_delta"),
            source_brief_trigger_id="t1",
        )
        snapshot = {"market": {"current_price": 5605.0, "cumulative_delta": 10.0}}

        bundle = self.evaluator.evaluate([spec], snapshot)

        self.assertTrue(bundle.query_gate_true)
        self.assertTrue(bundle.evaluations[0].is_valid)

    def test_fails_closed_on_missing_dependency(self) -> None:
        spec = TriggerSpec(
            id="t2",
            predicate="market.current_price >= 5604",
            required_live_field_paths=("market.current_price",),
            source_brief_trigger_id="t2",
        )
        snapshot = {"market": {}}

        bundle = self.evaluator.evaluate([spec], snapshot)

        self.assertFalse(bundle.query_gate_true)
        self.assertFalse(bundle.evaluations[0].is_valid)

    def test_rejects_unknown_declared_live_field_path(self) -> None:
        spec = TriggerSpec(
            id="t4",
            predicate="market.unknown_field > 0",
            required_live_field_paths=("market.unknown_field",),
            source_brief_trigger_id="t4",
        )
        snapshot = {"market": {"unknown_field": 1.0}}

        bundle = self.evaluator.evaluate([spec], snapshot)

        self.assertFalse(bundle.query_gate_true)
        self.assertFalse(bundle.evaluations[0].is_valid)

    def test_rejects_undeclared_field_reference(self) -> None:
        spec = TriggerSpec(
            id="t3",
            predicate="market.current_price >= 5604 AND cross_asset.breadth.current_advancers_pct > 0.55",
            required_live_field_paths=("market.current_price",),
            source_brief_trigger_id="t3",
        )
        snapshot = {
            "market": {"current_price": 5605.0},
            "cross_asset": {"breadth": {"current_advancers_pct": 0.6}},
        }

        bundle = self.evaluator.evaluate([spec], snapshot)

        self.assertFalse(bundle.query_gate_true)
        self.assertFalse(bundle.evaluations[0].is_valid)


if __name__ == "__main__":
    unittest.main()
