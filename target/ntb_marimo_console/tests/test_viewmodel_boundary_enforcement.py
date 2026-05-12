from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

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
from ntb_marimo_console.ui.marimo_phase1_renderer import build_stream_health_markdown, render_stream_health_panel
from ntb_marimo_console.viewmodels.mappers import (
    live_observable_vm_from_snapshot,
    premarket_brief_vm_from_brief,
    readiness_card_vm_from_context,
    stream_health_vm_from_snapshot,
)
from ntb_marimo_console.viewmodels.models import LiveObservableVM, PreMarketBriefVM, ReadinessCardVM, StreamHealthVM


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


if __name__ == "__main__":
    unittest.main()
