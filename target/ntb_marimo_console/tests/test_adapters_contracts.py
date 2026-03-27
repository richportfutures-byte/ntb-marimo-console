from __future__ import annotations

import unittest

from ntb_marimo_console.adapters.contracts import (
    LIVE_OBSERVABLE_FIELD_PATHS,
    SessionTarget,
    TriggerSpec,
)
from ntb_marimo_console.adapters.run_history_store import FixtureRunHistoryStore


class AdapterContractTests(unittest.TestCase):
    def test_trigger_spec_requires_explicit_dependencies(self) -> None:
        spec = TriggerSpec(
            id="x",
            predicate="market.current_price > 0",
            required_live_field_paths=("market.current_price",),
            source_brief_trigger_id="x",
        )
        self.assertEqual(spec.required_live_field_paths, ("market.current_price",))

    def test_run_history_store_fixture_scope(self) -> None:
        store = FixtureRunHistoryStore(
            "fixtures/golden/phase1"
        )
        rows = store.list_rows(SessionTarget(contract="ES", session_date="2026-03-25"))
        self.assertGreaterEqual(len(rows), 1)
        self.assertIsInstance(rows[0], dict)

    def test_live_observable_authority_contains_required_paths(self) -> None:
        self.assertIn("market.current_price", LIVE_OBSERVABLE_FIELD_PATHS)
        self.assertIn("market.cumulative_delta", LIVE_OBSERVABLE_FIELD_PATHS)


if __name__ == "__main__":
    unittest.main()
