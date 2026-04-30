#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import schwab_token_utils
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import schwab_token_utils


class TokenRefreshProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class TokenRefreshConfig:
    app_key: str
    app_secret: str
    token_path: Path
    token_url: str
    live: bool
    target_root: Path


def _target_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_config(env: dict[str, str] | None = None) -> TokenRefreshConfig:
    values = os.environ if env is None else env
    missing = tuple(
        name
        for name in ("SCHWAB_APP_KEY", "SCHWAB_APP_SECRET", "SCHWAB_TOKEN_PATH")
        if not values.get(name, "").strip()
    )
    if missing:
        raise TokenRefreshProbeError(f"Missing required environment variables: {', '.join(missing)}.")

    target_root = _target_root()
    token_path = schwab_token_utils.resolve_token_path(values["SCHWAB_TOKEN_PATH"], target_root=target_root)
    schwab_token_utils.require_under_state(token_path, target_root=target_root)
    return TokenRefreshConfig(
        app_key=values["SCHWAB_APP_KEY"].strip(),
        app_secret=values["SCHWAB_APP_SECRET"].strip(),
        token_path=token_path,
        token_url=values.get("SCHWAB_OAUTH_TOKEN_URL", schwab_token_utils.DEFAULT_TOKEN_URL).strip()
        or schwab_token_utils.DEFAULT_TOKEN_URL,
        live=values.get("SCHWAB_TOKEN_REFRESH_LIVE", "").strip() == "true",
        target_root=target_root,
    )


def print_header() -> None:
    print("SCHWAB_TOKEN_REFRESH_PROBE")


def print_failure(exc: BaseException, *, refresh_token_present: bool | None = None) -> None:
    print("TOKEN_REFRESH_FAIL")
    print("refreshed_access_token=no")
    print("token_file_rewritten=no")
    if refresh_token_present is not None:
        print(f"refresh_token_present={'yes' if refresh_token_present else 'no'}")
    if isinstance(exc, schwab_token_utils.SchwabTokenError):
        if exc.exception_class:
            print(f"exception_class={exc.exception_class}")
        if exc.http_status is not None:
            print(f"http_status={exc.http_status}")
    else:
        print(f"exception_class={exc.__class__.__name__}")


def run(
    argv: list[str] | None = None,
    *,
    env: dict[str, str] | None = None,
    refresh_func=schwab_token_utils.refresh_token_file,
) -> int:
    parser = argparse.ArgumentParser(description="Force a safe Schwab refresh-token verification.")
    parser.parse_args(argv)
    print_header()

    refresh_token_present: bool | None = None
    try:
        config = load_config(env)
        print("token_path_safety=UNDER_TARGET_STATE")
        token_data = schwab_token_utils.load_token_json(config.token_path, target_root=config.target_root)
        try:
            schwab_token_utils.refresh_token_from(token_data)
            refresh_token_present = True
        except schwab_token_utils.SchwabTokenError:
            refresh_token_present = False
            raise
        print("refresh_token_present=yes")
        if not config.live:
            print("TOKEN_REFRESH_PASS")
            print("refreshed_access_token=no")
            print("token_file_rewritten=no")
            return 0
        refreshed = refresh_func(
            config.token_path,
            target_root=config.target_root,
            app_key=config.app_key,
            app_secret=config.app_secret,
            token_url=config.token_url,
        )
        schwab_token_utils.access_token_from(refreshed)
        print("TOKEN_REFRESH_PASS")
        print("refreshed_access_token=yes")
        print("token_file_rewritten=yes")
        return 0
    except (TokenRefreshProbeError, schwab_token_utils.SchwabTokenError, Exception) as exc:
        print_failure(exc, refresh_token_present=refresh_token_present)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
