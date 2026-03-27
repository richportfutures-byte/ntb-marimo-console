from __future__ import annotations

import unittest
from pathlib import Path

from ntb_marimo_console.runtime_profiles import (
    RuntimeProfile,
    RuntimeProfileError,
    get_runtime_profile,
    list_runtime_profiles,
)


class RuntimeProfilesTests(unittest.TestCase):
    def test_supported_profile_selection_succeeds(self) -> None:
        profile = get_runtime_profile("preserved_es_phase1")

        self.assertEqual(profile.profile_id, "preserved_es_phase1")
        self.assertEqual(profile.runtime_mode, "preserved_engine")
        self.assertEqual(profile.contract, "ES")

    def test_second_preserved_profile_selection_succeeds(self) -> None:
        profile = get_runtime_profile("preserved_zn_phase1")

        self.assertEqual(profile.profile_id, "preserved_zn_phase1")
        self.assertEqual(profile.runtime_mode, "preserved_engine")
        self.assertEqual(profile.contract, "ZN")
        self.assertEqual(profile.artifact_contract_dir, "ZN")

    def test_unsupported_profile_fails_closed(self) -> None:
        with self.assertRaises(RuntimeProfileError):
            get_runtime_profile("unknown_profile")

    def test_malformed_profile_definition_fails_closed(self) -> None:
        broken_profile = RuntimeProfile(
            profile_id="broken_preserved",
            runtime_mode="preserved_engine",
            contract="ES",
            session_date="2026-03-25",
            evaluation_timestamp_iso="2026-03-25T09:35:00-04:00",
            artifact_root_relative=Path("."),
            artifact_contract_dir="ES",
            readiness_trigger={"trigger_family": "price_level_touch"},
            default_model_adapter_ref=None,
        )

        with self.assertRaises(RuntimeProfileError):
            get_runtime_profile(
                "broken_preserved",
                registry={"broken_preserved": broken_profile},
            )

    def test_registry_listing_is_valid_and_stable(self) -> None:
        profiles = list_runtime_profiles()

        self.assertEqual(
            tuple(profile.profile_id for profile in profiles),
            ("fixture_es_demo", "preserved_es_phase1", "preserved_zn_phase1"),
        )


if __name__ == "__main__":
    unittest.main()
