from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from ntb_marimo_console.active_trade import ActiveTradeRegistry, ThesisReference
from ntb_marimo_console.anchor_inputs import AnchorInputRegistry
from ntb_marimo_console.market_data.futures_quote_service import (
    FixtureFuturesQuoteProvider,
    FuturesQuote,
    FuturesQuoteService,
)
from ntb_marimo_console.market_data.stream_manager import (
    SchwabStreamManager,
    SchwabStreamManagerConfig,
    StreamClientResult,
    StreamSubscriptionRequest,
)
from ntb_marimo_console.operator_workspace import OperatorWorkspaceRequest, build_r14_cockpit_view_model
from ntb_marimo_console.operator_notes import OperatorNotesRegistry
from ntb_marimo_console.ui.marimo_phase1_renderer import (
    build_audit_timeline_markdown,
    build_anchor_inputs_markdown,
    build_active_trades_markdown,
    build_operator_notes_markdown,
    render_anchor_inputs_panel,
    build_stream_health_markdown,
    render_active_trades_panel,
    render_operator_notes_panel,
    render_stream_health_panel,
)
from ntb_marimo_console.viewmodels.mappers import (
    active_trade_vms_from_registry,
    live_observable_vm_from_snapshot,
    premarket_brief_vm_from_brief,
    readiness_card_vm_from_context,
    stream_health_vm_from_snapshot,
    timeline_events_from_session,
)
from ntb_marimo_console.viewmodels.models import (
    ActiveTradeVM,
    LiveObservableVM,
    PipelineTraceVM,
    PreMarketBriefVM,
    ReadinessCardVM,
    StreamHealthVM,
    TimelineEventVM,
)


@dataclass
class FakeClock:
    current: datetime = datetime(2026, 5, 12, 14, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current = self.current + timedelta(seconds=seconds)


class FakeStreamClient:
    def login(self, config: SchwabStreamManagerConfig) -> StreamClientResult:
        return StreamClientResult(succeeded=True)

    def subscribe(self, request: StreamSubscriptionRequest) -> StreamClientResult:
        return StreamClientResult(succeeded=True)

    def close(self) -> StreamClientResult:
        return StreamClientResult(succeeded=True)


def live_config(
    *,
    contracts: tuple[str, ...] = ("ES",),
    symbols: tuple[str, ...] = ("ES_TEST",),
) -> SchwabStreamManagerConfig:
    return SchwabStreamManagerConfig(
        provider="schwab",
        services_requested=("LEVELONE_FUTURES",),
        symbols_requested=symbols,
        fields_requested=(0, 1, 2, 3, 4, 5),
        explicit_live_opt_in=True,
        contracts_requested=contracts,
    )


def quote_message(*, contract: str, symbol: str, received_at: str) -> dict[str, object]:
    return {
        "service": "LEVELONE_FUTURES",
        "symbol": symbol,
        "contract": contract,
        "message_type": "quote",
        "fields": {"bid": 1.0, "ask": 1.25, "last": 1.125},
        "received_at": received_at,
    }


class ViewModelBoundaryEnforcementTests(unittest.TestCase):
    def test_engine_context_projects_to_readiness_vm_only(self) -> None:
        context = SimpleNamespace(
            contract="ES",
            event_risk_state="clear",
            vwap_posture_state="price_above_vwap",
            value_location_state="inside_value",
            level_proximity_state="clear_of_structure",
            hard_lockout_flags=[],
            awareness_flags=["awareness"],
            missing_inputs=[],
            extra_engine_only_field={"internal": True},
        )

        vm = readiness_card_vm_from_context(context)

        self.assertIsInstance(vm, ReadinessCardVM)
        self.assertFalse(hasattr(vm, "extra_engine_only_field"))

    def test_premarket_mapping_does_not_leak_full_engine_model(self) -> None:
        brief = {
            "contract": "ES",
            "session_date": "2026-03-25",
            "status": "READY",
            "structural_setups": [
                {
                    "summary": "Setup summary",
                    "warnings": ["warning"],
                    "fields_used": ["market.current_price"],
                    "engine_internal_payload": {"raw": "data"},
                }
            ],
        }

        vm = premarket_brief_vm_from_brief(brief)

        self.assertIsInstance(vm, PreMarketBriefVM)
        self.assertEqual(vm.setup_summaries, ("Setup summary",))
        self.assertFalse(hasattr(vm, "engine_internal_payload"))

    def test_live_observable_market_data_projection_is_safe_and_read_only(self) -> None:
        service = FuturesQuoteService(
            FixtureFuturesQuoteProvider(
                FuturesQuote(
                    symbol="ES",
                    bid_price=7175,
                    ask_price=7175.5,
                    last_price=7175.25,
                    bid_size=19,
                    ask_size=14,
                    received_at="2026-04-30T11:59:58+00:00",
                )
            ),
            clock=lambda: datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc),
        )

        vm = live_observable_vm_from_snapshot(
            {
                "contract": "ES",
                "timestamp_et": "2026-03-25T09:35:00-04:00",
                "market": {"current_price": 5600.0},
            },
            market_data_service=service,
            market_data_symbol="ES",
        )

        self.assertIsInstance(vm, LiveObservableVM)
        self.assertEqual(vm.market_data.status, "Fixture quote")
        self.assertEqual(vm.market_data.bid, "7175")
        self.assertEqual(vm.market_data.ask, "7175.5")
        self.assertEqual(vm.market_data.last, "7175.25")
        self.assertFalse(hasattr(vm.market_data, "provider_name"))
        self.assertFalse(hasattr(vm.market_data, "failure_reason"))
        self.assertFalse(hasattr(vm.market_data, "quote_age_seconds"))

    def test_stream_health_vm_from_active_snapshot_with_all_contracts_receiving(self) -> None:
        clock = FakeClock()
        manager = SchwabStreamManager(
            live_config(contracts=("ES", "NQ"), symbols=("ES_TEST", "NQ_TEST")),
            client=FakeStreamClient(),
            clock=clock,
        )
        manager.start()
        manager.ingest_message(
            quote_message(contract="ES", symbol="ES_TEST", received_at="2026-05-12T14:00:00+00:00")
        )
        manager.ingest_message(
            quote_message(contract="NQ", symbol="NQ_TEST", received_at="2026-05-12T14:00:00+00:00")
        )

        vm = stream_health_vm_from_snapshot(
            manager.snapshot(),
            token_status={"valid": True, "expires_in_seconds": 1200, "refresh_count": 0},
        )

        self.assertIsInstance(vm, StreamHealthVM)
        self.assertEqual(vm.connection_state, "active")
        self.assertEqual(vm.token_status, "valid")
        self.assertEqual(vm.per_contract_status, {"ES": "active", "NQ": "active"})
        self.assertEqual(vm.overall_health, "healthy")

    def test_stream_health_vm_from_snapshot_with_mixed_stale_and_no_data_contracts(self) -> None:
        clock = FakeClock()
        manager = SchwabStreamManager(
            live_config(contracts=("ES", "NQ", "CL"), symbols=("ES_TEST", "NQ_TEST", "CL_TEST")),
            client=FakeStreamClient(),
            clock=clock,
        )
        manager.start()
        manager.ingest_message(
            quote_message(contract="ES", symbol="ES_TEST", received_at="2026-05-12T14:00:00+00:00")
        )
        clock.advance(20)
        manager.ingest_message(
            quote_message(contract="NQ", symbol="NQ_TEST", received_at="2026-05-12T14:00:20+00:00")
        )
        clock.advance(15)
        snapshot = manager.check_contract_heartbeats()

        vm = stream_health_vm_from_snapshot(
            snapshot,
            token_status={"valid": True, "expires_in_seconds": 1200, "refresh_count": 0},
        )

        self.assertEqual(vm.per_contract_status["ES"], "stale")
        self.assertEqual(vm.per_contract_status["NQ"], "active")
        self.assertEqual(vm.per_contract_status["CL"], "no_data")
        self.assertEqual(vm.stale_contracts, ("ES",))
        self.assertIn("contract_stale:ES", vm.blocking_reasons)
        self.assertIn("contract_no_data:CL", vm.blocking_reasons)
        self.assertEqual(vm.overall_health, "degraded")

    def test_stream_health_vm_from_disconnected_and_reconnecting_snapshots(self) -> None:
        manager = SchwabStreamManager(live_config(), client=FakeStreamClient(), clock=FakeClock())
        manager.start()
        disconnected = manager.mark_connection_lost("connection_lost")
        disconnected_vm = stream_health_vm_from_snapshot(
            disconnected,
            token_status={"valid": True, "expires_in_seconds": 1200},
        )

        manager = SchwabStreamManager(live_config(), client=FakeStreamClient(), clock=FakeClock())
        manager.start()
        reconnecting = manager.begin_reconnect_attempt(attempt=1, delay_seconds=1.0)
        reconnecting_vm = stream_health_vm_from_snapshot(
            reconnecting,
            token_status={"valid": True, "expires_in_seconds": 1200},
        )

        self.assertEqual(disconnected_vm.connection_state, "disconnected")
        self.assertEqual(disconnected_vm.overall_health, "blocked")
        self.assertEqual(reconnecting_vm.connection_state, "reconnecting")
        self.assertTrue(reconnecting_vm.reconnect_active)
        self.assertEqual(reconnecting_vm.reconnect_attempts, 1)
        self.assertEqual(reconnecting_vm.overall_health, "degraded")

    def test_stream_health_vm_with_token_expiring_soon(self) -> None:
        manager = SchwabStreamManager(live_config(), client=FakeStreamClient(), clock=FakeClock())
        manager.start()
        manager.ingest_message(
            quote_message(contract="ES", symbol="ES_TEST", received_at="2026-05-12T14:00:00+00:00")
        )

        vm = stream_health_vm_from_snapshot(
            manager.snapshot(),
            token_status={"valid": True, "expires_in_seconds": 120, "refresh_count": 0},
        )

        self.assertEqual(vm.token_status, "expiring_soon")
        self.assertEqual(vm.token_expires_in_seconds, 120)
        self.assertEqual(vm.overall_health, "degraded")

    def test_stream_health_vm_with_token_refresh_failed(self) -> None:
        manager = SchwabStreamManager(live_config(), client=FakeStreamClient(), clock=FakeClock())
        manager.start()
        manager.ingest_message(
            quote_message(contract="ES", symbol="ES_TEST", received_at="2026-05-12T14:00:00+00:00")
        )

        vm = stream_health_vm_from_snapshot(
            manager.snapshot(),
            token_status={"valid": False, "expires_in_seconds": 1200, "refresh_count": 1},
        )

        self.assertEqual(vm.token_status, "refresh_failed")
        self.assertEqual(vm.overall_health, "blocked")

    def test_stream_health_overall_health_resolves_healthy_degraded_blocked(self) -> None:
        clock = FakeClock()
        manager = SchwabStreamManager(live_config(), client=FakeStreamClient(), clock=clock)
        manager.start()
        manager.ingest_message(
            quote_message(contract="ES", symbol="ES_TEST", received_at="2026-05-12T14:00:00+00:00")
        )
        healthy = stream_health_vm_from_snapshot(
            manager.snapshot(),
            token_status={"valid": True, "expires_in_seconds": 1200},
        )
        clock.advance(31)
        degraded = stream_health_vm_from_snapshot(
            manager.check_contract_heartbeats(),
            token_status={"valid": True, "expires_in_seconds": 1200},
        )
        blocked = stream_health_vm_from_snapshot(
            manager.mark_connection_lost("connection_lost"),
            token_status={"valid": True, "expires_in_seconds": 1200},
        )

        self.assertEqual(healthy.overall_health, "healthy")
        self.assertEqual(degraded.overall_health, "degraded")
        self.assertEqual(blocked.overall_health, "blocked")

    def test_fixture_non_live_mode_has_no_primary_stream_health_panel(self) -> None:
        rendered = render_stream_health_panel(
            {"runtime": {"operator_live_runtime_mode": "SAFE_NON_LIVE"}}
        )

        self.assertIsNone(rendered)

    def test_stream_health_markdown_surfaces_degraded_alerts_without_gate_enablement(self) -> None:
        markdown = build_stream_health_markdown(
            {
                "connection_state": "reconnecting",
                "token_status": "expiring_soon",
                "token_expires_in_seconds": 120,
                "reconnect_attempts": 2,
                "reconnect_active": True,
                "per_contract_status": {"ES": "active", "CL": "stale", "MGC": "no_data"},
                "stale_contracts": ["CL"],
                "blocking_reasons": ["contract_stale:CL"],
                "overall_health": "degraded",
            }
        )

        self.assertIn("## Live Stream Health", markdown)
        self.assertIn("Overall Health: `degraded`", markdown)
        self.assertIn("| `ES` | `green` | `active` |", markdown)
        self.assertIn("| `CL` | `red` | `stale` |", markdown)
        self.assertIn("contract_stale:CL", markdown)
        self.assertNotIn("Query Enabled: `True`", markdown)

    def test_r14_cockpit_runtime_status_passes_through_stream_health(self) -> None:
        cockpit = build_r14_cockpit_view_model(
            OperatorWorkspaceRequest(
                contract="ES",
                profile_id="fixture_es_demo",
                watchman_validator={"status": "READY"},
                trigger_state=None,
                pipeline_query_gate={},
                stream_health={
                    "connection_state": "active",
                    "token_status": "valid",
                    "token_expires_in_seconds": 1200,
                    "reconnect_attempts": 0,
                    "reconnect_active": False,
                    "per_contract_status": {"ES": "active"},
                    "stale_contracts": [],
                    "blocking_reasons": [],
                    "overall_health": "healthy",
                },
            )
        ).to_dict()

        stream_health = cockpit["runtime_status"]["stream_health"]  # type: ignore[index]
        self.assertEqual(stream_health["per_contract_status"], {"ES": "active"})
        self.assertEqual(stream_health["overall_health"], "healthy")

    def test_active_trade_vm_maps_open_trades_from_registry_and_cache(self) -> None:
        registry = ActiveTradeRegistry(clock=FakeClock())
        trade = registry.add(
            trade_id="trade-es-fixture-001",
            contract="ES",
            direction="long",
            entry_price=5325.0,
            thesis_reference=ThesisReference(
                pipeline_result_id="pipeline-result-fixture-001",
                trigger_name="fixture-trigger",
                trigger_state="QUERY_READY",
            ),
            stop_loss=5315.0,
            target=5345.0,
            operator_notes="Operator-entered fixture annotation.",
        )
        manager = SchwabStreamManager(live_config(), client=FakeStreamClient(), clock=FakeClock())
        manager.start()
        manager.ingest_message(
            {
                **quote_message(contract="ES", symbol="ES_TEST", received_at="2026-05-12T14:00:00+00:00"),
                "fields": {"bid": 5334.75, "ask": 5335.25, "last": 5335.0},
            }
        )

        rows = active_trade_vms_from_registry(registry, manager.snapshot().cache)

        self.assertEqual(len(rows), 1)
        self.assertIsInstance(rows[0], ActiveTradeVM)
        self.assertEqual(rows[0].trade_id, trade.trade_id)
        self.assertEqual(rows[0].current_price, 5335.0)
        self.assertEqual(rows[0].unrealized_pnl, 10.0)
        self.assertEqual(rows[0].thesis_health, "healthy")
        self.assertEqual(rows[0].distance_from_stop, 20.0)
        self.assertEqual(rows[0].distance_from_target, 10.0)

    def test_active_trade_vm_unrealized_points_are_direction_aware_for_shorts(self) -> None:
        registry = ActiveTradeRegistry(clock=FakeClock())
        registry.add(
            trade_id="trade-nq-short-fixture",
            contract="NQ",
            direction="short",
            entry_price=100.0,
            thesis_reference=ThesisReference(
                pipeline_result_id="pipeline-result-fixture-001",
                trigger_name="fixture-trigger",
                trigger_state="QUERY_READY",
            ),
            stop_loss=105.0,
            target=90.0,
        )
        manager = SchwabStreamManager(
            live_config(contracts=("NQ",), symbols=("NQ_TEST",)),
            client=FakeStreamClient(),
            clock=FakeClock(),
        )
        manager.start()
        manager.ingest_message(
            {
                **quote_message(contract="NQ", symbol="NQ_TEST", received_at="2026-05-12T14:00:00+00:00"),
                "fields": {"last": 95.0},
            }
        )

        rows = active_trade_vms_from_registry(registry, manager.snapshot().cache)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].direction, "short")
        self.assertEqual(rows[0].unrealized_pnl, 5.0)

    def test_active_trade_vm_excludes_closed_trades(self) -> None:
        registry = ActiveTradeRegistry(clock=FakeClock())
        open_trade = registry.add(
            trade_id="trade-es-open",
            contract="ES",
            direction="long",
            entry_price=5325.0,
            stop_loss=5315.0,
            target=5345.0,
        )
        closed_trade = registry.add(
            trade_id="trade-es-closed",
            contract="ES",
            direction="long",
            entry_price=5320.0,
            stop_loss=5310.0,
            target=5340.0,
        )
        registry.close(closed_trade.trade_id, status="closed", close_reason="fixture_closed")
        manager = SchwabStreamManager(live_config(), client=FakeStreamClient(), clock=FakeClock())
        manager.start()
        manager.ingest_message(
            {
                **quote_message(contract="ES", symbol="ES_TEST", received_at="2026-05-12T14:00:00+00:00"),
                "fields": {"last": 5330.0},
            }
        )

        rows = active_trade_vms_from_registry(registry, manager.snapshot().cache)

        self.assertEqual(tuple(row.trade_id for row in rows), (open_trade.trade_id,))

    def test_active_trade_markdown_is_display_only_and_does_not_enable_query_or_execution(self) -> None:
        markdown = build_active_trades_markdown(
            {
                "status": "ready",
                "message": "Operator-recorded annotations only; P&L is a display calculation and execution remains manual.",
                "rows": [
                    {
                        "trade_id": "trade-es-fixture-001",
                        "contract": "ES",
                        "direction": "long",
                        "entry_price": 5325.0,
                        "entry_time": "2026-05-12T14:00:00+00:00",
                        "stop_loss": 5315.0,
                        "target": 5345.0,
                        "status": "open",
                        "current_price": 5335.0,
                        "unrealized_pnl": 10.0,
                        "thesis_health": "healthy",
                        "thesis_health_reasons": ["thesis_holding"],
                        "distance_from_stop": 20.0,
                        "distance_from_target": 10.0,
                        "operator_notes": "fixture annotation",
                    }
                ],
            }
        )

        self.assertIn("## Active Trades", markdown)
        self.assertIn("green healthy", markdown)
        self.assertIn("green 10", markdown)
        self.assertIn("execution remains manual", markdown)
        self.assertNotIn("Query Enabled: `True`", markdown)
        self.assertNotIn("submit order", markdown.lower())
        self.assertNotIn("broker", markdown.lower())

    def test_fixture_non_live_mode_has_no_primary_active_trade_panel(self) -> None:
        rendered = render_active_trades_panel(
            {"runtime": {"operator_live_runtime_mode": "SAFE_NON_LIVE"}}
        )

        self.assertIsNone(rendered)

    def test_anchor_inputs_markdown_is_operator_context_not_decision_authority(self) -> None:
        markdown = build_anchor_inputs_markdown(
            {
                "status": "ready",
                "message": "Operator-supplied context only; preserved engine remains decision authority.",
                "integration_status": "operator_context_available_not_gate_enforced",
                "rows": [
                    {
                        "contract": "NQ",
                        "key_levels": [18650.0, 18725.5],
                        "session_high": 18780.0,
                        "session_low": 18590.25,
                        "correlation_anchor": "ES",
                        "operator_note": "Fixture anchor note.",
                        "updated_at": "2026-05-12T15:30:00+00:00",
                    }
                ],
            }
        )

        self.assertIn("## Cross-Asset Anchor Inputs", markdown)
        self.assertIn("operator_context_available_not_gate_enforced", markdown)
        self.assertIn("preserved engine remains decision authority", markdown)
        self.assertIn("NQ", markdown)
        self.assertIn("ES", markdown)
        self.assertNotIn("Query Enabled: `True`", markdown)
        self.assertNotIn("trade_authorized", markdown)

    def test_anchor_inputs_panel_renders_in_safe_non_live_mode(self) -> None:
        rendered = render_anchor_inputs_panel(
            {"runtime": {"operator_live_runtime_mode": "SAFE_NON_LIVE"}}
        )

        self.assertIsNotNone(rendered)

    def test_operator_notes_markdown_is_annotation_only(self) -> None:
        markdown = build_operator_notes_markdown(
            {
                "status": "ready",
                "message": "Session journal entries are operator annotations only.",
                "rows": [
                    {
                        "note_id": "note-1",
                        "timestamp": "2026-05-12T13:00:00+00:00",
                        "category": "pre_market",
                        "contract": None,
                        "content": "Fixture session context.",
                        "tags": ["context", "plan"],
                    }
                ],
            }
        )

        self.assertIn("## Operator Notes", markdown)
        self.assertIn("blue pre_market", markdown)
        self.assertIn("Fixture session context", markdown)
        self.assertIn("annotations only", markdown)
        self.assertNotIn("Query Enabled: `True`", markdown)
        self.assertNotIn("trade_authorized", markdown)

    def test_operator_notes_panel_renders_in_safe_non_live_mode(self) -> None:
        rendered = render_operator_notes_panel(
            {"runtime": {"operator_live_runtime_mode": "SAFE_NON_LIVE"}}
        )

        self.assertIsNotNone(rendered)

    def test_timeline_events_aggregate_session_artifacts_chronologically(self) -> None:
        clock = FakeClock()
        trade_registry = ActiveTradeRegistry(clock=clock)
        trade = trade_registry.add(
            trade_id="trade-es-timeline",
            contract="ES",
            direction="long",
            entry_price=5325.0,
            stop_loss=5315.0,
            target=5345.0,
        )
        clock.advance(60)
        trade_registry.close(trade.trade_id, status="closed", close_reason="fixture_close")
        notes = OperatorNotesRegistry()
        notes.add(
            note_id="note-es-timeline",
            timestamp="2026-05-12T13:30:00+00:00",
            category="intraday",
            contract="ES",
            content="Fixture timeline note.",
            tags=("audit",),
        )
        anchors = AnchorInputRegistry()
        anchors.set(
            contract="NQ",
            key_levels=(18650.0,),
            updated_at="2026-05-12T13:45:00+00:00",
            operator_note="Fixture anchor update.",
        )
        trace = PipelineTraceVM(
            contract="ES",
            termination_stage="risk_authorization",
            final_decision="NO_TRADE",
            stage_a_status="READY",
            stage_b_outcome="SETUP_PROPOSED",
            stage_c_outcome="SETUP_PROPOSED",
            stage_d_decision="REJECTED",
        )

        events = timeline_events_from_session(
            trigger_transitions=(
                {
                    "contract": "ES",
                    "trigger_id": "fixture-trigger",
                    "state": "QUERY_READY",
                    "last_updated": "2026-05-12T13:00:00+00:00",
                    "missing_fields": [],
                    "blocking_reasons": [],
                    "invalid_reasons": [],
                    "required_fields": [],
                },
            ),
            pipeline_traces=(trace,),
            active_trade_registry=trade_registry,
            operator_notes_registry=notes,
            anchor_input_registry=anchors,
            session_timestamp="2026-05-12T13:05:00+00:00",
        )

        self.assertTrue(all(isinstance(event, TimelineEventVM) for event in events))
        self.assertEqual(
            tuple(event.event_type for event in events),
            ("trigger_transition", "pipeline_result", "note", "anchor_update", "trade_entry", "trade_close"),
        )
        self.assertEqual(events[0].status_badge, "green QUERY_READY")
        self.assertIn("preserved pipeline must still decide", events[0].detail)

    def test_audit_timeline_markdown_is_read_only_and_filterable(self) -> None:
        markdown = build_audit_timeline_markdown(
            {
                "timeline_status": "ready",
                "timeline_filters": {
                    "event_types": ["pipeline_result", "note"],
                    "contracts": ["ES"],
                },
                "timeline_events": [
                    {
                        "event_id": "event-1",
                        "timestamp": "2026-05-12T13:05:00+00:00",
                        "event_type": "pipeline_result",
                        "contract": "ES",
                        "summary": "Pipeline result: NO_TRADE",
                        "detail": "termination_stage=risk_authorization",
                        "status_badge": "gray NO_TRADE",
                    }
                ],
            }
        )

        self.assertIn("## Audit / Replay Timeline", markdown)
        self.assertIn("Event Type Filters: `pipeline_result`, `note`", markdown)
        self.assertIn("Contract Filters: `ES`", markdown)
        self.assertIn("read-only audit context", markdown)
        self.assertIn("Pipeline result: NO_TRADE", markdown)
        self.assertNotIn("Query Enabled: `True`", markdown)
        self.assertNotIn("trade_authorized", markdown)

    def test_audit_timeline_markdown_applies_supplied_filters(self) -> None:
        markdown = build_audit_timeline_markdown(
            {
                "timeline_status": "ready",
                "timeline_filters": {
                    "event_types": ["pipeline_result", "note"],
                    "contracts": ["ES", "NQ"],
                    "selected_event_types": ["note"],
                    "selected_contracts": ["NQ"],
                },
                "timeline_events": [
                    {
                        "event_id": "event-1",
                        "timestamp": "2026-05-12T13:05:00+00:00",
                        "event_type": "pipeline_result",
                        "contract": "ES",
                        "summary": "Pipeline result: NO_TRADE",
                        "detail": "termination_stage=risk_authorization",
                        "status_badge": "gray NO_TRADE",
                    },
                    {
                        "event_id": "event-2",
                        "timestamp": "2026-05-12T13:10:00+00:00",
                        "event_type": "note",
                        "contract": "NQ",
                        "summary": "Operator note: intraday",
                        "detail": "NQ note",
                        "status_badge": "gray operator_annotation",
                    },
                ],
            }
        )

        self.assertIn("Active Event Type Filters: `note`", markdown)
        self.assertIn("Active Contract Filters: `NQ`", markdown)
        self.assertIn("Operator note: intraday", markdown)
        self.assertNotIn("Pipeline result: NO_TRADE", markdown)

    def test_viewmodels_public_exports_include_new_runtime_symbols(self) -> None:
        import ntb_marimo_console.viewmodels as public

        self.assertIs(public.TimelineEventVM, TimelineEventVM)
        self.assertIs(public.StreamHealthVM, StreamHealthVM)
        self.assertIs(public.timeline_events_from_session, timeline_events_from_session)


if __name__ == "__main__":
    unittest.main()
