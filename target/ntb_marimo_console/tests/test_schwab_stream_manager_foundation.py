from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ntb_marimo_console.contract_universe import (
    excluded_final_target_contracts,
    final_target_contracts,
    is_final_target_contract,
    is_never_supported_contract,
)
from ntb_marimo_console.market_data.stream_events import STREAM_EVENT_TYPES
from ntb_marimo_console.market_data.stream_lifecycle import STREAM_LIFECYCLE_STATES
from ntb_marimo_console.market_data.stream_manager import (
    MIN_STREAM_REFRESH_FLOOR_SECONDS,
    SchwabStreamManager,
    SchwabStreamManagerConfig,
    StreamClientResult,
    StreamSubscriptionRequest,
)


@dataclass
class FakeClock:
    current: datetime = datetime(2026, 5, 6, 13, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current = self.current + timedelta(seconds=seconds)


class FakeStreamClient:
    def __init__(
        self,
        *,
        login_result: StreamClientResult | None = None,
        subscription_result: StreamClientResult | None = None,
    ) -> None:
        self.login_result = login_result or StreamClientResult(succeeded=True)
        self.subscription_result = subscription_result or StreamClientResult(succeeded=True)
        self.login_calls = 0
        self.subscription_calls = 0
        self.close_calls = 0
        self.subscription_requests: list[StreamSubscriptionRequest] = []

    def login(self, config: SchwabStreamManagerConfig) -> StreamClientResult:
        self.login_calls += 1
        return self.login_result

    def subscribe(self, request: StreamSubscriptionRequest) -> StreamClientResult:
        self.subscription_calls += 1
        self.subscription_requests.append(request)
        return self.subscription_result

    def close(self) -> StreamClientResult:
        self.close_calls += 1
        return StreamClientResult(succeeded=True)


def live_config(**overrides: object) -> SchwabStreamManagerConfig:
    values = {
        "provider": "schwab",
        "services_requested": ("LEVELONE_FUTURES",),
        "symbols_requested": ("ES_TEST",),
        "fields_requested": (0, 1, 2, 3, 4, 5),
        "contracts_requested": ("ES",),
        "explicit_live_opt_in": True,
    }
    values.update(overrides)
    return SchwabStreamManagerConfig(**values)  # type: ignore[arg-type]


def quote_message(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "service": "LEVELONE_FUTURES",
        "symbol": "ES_TEST",
        "contract": "ES",
        "message_type": "quote",
        "fields": {"bid": 7175, "ask": 7175.5, "last": 7175.25},
        "received_at": "2026-05-06T13:00:00+00:00",
    }
    values.update(overrides)
    return values


def chart_message(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "service": "CHART_FUTURES",
        "symbol": "ES_TEST",
        "contract": "ES",
        "message_type": "bar",
        "fields": {
            "start_time": "2026-05-06T12:59:00+00:00",
            "end_time": "2026-05-06T13:00:00+00:00",
            "open": 7170,
            "high": 7176,
            "low": 7168,
            "close": 7175,
            "completed": True,
        },
        "received_at": "2026-05-06T13:00:00+00:00",
    }
    values.update(overrides)
    return values


def sensitive_reason() -> str:
    endpoint = "".join(("wss", "://", "stream-redaction.invalid", "/ws?", "credential=hidden"))
    return (
        "access_token=ACCESS_VALUE_PRIVATE refresh_token=REFRESH_VALUE_PRIVATE "
        "Authorization: Bearer BEARER_VALUE_PRIVATE_12345678901234567890 "
        "customerId=CUSTOMER_VALUE_PRIVATE correlId=CORREL_VALUE_PRIVATE "
        f"accountNumber=ACCOUNT_VALUE_PRIVATE {endpoint} "
        '{"customerId":"CUSTOMER_JSON_PRIVATE","correlId":"CORREL_JSON_PRIVATE"}'
    )


def public_text(snapshot: object) -> str:
    return repr(snapshot) + json.dumps(snapshot.to_dict(), sort_keys=True)  # type: ignore[attr-defined]


def test_default_config_is_non_live_and_disabled() -> None:
    manager = SchwabStreamManager(clock=FakeClock())

    snapshot = manager.snapshot()

    assert snapshot.state == "disabled"
    assert snapshot.config.provider == "disabled"
    assert snapshot.config.explicit_live_opt_in is False
    assert snapshot.config.startup_mode == "default_non_live"
    assert snapshot.config.refresh_floor_seconds == MIN_STREAM_REFRESH_FLOOR_SECONDS
    assert snapshot.cache.provider_status == "disabled"
    assert snapshot.login_count == 0


def test_explicit_live_opt_in_required_before_start_attempts_login() -> None:
    client = FakeStreamClient()
    manager = SchwabStreamManager(
        SchwabStreamManagerConfig(
            provider="schwab",
            services_requested=("LEVELONE_FUTURES",),
            symbols_requested=("ES_TEST",),
            fields_requested=(0, 1, 2),
            contracts_requested=("ES",),
            explicit_live_opt_in=False,
        ),
        client=client,
        clock=FakeClock(),
    )

    snapshot = manager.start()

    assert snapshot.state == "blocked"
    assert "explicit_live_opt_in_required" in snapshot.blocking_reasons
    assert client.login_calls == 0
    assert snapshot.login_count == 0


def test_fixture_client_success_transitions_to_active_connected_state() -> None:
    client = FakeStreamClient()
    manager = SchwabStreamManager(live_config(), client=client, clock=FakeClock())

    snapshot = manager.start()

    assert snapshot.state == "active"
    assert snapshot.cache.provider_status == "active"
    assert snapshot.ready is False
    assert client.login_calls == 1
    assert client.subscription_calls == 1
    assert snapshot.events[1].event_type == "login_succeeded"
    assert snapshot.events[1].state == "connected"
    assert client.subscription_requests[0].symbols == ("ES_TEST",)


def test_snapshot_exposes_subscription_request_and_result_state() -> None:
    client = FakeStreamClient()
    manager = SchwabStreamManager(live_config(), client=client, clock=FakeClock())

    snapshot = manager.start()
    payload = snapshot.to_dict()

    assert snapshot.last_subscription_request is client.subscription_requests[0]
    assert snapshot.last_subscription_request.symbols == ("ES_TEST",)
    assert snapshot.last_subscription_request.contracts == ("ES",)
    assert snapshot.last_subscription_result == StreamClientResult(succeeded=True)
    assert payload["last_subscription_request"] == {
        "provider": "schwab",
        "services": ["LEVELONE_FUTURES"],
        "symbols": ["ES_TEST"],
        "fields": [0, 1, 2, 3, 4, 5],
        "contracts": ["ES"],
    }
    assert payload["last_subscription_result"] == {"succeeded": True, "reason": None}


def test_subscription_exception_result_is_redacted_on_snapshot() -> None:
    class RaisingSubscribeClient(FakeStreamClient):
        def subscribe(self, request: StreamSubscriptionRequest) -> StreamClientResult:
            self.subscription_calls += 1
            self.subscription_requests.append(request)
            raise RuntimeError(sensitive_reason())

    manager = SchwabStreamManager(live_config(), client=RaisingSubscribeClient(), clock=FakeClock())

    snapshot = manager.start()
    rendered = public_text(snapshot)

    assert snapshot.state == "blocked"
    assert snapshot.last_subscription_result is not None
    assert snapshot.last_subscription_result.succeeded is False
    assert "subscription_exception" in (snapshot.last_subscription_result.reason or "")
    assert "ACCESS_VALUE_PRIVATE" not in rendered
    assert "CUSTOMER_VALUE_PRIVATE" not in rendered
    assert "stream-redaction" not in rendered


def test_login_denied_blocks_with_redacted_reason() -> None:
    client = FakeStreamClient(login_result=StreamClientResult(succeeded=False, reason=sensitive_reason()))
    manager = SchwabStreamManager(live_config(), client=client, clock=FakeClock())

    snapshot = manager.start()
    rendered = public_text(snapshot)

    assert snapshot.state == "blocked"
    assert client.subscription_calls == 0
    assert "ACCESS_VALUE_PRIVATE" not in rendered
    assert "REFRESH_VALUE_PRIVATE" not in rendered
    assert "BEARER_VALUE_PRIVATE" not in rendered
    assert "CUSTOMER_VALUE_PRIVATE" not in rendered
    assert "CORREL_VALUE_PRIVATE" not in rendered
    assert "ACCOUNT_VALUE_PRIVATE" not in rendered
    assert "stream-redaction" not in rendered


def test_subscription_failure_blocks_with_redacted_reason() -> None:
    client = FakeStreamClient(subscription_result=StreamClientResult(succeeded=False, reason=sensitive_reason()))
    manager = SchwabStreamManager(live_config(), client=client, clock=FakeClock())

    snapshot = manager.start()
    rendered = public_text(snapshot)

    assert snapshot.state == "blocked"
    assert client.login_calls == 1
    assert client.subscription_calls == 1
    assert "ACCESS_VALUE_PRIVATE" not in rendered
    assert "CUSTOMER_VALUE_PRIVATE" not in rendered
    assert "stream-redaction" not in rendered


def test_heartbeat_timeout_marks_stream_stale_fail_closed() -> None:
    clock = FakeClock()
    manager = SchwabStreamManager(live_config(), client=FakeStreamClient(), clock=clock)
    manager.start()
    heartbeat_snapshot = manager.record_heartbeat()

    assert heartbeat_snapshot.last_heartbeat_at == "2026-05-06T13:00:00+00:00"
    assert heartbeat_snapshot.heartbeat_age_seconds == 0.0

    clock.advance(MIN_STREAM_REFRESH_FLOOR_SECONDS + 1)
    snapshot = manager.check_heartbeat()

    assert snapshot.state == "stale"
    assert snapshot.cache.provider_status == "stale"
    assert "heartbeat_stale" in snapshot.blocking_reasons
    assert snapshot.ready is False
    assert snapshot.events[-1].event_type == "heartbeat_stale"
    assert snapshot.last_heartbeat_at == "2026-05-06T13:00:00+00:00"
    assert snapshot.heartbeat_age_seconds == MIN_STREAM_REFRESH_FLOOR_SECONDS + 1


def test_contract_receiving_data_has_active_heartbeat_status() -> None:
    manager = SchwabStreamManager(live_config(), client=FakeStreamClient(), clock=FakeClock())
    manager.start()

    snapshot = manager.ingest_message(quote_message())
    snapshot = manager.check_contract_heartbeats()

    assert snapshot.contract_heartbeat_status is not None
    assert snapshot.contract_heartbeat_status["ES"] == {
        "last_seen": "2026-05-06T13:00:00+00:00",
        "age_seconds": 0.0,
        "status": "active",
    }
    assert snapshot.stale_contracts == ()
    assert snapshot.blocking_reasons == ()


def test_contract_not_receiving_data_within_threshold_is_marked_stale() -> None:
    clock = FakeClock()
    manager = SchwabStreamManager(live_config(), client=FakeStreamClient(), clock=clock)
    manager.start()
    manager.ingest_message(quote_message())

    clock.advance((2 * MIN_STREAM_REFRESH_FLOOR_SECONDS) + 1)
    snapshot = manager.check_contract_heartbeats()

    assert snapshot.state == "stale"
    assert snapshot.stale_contracts == ("ES",)
    assert snapshot.contract_heartbeat_status is not None
    assert snapshot.contract_heartbeat_status["ES"]["status"] == "stale"
    assert snapshot.contract_heartbeat_status["ES"]["age_seconds"] == (
        2 * MIN_STREAM_REFRESH_FLOOR_SECONDS
    ) + 1
    assert "contract_stale:ES" in snapshot.blocking_reasons


def test_contract_that_never_received_data_is_marked_no_data_after_threshold() -> None:
    clock = FakeClock()
    manager = SchwabStreamManager(live_config(), client=FakeStreamClient(), clock=clock)
    manager.start()

    clock.advance((2 * MIN_STREAM_REFRESH_FLOOR_SECONDS) + 1)
    snapshot = manager.check_contract_heartbeats()

    assert snapshot.state == "stale"
    assert snapshot.stale_contracts == ()
    assert snapshot.contract_heartbeat_status is not None
    assert snapshot.contract_heartbeat_status["ES"] == {
        "last_seen": None,
        "age_seconds": None,
        "status": "no_data",
    }
    assert "contract_no_data:ES" in snapshot.blocking_reasons


def test_multiple_contract_heartbeat_statuses_can_be_active_stale_and_no_data() -> None:
    clock = FakeClock()
    manager = SchwabStreamManager(
        live_config(
            contracts_requested=("ES", "NQ", "CL"),
            symbols_requested=("ES_TEST", "NQ_TEST", "CL_TEST"),
        ),
        client=FakeStreamClient(),
        clock=clock,
    )
    manager.start()
    manager.ingest_message(quote_message(contract="ES", symbol="ES_TEST"))
    clock.advance(20)
    manager.ingest_message(quote_message(contract="NQ", symbol="NQ_TEST"))
    clock.advance(15)

    snapshot = manager.check_contract_heartbeats()

    assert snapshot.contract_heartbeat_status is not None
    assert snapshot.contract_heartbeat_status["ES"]["status"] == "stale"
    assert snapshot.contract_heartbeat_status["NQ"]["status"] == "active"
    assert snapshot.contract_heartbeat_status["CL"]["status"] == "no_data"
    assert snapshot.stale_contracts == ("ES",)
    assert "contract_stale:ES" in snapshot.blocking_reasons
    assert "contract_no_data:CL" in snapshot.blocking_reasons


def test_contract_heartbeat_status_appears_in_snapshot_dict() -> None:
    manager = SchwabStreamManager(live_config(), client=FakeStreamClient(), clock=FakeClock())
    manager.start()
    snapshot = manager.ingest_message(quote_message()).to_dict()

    assert snapshot["stale_contracts"] == []
    assert snapshot["contract_heartbeat_status"] == {
        "ES": {
            "last_seen": "2026-05-06T13:00:00+00:00",
            "age_seconds": 0.0,
            "status": "active",
        }
    }


def test_cache_tracks_levelone_and_chart_futures_separately_for_same_contract_symbol() -> None:
    manager = SchwabStreamManager(
        live_config(services_requested=("LEVELONE_FUTURES", "CHART_FUTURES")),
        client=FakeStreamClient(),
        clock=FakeClock(),
    )
    manager.start()
    manager.ingest_message(quote_message())

    snapshot = manager.ingest_message(chart_message())

    records = {(record.service, record.message_type): record for record in snapshot.cache.records}
    assert tuple(records) == (
        ("CHART_FUTURES", "bar"),
        ("LEVELONE_FUTURES", "quote"),
    )
    assert records[("LEVELONE_FUTURES", "quote")].contract == "ES"
    assert records[("CHART_FUTURES", "bar")].contract == "ES"
    assert snapshot.contract_service_status is not None
    assert snapshot.contract_service_status["ES"]["LEVELONE_FUTURES"]["status"] == "active"
    assert snapshot.contract_service_status["ES"]["CHART_FUTURES"]["status"] == "active"
    assert snapshot.ready is True


def test_unrequested_stream_service_blocks_and_does_not_seed_cache() -> None:
    manager = SchwabStreamManager(live_config(), client=FakeStreamClient(), clock=FakeClock())
    manager.start()

    snapshot = manager.ingest_message(chart_message())

    assert snapshot.state == "blocked"
    assert "service_mismatch:ES:CHART_FUTURES" in snapshot.blocking_reasons
    assert snapshot.cache.records == ()
    assert snapshot.ready is False


def test_contract_service_heartbeat_marks_missing_chart_service_stale_fail_closed() -> None:
    clock = FakeClock()
    manager = SchwabStreamManager(
        live_config(services_requested=("LEVELONE_FUTURES", "CHART_FUTURES")),
        client=FakeStreamClient(),
        clock=clock,
    )
    manager.start()
    snapshot = manager.ingest_message(quote_message())

    assert snapshot.contract_service_status is not None
    assert snapshot.contract_service_status["ES"]["LEVELONE_FUTURES"]["status"] == "active"
    assert snapshot.contract_service_status["ES"]["CHART_FUTURES"]["status"] == "no_data"
    assert snapshot.ready is False
    assert snapshot.cache.ready is True

    clock.advance((2 * MIN_STREAM_REFRESH_FLOOR_SECONDS) + 1)
    stale_snapshot = manager.check_contract_heartbeats()

    assert stale_snapshot.state == "stale"
    assert stale_snapshot.contract_service_status is not None
    assert stale_snapshot.contract_service_status["ES"]["LEVELONE_FUTURES"]["status"] == "stale"
    assert stale_snapshot.contract_service_status["ES"]["CHART_FUTURES"]["status"] == "no_data"
    assert "contract_service_stale:ES:LEVELONE_FUTURES" in stale_snapshot.blocking_reasons
    assert "contract_service_no_data:ES:CHART_FUTURES" in stale_snapshot.blocking_reasons


def test_contract_watchdog_threshold_defaults_to_twice_cache_max_age_seconds() -> None:
    clock = FakeClock()
    manager = SchwabStreamManager(
        live_config(cache_max_age_seconds=20.0),
        client=FakeStreamClient(),
        clock=clock,
    )
    manager.start()
    manager.ingest_message(quote_message())

    clock.advance(40.0)
    threshold_snapshot = manager.check_contract_heartbeats()
    clock.advance(0.1)
    stale_snapshot = manager.check_contract_heartbeats()

    assert threshold_snapshot.config.contract_heartbeat_max_age_seconds == 40.0
    assert "contract_stale:ES" not in threshold_snapshot.blocking_reasons
    assert "contract_stale:ES" in stale_snapshot.blocking_reasons


def test_malformed_data_is_recorded_without_permitting_readiness() -> None:
    manager = SchwabStreamManager(live_config(), client=FakeStreamClient(), clock=FakeClock())
    manager.start()

    snapshot = manager.ingest_message({"service": "LEVELONE_FUTURES"})

    assert snapshot.state == "blocked"
    assert snapshot.ready is False
    assert snapshot.events[-1].event_type == "malformed_message"
    assert any("malformed_message" in reason for reason in snapshot.blocking_reasons)


def test_repeated_marimo_style_cache_reads_do_not_login_again() -> None:
    client = FakeStreamClient()
    manager = SchwabStreamManager(live_config(), client=client, clock=FakeClock())
    manager.start()

    for _ in range(5):
        snapshot = manager.read_cache_snapshot()
        assert snapshot.provider_status == "active"

    assert client.login_calls == 1
    assert client.subscription_calls == 1


def test_repeated_start_while_active_is_idempotent() -> None:
    client = FakeStreamClient()
    manager = SchwabStreamManager(live_config(), client=client, clock=FakeClock())

    first = manager.start()
    second = manager.start()

    assert first.state == "active"
    assert second.state == "active"
    assert client.login_calls == 1
    assert client.subscription_calls == 1
    assert second.login_count == 1


def test_cache_snapshot_is_json_serializable_and_deterministic() -> None:
    manager = SchwabStreamManager(live_config(), client=FakeStreamClient(), clock=FakeClock())
    manager.start()

    snapshot = manager.ingest_message(quote_message())
    payload = snapshot.cache.to_dict()

    encoded = json.dumps(payload, sort_keys=True)
    assert '"provider_status": "active"' in encoded
    assert payload["ready"] is True
    assert payload["records"][0]["fields"] == {"ask": 7175.5, "bid": 7175, "last": 7175.25}


def test_cache_snapshot_redacts_sensitive_field_values() -> None:
    manager = SchwabStreamManager(live_config(), client=FakeStreamClient(), clock=FakeClock())
    manager.start()

    snapshot = manager.ingest_message(
        quote_message(fields={"bid": 7175, "provider_note": sensitive_reason()})
    )
    rendered = public_text(snapshot)

    assert "ACCESS_VALUE_PRIVATE" not in rendered
    assert "CUSTOMER_VALUE_PRIVATE" not in rendered
    assert "stream-redaction" not in rendered


def test_symbol_mismatch_creates_blocking_reason_for_affected_symbol() -> None:
    manager = SchwabStreamManager(live_config(), client=FakeStreamClient(), clock=FakeClock())
    manager.start()

    snapshot = manager.ingest_message(quote_message(symbol="NQ_TEST"))

    assert snapshot.state == "blocked"
    assert any("symbol_mismatch:ES:NQ_TEST" == reason for reason in snapshot.blocking_reasons)
    assert snapshot.cache.blocking_reasons == snapshot.blocking_reasons


def test_excluded_contract_request_blocks_before_login() -> None:
    client = FakeStreamClient()
    manager = SchwabStreamManager(
        live_config(contracts_requested=("ZN",), symbols_requested=("ZN_TEST",)),
        client=client,
        clock=FakeClock(),
    )

    snapshot = manager.start()

    assert snapshot.state == "blocked"
    assert "excluded_contract_requested:ZN" in snapshot.blocking_reasons
    assert client.login_calls == 0


def test_contract_universe_remains_final_target_with_zn_and_gc_excluded() -> None:
    assert final_target_contracts() == ("ES", "NQ", "CL", "6E", "MGC")
    assert excluded_final_target_contracts() == ("ZN", "GC")
    assert not is_final_target_contract("ZN")
    assert not is_final_target_contract("GC")
    assert is_never_supported_contract("GC")
    assert is_final_target_contract("MGC")


def test_stream_manager_declares_required_states_and_event_types() -> None:
    for state in (
        "disabled",
        "initialized",
        "connecting",
        "login_pending",
        "connected",
        "subscribing",
        "active",
        "reconnecting",
        "stale",
        "disconnected",
        "error",
        "blocked",
        "shutdown",
    ):
        assert state in STREAM_LIFECYCLE_STATES

    for event_type in (
        "login_requested",
        "login_succeeded",
        "login_denied",
        "subscription_requested",
        "subscription_succeeded",
        "subscription_failed",
        "reconnect_attempt",
        "reconnect_succeeded",
        "reconnect_exhausted",
        "data_received",
        "heartbeat_seen",
        "heartbeat_stale",
        "malformed_message",
        "connection_lost",
        "shutdown_requested",
        "shutdown_completed",
    ):
        assert event_type in STREAM_EVENT_TYPES
