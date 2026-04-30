#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import stat
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import re


DEFAULT_AUTH_URL = "https://api.schwabapi.com/v1/oauth/authorize"
DEFAULT_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"


class OAuthPrepError(RuntimeError):
    pass


class TokenEndpointError(OAuthPrepError):
    def __init__(
        self,
        *,
        http_status: int | None,
        body: str = "",
        exception_class: str | None = None,
        reason_class: str | None = None,
        reason: object | None = None,
    ) -> None:
        super().__init__("TOKEN_ENDPOINT_FAIL")
        self.http_status = http_status
        self.body = body
        self.exception_class = exception_class
        self.reason_class = reason_class
        self.reason = reason


@dataclass(frozen=True)
class OAuthConfig:
    app_key: str
    app_secret: str
    callback_url: str
    token_path: Path
    token_path_display: str
    oauth_live: bool
    oauth_scope: str
    auth_url: str
    token_url: str
    target_root: Path
    repo_root: Path


def _target_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _repo_root(target_root: Path) -> Path:
    return target_root.parents[1]


def _repo_relative(path: Path, *, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def _resolve_token_path(raw_value: str, *, target_root: Path) -> Path:
    token_path = Path(raw_value).expanduser()
    if not token_path.is_absolute():
        token_path = target_root / token_path
    return token_path.resolve(strict=False)


def _require_under_state(token_path: Path, *, target_root: Path) -> None:
    state_root = (target_root / ".state").resolve(strict=False)
    try:
        token_path.relative_to(state_root)
    except ValueError as exc:
        raise OAuthPrepError("SCHWAB_TOKEN_PATH must resolve under target/ntb_marimo_console/.state/.") from exc


def load_config(env: dict[str, str] | None = None) -> OAuthConfig:
    values = os.environ if env is None else env
    target_root = _target_root()
    repo_root = _repo_root(target_root)
    required = {
        "SCHWAB_APP_KEY": values.get("SCHWAB_APP_KEY", ""),
        "SCHWAB_APP_SECRET": values.get("SCHWAB_APP_SECRET", ""),
        "SCHWAB_CALLBACK_URL": values.get("SCHWAB_CALLBACK_URL", ""),
        "SCHWAB_TOKEN_PATH": values.get("SCHWAB_TOKEN_PATH", ""),
        "SCHWAB_OAUTH_LIVE": values.get("SCHWAB_OAUTH_LIVE", ""),
    }
    missing = tuple(name for name, value in required.items() if not value.strip())
    if missing:
        raise OAuthPrepError(f"Missing required environment variables: {', '.join(missing)}.")

    token_path = _resolve_token_path(required["SCHWAB_TOKEN_PATH"], target_root=target_root)
    _require_under_state(token_path, target_root=target_root)

    return OAuthConfig(
        app_key=required["SCHWAB_APP_KEY"].strip(),
        app_secret=required["SCHWAB_APP_SECRET"].strip(),
        callback_url=required["SCHWAB_CALLBACK_URL"].strip(),
        token_path=token_path,
        token_path_display=_repo_relative(token_path, repo_root=repo_root),
        oauth_live=required["SCHWAB_OAUTH_LIVE"].strip() == "true",
        oauth_scope=values.get("SCHWAB_OAUTH_SCOPE", "readonly").strip() or "readonly",
        auth_url=values.get("SCHWAB_OAUTH_AUTH_URL", DEFAULT_AUTH_URL).strip() or DEFAULT_AUTH_URL,
        token_url=values.get("SCHWAB_OAUTH_TOKEN_URL", DEFAULT_TOKEN_URL).strip() or DEFAULT_TOKEN_URL,
        target_root=target_root,
        repo_root=repo_root,
    )


def build_authorization_url(config: OAuthConfig) -> str:
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": config.app_key,
            "redirect_uri": config.callback_url,
            "scope": config.oauth_scope,
        }
    )
    return f"{config.auth_url}?{query}"


def extract_authorization_code(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        raise OAuthPrepError("Authorization code input was empty.")
    if "://" not in value and "code=" not in value:
        return urllib.parse.unquote(value)

    parsed = urllib.parse.urlparse(value)
    params = urllib.parse.parse_qs(parsed.query, keep_blank_values=False)
    code_values = params.get("code")
    if not code_values or not code_values[0].strip():
        raise OAuthPrepError("Pasted callback URL did not contain a code query parameter.")
    return code_values[0].strip()


def describe_authorization_code(code: str) -> str:
    if not code:
        shape = "UNKNOWN"
    elif code.startswith("C0."):
        shape = "C0_PREFIX"
    elif "." in code:
        shape = "OTHER_PREFIX"
    else:
        shape = "UNKNOWN"
    return f"code_present={'yes' if code else 'no'} code_shape={shape} code_length={len(code)}"


def _sanitize_diagnostic_text(value: object) -> str:
    text = str(value)
    text = re.sub(r"(?i)(access_token|refresh_token|code)=([^&\s]+)", r"\1=[REDACTED]", text)
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"\bCO\.[A-Za-z0-9._~+/=-]+", "CO.[REDACTED]", text)
    text = re.sub(r"https?://\S*code=[^\s]+", "[REDACTED_CALLBACK_URL]", text)
    return text


def _safe_error_body(raw_body: str) -> str:
    if not raw_body.strip():
        return ""
    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError:
        return _sanitize_diagnostic_text(raw_body)
    if not isinstance(parsed, dict):
        return _sanitize_diagnostic_text(raw_body)

    safe_fields: dict[str, str] = {}
    for key in ("error", "error_description"):
        if key in parsed:
            safe_fields[key] = _sanitize_diagnostic_text(parsed[key])
    if safe_fields:
        return json.dumps(safe_fields, sort_keys=True)
    return _sanitize_diagnostic_text(raw_body)


def _safe_reason(reason: object | None) -> str:
    if reason is None:
        return ""
    return _sanitize_diagnostic_text(reason)


def confirm_overwrite(token_path: Path, *, input_func=input) -> None:
    if not token_path.exists():
        return
    response = input_func("Token file already exists. Type OVERWRITE to replace it: ")
    if response.strip() != "OVERWRITE":
        raise OAuthPrepError("Existing token overwrite was not confirmed.")


def exchange_authorization_code(config: OAuthConfig, code: str) -> dict[str, Any]:
    payload = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config.callback_url,
        }
    ).encode("utf-8")
    credentials = f"{config.app_key}:{config.app_secret}".encode("utf-8")
    basic_auth = base64.b64encode(credentials).decode("ascii")
    request = urllib.request.Request(
        config.token_url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Basic {basic_auth}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "Content-Length": str(len(payload)),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        raise TokenEndpointError(http_status=exc.code, body=body, exception_class=exc.__class__.__name__) from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        raise TokenEndpointError(
            http_status=None,
            exception_class=exc.__class__.__name__,
            reason_class=reason.__class__.__name__ if reason is not None else None,
            reason=reason,
        ) from exc

    try:
        token_response = json.loads(body)
    except json.JSONDecodeError as exc:
        raise OAuthPrepError("Token endpoint response was not valid JSON.") from exc
    if not isinstance(token_response, dict):
        raise OAuthPrepError("Token endpoint response JSON was not an object.")
    if not token_response.get("access_token") or not token_response.get("refresh_token"):
        raise OAuthPrepError("Token response must contain access_token and refresh_token.")
    return token_response


def write_token_file(token_path: Path, token_response: dict[str, Any]) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".token.", suffix=".tmp", dir=token_path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(token_response, handle, indent=2, sort_keys=True)
            handle.write("\n")
        try:
            os.chmod(temp_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        temp_path.replace(token_path)
        try:
            os.chmod(token_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def print_safe_summary(config: OAuthConfig, authorization_url: str) -> None:
    print("SCHWAB_OAUTH_TOKEN_PREP")
    print(f"repo_root={config.repo_root}")
    print(f"target_root={_repo_relative(config.target_root, repo_root=config.repo_root)}")
    print(f"oauth_live={config.oauth_live}")
    print("credentials=SCHWAB_APP_KEY present: yes; SCHWAB_APP_SECRET present: yes")
    print("callback_url=present")
    print(f"token_path={config.token_path_display}")
    print("token_path_safety=UNDER_TARGET_STATE")
    print(f"authorization_url={authorization_url}")


def run(
    argv: list[str] | None = None,
    *,
    env: dict[str, str] | None = None,
    input_func=input,
    secret_input_func=getpass.getpass,
    exchange_func=exchange_authorization_code,
    write_func=write_token_file,
) -> int:
    parser = argparse.ArgumentParser(description="Prepare a Schwab OAuth token file by manual authorization-code flow.")
    parser.parse_args(argv)

    try:
        config = load_config(env)
        authorization_url = build_authorization_url(config)
        print_safe_summary(config, authorization_url)

        if not config.oauth_live:
            print("network_activity=SKIPPED_OAUTH_DRY_RUN")
            print("OAUTH_DRY_RUN_PASS")
            return 0

        confirm_overwrite(config.token_path, input_func=input_func)
        raw_code_or_url = secret_input_func("Paste redirected callback URL or raw authorization code: ")
        code = extract_authorization_code(raw_code_or_url)
        print(describe_authorization_code(code))
        token_response = exchange_func(config, code)
        if not token_response.get("access_token") or not token_response.get("refresh_token"):
            raise OAuthPrepError("Token response must contain access_token and refresh_token.")
        write_func(config.token_path, token_response)
        print("TOKEN_WRITE_PASS")
        return 0
    except OAuthPrepError as exc:
        print("OAUTH_PREP_FAIL")
        if isinstance(exc, TokenEndpointError):
            print("TOKEN_ENDPOINT_FAIL")
            if exc.http_status is not None:
                print(f"http_status={exc.http_status}")
            if exc.exception_class:
                print(f"exception_class={exc.exception_class}")
            safe_body = _safe_error_body(exc.body)
            if safe_body:
                print(f"error_body={safe_body}")
            if exc.reason_class:
                print(f"reason_class={exc.reason_class}")
            safe_reason = _safe_reason(exc.reason)
            if safe_reason:
                print(f"reason={safe_reason}")
        else:
            print(f"error={exc}")
        return 1


if __name__ == "__main__":
    sys.exit(run())
