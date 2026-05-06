from __future__ import annotations

import unittest

from ntb_marimo_console.contract_universe import (
    excluded_final_target_contracts,
    final_target_contracts,
    is_excluded_final_target_contract,
    is_final_target_contract,
    is_legacy_historical_contract,
    is_never_supported_contract,
    legacy_historical_contracts,
    never_supported_contracts,
)
from ntb_marimo_console.runtime_profiles import get_runtime_profile, list_runtime_profiles


class ContractUniverseTests(unittest.TestCase):
    def test_final_target_contracts_are_exact(self) -> None:
        self.assertEqual(final_target_contracts(), ("ES", "NQ", "CL", "6E", "MGC"))

    def test_excluded_contracts_include_zn_and_gc(self) -> None:
        self.assertEqual(excluded_final_target_contracts(), ("ZN", "GC"))
        self.assertTrue(is_excluded_final_target_contract("ZN"))
        self.assertTrue(is_excluded_final_target_contract("GC"))

    def test_zn_is_legacy_historical_not_final_target(self) -> None:
        self.assertEqual(legacy_historical_contracts(), ("ZN",))
        self.assertTrue(is_legacy_historical_contract("ZN"))
        self.assertFalse(is_final_target_contract("ZN"))

    def test_gc_is_never_supported_excluded(self) -> None:
        self.assertEqual(never_supported_contracts(), ("GC",))
        self.assertTrue(is_never_supported_contract("GC"))
        self.assertFalse(is_final_target_contract("GC"))

    def test_mgc_is_final_target_and_not_gc(self) -> None:
        self.assertTrue(is_final_target_contract("MGC"))
        self.assertFalse(is_final_target_contract("GC"))
        self.assertFalse(is_never_supported_contract("MGC"))

    def test_final_target_universe_does_not_depend_on_engine_or_runtime_deletion(self) -> None:
        profile_ids = {profile.profile_id for profile in list_runtime_profiles()}

        self.assertIn("preserved_zn_phase1", profile_ids)
        self.assertEqual(get_runtime_profile("preserved_zn_phase1").contract, "ZN")
        self.assertNotIn("ZN", final_target_contracts())


if __name__ == "__main__":
    unittest.main()
