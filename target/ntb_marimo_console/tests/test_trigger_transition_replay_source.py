from __future__ import annotations

import pytest

from ntb_marimo_console.evidence_replay import EVIDENCE_REPLAY_SCHEMA
from ntb_marimo_console.operator_workspace import OperatorWorkspaceRequest, build_operator_workspace_view_model
from ntb_marimo_console.trigger_state import TriggerState, TriggerStateResult
from ntb_marimo_console.trigger_transition_replay_source import TriggerTransitionReplaySource


TIMESTAMP = "2026-05-06T14:00:05+00:00"


def test_first_observation_records_no_transition_and_exposes_no_summary() -> None:
    source = TriggerTransitionReplaySource(source="fixture")

    emitted = source.observe(
        trigger_result("ES", TriggerState.DORMANT),
        timestamp=TIMESTAMP,
        profile_id="preserved_es_phase1",
    )

    assert emitted == ()
    assert source.events == ()
    assert source.replay_summary(contract="ES", profile_id="preserved_es_phase1") is None
    assert source.trigger_transition_log(contract="ES", profile_id="preserved_es_phase1") is None


@pytest.mark.parametrize(
    ("previous_state", "current_state", "event_type"),
    (
        (TriggerState.DORMANT, TriggerState.APPROACHING, "trigger_approaching"),
        (TriggerState.APPROACHING, TriggerState.TOUCHED, "trigger_touched"),
        (TriggerState.TOUCHED, TriggerState.ARMED, "trigger_armed"),
        (TriggerState.ARMED, TriggerState.QUERY_READY, "trigger_query_ready"),
        (TriggerState.QUERY_READY, TriggerState.INVALIDATED, "trigger_invalidated"),
    ),
)
def test_replay_source_records_supported_observed_transitions(
    previous_state: TriggerState,
    current_state: TriggerState,
    event_type: str,
) -> None:
    source = TriggerTransitionReplaySource(source="fixture")
    source.observe(
        trigger_result("ES", previous_state),
        timestamp="2026-05-06T14:00:04+00:00",
        profile_id="preserved_es_phase1",
        premarket_brief_ref="premarket/ES/2026-05-06/brief.json",
    )

    emitted = source.observe(
        trigger_result("ES", current_state),
        timestamp=TIMESTAMP,
        profile_id="preserved_es_phase1",
        premarket_brief_ref="premarket/ES/2026-05-06/brief.json",
    )
    log = source.trigger_transition_log(contract="ES", profile_id="preserved_es_phase1")

    assert len(emitted) == 1
    assert emitted[0].event_type == event_type
    assert emitted[0].contract == "ES"
    assert emitted[0].setup_id == "es_setup_1"
    assert emitted[0].trigger_id == "es_trigger_1"
    assert log is not None
    assert log["schema"] == EVIDENCE_REPLAY_SCHEMA
    assert log["contract"] == "ES"
    assert log["trigger_transitions"][-1]["event_type"] == event_type


def test_replay_source_records_no_duplicate_for_identical_state() -> None:
    source = TriggerTransitionReplaySource(source="fixture")
    source.observe(trigger_result("ES", TriggerState.TOUCHED), timestamp=TIMESTAMP, profile_id="preserved_es_phase1")

    emitted = source.observe(
        trigger_result("ES", TriggerState.TOUCHED),
        timestamp=TIMESTAMP,
        profile_id="preserved_es_phase1",
    )

    assert emitted == ()
    assert source.events == ()


@pytest.mark.parametrize(
    "current_state",
    (
        TriggerState.BLOCKED,
        TriggerState.LOCKOUT,
        TriggerState.STALE,
        TriggerState.ERROR,
        TriggerState.UNAVAILABLE,
        TriggerState.DORMANT,
    ),
)
def test_replay_source_records_no_transition_for_unsupported_current_states(current_state: TriggerState) -> None:
    source = TriggerTransitionReplaySource(source="fixture")
    source.observe(trigger_result("ES", TriggerState.APPROACHING), timestamp=TIMESTAMP, profile_id="preserved_es_phase1")

    emitted = source.observe(
        trigger_result("ES", current_state),
        timestamp="2026-05-06T14:00:06+00:00",
        profile_id="preserved_es_phase1",
    )

    assert emitted == ()
    assert source.events == ()


def test_replay_source_keeps_contract_setup_and_trigger_keys_separate() -> None:
    source = TriggerTransitionReplaySource(source="fixture")
    source.observe(
        trigger_result("ES", TriggerState.DORMANT, setup_id="shared_setup", trigger_id="shared_trigger"),
        timestamp="2026-05-06T14:00:00+00:00",
        profile_id="preserved_es_phase1",
    )
    cross_contract_first = source.observe(
        trigger_result("NQ", TriggerState.APPROACHING, setup_id="shared_setup", trigger_id="shared_trigger"),
        timestamp="2026-05-06T14:00:01+00:00",
        profile_id="preserved_nq_phase1",
    )
    es_transition = source.observe(
        trigger_result("ES", TriggerState.APPROACHING, setup_id="shared_setup", trigger_id="shared_trigger"),
        timestamp="2026-05-06T14:00:02+00:00",
        profile_id="preserved_es_phase1",
    )
    nq_transition = source.observe(
        trigger_result("NQ", TriggerState.TOUCHED, setup_id="shared_setup", trigger_id="shared_trigger"),
        timestamp="2026-05-06T14:00:03+00:00",
        profile_id="preserved_nq_phase1",
    )

    es_log = source.trigger_transition_log(contract="ES", profile_id="preserved_es_phase1")
    nq_log = source.trigger_transition_log(contract="NQ", profile_id="preserved_nq_phase1")

    assert cross_contract_first == ()
    assert len(es_transition) == 1
    assert len(nq_transition) == 1
    assert es_log is not None
    assert nq_log is not None
    assert [item["event_type"] for item in es_log["trigger_transitions"]] == ["trigger_approaching"]
    assert [item["event_type"] for item in nq_log["trigger_transitions"]] == ["trigger_touched"]
    assert es_log["contract"] == "ES"
    assert nq_log["contract"] == "NQ"


def test_replay_source_filters_events_by_contract_for_workspace_consumption() -> None:
    source = TriggerTransitionReplaySource(source="fixture")
    source.observe(trigger_result("ES", TriggerState.DORMANT), timestamp="2026-05-06T14:00:00+00:00", profile_id="preserved_es_phase1")
    source.observe(trigger_result("ES", TriggerState.APPROACHING), timestamp="2026-05-06T14:00:01+00:00", profile_id="preserved_es_phase1")
    source.observe(trigger_result("NQ", TriggerState.DORMANT), timestamp="2026-05-06T14:00:02+00:00", profile_id="preserved_nq_phase1")
    source.observe(trigger_result("NQ", TriggerState.TOUCHED), timestamp="2026-05-06T14:00:03+00:00", profile_id="preserved_nq_phase1")

    es_evidence = workspace_evidence(
        "ES",
        trigger_transition_log=source.trigger_transition_log(contract="ES", profile_id="preserved_es_phase1"),
    )

    assert es_evidence["trigger_transition_log_status"] == "available"
    assert es_evidence["trigger_transition_log"] == {
        "status": "available",
        "count": 1,
        "contract": "ES",
        "blocking_reasons": [],
        "source_schema": EVIDENCE_REPLAY_SCHEMA,
    }


def test_empty_replay_source_leaves_workspace_transition_log_unavailable() -> None:
    source = TriggerTransitionReplaySource(source="fixture")

    evidence = workspace_evidence("ES", trigger_transition_log=source.trigger_transition_log(contract="ES"))

    assert evidence["trigger_transition_log_status"] == "unavailable"
    assert evidence["trigger_transition_log"] == {
        "status": "unavailable",
        "count": 0,
        "contract": "ES",
        "blocking_reasons": ["log_source_not_wired"],
        "source_schema": None,
    }


def test_workspace_schema_guard_still_blocks_schema_less_and_decision_replay_logs() -> None:
    schema_less = {
        "contract": "ES",
        "trigger_transitions": [{"event_id": "evt-1", "event_type": "trigger_query_ready"}],
    }
    decision_replay_shape = {
        "schema": "decision_review_replay_shape",
        "contract": "ES",
        "trigger_transitions": [{"event_id": "evt-2", "event_type": "trigger_query_ready"}],
    }

    schema_less_evidence = workspace_evidence("ES", trigger_transition_log=schema_less)
    decision_replay_evidence = workspace_evidence("ES", trigger_transition_log=decision_replay_shape)

    assert schema_less_evidence["trigger_transition_log"]["status"] == "blocked"
    assert schema_less_evidence["trigger_transition_log"]["blocking_reasons"] == [
        "unsupported_transition_log_schema:<missing>",
    ]
    assert decision_replay_evidence["trigger_transition_log"]["status"] == "blocked"
    assert decision_replay_evidence["trigger_transition_log"]["blocking_reasons"] == [
        "unsupported_transition_log_schema:decision_review_replay_shape",
    ]


def trigger_result(
    contract: str,
    state: TriggerState,
    *,
    setup_id: str | None = None,
    trigger_id: str | None = None,
) -> TriggerStateResult:
    return TriggerStateResult(
        contract=contract,
        setup_id=setup_id or f"{contract.lower()}_setup_1",
        trigger_id=trigger_id or f"{contract.lower()}_trigger_1",
        state=state,
        distance_to_trigger_ticks=0.0 if state == TriggerState.QUERY_READY else None,
        required_fields=("market.current_price",),
        missing_fields=(),
        invalid_reasons=(),
        blocking_reasons=(),
        last_updated="2026-05-06T14:00:00+00:00",
    )


def workspace_evidence(
    contract: str,
    *,
    trigger_transition_log: dict[str, object] | None,
) -> dict[str, object]:
    workspace = build_operator_workspace_view_model(
        OperatorWorkspaceRequest(
            contract=contract,
            profile_id=f"preserved_{contract.lower()}_phase1",
            watchman_validator="READY",
            trigger_state=trigger_result(contract, TriggerState.QUERY_READY),
            pipeline_query_gate={
                "enabled": True,
                "pipeline_query_authorized": True,
                "profile_id": f"preserved_{contract.lower()}_phase1",
                "provider_status": "connected",
                "stream_status": "connected",
                "session_valid": True,
                "event_lockout_active": False,
            },
            trigger_transition_log=trigger_transition_log,
        )
    ).to_dict()
    return workspace["evidence_and_replay"]  # type: ignore[return-value]
