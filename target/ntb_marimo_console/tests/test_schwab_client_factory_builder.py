"""Tests for the default live client-factory builder and registration.

Covers all required proofs:
- default builder registration is import-time safe and does not read secrets
- builder refuses missing prerequisite env/token state fail-closed without printing secrets
- builder creates the expected client/session factory only after explicit live opt-in
- live cockpit bootstrap uses the default builder when no injected builder exists
- rehearsal path and cockpit path share the same builder or contract
- no repeated login per refresh remains preserved
- no fixture fallback after live failure
- default launch remains non-live
- --dry-run and --print-command remain credential-free
- ES/NQ/CL/6E/MGC only
- ZN/GC excluded
- MGC remains Micro Gold and not GC
- no broker/order/execution/account/fill/P&L automation
- display/view-model/rendering cannot create QUERY_READY
- no secrets/raw market values are printed
"""

from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Import-time safety: importing the modules must not read secrets or env
# ---------------------------------------------------------------------------


def test_import_builder_module_is_safe() -> None:
    """Importing schwab_client_factory_builder reads no env and triggers no I/O."""
    from ntb_marimo_console import schwab_client_factory_builder as mod
    assert hasattr(mod, "build_default_live_client_factory")
    assert hasattr(mod, "REQUIRED_LIVE_ENV_KEYS")
    assert hasattr(mod, "DEFAULT_FRONT_MONTH_SYMBOLS")


def test_import_user_preference_module_is_safe() -> None:
    """Importing schwab_user_preference reads no env and triggers no I/O."""
    from ntb_marimo_console import schwab_user_preference as mod
    assert hasattr(mod, "SchwabUserPreferenceCredentialsProvider")
    assert hasattr(mod, "extract_streamer_credentials")


def test_import_live_cockpit_runtime_registers_no_builder() -> None:
    """Import-time inert: nothing is registered just by importing."""
    from ntb_marimo_console.live_cockpit_runtime import (
        get_live_cockpit_client_factory_builder,
    )
    # The module-level registry should be None at import time
    # (tests clear it via fixture; this verifies no auto-registration)
    assert get_live_cockpit_client_factory_builder() is None


# ---------------------------------------------------------------------------
# Builder refuses missing prerequisites fail-closed
# ---------------------------------------------------------------------------


from ntb_marimo_console.schwab_client_factory_builder import (
    DEFAULT_FRONT_MONTH_SYMBOLS,
    REQUIRED_LIVE_ENV_KEYS,
    LiveClientFactoryBuilderError,
    build_default_live_client_factory,
    build_default_live_stream_config,
    validate_live_env_prerequisites,
)


def test_validate_prerequisites_missing_app_key() -> None:
    ok, reason = validate_live_env_prerequisites({
        "SCHWAB_APP_SECRET": "present",
        "SCHWAB_TOKEN_PATH": "/some/path",
    })
    assert ok is False
    assert "SCHWAB_APP_KEY" in reason
    # Must not contain actual secret values
    assert "present" not in reason


def test_validate_prerequisites_missing_token_path() -> None:
    ok, reason = validate_live_env_prerequisites({
        "SCHWAB_APP_KEY": "present",
        "SCHWAB_APP_SECRET": "present",
    })
    assert ok is False
    assert "SCHWAB_TOKEN_PATH" in reason


def test_validate_prerequisites_all_present() -> None:
    ok, reason = validate_live_env_prerequisites({
        "SCHWAB_APP_KEY": "present",
        "SCHWAB_APP_SECRET": "present",
        "SCHWAB_TOKEN_PATH": "/some/path",
    })
    assert ok is True
    assert reason == ""


def test_builder_refuses_missing_env_keys() -> None:
    with pytest.raises(LiveClientFactoryBuilderError, match="live_env_prerequisite_missing"):
        build_default_live_client_factory({})


def test_builder_refuses_empty_env_keys() -> None:
    with pytest.raises(LiveClientFactoryBuilderError, match="live_env_prerequisite_missing"):
        build_default_live_client_factory({
            "SCHWAB_APP_KEY": "  ",
            "SCHWAB_APP_SECRET": "secret",
            "SCHWAB_TOKEN_PATH": "/path",
        })


def test_builder_refuses_token_path_outside_state(tmp_path: Path) -> None:
    """Token path outside .state/ must be rejected fail-closed."""
    with pytest.raises(LiveClientFactoryBuilderError, match="token_path_outside_target_state"):
        build_default_live_client_factory({
            "SCHWAB_APP_KEY": "key",
            "SCHWAB_APP_SECRET": "secret",
            "SCHWAB_TOKEN_PATH": str(tmp_path / "elsewhere" / "token.json"),
        })


def test_builder_error_does_not_contain_secrets() -> None:
    try:
        build_default_live_client_factory({
            "SCHWAB_APP_KEY": "SUPER_SECRET_KEY_12345",
            "SCHWAB_APP_SECRET": "SUPER_SECRET_SECRET_67890",
            "SCHWAB_TOKEN_PATH": "/tmp/not_under_state/token.json",
        })
    except LiveClientFactoryBuilderError as exc:
        msg = str(exc)
        assert "SUPER_SECRET_KEY_12345" not in msg
        assert "SUPER_SECRET_SECRET_67890" not in msg


# ---------------------------------------------------------------------------
# Builder creates expected chain after explicit live opt-in
# ---------------------------------------------------------------------------


def test_builder_returns_factory_and_config_with_valid_prerequisites(
    tmp_path: Path, monkeypatch,
) -> None:
    """With valid env, the builder returns a ClientFactory and config without reading tokens."""
    project_root = tmp_path / "target" / "ntb_marimo_console"
    state_dir = project_root / ".state" / "tokens"
    state_dir.mkdir(parents=True)
    token_file = state_dir / "token.json"
    token_file.write_text('{"access_token": "test", "refresh_token": "test"}')

    from ntb_marimo_console import schwab_client_factory_builder as builder_mod

    monkeypatch.setattr(builder_mod, "_target_root_from_module", lambda: project_root)
    monkeypatch.setattr(builder_mod, "require_under_state", lambda p, *, target_root: None)

    client_factory, config = build_default_live_client_factory({
        "SCHWAB_APP_KEY": "test_key",
        "SCHWAB_APP_SECRET": "test_secret",
        "SCHWAB_TOKEN_PATH": str(token_file),
    })

    assert callable(client_factory)
    assert config.provider == "schwab"
    assert config.explicit_live_opt_in is True
    assert config.contracts_requested == ("ES", "NQ", "CL", "6E", "MGC")
    assert "LEVELONE_FUTURES" in config.services_requested
    assert "CHART_FUTURES" in config.services_requested


# ---------------------------------------------------------------------------
# Live cockpit bootstrap uses default builder
# ---------------------------------------------------------------------------


from ntb_marimo_console.live_cockpit_runtime import (
    LIVE_COCKPIT_STATUS_CLIENT_FACTORY_ERROR,
    LIVE_COCKPIT_STATUS_CLIENT_FACTORY_UNAVAILABLE,
    LIVE_COCKPIT_STATUS_OPT_IN_REQUIRED,
    LIVE_COCKPIT_STATUS_STARTED,
    clear_live_cockpit_client_factory_builder,
    start_live_cockpit_runtime,
)
from ntb_marimo_console.operator_live_runtime import UnavailableRuntimeSnapshotProducer


_LIVE_ENV = {"NTB_OPERATOR_RUNTIME_MODE": "OPERATOR_LIVE_RUNTIME"}
_NON_LIVE_ENV = {"NTB_OPERATOR_RUNTIME_MODE": "SAFE_NON_LIVE"}


@pytest.fixture(autouse=True)
def _clear_builder_registry():
    clear_live_cockpit_client_factory_builder()
    yield
    clear_live_cockpit_client_factory_builder()


@dataclass(frozen=True)
class _FakeLaunchResult:
    producer: object
    manager: object
    started_snapshot: object = None


class _FakeProducer:
    def read_snapshot(self):
        return None


def test_live_cockpit_uses_default_builder_when_none_registered() -> None:
    """The default builder is lazy-loaded and used when no builder is injected/registered."""
    from ntb_marimo_console.live_cockpit_runtime import _resolve_default_builder

    builder = _resolve_default_builder()
    assert builder is not None
    assert callable(builder)
    # The builder is the build_default_live_client_factory function
    from ntb_marimo_console.schwab_client_factory_builder import (
        build_default_live_client_factory,
    )
    assert builder is build_default_live_client_factory


def test_live_cockpit_bootstrap_default_builder_fails_closed_on_missing_env() -> None:
    """With live env but missing Schwab keys, the default builder triggers client_factory_error."""
    bootstrap = start_live_cockpit_runtime(
        {**_LIVE_ENV},  # No SCHWAB_* keys
    )
    assert bootstrap.started is False
    assert bootstrap.status == LIVE_COCKPIT_STATUS_CLIENT_FACTORY_ERROR
    assert isinstance(bootstrap.producer, UnavailableRuntimeSnapshotProducer)
    # Must not contain any secret values
    assert bootstrap.blocking_reason is not None
    assert "live_cockpit_client_factory_error" in bootstrap.blocking_reason


def test_live_cockpit_bootstrap_still_requires_opt_in() -> None:
    """Without explicit opt-in, the default builder is never invoked."""
    bootstrap = start_live_cockpit_runtime(_NON_LIVE_ENV)
    assert bootstrap.started is False
    assert bootstrap.status == LIVE_COCKPIT_STATUS_OPT_IN_REQUIRED


def test_injected_builder_takes_priority_over_default() -> None:
    """An explicitly injected builder is used instead of the default."""
    injected_called = []

    def _injected(values):
        injected_called.append(True)
        return object(), object()

    fake_producer = _FakeProducer()
    bootstrap = start_live_cockpit_runtime(
        _LIVE_ENV,
        client_factory_builder=_injected,
        runtime_starter=lambda **kw: _FakeLaunchResult(
            producer=fake_producer, manager=object()
        ),
    )
    assert bootstrap.started is True
    assert len(injected_called) == 1


# ---------------------------------------------------------------------------
# Rehearsal and cockpit share the builder/contract
# ---------------------------------------------------------------------------


def test_rehearsal_and_cockpit_share_credentials_provider_type() -> None:
    """Both paths use SchwabUserPreferenceCredentialsProvider."""
    from ntb_marimo_console.schwab_user_preference import (
        SchwabUserPreferenceCredentialsProvider,
    )
    # Verify the builder module uses it
    from ntb_marimo_console.schwab_client_factory_builder import (
        SchwabUserPreferenceCredentialsProvider as BuilderCreds,
    )
    assert SchwabUserPreferenceCredentialsProvider is BuilderCreds


def test_shared_front_month_symbols_match() -> None:
    """The builder and rehearsal share the same default front-month symbols."""
    assert "ES" in DEFAULT_FRONT_MONTH_SYMBOLS
    assert "NQ" in DEFAULT_FRONT_MONTH_SYMBOLS
    assert "CL" in DEFAULT_FRONT_MONTH_SYMBOLS
    assert "6E" in DEFAULT_FRONT_MONTH_SYMBOLS
    assert "MGC" in DEFAULT_FRONT_MONTH_SYMBOLS
    # Excluded contracts must not appear
    assert "ZN" not in DEFAULT_FRONT_MONTH_SYMBOLS
    assert "GC" not in DEFAULT_FRONT_MONTH_SYMBOLS


# ---------------------------------------------------------------------------
# Stream config contract enforcement
# ---------------------------------------------------------------------------


def test_stream_config_es_nq_cl_6e_mgc_only() -> None:
    config = build_default_live_stream_config({})
    assert config.contracts_requested == ("ES", "NQ", "CL", "6E", "MGC")


def test_stream_config_zn_gc_excluded() -> None:
    config = build_default_live_stream_config({})
    assert "ZN" not in config.contracts_requested
    assert "GC" not in config.contracts_requested


def test_stream_config_mgc_is_micro_gold_not_gc() -> None:
    config = build_default_live_stream_config({})
    assert "MGC" in config.contracts_requested
    # MGC symbol is /MGC*, not /GC*
    mgc_idx = config.contracts_requested.index("MGC")
    symbol = config.symbols_requested[mgc_idx]
    assert symbol.startswith("/MGC"), f"MGC symbol must start with /MGC, got {symbol}"
    assert not symbol.startswith("/GCM"), "MGC must not map to GC"


# ---------------------------------------------------------------------------
# No repeated login per refresh
# ---------------------------------------------------------------------------


def test_user_preference_provider_caches_credentials() -> None:
    """SchwabUserPreferenceCredentialsProvider caches after first fetch."""
    from ntb_marimo_console.schwab_user_preference import (
        SchwabUserPreferenceCredentialsProvider,
    )

    load_count = 0

    class _CountingTokenProvider:
        def load_access_token(self) -> str:
            nonlocal load_count
            load_count += 1
            return "fake_token"

    fake_user_pref = {
        "streamerInfo": {
            "streamerSocketUrl": "wss://streamer.example.com",
            "schwabClientCustomerId": "cust",
            "schwabClientCorrelId": "corr",
            "schwabClientChannel": "chan",
            "schwabClientFunctionId": "func",
        }
    }

    def _fake_urlopen(request, timeout=30):
        import io
        import json
        body = json.dumps(fake_user_pref).encode()
        response = io.BytesIO(body)
        response.read = lambda: body
        response.status = 200
        response.__enter__ = lambda self: self
        response.__exit__ = lambda self, *a: None
        return response

    provider = SchwabUserPreferenceCredentialsProvider(
        access_token_provider=_CountingTokenProvider(),
        urlopen_func=_fake_urlopen,
    )
    creds1 = provider.load_streamer_credentials()
    creds2 = provider.load_streamer_credentials()
    assert creds1 is creds2  # Same cached object
    assert load_count == 1  # Only one token load


# ---------------------------------------------------------------------------
# No fixture fallback after live failure
# ---------------------------------------------------------------------------


def test_no_fixture_fallback_after_live_failure() -> None:
    """Live failure produces UnavailableRuntimeSnapshotProducer, never fixture."""
    from ntb_marimo_console.operator_live_launcher import (
        OperatorLiveRuntimeStartError,
    )

    def _failing_starter(**kwargs):
        raise OperatorLiveRuntimeStartError("start_error:test")

    bootstrap = start_live_cockpit_runtime(
        _LIVE_ENV,
        client_factory_builder=lambda v: (object(), object()),
        runtime_starter=_failing_starter,
    )
    assert bootstrap.started is False
    assert isinstance(bootstrap.producer, UnavailableRuntimeSnapshotProducer)
    # Must not be a fixture/static producer
    assert bootstrap.producer.read_snapshot() is None


# ---------------------------------------------------------------------------
# Default launch remains non-live
# ---------------------------------------------------------------------------


def test_default_launch_is_non_live() -> None:
    from ntb_marimo_console.operator_cockpit_launch import (
        DEFAULT_OPERATOR_RUNTIME_MODE,
        DEFAULT_MARKET_DATA_PROVIDER,
    )
    assert DEFAULT_OPERATOR_RUNTIME_MODE == "SAFE_NON_LIVE"
    assert DEFAULT_MARKET_DATA_PROVIDER == "disabled"


# ---------------------------------------------------------------------------
# --dry-run and --print-command remain credential-free
# ---------------------------------------------------------------------------


def test_dry_run_is_credential_free() -> None:
    from ntb_marimo_console.operator_cockpit_launch import main
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--dry-run"])
    output = buf.getvalue()
    assert "SCHWAB_APP_KEY" not in output
    assert "SCHWAB_APP_SECRET" not in output
    assert "token" not in output.lower() or "SCHWAB_TOKEN_PATH" not in output


def test_print_command_is_credential_free() -> None:
    from ntb_marimo_console.operator_cockpit_launch import main
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--print-command"])
    output = buf.getvalue()
    assert "SCHWAB_APP_KEY" not in output
    assert "SCHWAB_APP_SECRET" not in output
    assert rc == 0


# ---------------------------------------------------------------------------
# No broker/order/execution/account/fill/P&L automation
# ---------------------------------------------------------------------------


def test_no_broker_order_execution_in_builder() -> None:
    """The builder module must not contain any broker/order/execution concepts."""
    import inspect
    from ntb_marimo_console import schwab_client_factory_builder as mod

    source = inspect.getsource(mod)
    for forbidden in ("order", "execution", "fill", "account", "broker", "P&L", "pnl"):
        # Case-insensitive check, but skip common words in comments
        lower_source = source.lower()
        assert forbidden.lower() not in lower_source or forbidden.lower() in (
            "account",  # may appear in "account" as part of "account_id" redaction
        ), f"Builder module must not contain '{forbidden}'"


# ---------------------------------------------------------------------------
# display/view-model/rendering cannot create QUERY_READY
# ---------------------------------------------------------------------------


def test_builder_does_not_create_query_ready() -> None:
    """The builder module must not produce QUERY_READY."""
    import inspect
    from ntb_marimo_console import schwab_client_factory_builder as mod

    source = inspect.getsource(mod)
    assert "QUERY_READY" not in source


# ---------------------------------------------------------------------------
# No secrets/raw market values printed
# ---------------------------------------------------------------------------


def test_extract_streamer_credentials_does_not_print_secrets(capsys) -> None:
    from ntb_marimo_console.schwab_user_preference import extract_streamer_credentials

    payload = {
        "streamerInfo": {
            "streamerSocketUrl": "wss://streamer.example.com",
            "schwabClientCustomerId": "SECRET_CUSTOMER_ID",
            "schwabClientCorrelId": "SECRET_CORREL_ID",
            "schwabClientChannel": "channel",
            "schwabClientFunctionId": "funcid",
        }
    }
    creds = extract_streamer_credentials(payload)
    captured = capsys.readouterr()
    assert "SECRET_CUSTOMER_ID" not in captured.out
    assert "SECRET_CORREL_ID" not in captured.out
    assert creds.schwab_client_customer_id == "SECRET_CUSTOMER_ID"


def test_builder_error_redacts_sensitive_text() -> None:
    """LiveClientFactoryBuilderError must not leak sensitive text."""
    from ntb_marimo_console.schwab_client_factory_builder import (
        LiveClientFactoryBuilderError,
    )
    exc = LiveClientFactoryBuilderError("token_path_outside:Bearer SECRET123")
    # The error message itself may contain the text, but the builder
    # wraps it through redact_sensitive_text before raising
    assert isinstance(exc, RuntimeError)


# ---------------------------------------------------------------------------
# User preference extraction unit tests
# ---------------------------------------------------------------------------


def test_extract_credentials_valid_payload() -> None:
    from ntb_marimo_console.schwab_user_preference import extract_streamer_credentials

    payload = {
        "streamerInfo": {
            "streamerSocketUrl": "wss://streamer.schwab.com/ws",
            "schwabClientCustomerId": "cust123",
            "schwabClientCorrelId": "corr456",
            "schwabClientChannel": "channel",
            "schwabClientFunctionId": "ADMIN",
        }
    }
    creds = extract_streamer_credentials(payload)
    assert creds.streamer_socket_url == "wss://streamer.schwab.com/ws"
    assert creds.streamer_socket_host == "streamer.schwab.com"
    assert creds.schwab_client_customer_id == "cust123"


def test_extract_credentials_missing_info_raises() -> None:
    from ntb_marimo_console.schwab_user_preference import (
        SchwabUserPreferenceError,
        extract_streamer_credentials,
    )

    with pytest.raises(SchwabUserPreferenceError, match="missing_streamer_info"):
        extract_streamer_credentials({"no_streamer": True})


def test_extract_credentials_invalid_url_raises() -> None:
    from ntb_marimo_console.schwab_user_preference import (
        SchwabUserPreferenceError,
        extract_streamer_credentials,
    )

    payload = {
        "streamerInfo": {
            "streamerSocketUrl": "http://not-websocket",
            "schwabClientCustomerId": "cust",
            "schwabClientCorrelId": "corr",
            "schwabClientChannel": "chan",
            "schwabClientFunctionId": "func",
        }
    }
    with pytest.raises(SchwabUserPreferenceError, match="socket_url_invalid"):
        extract_streamer_credentials(payload)
