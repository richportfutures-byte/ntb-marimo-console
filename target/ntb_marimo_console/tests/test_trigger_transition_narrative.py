from __future__ import annotations

import json

import pytest

from ntb_marimo_console.trigger_state import TriggerState, TriggerStateResult
from ntb_marimo_console.trigger_transition_narrative import narrate_trigger_transition


@pytest.mark.parametrize(
    ("state", "snippet"),
    (
        (TriggerState.UNAVAILABLE, "artifact, profile, snapshot, or app-owned trigger state is unavailable"),
        (TriggerState.DORMANT, "No actionable trigger proximity has been reached"),
        (TriggerState.APPROACHING, "approaching its declared level"),
        (TriggerState.TOUCHED, "level contact is reported"),
        (TriggerState.ARMED, "Partial deterministic confirmation is present"),
        (TriggerState.QUERY_READY, "Deterministic trigger and data-quality gates are satisfied"),
        (TriggerState.INVALIDATED, "invalidated by app-owned invalidation state"),
        (TriggerState.BLOCKED, "blocked by deterministic prerequisites"),
        (TriggerState.LOCKOUT, "lockout is active"),
        (TriggerState.STALE, "stale for the trigger read model"),
        (TriggerState.ERROR, "runtime or predicate error"),
    ),
)
def test_narrates_every_trigger_state_deterministically(state: TriggerState, snippet: str) -> None:
    distance = 2.0 if state == TriggerState.APPROACHING else None
    narrative = narrate_trigger_transition(trigger_result(state, distance_to_trigger_ticks=distance)).to_dict()

    assert narrative["narrative_available"] is True
    assert narrative["state_label"] == state.value
    assert snippet in narrative_text(narrative)
    assert "state" in narrative["source_fields"]


def test_query_ready_preserves_pipeline_authority_and_manual_execution_language() -> None:
    narrative = narrate_trigger_transition(
        trigger_result(TriggerState.QUERY_READY, distance_to_trigger_ticks=0.0)
    ).to_dict()
    text = narrative_text(narrative)

    assert "The preserved pipeline must still decide" in text
    assert "execution remains manual" in text
    assert "does not approve or authorize a trade" in text


def test_missing_trigger_level_does_not_infer_level() -> None:
    narrative = narrate_trigger_transition(
        trigger_result(TriggerState.BLOCKED, blocking_reasons=("trigger_level_required",))
    ).to_dict()

    assert "Trigger level is unavailable; no level is inferred." in narrative["missing_data_explanation"]
    assert "trigger_level_required" in narrative["blocking_explanation"]


def test_missing_distance_does_not_infer_proximity() -> None:
    narrative = narrate_trigger_transition(
        trigger_result(TriggerState.APPROACHING, distance_to_trigger_ticks=None)
    ).to_dict()
    text = narrative_text(narrative)

    assert "distance-to-trigger ticks is unavailable" in text
    assert "not inferred" in text


def test_missing_required_fields_render_blocking_language() -> None:
    narrative = narrate_trigger_transition(
        trigger_result(
            TriggerState.BLOCKED,
            missing_fields=("market.current_price", "market.cumulative_delta"),
            blocking_reasons=("missing_required_live_fields",),
        )
    ).to_dict()

    assert "Missing required trigger data: market.current_price, market.cumulative_delta." in narrative[
        "missing_data_explanation"
    ]
    assert "missing_required_live_fields" in narrative["blocking_explanation"]
    assert "bounded pipeline query gate remains unavailable" in narrative["readiness_explanation"]


def test_absent_payload_renders_explicit_unavailable_language() -> None:
    narrative = narrate_trigger_transition(None).to_dict()

    assert narrative["narrative_available"] is False
    assert narrative["state_label"] == "UNAVAILABLE"
    assert "no trigger-state payload was supplied" in narrative["transition_summary"]
    assert "Required trigger-state fields are unavailable" in narrative["missing_data_explanation"]


def test_unrecognized_state_renders_unavailable_not_success() -> None:
    narrative = narrate_trigger_transition({"state": "NOT_A_STATE"}).to_dict()

    assert narrative["narrative_available"] is False
    assert narrative["state_label"] == "UNAVAILABLE"
    assert "missing or unrecognized" in narrative["transition_summary"]


def test_stale_state_does_not_render_query_ready_language() -> None:
    narrative = narrate_trigger_transition(
        trigger_result(TriggerState.STALE, blocking_reasons=("quote_stale",))
    ).to_dict()
    text = narrative_text(narrative).lower()

    assert "fresh deterministic inputs are required" in text
    assert "query_ready" not in text
    assert "query ready" not in text


def test_lockout_overrides_readiness_language() -> None:
    narrative = narrate_trigger_transition(
        trigger_result(
            TriggerState.LOCKOUT,
            distance_to_trigger_ticks=0.0,
            blocking_reasons=("event_lockout_active", "operator_event_lockout"),
        )
    ).to_dict()
    text = narrative_text(narrative)

    assert "Lockout suppresses trigger readiness" in text
    assert "event_lockout_active" in text
    assert "Deterministic trigger and data-quality gates are satisfied" not in text


def test_invalidated_state_does_not_imply_replacement_or_reset() -> None:
    narrative = narrate_trigger_transition(
        trigger_result(
            TriggerState.INVALIDATED,
            invalid_reasons=("invalidator_fired:acceptance_failure",),
            blocking_reasons=("invalidator_fired:acceptance_failure",),
        )
    ).to_dict()
    text = narrative_text(narrative).lower()

    assert "invalidator_fired:acceptance_failure" in text
    assert "replacement thesis" in text
    assert "re-entry" not in text
    assert "alternate setup" not in text


def test_trigger_transition_narrative_has_no_execution_or_active_management_language() -> None:
    forbidden_phrases = (
        "take the trade",
        "enter",
        "buy",
        "sell",
        "short now",
        "long now",
        "move stop",
        "trail",
        "scale out",
        "fill",
        "p&l",
    )
    for state in TriggerState:
        text = narrative_text(narrate_trigger_transition(trigger_result(state)).to_dict()).lower()
        for phrase in forbidden_phrases:
            assert phrase not in text


def test_trigger_transition_narrative_introduces_no_broker_order_account_fields() -> None:
    narrative = narrate_trigger_transition(trigger_result(TriggerState.QUERY_READY)).to_dict()
    encoded = json.dumps(narrative, sort_keys=True).lower()

    for forbidden_key in ("broker", "order", "fill", "account", "pnl"):
        assert forbidden_key not in encoded


def test_trigger_transition_narrative_does_not_promote_zn_or_gc_and_does_not_map_mgc() -> None:
    mgc = trigger_result(TriggerState.QUERY_READY, contract="MGC", trigger_id="mgc_trigger_1")
    narrative = narrate_trigger_transition(mgc).to_dict()
    encoded = json.dumps(narrative, sort_keys=True)

    assert '"GC"' not in encoded
    assert '"ZN"' not in encoded
    assert "Micro Gold" not in encoded
    assert "mgc_trigger_1" in encoded


def narrative_text(narrative: dict[str, object]) -> str:
    return " ".join(str(value) for value in narrative.values() if value is not None)


def trigger_result(
    state: TriggerState,
    *,
    contract: str = "ES",
    setup_id: str = "es_setup_1",
    trigger_id: str = "es_trigger_1",
    distance_to_trigger_ticks: float | None = None,
    required_fields: tuple[str, ...] = ("market.current_price", "market.cumulative_delta"),
    missing_fields: tuple[str, ...] = (),
    invalid_reasons: tuple[str, ...] = (),
    blocking_reasons: tuple[str, ...] = (),
) -> TriggerStateResult:
    return TriggerStateResult(
        contract=contract,
        setup_id=setup_id,
        trigger_id=trigger_id,
        state=state,
        distance_to_trigger_ticks=distance_to_trigger_ticks,
        required_fields=required_fields,
        missing_fields=missing_fields,
        invalid_reasons=invalid_reasons,
        blocking_reasons=blocking_reasons,
        last_updated="2026-05-06T14:00:00+00:00",
    )
