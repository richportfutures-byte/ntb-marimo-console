from __future__ import annotations

from dataclasses import dataclass

import pytest

from ntb_marimo_console.live_cockpit_runtime import (
    LIVE_COCKPIT_STATUS_CLIENT_FACTORY_ERROR,
    LIVE_COCKPIT_STATUS_CLIENT_FACTORY_UNAVAILABLE,
    LIVE_COCKPIT_STATUS_OPT_IN_REQUIRED,
    LIVE_COCKPIT_STATUS_START_FAILED,
    LIVE_COCKPIT_STATUS_STARTED,
    clear_live_cockpit_client_factory_builder,
    get_live_cockpit_client_factory_builder,
    register_live_cockpit_client_factory_builder,
    start_live_cockpit_runtime,
    stop_live_cockpit_runtime,
)
import ntb_marimo_console.live_cockpit_runtime as live_cockpit_runtime
from ntb_marimo_console.operator_live_launcher import OperatorLiveRuntimeStartError
from ntb_marimo_console.operator_live_runtime import UnavailableRuntimeSnapshotProducer


_LIVE_ENV = {"NTB_OPERATOR_RUNTIME_MODE": "OPERATOR_LIVE_RUNTIME"}
_NON_LIVE_ENV = {"NTB_OPERATOR_RUNTIME_MODE": "SAFE_NON_LIVE"}


@pytest.fixture(autouse=True)
def _clear_builder_registry():
    clear_live_cockpit_client_factory_builder()
    yield
    clear_live_cockpit_client_factory_builder()


class _FakeProducer:
    def __init__(self) -> None:
        self.read_calls = 0

    def read_snapshot(self):
        self.read_calls += 1
        return None


class _FakeManager:
    pass


@dataclass(frozen=True)
class _FakeLaunchResult:
    producer: object
    manager: object
    started_snapshot: object = None


def _builder_returning(factory_obj, config_obj):
    def _builder(values):
        assert isinstance(values, dict)
        return factory_obj, config_obj

    return _builder


def _recording_starter(result):
    calls: list[dict] = []

    def _starter(**kwargs):
        calls.append(kwargs)
        return result

    return _starter, calls


def test_module_import_registers_no_builder() -> None:
    # Import-time inert: nothing is registered just by importing the module.
    assert get_live_cockpit_client_factory_builder() is None


def test_start_requires_explicit_opt_in() -> None:
    bootstrap = start_live_cockpit_runtime(_NON_LIVE_ENV)

    assert bootstrap.started is False
    assert bootstrap.status == LIVE_COCKPIT_STATUS_OPT_IN_REQUIRED
    assert isinstance(bootstrap.producer, UnavailableRuntimeSnapshotProducer)
    assert bootstrap.blocking_reason == "operator_live_runtime_opt_in_required"
    assert bootstrap.manager is None


def test_start_fails_closed_without_client_factory_builder() -> None:
    bootstrap = start_live_cockpit_runtime(_LIVE_ENV)

    assert bootstrap.started is False
    assert bootstrap.status == LIVE_COCKPIT_STATUS_CLIENT_FACTORY_UNAVAILABLE
    assert isinstance(bootstrap.producer, UnavailableRuntimeSnapshotProducer)
    assert bootstrap.blocking_reason == "live_cockpit_client_factory_unavailable"


def test_start_and_register_with_injected_builder_and_starter() -> None:
    fake_producer = _FakeProducer()
    fake_manager = _FakeManager()
    starter, calls = _recording_starter(
        _FakeLaunchResult(producer=fake_producer, manager=fake_manager)
    )
    factory_obj = object()
    config_obj = object()

    bootstrap = start_live_cockpit_runtime(
        _LIVE_ENV,
        client_factory_builder=_builder_returning(factory_obj, config_obj),
        runtime_starter=starter,
    )

    assert bootstrap.started is True
    assert bootstrap.status == LIVE_COCKPIT_STATUS_STARTED
    assert bootstrap.producer is fake_producer
    assert bootstrap.manager is fake_manager
    assert bootstrap.blocking_reason is None
    # Started and registered exactly once, with register=True.
    assert len(calls) == 1
    assert calls[0]["register"] is True
    assert calls[0]["client_factory"] is factory_obj
    assert calls[0]["config"] is config_obj


def test_start_failure_is_fail_closed_and_does_not_fall_back_to_fixture() -> None:
    def _failing_starter(**kwargs):
        raise OperatorLiveRuntimeStartError(
            "operator_live_runtime_start_error:subscribe_denied"
        )

    bootstrap = start_live_cockpit_runtime(
        _LIVE_ENV,
        client_factory_builder=_builder_returning(object(), object()),
        runtime_starter=_failing_starter,
    )

    assert bootstrap.started is False
    assert bootstrap.status == LIVE_COCKPIT_STATUS_START_FAILED
    # Fail-closed: an Unavailable producer, never a fixture/static producer.
    assert isinstance(bootstrap.producer, UnavailableRuntimeSnapshotProducer)
    assert bootstrap.manager is None
    assert bootstrap.blocking_reason is not None
    assert bootstrap.blocking_reason.startswith("live_cockpit_runtime_start_failed:")


def test_client_factory_error_is_fail_closed_and_redacted() -> None:
    def _leaky_builder(values):
        raise ValueError(
            "Authorization: Bearer LEAKEDTOKEN999999 customerId=LEAKCUST123"
        )

    bootstrap = start_live_cockpit_runtime(
        _LIVE_ENV,
        client_factory_builder=_leaky_builder,
        runtime_starter=lambda **kwargs: pytest.fail("starter must not run"),
    )

    assert bootstrap.started is False
    assert bootstrap.status == LIVE_COCKPIT_STATUS_CLIENT_FACTORY_ERROR
    assert isinstance(bootstrap.producer, UnavailableRuntimeSnapshotProducer)
    assert bootstrap.blocking_reason is not None
    assert bootstrap.blocking_reason.startswith("live_cockpit_client_factory_error:")
    assert "LEAKEDTOKEN999999" not in bootstrap.blocking_reason
    assert "LEAKCUST123" not in bootstrap.blocking_reason


def test_registered_builder_is_used_and_clearable() -> None:
    fake_producer = _FakeProducer()
    starter, calls = _recording_starter(
        _FakeLaunchResult(producer=fake_producer, manager=_FakeManager())
    )
    register_live_cockpit_client_factory_builder(
        _builder_returning(object(), object())
    )

    bootstrap = start_live_cockpit_runtime(_LIVE_ENV, runtime_starter=starter)
    assert bootstrap.started is True
    assert bootstrap.producer is fake_producer
    assert len(calls) == 1

    clear_live_cockpit_client_factory_builder()
    after_clear = start_live_cockpit_runtime(_LIVE_ENV, runtime_starter=starter)
    assert after_clear.started is False
    assert after_clear.status == LIVE_COCKPIT_STATUS_CLIENT_FACTORY_UNAVAILABLE
    # No additional start attempt once the builder is gone.
    assert len(calls) == 1


def test_stop_live_cockpit_runtime_shuts_down_started_manager(monkeypatch) -> None:
    stopped: list[object] = []

    def _fake_stop(manager):
        stopped.append(manager)

    monkeypatch.setattr(live_cockpit_runtime, "stop_operator_live_runtime", _fake_stop)

    fake_manager = _FakeManager()
    started = start_live_cockpit_runtime(
        _LIVE_ENV,
        client_factory_builder=_builder_returning(object(), object()),
        runtime_starter=lambda **kwargs: _FakeLaunchResult(
            producer=_FakeProducer(), manager=fake_manager
        ),
    )

    assert stop_live_cockpit_runtime(started) is True
    assert stopped == [fake_manager]


def test_stop_live_cockpit_runtime_is_noop_for_fail_closed_bootstrap(monkeypatch) -> None:
    monkeypatch.setattr(
        live_cockpit_runtime,
        "stop_operator_live_runtime",
        lambda manager: pytest.fail("must not stop a fail-closed bootstrap"),
    )

    fail_closed = start_live_cockpit_runtime(_NON_LIVE_ENV)
    assert stop_live_cockpit_runtime(fail_closed) is False
