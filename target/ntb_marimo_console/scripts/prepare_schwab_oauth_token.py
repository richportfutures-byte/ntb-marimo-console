#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import getpass
import gzip
import hashlib
import json
import os
import stat
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import re


DEFAULT_AUTH_URL = "https://api.schwabapi.com/v1/oauth/authorize"
DEFAULT_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
AUTHORIZATION_CODE_MIN_LENGTH = 7


class OAuthPrepError(RuntimeError):
    pass


class TokenEndpointError(OAuthPrepError):
    def __init__(
        self,
        *,
        http_status: int | None,
        body: bytes | str = b"",
        content_type: str = "",
        content_encoding: str = "",
        exception_class: str | None = None,
        reason_class: str | None = None,
        reason: object | None = None,
    ) -> None:
        super().__init__("TOKEN_ENDPOINT_FAIL")
        self.http_status = http_status
        self.body = body
        self.content_type = content_type
        self.content_encoding = content_encoding
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


@dataclass(frozen=True)
class TokenErrorSummary:
    token_error_present: str
    token_error_code: str
    token_error_description_present: str
    token_error_description_class: str
    response_content_type: str
    response_content_encoding: str
    response_decode_status: str
    retryable: str
    blocking_reason: str


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


def _authorization_url_path(*, target_root: Path) -> Path:
    return (target_root / ".state" / "schwab" / "oauth_authorization_url.txt").resolve(strict=False)


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
        raise OAuthPrepError("Missing required Schwab OAuth environment configuration.")

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


def _callback_url_fingerprint(callback_url: str) -> str:
    return hashlib.sha256(callback_url.encode("utf-8")).hexdigest()


def _validate_authorization_code_shape(code: str) -> str:
    if len(code) < AUTHORIZATION_CODE_MIN_LENGTH:
        raise OAuthPrepError("Authorization code input was too short.")
    if not (code.startswith("C0.") or code.startswith("CO.")):
        raise OAuthPrepError("Authorization code input had an unsupported shape.")
    if any(ch.isspace() for ch in code) or any(marker in code for marker in ("&", "?", "code=", "://")):
        raise OAuthPrepError("Authorization code input was malformed.")
    return code


def extract_authorization_code(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        raise OAuthPrepError("Authorization code input was empty.")
    if "://" not in value and "code=" not in value:
        return _validate_authorization_code_shape(urllib.parse.unquote(value))

    parsed = urllib.parse.urlparse(value)
    params = urllib.parse.parse_qs(parsed.query, keep_blank_values=False)
    code_values = params.get("code")
    if not code_values or not code_values[0].strip():
        raise OAuthPrepError("Pasted callback URL did not contain a code query parameter.")
    return _validate_authorization_code_shape(code_values[0].strip())


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
    text = re.sub(
        r"(?i)(access_token|refresh_token|code|client_id|client_secret)=([^&\s]+)",
        r"\1=[REDACTED]",
        text,
    )
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"\bCO\.[A-Za-z0-9._~+/=-]+", "CO.[REDACTED]", text)
    text = re.sub(r"\bC0\.[A-Za-z0-9._~+/=-]+", "C0.[REDACTED]", text)
    text = re.sub(r"https?://\S*code=[^\s]+", "[REDACTED_CALLBACK_URL]", text)
    text = re.sub(r"https?://\S*/oauth/authorize\?\S+", "[REDACTED_AUTHORIZATION_URL]", text)
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


def _safe_content_type(value: str) -> str:
    content_type = value.split(";", maxsplit=1)[0].strip().lower()
    if not content_type:
        return "unknown"
    if not re.fullmatch(r"[a-z0-9][a-z0-9.+/-]{0,80}", content_type):
        return "unsafe"
    return content_type


def _safe_content_encoding(value: str) -> str:
    content_encoding = value.split(",", maxsplit=1)[0].strip().lower()
    if not content_encoding:
        return "identity"
    if content_encoding in {"identity", "gzip", "deflate"}:
        return content_encoding
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,40}", content_encoding):
        return "unsafe"
    return "unsupported"


def _safe_token_error_code(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return "unavailable"
    token_error_code = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", token_error_code):
        return "unsafe"
    return token_error_code


def _decode_response_body(body: bytes | str, *, content_encoding: str = "") -> tuple[str, str]:
    if isinstance(body, str):
        return body, "ok"
    if not body:
        return "", "ok"
    safe_encoding = _safe_content_encoding(content_encoding)
    try:
        if safe_encoding == "gzip":
            body = gzip.decompress(body)
        elif safe_encoding == "deflate":
            body = zlib.decompress(body)
        elif safe_encoding in {"unsafe", "unsupported"}:
            return "", "failed"
    except (OSError, zlib.error):
        return "", "failed"
    try:
        return body.decode("utf-8"), "ok"
    except UnicodeDecodeError:
        return "", "failed"


def _classify_token_error_description(error_code: str, description: object) -> str:
    if not isinstance(description, str) or not description.strip():
        return "none"

    text = description.lower()
    if "redirect_uri" in text or "redirect uri" in text or "callback" in text:
        return "redirect_uri_or_callback"
    if "request" in text or "grant_type" in text or error_code in {"invalid_request", "unsupported_grant_type"}:
        return "malformed_request"
    if "authorization code" in text or "code" in text or "grant" in text or error_code == "invalid_grant":
        return "authorization_code_or_grant"
    if "client" in text or "secret" in text or "basic" in text or error_code == "invalid_client":
        return "client_auth"
    if "token" in text:
        return "token_value"
    return "present"


def _token_error_retryable(http_status: int | None, error_code: str) -> str:
    if http_status is not None and http_status >= 500:
        return "yes"
    if error_code in {"temporarily_unavailable", "server_error"}:
        return "yes"
    return "no"


def _token_error_blocking_reason(
    *,
    http_status: int | None,
    error_code: str,
    description_class: str,
    decode_status: str,
) -> str:
    if decode_status == "failed":
        return "token_endpoint_response_unreadable"
    if error_code == "invalid_grant":
        return "authorization_code_or_grant_rejected"
    if error_code == "invalid_client":
        return "client_auth_rejected"
    if error_code in {"invalid_request", "unsupported_grant_type"}:
        return "malformed_token_request"
    if description_class == "redirect_uri_or_callback":
        return "redirect_uri_mismatch_possible"
    if http_status is not None and http_status >= 500:
        return "token_endpoint_retryable"
    if error_code == "unavailable":
        return "token_endpoint_response_unclassified"
    return "token_endpoint_rejected"


def summarize_token_endpoint_error(error: TokenEndpointError) -> TokenErrorSummary:
    body_text, decode_status = _decode_response_body(error.body, content_encoding=error.content_encoding)
    response_content_type = _safe_content_type(error.content_type)
    response_content_encoding = _safe_content_encoding(error.content_encoding)
    fallback_description_class = "decode_failed" if decode_status == "failed" else "non_json"
    if not body_text.strip():
        fallback_description_class = "decode_failed" if decode_status == "failed" else "empty"

    try:
        parsed = json.loads(body_text) if body_text.strip() and decode_status == "ok" else None
    except json.JSONDecodeError:
        parsed = None

    if not isinstance(parsed, dict):
        return TokenErrorSummary(
            token_error_present="no",
            token_error_code="unavailable",
            token_error_description_present="no",
            token_error_description_class=fallback_description_class,
            response_content_type=response_content_type,
            response_content_encoding=response_content_encoding,
            response_decode_status=decode_status,
            retryable=_token_error_retryable(error.http_status, "unavailable"),
            blocking_reason=_token_error_blocking_reason(
                http_status=error.http_status,
                error_code="unavailable",
                description_class=fallback_description_class,
                decode_status=decode_status,
            ),
        )

    raw_error = parsed.get("error")
    error_code = _safe_token_error_code(raw_error)
    raw_description = parsed.get("error_description")
    description_present = isinstance(raw_description, str) and bool(raw_description.strip())
    description_class = _classify_token_error_description(error_code, raw_description)
    return TokenErrorSummary(
        token_error_present="yes" if raw_error is not None else "no",
        token_error_code=error_code,
        token_error_description_present="yes" if description_present else "no",
        token_error_description_class=description_class,
        response_content_type=response_content_type,
        response_content_encoding=response_content_encoding,
        response_decode_status=decode_status,
        retryable=_token_error_retryable(error.http_status, error_code),
        blocking_reason=_token_error_blocking_reason(
            http_status=error.http_status,
            error_code=error_code,
            description_class=description_class,
            decode_status=decode_status,
        ),
    )


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


def validate_initial_token_response(token_response: dict[str, Any]) -> None:
    if not isinstance(token_response.get("access_token"), str) or not token_response["access_token"].strip():
        raise OAuthPrepError("Token response missing required token fields.")
    if not isinstance(token_response.get("refresh_token"), str) or not token_response["refresh_token"].strip():
        raise OAuthPrepError("Token response missing required token fields.")


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
            body = exc.read()
        except Exception:
            body = b""
        raise TokenEndpointError(
            http_status=exc.code,
            body=body,
            content_type=exc.headers.get("Content-Type", "") if exc.headers is not None else "",
            content_encoding=exc.headers.get("Content-Encoding", "") if exc.headers is not None else "",
            exception_class=exc.__class__.__name__,
        ) from exc
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
    validate_initial_token_response(token_response)
    return token_response


def write_token_file(token_path: Path, token_response: dict[str, Any]) -> None:
    validate_initial_token_response(token_response)
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


def write_authorization_url_file(config: OAuthConfig, authorization_url: str) -> Path:
    url_path = _authorization_url_path(target_root=config.target_root)
    _require_under_state(url_path, target_root=config.target_root)
    url_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".oauth_authorization_url.", suffix=".tmp", dir=url_path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(authorization_url)
            handle.write("\n")
        try:
            os.chmod(temp_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        temp_path.replace(url_path)
        try:
            os.chmod(url_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return url_path


def print_safe_summary(
    config: OAuthConfig,
    *,
    authorization_url_written: bool,
    authorization_url_path: Path | None,
    browser_opened: bool,
) -> None:
    print("SCHWAB_OAUTH_TOKEN_PREP")
    print(f"repo_root={config.repo_root}")
    print(f"target_root={_repo_relative(config.target_root, repo_root=config.repo_root)}")
    print(f"oauth_live={config.oauth_live}")
    print("oauth_credentials_present=yes")
    print("callback_url_present=yes")
    print("callback_url_printed=no")
    print(f"callback_url_fingerprint_sha256={_callback_url_fingerprint(config.callback_url)}")
    print("token_url_present=yes")
    print("token_url_printed=no")
    print(f"token_path={config.token_path_display}")
    print("token_path_safety=UNDER_TARGET_STATE")
    print("authorization_url_present=yes")
    print("authorization_url_printed=no")
    print(f"authorization_url_written={'yes' if authorization_url_written else 'no'}")
    if authorization_url_path is not None:
        print(f"authorization_url_path={_repo_relative(authorization_url_path, repo_root=config.repo_root)}")
    print(f"browser_opened={'yes' if browser_opened else 'no'}")
    print("values_printed=no")


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
    parser.add_argument(
        "--write-authorization-url",
        action="store_true",
        help="Write the raw authorization URL to a 0600 file under target/ntb_marimo_console/.state/.",
    )
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the raw authorization URL in the default browser without printing it.",
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(env)
        authorization_url = build_authorization_url(config)
        authorization_url_path = None
        if args.write_authorization_url:
            authorization_url_path = write_authorization_url_file(config, authorization_url)
        browser_opened = False
        if args.open_browser:
            if not config.oauth_live:
                raise OAuthPrepError("--open-browser requires SCHWAB_OAUTH_LIVE=true.")
            browser_opened = webbrowser.open(authorization_url)
        print_safe_summary(
            config,
            authorization_url_written=authorization_url_path is not None,
            authorization_url_path=authorization_url_path,
            browser_opened=browser_opened,
        )

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
            raise OAuthPrepError("Token response missing required token fields.")
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
            summary = summarize_token_endpoint_error(exc)
            print(f"token_error_present={summary.token_error_present}")
            print(f"token_error_code={summary.token_error_code}")
            print(f"token_error_description_present={summary.token_error_description_present}")
            print(f"token_error_description_class={summary.token_error_description_class}")
            print(f"response_content_type={summary.response_content_type}")
            print(f"response_content_encoding={summary.response_content_encoding}")
            print(f"response_decode_status={summary.response_decode_status}")
            print(f"retryable={summary.retryable}")
            print(f"blocking_reason={summary.blocking_reason}")
            print("values_printed=no")
            if exc.reason_class:
                print(f"reason_class={exc.reason_class}")
            safe_reason = _safe_reason(exc.reason)
            if safe_reason:
                print(f"reason={safe_reason}")
        else:
            print(f"error={_sanitize_diagnostic_text(exc)}")
        return 1


if __name__ == "__main__":
    sys.exit(run())
