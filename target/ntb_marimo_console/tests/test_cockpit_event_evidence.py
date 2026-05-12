from __future__ import annotations

import json

import pytest

from ntb_marimo_console.cockpit_event_evidence import (
    CockpitEventReplaySource,
    CockpitEvidenceEventType,
    CockpitEvidenceRecord,
)
from ntb_marimo_console.evidence_replay import EVIDENCE_REPLAY_SCHEMA
from ntb_marimo_console.market_data.stream_cache import StreamCacheRecord, StreamCacheSnapshot
from ntb_marimo_console.market_data.stream_events import StreamEvent
from ntb_marimo_console.market_data.stream_manager import SchwabStreamManagerConfig, StreamManagerSnapshot
from ntb_marimo_console.operator_workspace import OperatorWorkspaceRequest, build_operator_workspace_view_model
from ntb_marimo_console.pipeline_query_gate import PipelineQueryGateRequest, evaluate_pipeline_query_gate
from ntb_marimo_console.trigger_state import TriggerState, TriggerStateResult
from ntb_marimo_console.trigger_transition_replay_source import TriggerTransitionReplaySource
from ntb_marimo_console.viewmodels.models import TriggerStatusVM


NOW = "2026-05-06T14:00:00+00:00"
PREMARKET_REF = "premarket/ES/2026-05-06/brief.json"


def test_cockpit_stream_events_are_from_app_owned_snapshot_and_deterministic() -> None:
    source = CockpitEventReplaySource(source="live_stream")
    snapshot = stream_snapshot(
        events=(
            stream_event("login_succeeded", "connected", NOW),
            stream_event("subscription_succeeded", "active", "2026-05-06T14:00:01+00:00"),
        ),
    )

    first = source.observe_stream_snapshot(
        snapshot,
        profile_id="preserved_es_phase1",
        premarket_brief_ref=PREMARKET_REF,
    )
    second = source.observe_stream_snapshot(
        snapshot,
        profile_id="preserved_es_phase1",
        premarket_brief_ref=PREMARKET_REF,
    )

    assert len(first) == 2
    assert second == ()
    assert [event.event_type for event in source.events] == ["stream_connected", "subscription_added"]
    assert [event.contract for event in source.events] == ["ES", "ES"]
    assert all(event.profile_id == "preserved_es_phase1" for event in source.events)
    assert all(event.synthetic is False for event in source.events)
    assert json.dumps([event.to_dict() for event in source.events], sort_keys=True)


def test_cockpit_stream_observation_rejects_display_or_mapping_payloads() -> None:
    source = CockpitEventReplaySource(source="fixture")

    with pytest.raises(TypeError, match="StreamManagerSnapshot"):
        source.observe_stream_snapshot({"state": "active"}, profile_id="preserved_es_phase1")  # type: ignore[arg-type]

    assert source.events == ()


def test_cockpit_replay_blocks_missing_replay_data_in_workspace() -> None:
    source = CockpitEventReplaySource(source="live_stream")
    source.observe_stream_snapshot(
        stream_snapshot(events=(stream_event("login_succeeded", "connected", NOW),)),
        profile_id="preserved_es_phase1",
        premarket_brief_ref=PREMARKET_REF,
    )
    replay = source.replay_log(contract="ES", profile_id="preserved_es_phase1")

    evidence = workspace_evidence("ES", cockpit_event_replay=replay)

    assert replay is not None
    assert replay["status"] == "incomplete"
    assert evidence["cockpit_event_replay_status"] == "blocked"
    assert evidence["cockpit_event_replay"]["incomplete_reasons"] == [
        "trigger_transition_evidence_missing",
    ]


def test_cockpit_replay_accepts_complete_real_app_owned_sequence() -> None:
    source = CockpitEventReplaySource(source="fixture")
    source.append_trigger_transition_events(trigger_transition_events("ES", "preserved_es_phase1"))
    source.append_records(
        (
            record(CockpitEvidenceEventType.STREAM_CONNECTED, timestamp=NOW),
        )
    )
    trigger = trigger_result("ES", TriggerState.QUERY_READY)
    gate = query_gate("ES", trigger)
    source.observe_query_submission(
        gate=gate,
        trigger_state=trigger,
        timestamp="2026-05-06T14:00:02+00:00",
        pipeline_run_id="run-es-1",
        premarket_brief_ref=PREMARKET_REF,
    )
    source.observe_pipeline_result(
        contract="ES",
        profile_id="preserved_es_phase1",
        timestamp="2026-05-06T14:00:03+00:00",
        pipeline_run_id="run-es-1",
        pipeline_summary={"contract": "ES", "final_decision": "NO_TRADE"},
        premarket_brief_ref=PREMARKET_REF,
    )
    source.observe_operator_note(
        contract="ES",
        profile_id="preserved_es_phase1",
        timestamp="2026-05-06T14:00:04+00:00",
        operator_note="Reviewed after the bounded query.",
        premarket_brief_ref=PREMARKET_REF,
    )
    replay = source.replay_log(contract="ES", profile_id="preserved_es_phase1")
    evidence = workspace_evidence("ES", cockpit_event_replay=replay)

    assert replay is not None
    assert replay["schema"] == EVIDENCE_REPLAY_SCHEMA
    assert replay["status"] == "complete"
    assert replay["complete"] is True
    assert evidence["cockpit_event_replay_status"] == "available"
    assert evidence["cockpit_event_replay"]["event_count"] == 6


def test_cockpit_replay_blocks_synthetic_evidence_even_when_source_is_fixture() -> None:
    source = CockpitEventReplaySource(source="fixture")
    source.append_trigger_transition_events(trigger_transition_events("ES", "preserved_es_phase1"))
    source.append_records(
        (
            record(CockpitEvidenceEventType.STREAM_CONNECTED, timestamp=NOW, synthetic=True),
        )
    )
    replay = source.replay_log(contract="ES", profile_id="preserved_es_phase1")

    assert replay is not None
    assert replay["status"] == "blocked"
    assert "synthetic_evidence_not_replayable:" in " ".join(replay["blocking_reasons"])
    assert replay["synthetic_replay_labeled_real"] is False


@pytest.mark.parametrize("contract", ("ES", "NQ", "CL", "6E", "MGC"))
def test_cockpit_events_are_contract_attributed_without_bleed(contract: str) -> None:
    profile_id = f"preserved_{contract.lower()}_phase1"
    source = CockpitEventReplaySource(source="fixture")
    source.append_trigger_transition_events(trigger_transition_events(contract, profile_id))
    source.append_records(
        (
            record(
                CockpitEvidenceEventType.STREAM_CONNECTED,
                contract=contract,
                profile_id=profile_id,
                timestamp=NOW,
                premarket_brief_ref=f"premarket/{contract}/2026-05-06/brief.json",
            ),
        )
    )

    replay = source.replay_log(contract=contract, profile_id=profile_id)
    evidence = workspace_evidence(contract, cockpit_event_replay=replay)
    rendered = json.dumps(evidence, sort_keys=True)

    assert evidence["cockpit_event_replay"]["contract"] == contract
    assert evidence["cockpit_event_replay"]["status"] == "available"
    for other in ("ES", "NQ", "CL", "6E", "MGC"):
        if other != contract:
            assert f"preserved_{other.lower()}_phase1" not in rendered


def test_cross_contract_cockpit_replay_is_blocked_by_workspace() -> None:
    source = CockpitEventReplaySource(source="fixture")
    source.append_trigger_transition_events(trigger_transition_events("NQ", "preserved_nq_phase1"))
    source.append_records(
        (
            record(CockpitEvidenceEventType.STREAM_CONNECTED, contract="NQ", profile_id="preserved_nq_phase1"),
        )
    )
    replay = source.replay_log(contract="NQ", profile_id="preserved_nq_phase1")

    evidence = workspace_evidence("ES", cockpit_event_replay=replay)

    assert evidence["cockpit_event_replay_status"] == "blocked"
    assert evidence["cockpit_event_replay"]["blocking_reasons"] == [
        "cross_contract_cockpit_event_replay:NQ",
    ]


def test_display_view_model_cannot_create_query_submitted_cockpit_evidence() -> None:
    source = CockpitEventReplaySource(source="fixture")
    display_trigger = TriggerStatusVM(
        trigger_id="display_query_ready",
        is_valid=True,
        is_true=True,
        missing_fields=(),
        invalid_reasons=(),
    )

    emitted = source.observe_query_submission(
        gate={"enabled": True},  # type: ignore[arg-type]
        trigger_state=display_trigger,  # type: ignore[arg-type]
        timestamp="2026-05-06T14:00:02+00:00",
        pipeline_run_id="run-display",
    )

    assert emitted == ()
    assert source.events == ()


def test_bar_closed_and_session_reset_events_are_real_app_owned_records() -> None:
    source = CockpitEventReplaySource(source="fixture")
    source.observe_stream_snapshot(
        stream_snapshot(
            records=(
                cache_record("ES", message_type="bar"),
            ),
            events=(),
        ),
        profile_id="preserved_es_phase1",
        premarket_brief_ref=PREMARKET_REF,
    )
    source.observe_session_reset(
        contract="ES",
        profile_id="preserved_es_phase1",
        timestamp="2026-05-06T14:00:05+00:00",
        premarket_brief_ref=PREMARKET_REF,
    )

    assert [event.event_type for event in source.events] == ["bar_closed", "session_reset"]
    assert all(event.contract == "ES" for event in source.events)


def record(
    event_type: CockpitEvidenceEventType,
    *,
    contract: str = "ES",
    profile_id: str = "preserved_es_phase1",
    timestamp: str = NOW,
    premarket_brief_ref: str = PREMARKET_REF,
    data_quality: dict[str, object] | None = None,
    synthetic: bool = False,
) -> CockpitEvidenceRecord:
    return CockpitEvidenceRecord(
        contract=contract,
        profile_id=profile_id,
        event_type=event_type,
        timestamp=timestamp,
        source="fixture",
        setup_id=f"{contract.lower()}_setup_1",
        trigger_id=f"{contract.lower()}_trigger_1",
        premarket_brief_ref=premarket_brief_ref,
        data_quality=data_quality or {},
        synthetic=synthetic,
    )


def stream_snapshot(
    *,
    records: tuple[StreamCacheRecord, ...] | None = None,
    events: tuple[StreamEvent, ...] = (),
) -> StreamManagerSnapshot:
    cache_records = records if records is not None else (cache_record("ES"),)
    return StreamManagerSnapshot(
        state="active",
        config=SchwabStreamManagerConfig(
            provider="schwab",
            services_requested=("LEVELONE_FUTURES",),
            symbols_requested=("/ESM26",),
            fields_requested=(0, 1, 2),
            explicit_live_opt_in=True,
            contracts_requested=("ES",),
        ),
        cache=StreamCacheSnapshot(
            generated_at=NOW,
            provider="schwab",
            provider_status="active",
            cache_max_age_seconds=15.0,
            records=cache_records,
            blocking_reasons=(),
            stale_symbols=(),
        ),
        events=events,
        blocking_reasons=(),
        login_count=1,
        subscription_count=1,
    )


def cache_record(contract: str, *, message_type: str = "quote", fresh: bool = True) -> StreamCacheRecord:
    return StreamCacheRecord(
        provider="schwab",
        service="LEVELONE_FUTURES",
        symbol=f"/{contract}M26",
        contract=contract,
        message_type=message_type,  # type: ignore[arg-type]
        fields=(("last", 100.0),),
        updated_at=NOW,
        age_seconds=0.0 if fresh else 30.0,
        fresh=fresh,
        blocking_reasons=(),
    )


def stream_event(event_type: str, state: str, generated_at: str) -> StreamEvent:
    return StreamEvent(
        event_type=event_type,  # type: ignore[arg-type]
        state=state,  # type: ignore[arg-type]
        provider="schwab",
        summary=event_type,
        generated_at=generated_at,
        symbols=("/ESM26",),
        services=("LEVELONE_FUTURES",),
    )


def trigger_result(contract: str, state: TriggerState) -> TriggerStateResult:
    return TriggerStateResult(
        contract=contract,
        setup_id=f"{contract.lower()}_setup_1",
        trigger_id=f"{contract.lower()}_trigger_1",
        state=state,
        distance_to_trigger_ticks=0.0 if state == TriggerState.QUERY_READY else None,
        required_fields=("market.current_price",),
        missing_fields=(),
        invalid_reasons=(),
        blocking_reasons=(),
        last_updated=NOW,
    )


def trigger_transition_events(contract: str, profile_id: str) -> tuple[object, ...]:
    source = TriggerTransitionReplaySource(source="fixture")
    source.observe(
        trigger_result(contract, TriggerState.ARMED),
        timestamp="2026-05-06T14:00:00+00:00",
        profile_id=profile_id,
        premarket_brief_ref=f"premarket/{contract}/2026-05-06/brief.json",
    )
    return source.observe(
        trigger_result(contract, TriggerState.QUERY_READY),
        timestamp="2026-05-06T14:00:01+00:00",
        profile_id=profile_id,
        premarket_brief_ref=f"premarket/{contract}/2026-05-06/brief.json",
    )


def query_gate(contract: str, trigger: TriggerStateResult) -> object:
    return evaluate_pipeline_query_gate(
        PipelineQueryGateRequest(
            contract=contract,
            profile_id=f"preserved_{contract.lower()}_phase1",
            profile_exists=True,
            profile_preflight_passed=True,
            watchman_validator_status="READY",
            live_snapshot={"contract": contract},
            live_snapshot_fresh=True,
            quote_fresh=True,
            bars_available=True,
            bars_fresh=True,
            required_trigger_fields_present=True,
            trigger_state=trigger,
            provider_status="fixture",
            stream_status="fixture",
            session_valid=True,
            event_lockout_active=False,
            fixture_mode_accepted=True,
            trigger_state_from_real_producer=True,
            evaluated_at=NOW,
        )
    )


def workspace_evidence(
    contract: str,
    *,
    cockpit_event_replay: dict[str, object] | None,
) -> dict[str, object]:
    workspace = build_operator_workspace_view_model(
        OperatorWorkspaceRequest(
            contract=contract,
            profile_id=f"preserved_{contract.lower()}_phase1",
            watchman_validator="READY",
            trigger_state=trigger_result(contract, TriggerState.QUERY_READY),
            pipeline_query_gate=query_gate(contract, trigger_result(contract, TriggerState.QUERY_READY)),
            cockpit_event_replay=cockpit_event_replay,
        )
    ).to_dict()
    return workspace["evidence_and_replay"]  # type: ignore[return-value]
