"""Default live client-factory builder for the live cockpit.

This module provides the app-owned default
:data:`LiveCockpitClientFactoryBuilder` that resolves the current blocker:
live cockpit bootstrap can now connect real Schwab data without test
injection.

**Import-time inert**: importing this module performs no env reads, file
opens, network calls, websocket imports, or runtime starts. All such work
happens only when :func:`build_default_live_client_factory` is explicitly
invoked inside :func:`start_live_cockpit_runtime` under live opt-in.

**Fail-closed**: the builder refuses to proceed and raises if any
prerequisite env key is missing or if the token path is outside the
expected ``.state/`` subtree. No secrets are printed, exposed, or logged.
"""

from __future__ import annotations

import os
from pathlib import Path

from .contract_universe import final_target_contracts
from .market_data.stream_events import redact_sensitive_text
from .market_data.stream_manager import SchwabStreamManagerConfig
from .schwab_stream_client import (
    ClientFactory,
    build_operator_schwab_stream_client_factory,
)
from .schwab_streamer_session import (
    DEFAULT_LEVELONE_FUTURES_FIELD_IDS,
    build_operator_schwab_streamer_session_factory,
    default_schwab_websocket_factory,
)
from .schwab_token_lifecycle import (
    DEFAULT_TOKEN_URL,
    RefreshableAccessTokenProvider,
    resolve_token_path,
    require_under_state,
)
from .schwab_user_preference import SchwabUserPreferenceCredentialsProvider


REQUIRED_LIVE_ENV_KEYS: tuple[str, ...] = (
    "SCHWAB_APP_KEY",
    "SCHWAB_APP_SECRET",
    "SCHWAB_TOKEN_PATH",
)

DEFAULT_FRONT_MONTH_SYMBOLS: dict[str, str] = {
    "ES": "/ESM26",
    "NQ": "/NQM26",
    "CL": "/CLM26",
    "6E": "/6EM26",
    "MGC": "/MGCM26",
}


class LiveClientFactoryBuilderError(RuntimeError):
    """Raised when the builder cannot construct a live client factory.

    Reasons are redacted — no secret values appear in the message.
    """


def _target_root_from_module() -> Path:
    """Resolve the target root from the module's filesystem location."""

    return Path(__file__).resolve().parents[2]


def _resolve_front_month_symbols(
    values: dict[str, str],
) -> dict[str, str]:
    """Return front-month symbol map, allowing env-var overrides."""

    base = dict(DEFAULT_FRONT_MONTH_SYMBOLS)
    for contract in final_target_contracts():
        env_key = f"NTB_LIVE_SYMBOL_{contract}"
        override = values.get(env_key, "").strip()
        if override:
            base[contract] = override
    return base


def validate_live_env_prerequisites(
    values: dict[str, str],
) -> tuple[bool, str]:
    """Check that required env keys are present (values are not inspected).

    Returns ``(True, "")`` when prerequisites are satisfied, or
    ``(False, reason)`` with a safe, secret-free blocking reason.
    """

    for key in REQUIRED_LIVE_ENV_KEYS:
        if not values.get(key, "").strip():
            return False, f"live_env_prerequisite_missing:{key}"
    return True, ""


def build_default_live_stream_config(
    values: dict[str, str],
) -> SchwabStreamManagerConfig:
    """Build the ``SchwabStreamManagerConfig`` for the five-contract live runtime."""

    contracts = final_target_contracts()
    symbol_map = _resolve_front_month_symbols(values)
    symbols = tuple(symbol_map[contract] for contract in contracts)
    return SchwabStreamManagerConfig(
        provider="schwab",
        services_requested=("LEVELONE_FUTURES", "CHART_FUTURES"),
        symbols_requested=symbols,
        fields_requested=DEFAULT_LEVELONE_FUTURES_FIELD_IDS,
        explicit_live_opt_in=True,
        contracts_requested=contracts,
    )


def build_default_live_client_factory(
    values: dict[str, str],
) -> tuple[ClientFactory, SchwabStreamManagerConfig]:
    """Default ``LiveCockpitClientFactoryBuilder`` for live cockpit startup.

    Validates prerequisites, constructs the full provider chain
    (``RefreshableAccessTokenProvider`` → ``SchwabUserPreferenceCredentialsProvider``
    → ``build_operator_schwab_streamer_session_factory`` →
    ``build_operator_schwab_stream_client_factory``), and returns the
    ``ClientFactory`` plus ``SchwabStreamManagerConfig``.

    **Fail-closed**: raises ``LiveClientFactoryBuilderError`` if any
    prerequisite is missing. No secrets are printed, inspected, or exposed.

    **No I/O at builder time**: the returned ``ClientFactory`` performs its
    Schwab interactions lazily when the operator launcher invokes it under
    explicit ``OPERATOR_LIVE_RUNTIME`` opt-in.
    """

    prerequisites_ok, blocking_reason = validate_live_env_prerequisites(values)
    if not prerequisites_ok:
        raise LiveClientFactoryBuilderError(blocking_reason)

    app_key = values["SCHWAB_APP_KEY"].strip()
    app_secret = values["SCHWAB_APP_SECRET"].strip()
    raw_token_path = values["SCHWAB_TOKEN_PATH"].strip()
    token_url = values.get("SCHWAB_TOKEN_URL", "").strip() or DEFAULT_TOKEN_URL

    target_root = _target_root_from_module()
    token_path = resolve_token_path(raw_token_path, target_root=target_root)

    try:
        require_under_state(token_path, target_root=target_root)
    except Exception as exc:
        raise LiveClientFactoryBuilderError(
            f"token_path_outside_target_state:{redact_sensitive_text(exc)}"
        ) from exc

    # All providers are lazy — no file I/O, network, or token reads here.
    access_token_provider = RefreshableAccessTokenProvider(
        token_path=token_path,
        target_root=target_root,
        app_key=app_key,
        app_secret=app_secret,
        token_url=token_url,
    )
    credentials_provider = SchwabUserPreferenceCredentialsProvider(
        access_token_provider=access_token_provider,
    )
    websocket_factory = default_schwab_websocket_factory()

    session_factory = build_operator_schwab_streamer_session_factory(
        access_token_provider=access_token_provider,
        credentials_provider=credentials_provider,
        websocket_factory=websocket_factory,
    )
    client_factory = build_operator_schwab_stream_client_factory(
        streamer_session_factory=session_factory,
    )
    config = build_default_live_stream_config(values)

    return client_factory, config
