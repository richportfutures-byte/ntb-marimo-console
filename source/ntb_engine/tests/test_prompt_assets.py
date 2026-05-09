from __future__ import annotations

from ninjatradebuilder.prompt_assets import PROMPT_REGISTRY, get_prompt_asset, render_prompt


def _stage_ab_inputs() -> dict:
    return {
        "master_doctrine_text": render_prompt(1),
        "evaluation_timestamp_iso": "2026-01-14T14:05:00Z",
        "challenge_state_json": {"current_balance": 50000},
        "contract_metadata_json": {"contract": "ES"},
        "market_packet_json": {"contract": "ES", "current_price": 4490.0},
        "contract_specific_extension_json": {"contract": "ES", "breadth": "positive"},
        "attached_visuals_json": {"execution_chart_attached": True},
    }


def _stage_c_inputs() -> dict:
    return {
        "master_doctrine_text": render_prompt(1),
        "evaluation_timestamp_iso": "2026-01-14T14:06:00Z",
        "current_price": 4490.0,
        "challenge_state_json": {"max_risk_per_trade_dollars": 1450},
        "contract_metadata_json": {"contract": "ES"},
        "contract_analysis_json": {"contract": "ES", "evidence_score": 6},
    }


def _stage_d_inputs() -> dict:
    return {
        "master_doctrine_text": render_prompt(1),
        "evaluation_timestamp_iso": "2026-01-14T14:07:00Z",
        "challenge_state_json": {"last_trade_direction_by_contract": {"ES": "LONG"}},
        "contract_metadata_json": {"contract": "ES"},
        "proposed_setup_json": {"contract": "ES", "outcome": "SETUP_PROPOSED"},
        "event_calendar_remainder_json": [],
    }


def test_prompt_inventory_and_exact_mapping() -> None:
    assert list(PROMPT_REGISTRY) == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert PROMPT_REGISTRY[2].contract_scope == "ES"
    assert PROMPT_REGISTRY[3].contract_scope == "NQ"
    assert PROMPT_REGISTRY[4].contract_scope == "CL"
    assert PROMPT_REGISTRY[5].contract_scope == "ZN"
    assert PROMPT_REGISTRY[6].contract_scope == "6E"
    assert PROMPT_REGISTRY[7].contract_scope == "MGC"
    assert PROMPT_REGISTRY[8].contract_scope == "shared"
    assert PROMPT_REGISTRY[9].contract_scope == "shared"
    assert PROMPT_REGISTRY[8].stages == ("C",)
    assert PROMPT_REGISTRY[9].stages == ("D",)


def test_expected_output_boundary_binding_is_exact() -> None:
    for prompt_id in range(2, 8):
        assert PROMPT_REGISTRY[prompt_id].expected_output_boundaries == (
            "sufficiency_gate_output",
            "contract_analysis",
        )
    assert PROMPT_REGISTRY[8].expected_output_boundaries == ("proposed_setup",)
    assert PROMPT_REGISTRY[9].expected_output_boundaries == ("risk_authorization",)


def test_required_slot_validation_rejects_missing_and_extra_inputs() -> None:
    try:
        render_prompt(2, {"master_doctrine_text": render_prompt(1)})
    except ValueError as exc:
        assert "missing required runtime inputs" in str(exc)
    else:
        raise AssertionError("Expected missing-slot validation failure")

    invalid_inputs = _stage_c_inputs()
    invalid_inputs["extra_slot"] = "nope"
    try:
        render_prompt(8, invalid_inputs)
    except ValueError as exc:
        assert "unexpected runtime inputs" in str(exc)
    else:
        raise AssertionError("Expected extra-slot validation failure")


def test_master_doctrine_contains_stage4a_additions() -> None:
    doctrine = render_prompt(1)

    assert "NO_TRADE is the expected majority outcome (60-80% of evaluations)" in doctrine
    assert "Each pipeline run is independent" in doctrine


def test_all_stage_ab_prompts_include_shared_correction_anchors() -> None:
    for prompt_id in range(2, 8):
        rendered = render_prompt(prompt_id, _stage_ab_inputs())
        assert 'data_quality_flag "session_winding_down"' in rendered
        assert "If conflicting_signals contains >= 2 entries, evidence_score must not exceed 6." in rendered
        assert "If conflicting_signals contains >= 3 entries, evidence_score must not exceed 4." in rendered
        assert "Every claim in structural_notes must reference at least one specific field" in rendered
        assert "event_lockout_detail must be the exact schema object" in rendered
        assert "Even for post-event lockout, use the schema field name minutes_until" in rendered


def test_contract_specific_prompt_corrections_are_present() -> None:
    es = render_prompt(2, _stage_ab_inputs())
    nq = render_prompt(3, _stage_ab_inputs())
    cl = render_prompt(4, _stage_ab_inputs())
    zn = render_prompt(5, _stage_ab_inputs())
    six_e = render_prompt(6, _stage_ab_inputs())
    mgc = render_prompt(7, _stage_ab_inputs())

    assert "If breadth, index_cash_tone, or cumulative_delta materially diverge from price direction" in es
    assert "Do not return ANALYSIS_COMPLETE when price direction is not confirmed" in es
    assert 'data_quality_flag "megacap_earnings_risk"' in nq
    assert 'If relative_strength_vs_es < 1.0 and megacap leadership is fragile, lagging, or earnings-risk driven, favor outcome = NO_TRADE' in nq
    assert "Do not return ANALYSIS_COMPLETE when relative_strength_vs_es shows NQ lagging ES" in nq
    assert 'eia_timing.status = "released" and minutes_since < 15' in cl
    assert "evidence_score must not exceed 7" in cl
    assert "auction_proximity_risk" in zn
    assert "0.125 / 0.015625 = 8" in zn
    assert 'data_quality_flag "london_close_thin_liquidity"' in six_e
    assert 'favor outcome = NO_TRADE unless one coherent dominant driver is clearly established' in mgc
    assert "Do not return ANALYSIS_COMPLETE when fear-catalyst instability is active" in mgc
    assert "directional_bias must use only schema-valid literals: bullish, bearish, neutral, or unclear." in mgc


def test_stage_c_prompt_contains_shared_runtime_corrections() -> None:
    rendered = render_prompt(8, _stage_c_inputs())

    assert "Entry price defaults to current_price (market order)." in rendered
    assert 'return NO_TRADE with reason "stale_market_read"' in rendered
    assert "rationale must reference only contract_analysis fields and values." in rendered
    assert "Max stop distance guidelines: ES 16 ticks, NQ 40 ticks, CL 20 ticks, ZN 16 ticks, 6E 40 ticks, MGC 50 ticks." in rendered
    assert "Always include contract using contract_metadata.contract." in rendered
    assert "Always include timestamp using evaluation_timestamp." in rendered
    assert 'If outcome = "SETUP_PROPOSED", always include outcome exactly as "SETUP_PROPOSED".' in rendered
    assert 'Populate no_trade_reason with exactly one schema-valid reason string.' in rendered
    assert 'direction must be the schema enum "LONG" or "SHORT" only.' in rendered
    assert "sizing_math must be a structured object" in rendered
    assert "bullish -> LONG, bearish -> SHORT" in rendered
    assert "Do not emit extra keys such as disqualification_reasons" in rendered
    assert 'If outcome = "SETUP_PROPOSED", no_trade_reason must be null.' in rendered
    assert "If position_size = 1, target_2 must be null." in rendered
    assert 'If position_size > 1, target_2 is required.' in rendered


def test_stage_d_prompt_contains_check_10_correction_and_completeness_anchor() -> None:
    rendered = render_prompt(9, _stage_d_inputs())

    assert "last_trade_direction_by_contract" in rendered
    assert "checks_count must equal 13" in rendered
    assert "decision is the required top-level decision field" in rendered
    assert "Do not emit outcome in Stage D." in rendered
    assert "check_id is required for every check and must run from 1 through 13 in order" in rendered
    assert "Do not emit singular rejection_reason." in rendered


def test_get_prompt_asset_returns_expected_prompt() -> None:
    asset = get_prompt_asset(4)

    assert asset.name == "CL Sufficiency + Market Read"
    assert asset.contract_scope == "CL"


def test_stage_b_structural_notes_synthesis_contract_renders_in_all_contract_prompts() -> None:
    """structural_notes is the trader-facing market read.

    Every Stage A+B contract prompt (ES, NQ, CL, ZN, 6E, MGC) must carry the synthesis
    mandate: directional_bias + numeric anchor + next watch-for, all grounded in
    structured fields, with explicit rejection of generic state-description prose.
    """

    for prompt_id in range(2, 8):
        rendered = render_prompt(prompt_id, _stage_ab_inputs())

        assert "structural_notes is the trader-facing market read" in rendered
        assert "states or unambiguously implies the directional_bias" in rendered
        assert "names the specific numeric anchor level" in rendered
        assert "next concrete observation the trader is watching for" in rendered
        assert (
            "A reader of structural_notes alone should know the bias, the anchor, "
            "and the next decision point without cross-referencing any other field."
        ) in rendered

        assert 'Strings of the form "Price is holding above pivot"' in rendered
        assert "are malformed structural_notes and must not be emitted" in rendered

        assert "structural_notes must not introduce price-action observations" in rendered
        assert "If a claim cannot be tied to a specific structured field, do not make the claim." in rendered

        assert "structural_notes must not override or contradict structured fields" in rendered


def test_stage_b_conflicting_signals_content_contract_renders_in_all_contract_prompts() -> None:
    """conflicting_signals must be real directional tensions, not vague placeholders.

    Each entry must name the specific signal/field, the directional pull relative
    to bias, the structured field/value creating the tension, and be material.
    Vague entries that pollute the conflict count must be explicitly rejected.
    """

    for prompt_id in range(2, 8):
        rendered = render_prompt(prompt_id, _stage_ab_inputs())

        assert "Each entry in conflicting_signals must be a real directional tension" in rendered
        assert "name the specific signal or field" in rendered
        assert "state the direction it pulls relative to directional_bias" in rendered
        assert "reference the structured field or value that creates the tension" in rendered

        assert '"delta mixed"' in rendered
        assert '"balance intact"' in rendered
        assert '"macro neutral"' in rendered
        assert "Neutral or balanced context is not a conflict" in rendered
        assert "Missing data is not a conflict" in rendered

        assert "Inflating the count with vague entries to artificially cap evidence_score" in rendered

        # Existing evidence_score caps must still be present and unchanged.
        assert "If conflicting_signals contains >= 2 entries, evidence_score must not exceed 6." in rendered
        assert "If conflicting_signals contains >= 3 entries, evidence_score must not exceed 4." in rendered


def test_stage_c_rationale_defense_contract_renders_and_preserves_no_reread_boundary() -> None:
    """rationale must positively defend the trade while remaining downstream-only.

    The no-reread boundary is preserved (rule 11). The defense mandate (rule 12)
    requires entry/stop/target/setup_class/invalidation defense drawn entirely
    from contract_analysis. Tautology and rescue-prose are explicitly rejected.
    """

    rendered = render_prompt(8, _stage_c_inputs())

    # No-reread boundary is preserved verbatim.
    assert (
        "rationale must reference only contract_analysis fields and values. "
        "Do not re-read the market. Do not add new price-action observations."
    ) in rendered

    # Defense mandate.
    assert "rationale must positively defend the trade against a wait or a different configuration" in rendered
    assert "the specific contract_analysis field or fields that justify entry_price" in rendered
    assert "places stop_price beyond the structural invalidation" in rendered
    assert "contract_analysis.key_levels reference that justifies target_1" in rendered
    assert "why setup_class fits this contract_analysis context" in rendered
    assert "the specific contract_analysis condition whose change would invalidate the setup" in rendered

    # Tautology rejection by example.
    assert '"bullish bias supports a scalp"' in rendered
    assert '"long from pivot toward resistance"' in rendered
    assert "are malformed rationale and must not be emitted" in rendered

    # Boundary in rule 11 explicitly preserved by rule 14.
    assert "The boundary in rule 11 stands." in rendered
    assert "If contract_analysis is too thin to satisfy rule 12, the correct response is NO_TRADE" in rendered

    # Rescue-prose rejection (must not undermine fail-closed behavior).
    assert "rationale must not rescue a weak setup with prose" in rendered
    assert "the hard NO_TRADE rules above govern" in rendered


def test_stage_c_disqualifiers_monitorable_token_contract_renders() -> None:
    """Stage C disqualifiers must be deterministic lockout tokens or monitorable tokens.

    Each entry names what to watch and the breach condition, so a future
    active-trade evaluator can check it against current state. Narrative
    tokens that cannot be monitored are explicitly rejected. The existing
    stop_distance_unusually_wide guidance is preserved.
    """

    rendered = render_prompt(8, _stage_c_inputs())

    # Existing stop-distance guidance preserved.
    assert (
        "Max stop distance guidelines: ES 16 ticks, NQ 40 ticks, CL 20 ticks, "
        "ZN 16 ticks, 6E 40 ticks, MGC 50 ticks."
    ) in rendered
    assert 'add disqualifier "stop_distance_unusually_wide"' in rendered

    # Monitorable token mandate.
    assert (
        "Each entry in disqualifiers must be either a deterministic lockout token"
    ) in rendered
    assert "monitorable token tied to a specific contract_analysis field" in rendered
    assert "A monitorable token names what to watch and the breach condition" in rendered

    # Acceptable example shapes (chosen to mirror the prompt's voice).
    for example in (
        "stop_distance_unusually_wide",
        "quote_stale",
        "event_lockout_active",
        "post_eia_settling",
        "breadth_below_55",
        "dxy_change_above_plus_30bp",
        "es_close_below_invalidation_anchor",
        "relative_strength_vs_es_below_1_0",
        "megacap_earnings_risk_active",
    ):
        assert example in rendered, f"Expected acceptable example {example!r} in Stage C prompt"

    # Narrative-token rejection by example.
    for malformed in (
        '"market_conditions_change"',
        '"thesis_invalidated"',
        '"structure_failed"',
        '"weak_context"',
        '"bad_trade_location"',
        '"poor_setup"',
        '"risky_trade"',
        '"context_shifted"',
        '"confidence_low"',
    ):
        assert malformed in rendered, f"Expected malformed example {malformed!r} called out in Stage C prompt"

    assert "are malformed disqualifiers and must not be emitted" in rendered

    # Boundary against alternate-trade suggestions (preserve manual-only / single-decision authority).
    assert "disqualifiers must not be used to suggest alternate trades" in rendered
    assert "They are conditions that would invalidate this proposed_setup" in rendered

    # Distinctness rule.
    assert "disqualifiers entries must be distinct in meaning" in rendered


def test_narrative_hardening_does_not_weaken_existing_no_trade_or_no_reread_invariants() -> None:
    """Final invariant guard: every existing fail-closed and boundary rule still renders.

    If a future edit to prompt_assets.py accidentally removes one of these phrases
    while tightening narrative quality, this test fails before the regression
    reaches the engine.
    """

    stage_ab = {prompt_id: render_prompt(prompt_id, _stage_ab_inputs()) for prompt_id in range(2, 8)}
    stage_c = render_prompt(8, _stage_c_inputs())

    for rendered in stage_ab.values():
        # Stage B fail-closed and boundary rules.
        assert "outcome must be Stage B outcome only: ANALYSIS_COMPLETE or NO_TRADE." in rendered
        assert "Do not leak Stage A fields into Stage B output." in rendered
        assert "Every claim in structural_notes must reference at least one specific field" in rendered

    # Stage C hard NO_TRADE rules still present.
    for hard_rule in (
        'return NO_TRADE with reason "market_read_returned_no_trade"',
        'return NO_TRADE with reason "confidence_band_low"',
        'return NO_TRADE with reason "medium_confidence_insufficient_evidence"',
        'return NO_TRADE with reason "directional_bias_unclear"',
        'return NO_TRADE with reason "neutral_in_range_no_edge"',
        'return NO_TRADE with reason "stale_market_read"',
    ):
        assert hard_rule in stage_c

    # Stage C no-reread boundary preserved.
    assert "rationale must reference only contract_analysis fields and values." in stage_c
    assert "Do not re-read the market." in stage_c
    assert "Do not add new price-action observations." in stage_c
