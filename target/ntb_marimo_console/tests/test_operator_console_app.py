from __future__ import annotations

import pytest


def test_operator_console_app_root_import_smoke() -> None:
    import ntb_marimo_console.operator_console_app as app_mod

    assert getattr(app_mod, "app", None) is not None


def test_partial_thesis_reference_form_payload_returns_validation_without_raise() -> None:
    import ntb_marimo_console.operator_console_app as app_mod
    from ntb_marimo_console.active_trade import ThesisReference

    thesis, error = app_mod.optional_thesis_reference_from_form(
        {
            "pipeline_result_id": "pipeline-result-fixture-001",
            "trigger_name": "",
            "trigger_state": "",
        },
        ThesisReference,
    )

    assert thesis is None
    assert error == "Thesis reference requires result id, trigger name, and trigger state."


def test_complete_thesis_reference_form_payload_builds_reference() -> None:
    import ntb_marimo_console.operator_console_app as app_mod
    from ntb_marimo_console.active_trade import ThesisReference

    thesis, error = app_mod.optional_thesis_reference_from_form(
        {
            "pipeline_result_id": "pipeline-result-fixture-001",
            "trigger_name": "fixture-trigger",
            "trigger_state": "QUERY_READY",
        },
        ThesisReference,
    )

    assert error is None
    assert thesis is not None
    assert thesis.pipeline_result_id == "pipeline-result-fixture-001"


def test_cached_runtime_producer_is_reused_without_restarting_live_runtime() -> None:
    import ntb_marimo_console.operator_console_app as app_mod

    sentinel_producer = object()
    live_starts: list[object] = []
    non_live_builds: list[object] = []

    resolved = app_mod.resolve_cockpit_runtime_snapshot_producer(
        sentinel_producer,
        operator_runtime_mode="OPERATOR_LIVE_RUNTIME",
        live_runtime_starter=lambda: live_starts.append(object()),
        non_live_producer_builder=lambda: non_live_builds.append(object()),
    )

    # Refresh/render path: the cached producer is reused, the live runtime is
    # NOT started again, and there is no repeated Schwab login.
    assert resolved is sentinel_producer
    assert live_starts == []
    assert non_live_builds == []


def test_first_live_resolution_starts_live_runtime_once() -> None:
    import ntb_marimo_console.operator_console_app as app_mod

    class _Bootstrap:
        def __init__(self, producer: object) -> None:
            self.producer = producer

    live_producer = object()
    starts: list[object] = []

    def _starter():
        starts.append(object())
        return _Bootstrap(live_producer)

    resolved = app_mod.resolve_cockpit_runtime_snapshot_producer(
        None,
        operator_runtime_mode="OPERATOR_LIVE_RUNTIME",
        live_runtime_starter=_starter,
        non_live_producer_builder=lambda: pytest.fail("non-live builder must not run"),
    )

    assert resolved is live_producer
    assert len(starts) == 1


def test_first_non_live_resolution_uses_non_live_builder_only() -> None:
    import ntb_marimo_console.operator_console_app as app_mod

    non_live_producer = object()

    resolved = app_mod.resolve_cockpit_runtime_snapshot_producer(
        None,
        operator_runtime_mode="SAFE_NON_LIVE",
        live_runtime_starter=lambda: pytest.fail("live runtime must not start in non-live mode"),
        non_live_producer_builder=lambda: non_live_producer,
    )

    assert resolved is non_live_producer


def test_live_runtime_start_failure_returns_fail_closed_producer_not_fixture() -> None:
    import ntb_marimo_console.operator_console_app as app_mod
    from ntb_marimo_console.operator_live_runtime import UnavailableRuntimeSnapshotProducer

    class _FailClosedBootstrap:
        producer = UnavailableRuntimeSnapshotProducer(
            reason="live_cockpit_runtime_start_failed:subscribe_denied"
        )

    resolved = app_mod.resolve_cockpit_runtime_snapshot_producer(
        None,
        operator_runtime_mode="OPERATOR_LIVE_RUNTIME",
        live_runtime_starter=lambda: _FailClosedBootstrap(),
        non_live_producer_builder=lambda: pytest.fail("must not fall back to fixture producer"),
    )

    assert isinstance(resolved, UnavailableRuntimeSnapshotProducer)
