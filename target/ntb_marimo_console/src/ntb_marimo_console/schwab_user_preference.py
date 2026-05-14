"""Schwab userPreference API client for streamer credential resolution.

Import-time inert: no env reads, file I/O, network calls, or websocket
imports at module level. All Schwab interaction happens only when the
provider or fetch functions are explicitly invoked under live opt-in.

The ``SchwabUserPreferenceCredentialsProvider`` is the reusable, app-owned
implementation of :class:`SchwabStreamerCredentialsProvider` that both the
live cockpit default builder and the rehearsal script share.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .market_data.stream_events import redact_sensitive_text
from .schwab_streamer_session import (
    SchwabAccessTokenProvider,
    SchwabStreamerCredentialsProvider,
    StreamerCredentials,
)


DEFAULT_USER_PREF_URL = "https://api.schwabapi.com/trader/v1/userPreference"
DEFAULT_USER_PREF_TIMEOUT_SECONDS = 30.0

STREAMER_INFO_FIELD_KEYS: tuple[str, ...] = (
    "streamerSocketUrl",
    "streamer_socket_url",
    "schwabClientCustomerId",
    "schwab_client_customer_id",
    "schwabClientCorrelId",
    "schwab_client_correl_id",
    "schwabClientChannel",
    "schwab_client_channel",
    "schwabClientFunctionId",
    "schwab_client_function_id",
)


class SchwabUserPreferenceError(RuntimeError):
    """Raised on user preference fetch or credential extraction failures.

    Reasons are auto-redacted before reaching any caller surface.
    """

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status


# ---------------------------------------------------------------------------
# Pure helpers (no I/O).
# ---------------------------------------------------------------------------


def _looks_like_streamer_info(value: object) -> bool:
    return isinstance(value, dict) and sum(
        1 for key in STREAMER_INFO_FIELD_KEYS if key in value
    ) >= 2


def find_streamer_info(payload: object) -> dict[str, Any] | None:
    """Recursively locate the streamerInfo block in a userPreference response."""

    if isinstance(payload, dict):
        if _looks_like_streamer_info(payload):
            return payload
        for key in ("streamerInfo", "streamer_info"):
            streamer_info = payload.get(key)
            if isinstance(streamer_info, dict):
                return streamer_info
            found = find_streamer_info(streamer_info)
            if found is not None:
                return found
        for child in payload.values():
            found = find_streamer_info(child)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = find_streamer_info(item)
            if found is not None:
                return found
    return None


def _first_field(mapping: dict[str, Any], *keys: str) -> object:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def extract_streamer_credentials(payload: object) -> StreamerCredentials:
    """Extract ``StreamerCredentials`` from a Schwab userPreference response.

    Raises :class:`SchwabUserPreferenceError` if required streamer metadata
    is missing or invalid. Never prints or returns raw credential values in
    error messages.
    """

    streamer_info = find_streamer_info(payload)
    if not isinstance(streamer_info, dict):
        raise SchwabUserPreferenceError("user_preference_missing_streamer_info")
    socket_url = _first_field(
        streamer_info, "streamerSocketUrl", "streamer_socket_url"
    )
    customer_id = _first_field(
        streamer_info, "schwabClientCustomerId", "schwab_client_customer_id"
    )
    correl_id = _first_field(
        streamer_info, "schwabClientCorrelId", "schwab_client_correl_id"
    )
    channel = _first_field(
        streamer_info, "schwabClientChannel", "schwab_client_channel"
    )
    function_id = _first_field(
        streamer_info, "schwabClientFunctionId", "schwab_client_function_id"
    )
    values = (socket_url, customer_id, correl_id, channel, function_id)
    if not all(isinstance(value, str) and value.strip() for value in values):
        raise SchwabUserPreferenceError(
            "user_preference_missing_required_streamer_metadata"
        )
    parsed = urllib.parse.urlparse(str(socket_url).strip())
    if parsed.scheme not in {"ws", "wss"} or not parsed.netloc:
        raise SchwabUserPreferenceError(
            "user_preference_streamer_socket_url_invalid"
        )
    return StreamerCredentials(
        streamer_socket_url=str(socket_url).strip(),
        streamer_socket_host=parsed.netloc,
        schwab_client_customer_id=str(customer_id).strip(),
        schwab_client_correl_id=str(correl_id).strip(),
        schwab_client_channel=str(channel).strip(),
        schwab_client_function_id=str(function_id).strip(),
    )


# ---------------------------------------------------------------------------
# User preference fetch (I/O only when invoked).
# ---------------------------------------------------------------------------


def fetch_user_preference(
    access_token: str,
    *,
    url: str = DEFAULT_USER_PREF_URL,
    timeout_seconds: float = DEFAULT_USER_PREF_TIMEOUT_SECONDS,
    urlopen_func: Callable[..., object] = urllib.request.urlopen,
) -> object:
    """Fetch the Schwab userPreference JSON payload.

    Performs a single authenticated HTTP GET. Raises
    :class:`SchwabUserPreferenceError` on failure. Never prints or returns
    raw credential values.
    """

    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen_func(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", 200)
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise SchwabUserPreferenceError(
            "user_preference_fetch_failed",
            http_status=exc.code,
        ) from exc
    except urllib.error.URLError as exc:
        raise SchwabUserPreferenceError(
            "user_preference_fetch_failed",
        ) from exc
    if status != 200:
        raise SchwabUserPreferenceError(
            "user_preference_non_200",
            http_status=status,
        )
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise SchwabUserPreferenceError(
            "user_preference_malformed_json",
        ) from exc


# ---------------------------------------------------------------------------
# Reusable credentials provider.
# ---------------------------------------------------------------------------


@dataclass
class SchwabUserPreferenceCredentialsProvider:
    """Lazy, caching ``SchwabStreamerCredentialsProvider`` backed by the
    Schwab userPreference API.

    Performs no I/O at construction. Fetches the userPreference exactly once
    on first ``load_streamer_credentials()`` call, extracts
    ``StreamerCredentials``, and caches the result. Subsequent calls return
    the cached credentials without network activity.

    If the initial fetch returns HTTP 401, one retry is attempted after
    re-loading the access token (which may trigger a token refresh).
    """

    access_token_provider: SchwabAccessTokenProvider
    user_pref_url: str = DEFAULT_USER_PREF_URL
    timeout_seconds: float = DEFAULT_USER_PREF_TIMEOUT_SECONDS
    urlopen_func: Callable[..., object] = field(
        default=urllib.request.urlopen, repr=False
    )
    _cached: StreamerCredentials | None = field(
        default=None, init=False, repr=False
    )

    def load_streamer_credentials(self) -> StreamerCredentials:
        if self._cached is not None:
            return self._cached
        access_token = self.access_token_provider.load_access_token()
        try:
            payload = fetch_user_preference(
                access_token,
                url=self.user_pref_url,
                timeout_seconds=self.timeout_seconds,
                urlopen_func=self.urlopen_func,
            )
        except SchwabUserPreferenceError as exc:
            if exc.http_status == 401:
                access_token = self.access_token_provider.load_access_token()
                payload = fetch_user_preference(
                    access_token,
                    url=self.user_pref_url,
                    timeout_seconds=self.timeout_seconds,
                    urlopen_func=self.urlopen_func,
                )
            else:
                raise
        self._cached = extract_streamer_credentials(payload)
        return self._cached
