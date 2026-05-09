"""Tests for Decision Review narrative surfacing (Companion Blueprint Initiative 1).

These tests cover four invariants:

1. The mapper extracts engine narrative verbatim from a preserved-engine
   PipelineNarrative payload, with no derivation, ranking, or string parsing.
2. The mapper tolerates absent/partial narrative without crashing.
3. The Decision Review surface renders narrative sections when present.
4. The Decision Review surface marks narrative sections as explicitly
   unavailable when absent, never as empty success. NO_TRADE renders as a
   first-class outcome with no alternate-trade prose.
"""

from __future__ import annotations

import unittest

from ntb_marimo_console.adapters.contracts import PipelineNarrative, PipelineSummary
from ntb_marimo_console.decision_review_audit import DECISION_REVIEW_AUDIT_EVENT_SCHEMA
from ntb_marimo_console.ui.surfaces.decision_review import (
    DISQUALIFIERS_UNAVAILABLE_DETAIL,
    NARRATIVE_UNAVAILABLE_DETAIL,
    render_decision_review_panel,
)
from ntb_marimo_console.viewmodels.mappers import pipeline_trace_vm_from_summary
from ntb_marimo_console.viewmodels.models import (
    NARRATIVE_UNAVAILABLE_LABEL,
    PipelineTraceVM,
)


def _approved_summary() -> PipelineSummary:
    return {
        "contract": "ES",
        "termination_stage": "risk_authorization",
        "final_decision": "TRADE_APPROVED",
        "sufficiency_gate_status": "READY",
        "contract_analysis_outcome": "ANALYSIS_COMPLETE",
        "proposed_setup_outcome": "SETUP_PROPOSED",
        "risk_authorization_decision": "APPROVED",
    }


def _no_trade_summary() -> PipelineSummary:
    return {
        "contract": "ES",
        "termination_stage": "contract_market_read",
        "final_decision": "NO_TRADE",
        "sufficiency_gate_status": "READY",
        "contract_analysis_outcome": "NO_TRADE",
        "proposed_setup_outcome": None,
        "risk_authorization_decision": None,
    }


def _full_narrative() -> PipelineNarrative:
    return {
        "contract_analysis": {
            "contract": "ES",
            "market_regime": "trending_up",
            "directional_bias": "bullish",
            "evidence_score": 7,
            "confidence_band": "HIGH",
            "structural_notes": (
                "ES bullish above weekly pivot 5604.50 with breadth 67%; "
                "watching for acceptance above resistance 5612 to confirm "
                "continuation, invalidates on close below 5598."
            ),
            "outcome": "ANALYSIS_COMPLETE",
            "conflicting_signals": [
                "delta divergence: positive bias contradicted by cumulative_delta -1450 (cumulative_delta)",
            ],
            "assumptions": [
                "Breadth holds above 60 percent through the next two bars (breadth)",
            ],
            "key_levels": {
                "pivot_level": 5604.5,
                "support_levels": [5598.0, 5594.25],
                "resistance_levels": [5612.0, 5618.5, 5624.0],
            },
        },
        "proposed_setup": {
            "outcome": "SETUP_PROPOSED",
            "no_trade_reason": None,
            "direction": "LONG",
            "setup_class": "intraday_swing",
            "entry_price": 5605.0,
            "stop_price": 5598.0,
            "target_1": 5612.0,
            "target_2": 5618.5,
            "position_size": 2,
            "risk_dollars": 700.0,
            "reward_risk_ratio": 2.1,
            "hold_time_estimate_minutes": 60,
            "rationale": (
                "Entry at 5605 is justified by ES bullish bias above weekly pivot "
                "with breadth 67%; stop at 5598 sits below structural support; "
                "target_1 5612 corresponds to nearest resistance from key_levels; "
                "intraday_swing fits trending_up regime; setup invalidates if "
                "breadth_below_55 or es_close_below_5598."
            ),
            "disqualifiers": [
                "stop_distance_unusually_wide",
                "breadth_below_55",
                "es_close_below_invalidation_anchor",
            ],
            "sizing_math": {
                "stop_distance_ticks": 28.0,
                "risk_per_tick": 12.5,
                "raw_risk_dollars": 700.0,
                "slippage_cost_dollars": 25.0,
                "adjusted_risk_dollars": 725.0,
                "blended_target_distance_ticks": 56.0,
                "blended_reward_dollars": 1400.0,
            },
        },
        "risk_authorization": {
            "decision": "APPROVED",
            "checks": [
                {"check_id": 1, "check_name": "daily_loss_stop", "passed": True, "detail": "$0 / $10000 today"},
                {"check_id": 2, "check_name": "per_trade_risk_cap", "passed": True, "detail": "$725 <= $1450"},
                {"check_id": 3, "check_name": "aggregate_open_risk", "passed": True, "detail": "$725 <= $40000"},
                {"check_id": 4, "check_name": "position_size_limit", "passed": True, "detail": "2 <= 2"},
                {"check_id": 5, "check_name": "per_contract_position_limit", "passed": True, "detail": "ES: 2/2"},
                {"check_id": 6, "check_name": "max_trades_today_all", "passed": True, "detail": "1/60"},
                {"check_id": 7, "check_name": "max_trades_today_contract", "passed": True, "detail": "ES: 1/3"},
                {"check_id": 8, "check_name": "event_lockout_recheck", "passed": True, "detail": "no Tier-1 events in window"},
                {"check_id": 9, "check_name": "cooldown_after_stopout", "passed": True, "detail": "no recent stop-out"},
                {"check_id": 10, "check_name": "opposite_direction_flip", "passed": True, "detail": "no prior trade direction"},
                {"check_id": 11, "check_name": "session_hours", "passed": True, "detail": "within ES allowed hours"},
                {"check_id": 12, "check_name": "overnight_hold_risk", "passed": True, "detail": "exit before session end"},
                {"check_id": 13, "check_name": "minimum_reward_risk", "passed": True, "detail": "2.1 >= 1.5"},
            ],
            "rejection_reasons": [],
            "adjusted_position_size": None,
            "adjusted_risk_dollars": None,
            "remaining_daily_risk_budget": 9275.0,
            "remaining_aggregate_risk_budget": 39275.0,
        },
    }


def _no_trade_narrative() -> PipelineNarrative:
    return {
        "contract_analysis": {
            "contract": "ES",
            "market_regime": "choppy",
            "directional_bias": "unclear",
            "evidence_score": 3,
            "confidence_band": "LOW",
            "structural_notes": (
                "ES choppy near VWAP with breadth 52%; no clean structural "
                "anchor; awaiting resolution of overnight range."
            ),
            "outcome": "NO_TRADE",
            "conflicting_signals": [
                "delta divergence: bullish price contradicted by cumulative_delta -2100 (cumulative_delta)",
                "breadth weakness: bullish bias contradicted by breadth=52 (breadth)",
            ],
            "assumptions": [],
            "key_levels": {
                "pivot_level": 5602.0,
                "support_levels": [5598.0],
                "resistance_levels": [5606.0],
            },
        },
        "proposed_setup": None,
        "risk_authorization": None,
    }


class PipelineTraceMapperTests(unittest.TestCase):
    def test_summary_only_yields_no_narrative_and_explicit_unavailable_flag(self) -> None:
        trace = pipeline_trace_vm_from_summary(_approved_summary(), narrative=None)

        self.assertEqual(trace.contract, "ES")
        self.assertEqual(trace.final_decision, "TRADE_APPROVED")
        self.assertFalse(trace.narrative_available)
        self.assertIsNone(trace.engine_reasoning)
        self.assertIsNone(trace.key_levels)
        self.assertIsNone(trace.trade_thesis)
        self.assertIsNone(trace.risk_authorization)

    def test_default_narrative_argument_preserves_legacy_callsites(self) -> None:
        trace = pipeline_trace_vm_from_summary(_approved_summary())

        self.assertFalse(trace.narrative_available)
        self.assertIsNone(trace.trade_thesis)

    def test_full_narrative_extracts_engine_reasoning_verbatim(self) -> None:
        trace = pipeline_trace_vm_from_summary(_approved_summary(), narrative=_full_narrative())

        self.assertTrue(trace.narrative_available)
        reasoning = trace.engine_reasoning
        assert reasoning is not None  # for type checker
        self.assertEqual(reasoning.market_regime, "trending_up")
        self.assertEqual(reasoning.directional_bias, "bullish")
        self.assertEqual(reasoning.evidence_score, 7)
        self.assertEqual(reasoning.confidence_band, "HIGH")
        self.assertEqual(reasoning.outcome, "ANALYSIS_COMPLETE")
        # structural_notes carried verbatim
        self.assertIsNotNone(reasoning.structural_notes)
        assert reasoning.structural_notes is not None
        self.assertIn("5604.50", reasoning.structural_notes)
        self.assertIn("breadth 67%", reasoning.structural_notes)
        self.assertEqual(len(reasoning.conflicting_signals), 1)
        self.assertEqual(len(reasoning.assumptions), 1)

    def test_full_narrative_extracts_key_levels(self) -> None:
        trace = pipeline_trace_vm_from_summary(_approved_summary(), narrative=_full_narrative())

        key_levels = trace.key_levels
        assert key_levels is not None
        self.assertEqual(key_levels.pivot_level, 5604.5)
        self.assertEqual(key_levels.support_levels, (5598.0, 5594.25))
        self.assertEqual(key_levels.resistance_levels, (5612.0, 5618.5, 5624.0))

    def test_full_narrative_extracts_trade_thesis_and_sizing_math(self) -> None:
        trace = pipeline_trace_vm_from_summary(_approved_summary(), narrative=_full_narrative())

        thesis = trace.trade_thesis
        assert thesis is not None
        self.assertEqual(thesis.outcome, "SETUP_PROPOSED")
        self.assertEqual(thesis.direction, "LONG")
        self.assertEqual(thesis.setup_class, "intraday_swing")
        self.assertEqual(thesis.entry_price, 5605.0)
        self.assertEqual(thesis.stop_price, 5598.0)
        self.assertEqual(thesis.target_1, 5612.0)
        self.assertEqual(thesis.target_2, 5618.5)
        self.assertEqual(thesis.position_size, 2)
        self.assertEqual(thesis.reward_risk_ratio, 2.1)
        self.assertIsNotNone(thesis.rationale)
        # disqualifiers must include the monitorable shapes the engine emitted
        self.assertIn("breadth_below_55", thesis.disqualifiers)
        self.assertIn("stop_distance_unusually_wide", thesis.disqualifiers)
        # sizing_math carried verbatim
        sm = thesis.sizing_math
        assert sm is not None
        self.assertEqual(sm.adjusted_risk_dollars, 725.0)
        self.assertEqual(sm.blended_reward_dollars, 1400.0)

    def test_full_narrative_extracts_risk_authorization_thirteen_checks(self) -> None:
        trace = pipeline_trace_vm_from_summary(_approved_summary(), narrative=_full_narrative())

        risk = trace.risk_authorization
        assert risk is not None
        self.assertEqual(risk.decision, "APPROVED")
        self.assertEqual(len(risk.checks), 13)
        check_ids = [c.check_id for c in risk.checks]
        self.assertEqual(check_ids, list(range(1, 14)))
        for check in risk.checks:
            self.assertIsInstance(check.check_name, str)
            self.assertNotEqual(check.check_name, "")
            self.assertIsInstance(check.passed, bool)
            self.assertIsInstance(check.detail, str)
        self.assertEqual(risk.rejection_reasons, ())

    def test_partial_narrative_stage_b_only_does_not_crash(self) -> None:
        narrative: PipelineNarrative = {
            "contract_analysis": _full_narrative()["contract_analysis"],
            "proposed_setup": None,
            "risk_authorization": None,
        }
        trace = pipeline_trace_vm_from_summary(_approved_summary(), narrative=narrative)

        self.assertTrue(trace.narrative_available)
        self.assertIsNotNone(trace.engine_reasoning)
        self.assertIsNone(trace.trade_thesis)
        self.assertIsNone(trace.risk_authorization)

    def test_no_trade_narrative_drops_stage_c_and_stage_d_cleanly(self) -> None:
        trace = pipeline_trace_vm_from_summary(_no_trade_summary(), narrative=_no_trade_narrative())

        self.assertEqual(trace.final_decision, "NO_TRADE")
        self.assertTrue(trace.narrative_available)
        self.assertIsNotNone(trace.engine_reasoning)
        self.assertIsNone(trace.trade_thesis)
        self.assertIsNone(trace.risk_authorization)

    def test_malformed_narrative_fields_are_dropped_not_inferred(self) -> None:
        narrative: PipelineNarrative = {
            "contract_analysis": {
                "market_regime": "trending_up",
                "directional_bias": "bullish",
                "evidence_score": "not-an-int",
                "confidence_band": "HIGH",
                "structural_notes": "",
                "conflicting_signals": ["valid_entry", 42, None, "another_valid"],
                "assumptions": "not-a-list",
                "key_levels": {"pivot_level": "not-a-number"},
            },
            "proposed_setup": None,
            "risk_authorization": None,
        }
        trace = pipeline_trace_vm_from_summary(_approved_summary(), narrative=narrative)

        reasoning = trace.engine_reasoning
        assert reasoning is not None
        self.assertIsNone(reasoning.evidence_score)  # bad type dropped, not coerced
        self.assertIsNone(reasoning.structural_notes)  # empty string dropped
        self.assertEqual(reasoning.conflicting_signals, ("valid_entry", "another_valid"))
        self.assertEqual(reasoning.assumptions, ())  # non-list dropped
        # key_levels VM still produced but with safe Nones / empty tuples
        self.assertIsNotNone(trace.key_levels)
        assert trace.key_levels is not None
        self.assertIsNone(trace.key_levels.pivot_level)
        self.assertEqual(trace.key_levels.support_levels, ())

    def test_missing_or_partial_risk_check_entries_are_dropped(self) -> None:
        narrative: PipelineNarrative = {
            "contract_analysis": None,
            "proposed_setup": None,
            "risk_authorization": {
                "decision": "REJECTED",
                "checks": [
                    {"check_id": 1, "check_name": "daily_loss_stop", "passed": True, "detail": "ok"},
                    {"check_id": 2, "check_name": "per_trade_risk_cap", "passed": False},  # missing detail
                    "not-a-mapping",
                    {"check_id": "bad", "check_name": "broken", "passed": True, "detail": "ok"},
                ],
                "rejection_reasons": ["per_trade_risk_cap_exceeded"],
            },
        }
        trace = pipeline_trace_vm_from_summary(_approved_summary(), narrative=narrative)

        risk = trace.risk_authorization
        assert risk is not None
        self.assertEqual([c.check_id for c in risk.checks], [1])
        self.assertEqual(risk.rejection_reasons, ("per_trade_risk_cap_exceeded",))

    def test_mapper_does_not_synthesize_text_or_numeric_values(self) -> None:
        """The mapper must not fabricate any values not in the source narrative."""
        narrative: PipelineNarrative = {
            "contract_analysis": None,
            "proposed_setup": None,
            "risk_authorization": None,
        }
        trace = pipeline_trace_vm_from_summary(_approved_summary(), narrative=narrative)

        # Every nested VM is None; nothing was synthesized to fill the gap.
        self.assertIsNone(trace.engine_reasoning)
        self.assertIsNone(trace.key_levels)
        self.assertIsNone(trace.trade_thesis)
        self.assertIsNone(trace.risk_authorization)
        self.assertFalse(trace.narrative_available)


class DecisionReviewSurfaceTests(unittest.TestCase):
    def test_no_trace_returns_pre_query_panel_with_unavailable_flag(self) -> None:
        panel = render_decision_review_panel(None)
        self.assertFalse(panel["has_result"])
        self.assertFalse(panel["narrative_available"])
        self.assertEqual(panel["narrative_audit_event"]["schema"], DECISION_REVIEW_AUDIT_EVENT_SCHEMA)
        self.assertFalse(panel["narrative_audit_event"]["decision_review_narrative"]["narrative_available"])

    def test_status_envelope_keys_remain_unchanged_when_narrative_absent(self) -> None:
        trace = pipeline_trace_vm_from_summary(_approved_summary(), narrative=None)
        panel = render_decision_review_panel(trace)

        self.assertTrue(panel["has_result"])
        self.assertEqual(panel["contract"], "ES")
        self.assertEqual(panel["termination_stage"], "risk_authorization")
        self.assertEqual(panel["final_decision"], "TRADE_APPROVED")
        self.assertEqual(panel["stage_a_status"], "READY")
        self.assertEqual(panel["stage_b_outcome"], "ANALYSIS_COMPLETE")
        self.assertEqual(panel["stage_c_outcome"], "SETUP_PROPOSED")
        self.assertEqual(panel["stage_d_decision"], "APPROVED")
        self.assertEqual(panel["narrative_audit_event"]["schema"], DECISION_REVIEW_AUDIT_EVENT_SCHEMA)
        self.assertFalse(panel["narrative_audit_event"]["decision_review_narrative"]["narrative_available"])

    def test_narrative_absent_marks_each_section_explicitly_unavailable(self) -> None:
        trace = pipeline_trace_vm_from_summary(_approved_summary(), narrative=None)
        panel = render_decision_review_panel(trace)

        self.assertFalse(panel["narrative_available"])
        self.assertEqual(panel["narrative_unavailable_message"], NARRATIVE_UNAVAILABLE_DETAIL)
        self.assertFalse(panel["engine_reasoning"]["available"])
        self.assertEqual(panel["engine_reasoning"]["unavailable_message"], NARRATIVE_UNAVAILABLE_LABEL)
        self.assertFalse(panel["trade_thesis"]["available"])
        self.assertFalse(panel["risk_authorization_detail"]["available"])
        self.assertFalse(panel["invalidation"]["available"])
        self.assertEqual(
            panel["invalidation"]["unavailable_message"], DISQUALIFIERS_UNAVAILABLE_DETAIL
        )

    def test_full_narrative_renders_engine_reasoning_section(self) -> None:
        trace = pipeline_trace_vm_from_summary(_approved_summary(), narrative=_full_narrative())
        panel = render_decision_review_panel(trace)

        section = panel["engine_reasoning"]
        self.assertTrue(section["available"])
        self.assertEqual(section["market_regime"], "trending_up")
        self.assertEqual(section["directional_bias"], "bullish")
        self.assertEqual(section["confidence_band"], "HIGH")
        self.assertEqual(section["evidence_score"], 7)
        self.assertIn("5604.50", section["structural_notes"])
        self.assertEqual(len(section["conflicting_signals"]), 1)
        self.assertEqual(len(section["assumptions"]), 1)
        self.assertIsInstance(section["key_levels"], dict)
        audit = panel["narrative_audit_event"]
        self.assertTrue(audit["decision_review_narrative"]["engine_reasoning_available"])
        self.assertEqual(audit["engine_reasoning_summary"]["market_regime"], "trending_up")

    def test_full_narrative_renders_trade_thesis_with_sizing_math(self) -> None:
        trace = pipeline_trace_vm_from_summary(_approved_summary(), narrative=_full_narrative())
        panel = render_decision_review_panel(trace)

        section = panel["trade_thesis"]
        self.assertTrue(section["available"])
        self.assertFalse(section["is_no_trade"])
        self.assertEqual(section["direction"], "LONG")
        self.assertEqual(section["setup_class"], "intraday_swing")
        self.assertEqual(section["entry_price"], 5605.0)
        self.assertIn("breadth_below_55", section["rationale"])
        self.assertIsInstance(section["sizing_math"], dict)

    def test_full_narrative_renders_thirteen_risk_checks_with_passed_text(self) -> None:
        trace = pipeline_trace_vm_from_summary(_approved_summary(), narrative=_full_narrative())
        panel = render_decision_review_panel(trace)

        section = panel["risk_authorization_detail"]
        self.assertTrue(section["available"])
        self.assertEqual(section["decision"], "APPROVED")
        self.assertEqual(len(section["checks"]), 13)
        for check in section["checks"]:
            # Every status carries text, not color-only.
            self.assertIn(check["passed_text"], ("PASS", "FAIL"))
            self.assertIsInstance(check["check_name"], str)

    def test_invalidation_section_lists_disqualifiers_when_present(self) -> None:
        trace = pipeline_trace_vm_from_summary(_approved_summary(), narrative=_full_narrative())
        panel = render_decision_review_panel(trace)

        section = panel["invalidation"]
        self.assertTrue(section["available"])
        self.assertIn("breadth_below_55", section["disqualifiers"])
        self.assertIn("es_close_below_invalidation_anchor", section["disqualifiers"])

    def test_no_trade_renders_first_class_outcome_no_alternate_trade_prose(self) -> None:
        trace = pipeline_trace_vm_from_summary(_no_trade_summary(), narrative=_no_trade_narrative())
        panel = render_decision_review_panel(trace)

        # NO_TRADE preserved at the envelope.
        self.assertEqual(panel["final_decision"], "NO_TRADE")
        # Stage C narrative absent (engine did not propose).
        self.assertFalse(panel["trade_thesis"]["available"])
        # Stage D narrative absent.
        self.assertFalse(panel["risk_authorization_detail"]["available"])
        # Engine reasoning still rendered.
        self.assertTrue(panel["engine_reasoning"]["available"])
        # No alternate-trade language anywhere in the rendered section text.
        rendered_text = repr(panel)
        for forbidden in ("take trade", "consider entering", "alternate setup", "try short", "try long"):
            self.assertNotIn(forbidden, rendered_text.lower())

    def test_no_trade_with_proposed_setup_no_trade_outcome_renders_no_trade_branch(self) -> None:
        # Stage C ran but emitted NO_TRADE (Stage C hard NO_TRADE rules).
        narrative: PipelineNarrative = {
            "contract_analysis": _full_narrative()["contract_analysis"],
            "proposed_setup": {
                "outcome": "NO_TRADE",
                "no_trade_reason": "confidence_band_low",
                "direction": None,
                "setup_class": None,
                "entry_price": None,
                "stop_price": None,
                "target_1": None,
                "target_2": None,
                "position_size": None,
                "risk_dollars": None,
                "reward_risk_ratio": None,
                "hold_time_estimate_minutes": None,
                "rationale": None,
                "disqualifiers": [],
                "sizing_math": None,
            },
            "risk_authorization": None,
        }
        summary = _no_trade_summary()
        summary["proposed_setup_outcome"] = "NO_TRADE"
        trace = pipeline_trace_vm_from_summary(summary, narrative=narrative)
        panel = render_decision_review_panel(trace)

        thesis = panel["trade_thesis"]
        self.assertTrue(thesis["available"])
        self.assertTrue(thesis["is_no_trade"])
        self.assertEqual(thesis["no_trade_reason"], "confidence_band_low")
        self.assertIsNone(thesis["direction"])
        self.assertIsNone(thesis["entry_price"])

    def test_panel_contains_no_color_only_status_indicators(self) -> None:
        trace = pipeline_trace_vm_from_summary(_approved_summary(), narrative=_full_narrative())
        panel = render_decision_review_panel(trace)

        # The risk_authorization section must carry passed_text for every check
        # so status is never communicated by color/boolean alone.
        for check in panel["risk_authorization_detail"]["checks"]:
            self.assertIn("passed_text", check)
            self.assertIn(check["passed_text"], ("PASS", "FAIL"))


class DecisionReviewTraceabilityTests(unittest.TestCase):
    """Structural invariants that prevent the mapper/renderer from becoming a second decision authority."""

    def test_mapper_does_not_import_engine_internals(self) -> None:
        """The mapper module must not import preserved-engine pipeline internals.

        Importing engine internals would create a path for the mapper to
        re-derive trade decisions. The narrative must come through the
        documented PipelineNarrative TypedDict only.
        """
        import ntb_marimo_console.viewmodels.mappers as mappers
        source = open(mappers.__file__, "r", encoding="utf-8").read()
        self.assertNotIn("from ninjatradebuilder", source)
        self.assertNotIn("import ninjatradebuilder", source)

    def test_decision_review_surface_does_not_import_engine_internals(self) -> None:
        import ntb_marimo_console.ui.surfaces.decision_review as surface
        source = open(surface.__file__, "r", encoding="utf-8").read()
        self.assertNotIn("from ninjatradebuilder", source)
        self.assertNotIn("import ninjatradebuilder", source)

    def test_pipeline_trace_vm_default_construction_remains_backward_compatible(self) -> None:
        """Existing callers that build PipelineTraceVM with only the seven status fields
        must still work; new narrative fields must default to safe absent values.
        """
        trace = PipelineTraceVM(
            contract="ES",
            termination_stage="contract_market_read",
            final_decision="NO_TRADE",
            stage_a_status="READY",
            stage_b_outcome="NO_TRADE",
            stage_c_outcome=None,
            stage_d_decision=None,
        )
        self.assertFalse(trace.narrative_available)
        self.assertIsNone(trace.engine_reasoning)
        self.assertIsNone(trace.trade_thesis)
        self.assertIsNone(trace.risk_authorization)


if __name__ == "__main__":
    unittest.main()
