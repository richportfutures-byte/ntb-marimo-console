from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ninjatradebuilder.adapters import InProcessStructuredAdapter
from ninjatradebuilder.pipeline import STAGE_AB_PROMPT_BY_CONTRACT

from .runtime_profiles import get_runtime_profile


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _load_json_fixture(relative_path: str) -> dict[str, Any]:
    path = _workspace_root() / relative_path
    return json.loads(path.read_text(encoding="utf-8"))


def _valid_contract_analysis_no_trade(
    *,
    contract: str,
    timestamp: str,
    support_level: float,
    resistance_level: float,
    pivot_level: float,
    structural_notes: str,
) -> dict[str, object]:
    return {
        "$schema": "contract_analysis_v1",
        "stage": "contract_market_read",
        "contract": contract,
        "timestamp": timestamp,
        "market_regime": "range_bound",
        "directional_bias": "bullish",
        "key_levels": {
            "support_levels": [support_level],
            "resistance_levels": [resistance_level],
            "pivot_level": pivot_level,
        },
        "evidence_score": 6,
        "confidence_band": "MEDIUM",
        "value_context": {
            "relative_to_prior_value_area": "above",
            "relative_to_current_developing_value": "above_vah",
            "relative_to_vwap": "above",
            "relative_to_prior_day_range": "above",
        },
        "structural_notes": structural_notes,
        "outcome": "NO_TRADE",
        "conflicting_signals": ["fixture_preserved_mode_bound_to_stage_b_no_trade"],
        "assumptions": [],
    }


def _es_fixture_analysis() -> dict[str, object]:
    profile = get_runtime_profile("preserved_es_phase1")
    return _valid_contract_analysis_no_trade(
        contract=profile.contract,
        timestamp=profile.evaluation_timestamp_iso,
        support_level=5576.0,
        resistance_level=5604.0,
        pivot_level=5589.0,
        structural_notes=(
            "Price is above the prior-day value area but the fixture integration path terminates at NO_TRADE."
        ),
    )


def _cl_fixture_analysis() -> dict[str, object]:
    profile = get_runtime_profile("preserved_cl_phase1")
    historical = _load_json_fixture("source/ntb_engine/tests/fixtures/compiler/cl_historical_input.valid.json")
    extension = _load_json_fixture("source/ntb_engine/tests/fixtures/compiler/cl_extension.valid.json")
    return _valid_contract_analysis_no_trade(
        contract=profile.contract,
        timestamp=profile.evaluation_timestamp_iso,
        support_level=float(historical["current_session_val"]),
        resistance_level=float(historical["prior_day_high"]),
        pivot_level=float(historical["current_session_poc"]),
        structural_notes=(
            "EIA remains scheduled in "
            f"{int(extension['eia_timing']['minutes_until'])} minutes with bid rebuilding near "
            f"session VWAP {float(historical['vwap']):.2f}, but the bounded preserved fixture adapter "
            "terminates at NO_TRADE."
        ),
    )


def _nq_fixture_analysis() -> dict[str, object]:
    profile = get_runtime_profile("preserved_nq_phase1")
    historical = _load_json_fixture("source/ntb_engine/tests/fixtures/compiler/nq_historical_input.valid.json")
    relative = _load_json_fixture("source/ntb_engine/tests/fixtures/compiler/nq_relative_strength.valid.json")
    return _valid_contract_analysis_no_trade(
        contract=profile.contract,
        timestamp=profile.evaluation_timestamp_iso,
        support_level=float(historical["current_session_val"]),
        resistance_level=float(historical["prior_day_high"]),
        pivot_level=float(historical["current_session_poc"]),
        structural_notes=(
            "NQ is bounded to fixture-safe NO_TRADE with explicit ES context at "
            f"{float(relative['es_current_price']):.2f}; the live workstation read model must still "
            "fail closed unless ES-relative gates pass."
        ),
    )


def _sixe_fixture_analysis() -> dict[str, object]:
    profile = get_runtime_profile("preserved_6e_phase1")
    historical = _load_json_fixture("source/ntb_engine/tests/fixtures/compiler/6e_historical_input.valid.json")
    return _valid_contract_analysis_no_trade(
        contract=profile.contract,
        timestamp=profile.evaluation_timestamp_iso,
        support_level=float(historical["current_session_val"]),
        resistance_level=float(historical["prior_day_high"]),
        pivot_level=float(historical["current_session_poc"]),
        structural_notes=(
            "6E is bounded to fixture-safe NO_TRADE; the live workstation read model requires explicit "
            "numeric DXY and session-sequence gates before it can surface query-ready read-model state."
        ),
    )


def _zn_fixture_analysis() -> dict[str, object]:
    profile = get_runtime_profile("preserved_zn_phase1")
    historical = _load_json_fixture("source/ntb_engine/tests/fixtures/compiler/zn_historical_input.valid.json")
    extension = _load_json_fixture("source/ntb_engine/tests/fixtures/compiler/zn_extension.valid.json")
    return _valid_contract_analysis_no_trade(
        contract=profile.contract,
        timestamp=profile.evaluation_timestamp_iso,
        support_level=float(historical["current_session_val"]),
        resistance_level=float(historical["prior_day_high"]),
        pivot_level=float(historical["current_session_poc"]),
        structural_notes=(
            "Cash 10Y yield remains anchored at "
            f"{float(extension['cash_10y_yield']):.2f} with buyer absorption near session VWAP, "
            "but the bounded preserved fixture adapter terminates at NO_TRADE."
        ),
    )


def build_profile_fixture_adapter(profile_id: str = "preserved_es_phase1") -> InProcessStructuredAdapter:
    profile = get_runtime_profile(profile_id)
    analysis_by_profile_id = {
        "preserved_es_phase1": _es_fixture_analysis,
        "preserved_cl_phase1": _cl_fixture_analysis,
        "preserved_nq_phase1": _nq_fixture_analysis,
        "preserved_6e_phase1": _sixe_fixture_analysis,
        "preserved_zn_phase1": _zn_fixture_analysis,
    }
    analysis_builder = analysis_by_profile_id.get(profile.profile_id)
    if analysis_builder is None:
        raise RuntimeError(f"Unsupported preserved fixture adapter profile: {profile.profile_id}")
    analysis = analysis_builder()
    return InProcessStructuredAdapter({STAGE_AB_PROMPT_BY_CONTRACT[profile.contract]: analysis})


adapter_es = build_profile_fixture_adapter("preserved_es_phase1")
adapter_cl = build_profile_fixture_adapter("preserved_cl_phase1")
adapter_nq = build_profile_fixture_adapter("preserved_nq_phase1")
adapter_6e = build_profile_fixture_adapter("preserved_6e_phase1")
adapter_zn = build_profile_fixture_adapter("preserved_zn_phase1")
adapter = adapter_es
