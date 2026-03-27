from __future__ import annotations

import unittest

from ntb_marimo_console.adapters.contracts import OperatorRuntimeInputs, PreMarketArtifacts
from ntb_marimo_console.adapters.premarket_store import FixturePreMarketArtifactStore
from ntb_marimo_console.demo_fixture_runtime import build_es_runtime_inputs


class PayloadContractStabilityTests(unittest.TestCase):
    def test_runtime_inputs_use_named_dataclass_contracts(self) -> None:
        inputs = build_es_runtime_inputs("fixtures/golden/phase1", mode="fixture_demo")

        self.assertIsInstance(inputs, OperatorRuntimeInputs)
        self.assertEqual(inputs.selection.mode, "fixture_demo")
        self.assertEqual(inputs.selection.profile_id, "fixture_es_demo")
        self.assertEqual(inputs.selection.session.contract, "ES")
        self.assertEqual(inputs.pipeline_query.contract, "ES")

    def test_premarket_store_returns_named_artifact_bundle(self) -> None:
        store = FixturePreMarketArtifactStore("fixtures/golden/phase1")
        session = build_es_runtime_inputs("fixtures/golden/phase1").selection.session
        artifacts = store.load(session)

        self.assertIsInstance(artifacts, PreMarketArtifacts)
        self.assertEqual(artifacts.packet["contract"], session.contract)
        self.assertEqual(artifacts.brief["contract"], session.contract)


if __name__ == "__main__":
    unittest.main()
