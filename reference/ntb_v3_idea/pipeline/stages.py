"""
Pipeline stage orchestration: A → B → C → D (fail-closed).
Also handles single-contract and multi-contract runs.
"""

from __future__ import annotations
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from google import genai
from google.genai import types

from .schemas import (
    MarketPacket, ChallengeState, PacketBundle,
    SufficiencyOutput, ContractAnalysis, ProposedSetup,
    RiskAuthorization, RiskCheck, PipelineRunRecord,
    SizingMath, KeyLevelAnalysis
)
from .prompts import stage_ab_prompt, stage_c_prompt, stage_d_prompt


MODEL = os.environ.get("NINJATRADEBUILDER_MODEL", "gemini-2.5-flash")


def _get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY not set.")
    return genai.Client(api_key=api_key)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        end = -1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end])
    return text


def _call_llm(system: str, user: str, max_tokens: int = 2048) -> dict:
    client = _get_client()
    response = client.models.generate_content(
        model=MODEL,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
        ),
    )
    raw = response.text
    return json.loads(_strip_fences(raw))


# ---------------------------------------------------------------------------
# Stage A+B
# ---------------------------------------------------------------------------

def run_stage_ab(contract: str, packet: MarketPacket, ext: dict, challenge: ChallengeState) -> tuple[SufficiencyOutput, Optional[ContractAnalysis]]:
    system, user = stage_ab_prompt(contract, packet, ext, challenge)
    data = _call_llm(system, user)

    suf_data = data.get("sufficiency", {})
    sufficiency = SufficiencyOutput(
        contract=suf_data.get("contract", contract),
        status=suf_data.get("status", "INSUFFICIENT_DATA"),
        missing_fields=suf_data.get("missing_fields", []),
        disqualifiers=suf_data.get("disqualifiers", []),
        packet_age_seconds=suf_data.get("packet_age_seconds"),
        event_lockout_detail=suf_data.get("event_lockout_detail"),
        challenge_state_valid=suf_data.get("challenge_state_valid", True),
        notes=suf_data.get("notes"),
    )

    analysis = None
    if sufficiency.status == "READY":
        ana_data = data.get("analysis", {})
        key_levels = [
            KeyLevelAnalysis(
                level_name=lvl.get("level_name", "unknown"),
                value=float(lvl.get("value", 0)),
                significance=lvl.get("significance", ""),
            )
            for lvl in ana_data.get("key_levels", [])
        ]
        analysis = ContractAnalysis(
            contract=ana_data.get("contract", contract),
            outcome=ana_data.get("outcome", "NO_TRADE"),
            market_regime=ana_data.get("market_regime"),
            directional_bias=ana_data.get("directional_bias"),
            evidence_score=ana_data.get("evidence_score"),
            confidence_band=ana_data.get("confidence_band"),
            key_levels=key_levels,
            value_context=ana_data.get("value_context"),
            structural_notes=ana_data.get("structural_notes"),
            conflicting_signals=ana_data.get("conflicting_signals", []),
            no_trade_reason=ana_data.get("no_trade_reason"),
        )

    return sufficiency, analysis


# ---------------------------------------------------------------------------
# Stage C
# ---------------------------------------------------------------------------

def run_stage_c(contract: str, packet: MarketPacket, analysis: ContractAnalysis) -> ProposedSetup:
    system, user = stage_c_prompt(contract, packet, analysis.model_dump())
    data = _call_llm(system, user)

    sizing = None
    if data.get("sizing_math"):
        sm = data["sizing_math"]
        sizing = SizingMath(
            stop_distance_ticks=float(sm.get("stop_distance_ticks", 0)),
            risk_per_tick_dollars=float(sm.get("risk_per_tick_dollars", 0)),
            raw_risk_dollars=float(sm.get("raw_risk_dollars", 0)),
            slippage_cost_dollars=float(sm.get("slippage_cost_dollars", 0)),
            adjusted_risk_dollars=float(sm.get("adjusted_risk_dollars", 0)),
            position_size=int(sm.get("position_size", 0)),
        )

    return ProposedSetup(
        contract=data.get("contract", contract),
        outcome=data.get("outcome", "NO_TRADE"),
        direction=data.get("direction"),
        entry_price=data.get("entry_price"),
        stop_price=data.get("stop_price"),
        target_1=data.get("target_1"),
        target_2=data.get("target_2"),
        reward_risk_ratio=data.get("reward_risk_ratio"),
        setup_class=data.get("setup_class"),
        hold_time_estimate_minutes=data.get("hold_time_estimate_minutes"),
        sizing_math=sizing,
        rationale=data.get("rationale"),
        no_trade_reason=data.get("no_trade_reason"),
        disqualifiers=data.get("disqualifiers", []),
    )


# ---------------------------------------------------------------------------
# Stage D
# ---------------------------------------------------------------------------

def run_stage_d(contract: str, setup: ProposedSetup, challenge: ChallengeState, packet: MarketPacket) -> RiskAuthorization:
    system, user = stage_d_prompt(contract, setup.model_dump(), challenge, packet)
    data = _call_llm(system, user)

    checks = [
        RiskCheck(
            check_id=c.get("check_id", i + 1),
            name=c.get("name", f"check_{i+1}"),
            passed=bool(c.get("passed", False)),
            detail=c.get("detail", ""),
        )
        for i, c in enumerate(data.get("checks", []))
    ]

    # Pad to 13 if model returned fewer
    while len(checks) < 13:
        idx = len(checks) + 1
        checks.append(RiskCheck(check_id=idx, name=f"check_{idx}", passed=False, detail="Not evaluated"))

    return RiskAuthorization(
        contract=data.get("contract", contract),
        decision=data.get("decision", "REJECTED"),
        checks=checks[:13],
        rejection_reasons=data.get("rejection_reasons", []),
        adjusted_position_size=data.get("adjusted_position_size"),
        adjusted_risk_dollars=data.get("adjusted_risk_dollars"),
        notes=data.get("notes"),
    )


# ---------------------------------------------------------------------------
# Full Pipeline Run
# ---------------------------------------------------------------------------

def run_pipeline(
    contract: str,
    bundle: PacketBundle,
) -> PipelineRunRecord:
    """
    Run the full A→B→C→D pipeline for a single contract.
    Fails closed at every stage gate.
    """
    run_id = str(uuid.uuid4())[:8]
    started_at = datetime.now(timezone.utc).isoformat()
    record = PipelineRunRecord(
        run_id=run_id,
        contract=contract,
        session_date=bundle.session_date,
        run_type="full_pipeline",
        started_at=started_at,
    )

    packet = bundle.packets.get(contract)
    if not packet:
        record.error = f"No packet found for {contract}"
        record.termination_stage = "PRE_STAGE_A"
        record.final_decision = "ERROR"
        record.completed_at = datetime.now(timezone.utc).isoformat()
        return record

    ext = bundle.extensions.get(contract, {})
    challenge = bundle.challenge_state

    # --- Stage A+B ---
    try:
        sufficiency, analysis = run_stage_ab(contract, packet, ext, challenge)
        record.sufficiency = sufficiency
    except Exception as e:
        record.error = f"Stage A/B error: {e}"
        record.termination_stage = "STAGE_A"
        record.final_decision = "ERROR"
        record.completed_at = datetime.now(timezone.utc).isoformat()
        return record

    if sufficiency.status != "READY":
        record.termination_stage = "STAGE_A"
        record.final_decision = sufficiency.status
        record.completed_at = datetime.now(timezone.utc).isoformat()
        return record

    if analysis is None or analysis.outcome == "NO_TRADE":
        record.analysis = analysis
        record.termination_stage = "STAGE_B"
        record.final_decision = "NO_TRADE"
        record.completed_at = datetime.now(timezone.utc).isoformat()
        return record

    record.analysis = analysis

    # --- Stage C ---
    try:
        setup = run_stage_c(contract, packet, analysis)
        record.setup = setup
    except Exception as e:
        record.error = f"Stage C error: {e}"
        record.termination_stage = "STAGE_C"
        record.final_decision = "ERROR"
        record.completed_at = datetime.now(timezone.utc).isoformat()
        return record

    if setup.outcome == "NO_TRADE":
        record.termination_stage = "STAGE_C"
        record.final_decision = "NO_TRADE"
        record.completed_at = datetime.now(timezone.utc).isoformat()
        return record

    # --- Stage D ---
    try:
        authorization = run_stage_d(contract, setup, challenge, packet)
        record.authorization = authorization
    except Exception as e:
        record.error = f"Stage D error: {e}"
        record.termination_stage = "STAGE_D"
        record.final_decision = "ERROR"
        record.completed_at = datetime.now(timezone.utc).isoformat()
        return record

    record.termination_stage = "STAGE_D"
    record.final_decision = authorization.decision
    record.completed_at = datetime.now(timezone.utc).isoformat()
    return record
