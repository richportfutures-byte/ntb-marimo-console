"""Regression tests: live data freshness path under OPERATOR_LIVE_RUNTIME.

These tests pin the contract that fresh LEVELONE_FUTURES data is the freshness
signal that drives provider/quote classification:

- A fresh LEVELONE_FUTURES record makes the contract's quote path fresh, even
  when CHART_FUTURES is stale or missing.
- CHART_FUTURES staleness alone does not flip provider to LIVE_RUNTIME_STALE
  or downgrade ``runtime_cache_provider_status`` to "stale".
- Per-row chart_status remains independently fail-closed when chart bars are
  stale or missing — chart staleness is a per-row chart blocker only.
- Missing required quote fields block only the affected contract.
- Evidence redaction stops false-positive flagging of normal lifecycle status
  codes such as ``operator_live_runtime_stale`` and ``operator_live_runtime_stale.``
  while still redacting real token-like material.
- The five-contract readiness summary surfaces the per-service active sets so
  the cockpit / live smoke can reason about the freshness chain.
- No display/view-model/readiness/rendering/evidence code creates QUERY_READY.
"""

from __future__ import annotations

import unittest

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.market_data.stream_cache import StreamCacheRecord, StreamCacheSnapshot
from ntb_marimo_console.market_data.stream_events import redact_sensitive_text
from ntb_marimo_console.market_data.stream_manager import (
    SchwabStreamManagerConfig,
    StreamManagerSnapshot,
)
from ntb_marimo_console.operator_live_runtime import (
    OPERATOR_LIVE_RUNTIME,
    StaticRuntimeSnapshotProducer,
    resolve_operator_runtime_snapshot,
)
from ntb_marimo_console.primary_cockpit import (
    LIVE_OBSERVATION_MODE_CONNECTED,
    build_live_observation_cockpit_surface,
)
from ntb_marimo_console.readiness_summary import (
    LIVE_RUNTIME_CONNECTED,
    LIVE_RUNTIME_STALE,
    build_five_contract_readiness_summary,
    build_five_contract_readiness_summary_surface,
)


NOW = "2026-05-15T14:00:00+00:00"

RUNTIME_SYMBOL_BY_CONTRACT: dict[str, str] = {
    "ES": "/ESM26",
    "NQ": "/NQM26",
    "CL": "/CLM26",
    "6E": "/6EM26",
    "MGC": "/MGCM26",
}


def _complete_levelone_fields(index: int = 0) -> tuple[tuple[str, object], ...]:
    return (
        ("bid", 100.0 + index),
        ("ask", 100.25 + index),
        ("last", 100.125 + index),
        ("bid_size", 10 + index),
        ("ask_size", 12 + index),
        ("quote_time", NOW),
        ("trade_time", NOW),
        ("volume", 25_000 + index),
        ("open", 99.5 + index),
        ("high", 101.0 + index),
        ("low", 98.75 + index),
        ("prior_close", 99.25 + index),
        ("tradable", True),
        ("active", True),
        ("security_status", "Normal"),
    )


def _quote_record(
    contract: str,
    *,
    fields: tuple[tuple[str, object], ...] | None = None,
    fresh: bool = True,
) -> StreamCacheRecord:
    return StreamCacheRecord(
        provider="schwab",
        service="LEVELONE_FUTURES",
        symbol=RUNTIME_SYMBOL_BY_CONTRACT[contract],
        contract=contract,
        message_type="quote",
        fields=fields or _complete_levelone_fields(),
        updated_at=NOW,
        age_seconds=0.0 if fresh else 30.0,
        fresh=fresh,
        blocking_reasons=(),
    )


def _bar_record(contract: str, *, fresh: bool = False) -> StreamCacheRecord:
    return StreamCacheRecord(
        provider="schwab",
        service="CHART_FUTURES",
        symbol=RUNTIME_SYMBOL_BY_CONTRACT[contract],
        contract=contract,
        message_type="bar",
        fields=(
            ("start_time", NOW),
            ("end_time", NOW),
            ("open", 100.0),
            ("high", 101.0),
            ("low", 99.0),
            ("close", 100.5),
        ),
        updated_at=NOW,
        age_seconds=0.0 if fresh else 60.0,
        fresh=fresh,
        blocking_reasons=(),
    )


def _service_status(
    *,
    contracts: tuple[str, ...],
    levelone_active: bool = True,
    chart_active: bool = True,
) -> dict:
    return {
        contract: {
            "LEVELONE_FUTURES": {
                "last_seen": NOW if levelone_active else None,
                "age_seconds": 0.0 if levelone_active else None,
                "status": "active" if levelone_active else "no_data",
            },
            "CHART_FUTURES": {
                "last_seen": NOW if chart_active else None,
                "age_seconds": 0.0 if chart_active else None,
                "status": "active" if chart_active else "no_data",
            },
        }
        for contract in contracts
    }


def _heartbeats(contracts: tuple[str, ...], *, active: bool = True) -> dict:
    return {
        contract: {
            "last_seen": NOW if active else None,
            "age_seconds": 0.0 if active else None,
            "status": "active" if active else "no_data",
        }
        for contract in contracts
    }


def _stream_manager_snapshot(
    *,
    state: str = "active",
    cache_records: tuple[StreamCacheRecord, ...] | None = None,
    cache_blocking_reasons: tuple[str, ...] = (),
    cache_provider_status: str = "active",
    cache_stale_symbols: tuple[str, ...] = (),
    blocking_reasons: tuple[str, ...] = (),
    levelone_active: bool = True,
    chart_active: bool = True,
) -> StreamManagerSnapshot:
    contracts = final_target_contracts()
    if cache_records is None:
        cache_records = tuple(_quote_record(c) for c in contracts) + tuple(
            _bar_record(c, fresh=chart_active) for c in contracts
        )
    cache = StreamCacheSnapshot(
        generated_at=NOW,
        provider="schwab",
        provider_status=cache_provider_status,  # type: ignore[arg-type]
        cache_max_age_seconds=15.0,
        records=cache_records,
        blocking_reasons=cache_blocking_reasons,
        stale_symbols=cache_stale_symbols,
    )
    return StreamManagerSnapshot(
        state=state,  # type: ignore[arg-type]
        config=SchwabStreamManagerConfig(
            provider="schwab",
            services_requested=("LEVELONE_FUTURES", "CHART_FUTURES"),
            symbols_requested=tuple(RUNTIME_SYMBOL_BY_CONTRACT[c] for c in contracts),
            fields_requested=(0, 1, 2, 3, 4, 5),
            explicit_live_opt_in=True,
            contracts_requested=contracts,
        ),
        cache=cache,
        events=(),
        blocking_reasons=blocking_reasons,
        login_count=1,
        subscription_count=1,
        last_heartbeat_at=NOW,
        heartbeat_age_seconds=0.0,
        contract_heartbeat_status=_heartbeats(contracts),
        contract_service_status=_service_status(
            contracts=contracts,
            levelone_active=levelone_active,
            chart_active=chart_active,
        ),
    )


class LevelOneFreshnessIndependenceTests(unittest.TestCase):
    def test_fresh_levelone_keeps_provider_active_when_chart_is_stale(self) -> None:
        snapshot = _stream_manager_snapshot(
            state="stale",  # manager flipped due to chart watchdog
            cache_provider_status="stale",
            cache_blocking_reasons=(
                "contract_service_stale:ES:CHART_FUTURES",
                "contract_service_stale:NQ:CHART_FUTURES",
            ),
            blocking_reasons=(
                "contract_service_stale:ES:CHART_FUTURES",
                "contract_service_stale:NQ:CHART_FUTURES",
            ),
            chart_active=False,
        )

        surface = build_five_contract_readiness_summary_surface(
            runtime_snapshot=snapshot,
        )

        # Provider/quote path stays active despite chart-only watchdog noise.
        self.assertEqual(surface["runtime_cache_provider_status"], "connected")
        self.assertTrue(surface["runtime_quote_path_active"])
        self.assertEqual(
            tuple(surface["runtime_levelone_active_contracts"]),
            final_target_contracts(),
        )
        self.assertEqual(tuple(surface["runtime_chart_active_contracts"]), ())
        # Lifecycle status is no longer LIVE_RUNTIME_STALE — quote path is
        # fresh; chart-only watchdog noise does not flip identity.
        self.assertEqual(surface["live_runtime_readiness_status"], LIVE_RUNTIME_CONNECTED)
        # Per-row quote freshness reflects fresh LEVELONE.
        for row in surface["rows"]:
            with self.subTest(contract=row["contract"]):
                self.assertEqual(row["quote_status"], "quote available")
                self.assertEqual(row["live_runtime_readiness_state"], LIVE_RUNTIME_CONNECTED)
        # Chart-only blockers no longer leak into provider-level blockers.
        global_blockers = surface["live_runtime_readiness_blockers"]
        for blocker in global_blockers:
            self.assertNotIn(":CHART_FUTURES", blocker)

    def test_chart_only_stale_is_per_row_chart_blocker(self) -> None:
        snapshot = _stream_manager_snapshot(
            state="stale",
            cache_provider_status="stale",
            blocking_reasons=("contract_service_stale:CL:CHART_FUTURES",),
            chart_active=False,
        )
        surface = build_five_contract_readiness_summary_surface(
            runtime_snapshot=snapshot,
        )
        rows = {row["contract"]: row for row in surface["rows"]}
        cl_row = rows["CL"]
        # Chart status reflects stale; quote stays available.
        self.assertIn(cl_row["chart_status"], {"chart stale", "chart missing"})
        self.assertEqual(cl_row["quote_status"], "quote available")
        # query_ready stays False — chart blocking holds.
        self.assertFalse(cl_row["query_ready"])

    def test_no_levelone_updates_remains_blocked_with_concrete_reason(self) -> None:
        # Manager active but no LEVELONE service heartbeat — quote path is not
        # active, classification stays STALE/missing-update, with concrete reason.
        contracts = final_target_contracts()
        cache = StreamCacheSnapshot(
            generated_at=NOW,
            provider="schwab",
            provider_status="active",
            cache_max_age_seconds=15.0,
            records=tuple(_bar_record(c, fresh=True) for c in contracts),
            blocking_reasons=(
                "contract_service_no_data:ES:LEVELONE_FUTURES",
                "contract_service_no_data:NQ:LEVELONE_FUTURES",
            ),
            stale_symbols=(),
        )
        snapshot = StreamManagerSnapshot(
            state="active",
            config=SchwabStreamManagerConfig(
                provider="schwab",
                services_requested=("LEVELONE_FUTURES", "CHART_FUTURES"),
                symbols_requested=tuple(RUNTIME_SYMBOL_BY_CONTRACT[c] for c in contracts),
                fields_requested=(0, 1, 2, 3, 4, 5),
                explicit_live_opt_in=True,
                contracts_requested=contracts,
            ),
            cache=cache,
            events=(),
            blocking_reasons=(
                "contract_service_no_data:ES:LEVELONE_FUTURES",
                "contract_service_no_data:NQ:LEVELONE_FUTURES",
            ),
            login_count=1,
            subscription_count=1,
            contract_heartbeat_status=_heartbeats(contracts, active=True),
            contract_service_status=_service_status(
                contracts=contracts,
                levelone_active=False,
                chart_active=True,
            ),
        )
        surface = build_five_contract_readiness_summary_surface(
            runtime_snapshot=snapshot,
        )
        # Quote-path-active is False — no LEVELONE updates yet.
        self.assertFalse(surface["runtime_quote_path_active"])
        self.assertEqual(tuple(surface["runtime_levelone_active_contracts"]), ())
        # The LEVELONE-side blocker reason is preserved as a concrete reason.
        joined = "|".join(surface["live_runtime_readiness_blockers"])
        self.assertIn("LEVELONE_FUTURES", joined)

    def test_partial_quote_blocks_only_affected_contract(self) -> None:
        contracts = final_target_contracts()
        partial = _quote_record("CL", fields=(("quote_time", NOW),))
        records = tuple(
            partial if c == "CL" else _quote_record(c) for c in contracts
        ) + tuple(_bar_record(c, fresh=True) for c in contracts)
        snapshot = _stream_manager_snapshot(
            cache_records=records,
        )
        surface = build_five_contract_readiness_summary_surface(
            runtime_snapshot=snapshot,
        )
        rows = {row["contract"]: row for row in surface["rows"]}
        # CL: quote missing required fields.
        self.assertIn("bid", rows["CL"]["missing_live_fields"])
        self.assertFalse(rows["CL"]["query_ready"])
        # ES: still healthy on quote.
        self.assertEqual(rows["ES"]["quote_status"], "quote available")


class CacheNotAdvancingTests(unittest.TestCase):
    def test_cache_not_advancing_surfaces_concrete_blocker(self) -> None:
        # No records yet, manager state="active" but cache empty → unavailable.
        contracts = final_target_contracts()
        cache = StreamCacheSnapshot(
            generated_at=NOW,
            provider="schwab",
            provider_status="active",
            cache_max_age_seconds=15.0,
            records=(),
            blocking_reasons=(),
            stale_symbols=(),
        )
        snapshot = StreamManagerSnapshot(
            state="active",
            config=SchwabStreamManagerConfig(
                provider="schwab",
                services_requested=("LEVELONE_FUTURES", "CHART_FUTURES"),
                symbols_requested=tuple(RUNTIME_SYMBOL_BY_CONTRACT[c] for c in contracts),
                fields_requested=(0, 1, 2, 3, 4, 5),
                explicit_live_opt_in=True,
                contracts_requested=contracts,
            ),
            cache=cache,
            events=(),
            blocking_reasons=(),
            login_count=1,
            subscription_count=1,
            contract_heartbeat_status=_heartbeats(contracts, active=False),
            contract_service_status=_service_status(
                contracts=contracts,
                levelone_active=False,
                chart_active=False,
            ),
        )
        result = resolve_operator_runtime_snapshot(
            mode=OPERATOR_LIVE_RUNTIME,
            producer=StaticRuntimeSnapshotProducer(snapshot),
        )
        # No records → LIVE_RUNTIME_UNAVAILABLE with concrete reason.
        self.assertEqual(result.status, "LIVE_RUNTIME_UNAVAILABLE")
        self.assertIn(
            "operator_live_runtime_snapshot_unavailable",
            result.blocking_reasons,
        )


class CockpitConsumesActiveQuotePathTests(unittest.TestCase):
    def test_active_quote_path_keeps_operator_runtime_status_live(self) -> None:
        snapshot = _stream_manager_snapshot(
            state="stale",
            cache_provider_status="stale",
            blocking_reasons=("contract_service_stale:ES:CHART_FUTURES",),
            chart_active=False,
        )
        operator_runtime = resolve_operator_runtime_snapshot(
            mode=OPERATOR_LIVE_RUNTIME,
            producer=StaticRuntimeSnapshotProducer(snapshot),
        )
        readiness = build_five_contract_readiness_summary_surface(
            runtime_snapshot=operator_runtime.snapshot,
        )
        cockpit = build_live_observation_cockpit_surface(
            readiness_summary=readiness,
            operator_live_runtime=operator_runtime.to_dict(),
        )
        # OperatorRuntimeStatus stays OPERATOR_LIVE_RUNTIME, not LIVE_RUNTIME_STALE.
        self.assertEqual(operator_runtime.status, OPERATOR_LIVE_RUNTIME)
        # The chart-only condition is surfaced as a concrete sanitized lifecycle hint.
        self.assertIn(
            "operator_live_runtime_chart_no_updates",
            operator_runtime.blocking_reasons,
        )
        # The five-contract readiness summary does not classify provider as stale.
        self.assertNotEqual(
            readiness["live_runtime_readiness_status"], LIVE_RUNTIME_STALE
        )
        # Display does not invent QUERY_READY — chart is still missing per row.
        for row in cockpit["rows"]:
            with self.subTest(contract=row["contract"]):
                self.assertFalse(row["query_enabled"])
                self.assertEqual(row["query_action_state"], "DISABLED")


class EvidenceRedactionPreservesLifecycleCodesTests(unittest.TestCase):
    def test_lifecycle_codes_no_longer_redacted_as_token_like(self) -> None:
        for code in (
            "operator_live_runtime_stale",
            "operator_live_runtime_stale.",
            "operator_live_runtime_chart_no_updates",
            "live_cockpit_runtime_start_failed:OperatorLiveRuntimeStartError",
            "operator_live_runtime_producer_error:RuntimeError",
            "contract_service_stale:ES:CHART_FUTURES",
            "Runtime snapshot refresh observed a stale live runtime cache: operator_live_runtime_stale.",
        ):
            with self.subTest(code=code):
                redacted = redact_sensitive_text(code)
                self.assertNotIn("[REDACTED_TOKEN_LIKE]", redacted)
                self.assertIn("operator_live_runtime", redacted) if "operator_live_runtime" in code else None

    def test_real_token_like_material_is_still_redacted(self) -> None:
        for sample in (
            "Authorization: Bearer abcdef1234567890ABCDEF1234567890XYZ",
            "access_token=abcdef1234567890ABCDEF1234567890XYZ",
            "app_key=abcdef1234567890ABCDEF1234567890XYZ",
            "01234567890123456789012345",  # 26-digit token-like
            "https://api.schwabapi.com/something/very/long",
        ):
            with self.subTest(sample=sample):
                redacted = redact_sensitive_text(sample)
                self.assertIn("REDACTED", redacted)


class DisplayDoesNotInventQueryReadyTests(unittest.TestCase):
    def test_query_ready_remains_false_with_active_quote_path_and_stale_chart(self) -> None:
        snapshot = _stream_manager_snapshot(
            state="stale",
            cache_provider_status="stale",
            chart_active=False,
        )
        readiness = build_five_contract_readiness_summary(
            runtime_snapshot=snapshot,
        ).to_dict()
        for row in readiness["rows"]:
            with self.subTest(contract=row["contract"]):
                self.assertFalse(row["query_ready"])
                self.assertTrue(row["query_not_ready_reasons"])


if __name__ == "__main__":
    unittest.main()
