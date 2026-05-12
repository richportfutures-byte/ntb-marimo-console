from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from ntb_marimo_console.active_trade import (
    ACTIVE_TRADE_PAYLOAD_TYPE,
    ACTIVE_TRADE_SCHEMA_VERSION,
    ActiveTradeRegistry,
    ThesisReference,
)


@dataclass
class FakeClock:
    current: datetime = datetime(2026, 5, 12, 14, 30, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current = self.current + timedelta(seconds=seconds)


def thesis_reference() -> ThesisReference:
    return ThesisReference(
        pipeline_result_id="pipeline-result-es-20260512-001",
        trigger_name="ES opening-drive continuation",
        trigger_state="TRIGGERED",
        query_session_id="query-session-fixture-001",
    )


def test_registry_adds_manual_active_trade_with_thesis_reference() -> None:
    registry = ActiveTradeRegistry(clock=FakeClock())

    trade = registry.add(
        trade_id="trade-es-fixture-001",
        contract=" es ",
        direction="long",
        entry_price=5325.25,
        thesis_reference=thesis_reference(),
        stop_loss=5317.25,
        target=5344.25,
        operator_notes="Manual entry after preserved-engine approval.",
    )

    assert trade.contract == "ES"
    assert trade.status == "open"
    assert trade.entry_time_utc == "2026-05-12T14:30:00+00:00"
    assert trade.thesis_reference.pipeline_result_id == "pipeline-result-es-20260512-001"
    assert registry.list() == (trade,)
    assert registry.list(status="open", contract="ES") == (trade,)


def test_current_pnl_state_is_read_only_live_price_calculation() -> None:
    registry = ActiveTradeRegistry(clock=FakeClock())
    long_trade = registry.add(
        trade_id="trade-es-long",
        contract="ES",
        direction="long",
        entry_price=5325.25,
        thesis_reference=thesis_reference(),
    )
    short_trade = registry.add(
        trade_id="trade-nq-short",
        contract="NQ",
        direction="short",
        entry_price=18650.0,
        thesis_reference=thesis_reference(),
    )

    long_pnl = long_trade.pnl_state(5330.75)
    short_pnl = short_trade.pnl_state(18642.5)

    assert long_pnl.to_dict() == {
        "trade_id": "trade-es-long",
        "contract": "ES",
        "status": "open",
        "direction": "long",
        "entry_price": 5325.25,
        "live_price": 5330.75,
        "price_delta": 5.5,
        "direction_adjusted_points": 5.5,
    }
    assert short_pnl.price_delta == -7.5
    assert short_pnl.direction_adjusted_points == 7.5
    assert registry.get("trade-es-long").status == "open"


def test_registry_updates_annotations_and_closes_without_execution_fields() -> None:
    clock = FakeClock()
    registry = ActiveTradeRegistry(clock=clock)
    trade = registry.add(
        trade_id="trade-cl-fixture-001",
        contract="CL",
        direction="short",
        entry_price=78.42,
        thesis_reference=thesis_reference(),
        stop_loss=79.05,
        target=77.2,
    )

    updated = registry.update(
        trade.trade_id,
        stop_loss=78.9,
        target=77.05,
        operator_notes="Scaled thesis confidence down after inventory headline.",
    )
    clock.advance(900)
    closed = registry.close(updated.trade_id, status="stopped", close_reason="manual_stop_recorded")

    assert updated.stop_loss == 78.9
    assert updated.target == 77.05
    assert updated.operator_notes == "Scaled thesis confidence down after inventory headline."
    assert closed.status == "stopped"
    assert closed.closed_at_utc == "2026-05-12T14:45:00+00:00"
    assert closed.close_reason == "manual_stop_recorded"
    payload = closed.to_dict()
    assert "broker" not in payload
    assert "order" not in payload
    assert "account" not in payload
    assert "fill" not in payload


def test_json_round_trip_preserves_active_trade_registry() -> None:
    clock = FakeClock()
    registry = ActiveTradeRegistry(clock=clock)
    registry.add(
        trade_id="trade-6e-fixture-001",
        contract="6e",
        direction="long",
        entry_price=1.0855,
        thesis_reference=thesis_reference(),
        stop_loss=1.0825,
        target=1.091,
        operator_notes="Fixture-only persistence check.",
    )

    restored = ActiveTradeRegistry.from_json(registry.to_json(), clock=clock)
    payload = restored.to_payload()

    assert payload["payload_type"] == ACTIVE_TRADE_PAYLOAD_TYPE
    assert payload["schema_version"] == ACTIVE_TRADE_SCHEMA_VERSION
    assert payload["saved_at_utc"] == "2026-05-12T14:30:00+00:00"
    assert payload["trades"] == registry.to_payload()["trades"]


def test_registry_rejects_excluded_and_unknown_contracts() -> None:
    registry = ActiveTradeRegistry(clock=FakeClock())

    for contract in ("ZN", "GC", "YM"):
        with pytest.raises(ValueError, match="not in the final target universe"):
            registry.add(
                trade_id=f"trade-{contract.lower()}",
                contract=contract,
                direction="long",
                entry_price=100.0,
                thesis_reference=thesis_reference(),
            )


def test_deserialize_rejects_malformed_payloads() -> None:
    registry = ActiveTradeRegistry(clock=FakeClock())
    trade = registry.add(
        trade_id="trade-mgc-fixture-001",
        contract="MGC",
        direction="long",
        entry_price=2385.4,
        thesis_reference=thesis_reference(),
    )
    payload = registry.to_payload()

    extra_root_key = dict(payload)
    extra_root_key["unexpected"] = True
    with pytest.raises(ValueError, match="payload keys are invalid"):
        ActiveTradeRegistry.from_payload(extra_root_key)

    encoded = json.loads(registry.to_json())
    encoded["trades"][0]["contract"] = "GC"
    with pytest.raises(ValueError, match="not in the final target universe"):
        ActiveTradeRegistry.from_payload(encoded)

    duplicate = dict(payload)
    duplicate["trades"] = [trade.to_dict(), trade.to_dict()]
    with pytest.raises(ValueError, match="Duplicate active trade id"):
        ActiveTradeRegistry.from_payload(duplicate)
