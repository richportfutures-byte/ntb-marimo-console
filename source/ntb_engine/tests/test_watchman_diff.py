from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from ninjatradebuilder.readiness_adapter import build_readiness_runtime_inputs_from_packet
from ninjatradebuilder.view_models import (
    WatchmanDiff,
    WatchmanFieldChange,
    diff_watchman_contexts,
)
from ninjatradebuilder.watchman import build_watchman_context_from_runtime_inputs

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _packet_payload(contract: str) -> dict[str, object]:
    bundle = json.loads((FIXTURES_DIR / "packets.valid.json").read_text(encoding="utf-8"))
    return {
        "$schema": "historical_packet_v1",
        "challenge_state": copy.deepcopy(bundle["shared"]["challenge_state"]),
        "attached_visuals": copy.deepcopy(bundle["shared"]["attached_visuals"]),
        "contract_metadata": copy.deepcopy(bundle["contracts"][contract]["contract_metadata"]),
        "market_packet": copy.deepcopy(bundle["contracts"][contract]["market_packet"]),
        "contract_specific_extension": copy.deepcopy(
            bundle["contracts"][contract]["contract_specific_extension"]
        ),
    }


def _recheck_trigger() -> dict[str, str]:
    return {
        "trigger_family": "recheck_at_time",
        "recheck_at_time": "2026-01-14T15:15:00Z",
    }


def _build_context(contract: str = "ES"):
    runtime_inputs = build_readiness_runtime_inputs_from_packet(_packet_payload(contract))
    return build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())


def test_diff_identical_contexts_has_no_changes() -> None:
    ctx = _build_context("ES")
    diff = diff_watchman_contexts(ctx, ctx)

    assert isinstance(diff, WatchmanDiff)
    assert diff.contract == "ES"
    assert diff.changes == ()
    assert not diff.has_changes


def test_diff_detects_state_change() -> None:
    prev = _build_context("ES")
    curr = prev.model_copy(update={"event_risk_state": "elevated"})

    diff = diff_watchman_contexts(prev, curr)

    assert diff.has_changes
    event_change = next(c for c in diff.changes if c.field == "event_risk_state")
    assert event_change.current == "elevated"
    assert event_change.previous == prev.event_risk_state


def test_diff_detects_multiple_state_changes() -> None:
    prev = _build_context("ES")
    curr = prev.model_copy(update={
        "vwap_posture_state": "price_below_vwap",
        "value_location_state": "below_value",
    })

    diff = diff_watchman_contexts(prev, curr)

    changed_fields = {c.field for c in diff.changes}
    assert "vwap_posture_state" in changed_fields
    assert "value_location_state" in changed_fields


def test_diff_detects_lockout_flag_change() -> None:
    prev = _build_context("ES")
    curr = prev.model_copy(update={"hard_lockout_flags": ["stale_market_packet"]})

    diff = diff_watchman_contexts(prev, curr)

    lockout_change = next(c for c in diff.changes if c.field == "hard_lockout_flags")
    assert "stale_market_packet" in lockout_change.current


def test_diff_detects_awareness_flag_change() -> None:
    prev = _build_context("ES").model_copy(update={"awareness_flags": ["yield_headwind"]})
    curr = prev.model_copy(update={"awareness_flags": []})

    diff = diff_watchman_contexts(prev, curr)

    flag_change = next(c for c in diff.changes if c.field == "awareness_flags")
    assert "yield_headwind" in flag_change.previous
    assert flag_change.current == "\u2014"


def test_diff_rejects_different_contracts() -> None:
    es_ctx = _build_context("ES")
    nq_ctx = _build_context("NQ")

    with pytest.raises(ValueError, match="different contracts"):
        diff_watchman_contexts(es_ctx, nq_ctx)


def test_diff_field_change_is_frozen() -> None:
    change = WatchmanFieldChange(field="event_risk_state", previous="normal", current="elevated")
    assert change.field == "event_risk_state"
    with pytest.raises(AttributeError):
        change.field = "something_else"
