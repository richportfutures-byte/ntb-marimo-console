from __future__ import annotations

import builtins
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from ntb_marimo_console.operator_cockpit_launch import (
    APP_ENTRYPOINT_RELATIVE,
    DEFAULT_OPERATOR_RUNTIME_MODE,
    build_marimo_launch_command,
    build_operator_cockpit_launch_smoke,
    build_safe_launch_environment,
    format_marimo_launch_command,
    launch_operator_cockpit,
    render_operator_cockpit_launch_smoke,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "launch_operator_cockpit.py"


def test_safe_launch_helper_points_to_actual_operator_app() -> None:
    command = build_marimo_launch_command(
        python_executable="python",
        project_root=PROJECT_ROOT,
    )

    assert command == (
        "python",
        "-m",
        "marimo",
        "run",
        APP_ENTRYPOINT_RELATIVE.as_posix(),
    )
    assert (PROJECT_ROOT / APP_ENTRYPOINT_RELATIVE).is_file()


def test_safe_launch_environment_overrides_live_and_sensitive_values() -> None:
    env = build_safe_launch_environment(
        {
            "PATH": os.environ.get("PATH", ""),
            "SCHWAB_APP_KEY": "must-not-survive",
            "SCHWAB_TOKEN_PATH": ".state/schwab/token.json",
            "NTB_OPERATOR_RUNTIME_MODE": "OPERATOR_LIVE_RUNTIME",
            "NTB_OPERATOR_LIVE_RUNTIME": "1",
            "NTB_CONSOLE_PROFILE": "preserved_es_phase1",
            "NTB_MARKET_DATA_PROVIDER": "schwab",
        },
        project_root=PROJECT_ROOT,
    )

    assert env["NTB_CONSOLE_MODE"] == "fixture_demo"
    assert env["NTB_CONSOLE_PROFILE"] == "fixture_es_demo"
    assert env["NTB_OPERATOR_RUNTIME_MODE"] == DEFAULT_OPERATOR_RUNTIME_MODE
    assert env["NTB_OPERATOR_LIVE_RUNTIME"] == "0"
    assert env["NTB_MARKET_DATA_PROVIDER"] == "disabled"
    assert "SCHWAB_APP_KEY" not in env
    assert "SCHWAB_TOKEN_PATH" not in env


def test_print_command_is_copy_pasteable_safe_marimo_launch() -> None:
    command = format_marimo_launch_command(
        python_executable="python",
        project_root=PROJECT_ROOT,
    )

    assert f"cd {PROJECT_ROOT}" in command
    assert "NTB_CONSOLE_MODE=fixture_demo" in command
    assert "NTB_CONSOLE_PROFILE=fixture_es_demo" in command
    assert "NTB_OPERATOR_RUNTIME_MODE=SAFE_NON_LIVE" in command
    assert "NTB_OPERATOR_LIVE_RUNTIME=0" in command
    assert "NTB_MARKET_DATA_PROVIDER=disabled" in command
    assert "python -m marimo run src/ntb_marimo_console/operator_console_app.py" in command
    assert "OPERATOR_LIVE_RUNTIME " not in command


def test_launch_helper_default_invokes_safe_marimo_command(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(command, *, cwd, env, check):  # type: ignore[no-untyped-def]
        calls.append({"command": command, "cwd": cwd, "env": env, "check": check})
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = launch_operator_cockpit(
        project_root=PROJECT_ROOT,
        python_executable="python",
    )

    assert result == 0
    assert calls == [
        {
            "command": (
                "python",
                "-m",
                "marimo",
                "run",
                "src/ntb_marimo_console/operator_console_app.py",
            ),
            "cwd": PROJECT_ROOT,
            "env": calls[0]["env"],
            "check": False,
        }
    ]
    env = calls[0]["env"]
    assert isinstance(env, dict)
    assert env["NTB_CONSOLE_MODE"] == "fixture_demo"
    assert env["NTB_CONSOLE_PROFILE"] == "fixture_es_demo"
    assert env["NTB_OPERATOR_RUNTIME_MODE"] == "SAFE_NON_LIVE"
    assert env["NTB_OPERATOR_LIVE_RUNTIME"] == "0"
    assert env["NTB_MARKET_DATA_PROVIDER"] == "disabled"


def test_dry_run_smoke_verifies_primary_fixture_cockpit() -> None:
    smoke = build_operator_cockpit_launch_smoke(
        project_root=PROJECT_ROOT,
        base_env={
            "PATH": os.environ.get("PATH", ""),
            "NTB_OPERATOR_RUNTIME_MODE": "OPERATOR_LIVE_RUNTIME",
            "NTB_OPERATOR_LIVE_RUNTIME": "1",
            "NTB_MARKET_DATA_PROVIDER": "schwab",
        },
        python_executable="python",
    )

    assert smoke.smoke_passed is True
    assert smoke.app_importable is True
    assert smoke.primary_cockpit_present is True
    assert smoke.mode == "fixture_demo"
    assert smoke.profile == "fixture_es_demo"
    assert smoke.operator_runtime_mode == "SAFE_NON_LIVE"
    assert smoke.market_data_provider == "disabled"
    assert smoke.live_credentials_required is False
    assert smoke.default_launch_live is False
    assert smoke.supported_contracts == ("ES", "NQ", "CL", "6E", "MGC")
    assert smoke.mgc_label == "Micro Gold"
    assert smoke.mgc_label != "GC"
    assert smoke.query_readiness_provenance_reflected is True


def test_dry_run_output_is_short_sanitized_and_final_target_only() -> None:
    smoke = build_operator_cockpit_launch_smoke(
        project_root=PROJECT_ROOT,
        python_executable="python",
    )
    text = render_operator_cockpit_launch_smoke(smoke)
    supported_line = next(
        line for line in text.splitlines() if line.startswith("supported_contracts=")
    )
    contract_tokens = [
        token
        for token in re.split(r"[^A-Z0-9]+", supported_line)
        if token in {"ES", "NQ", "CL", "6E", "MGC", "ZN", "GC"}
    ]

    assert "Fixture cockpit launch smoke: PASS" in text
    assert "supported_contracts=ES,NQ,CL,6E,MGC" in text
    assert contract_tokens == ["ES", "NQ", "CL", "6E", "MGC"]
    assert "MGC_label=Micro Gold" in text
    assert "query_readiness_provenance=reflected" in text
    for forbidden in (
        "1.125",
        "1.25",
        "OHLC",
        "raw streamer payload",
        "authorization",
        "client_secret",
        "api_key",
        "token_path",
        "account",
    ):
        assert forbidden.lower() not in text.lower()


def test_dry_run_does_not_read_secret_or_token_paths(monkeypatch) -> None:
    original_open = builtins.open
    original_read_text = Path.read_text

    def guarded_open(file, *args, **kwargs):  # type: ignore[no-untyped-def]
        text = str(file)
        assert ".state/secrets" not in text
        assert "schwab_live.env" not in text
        assert "token" not in text.lower()
        return original_open(file, *args, **kwargs)

    def guarded_read_text(self: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
        text = str(self)
        assert ".state/secrets" not in text
        assert "schwab_live.env" not in text
        assert "token" not in text.lower()
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    smoke = build_operator_cockpit_launch_smoke(project_root=PROJECT_ROOT)

    assert smoke.smoke_passed is True


def test_script_dry_run_runs_without_schwab_credentials() -> None:
    env = {
        key: value
        for key, value in os.environ.items()
        if "SCHWAB" not in key.upper() and "TOKEN" not in key.upper()
    }

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--dry-run"],
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )

    assert "Fixture cockpit launch smoke: PASS" in result.stdout
    assert "supported_contracts=ES,NQ,CL,6E,MGC" in result.stdout
    assert result.stderr == ""


def test_script_print_command_does_not_start_marimo() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--print-command"],
        cwd=PROJECT_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )

    assert "marimo run src/ntb_marimo_console/operator_console_app.py" in result.stdout
    assert "SAFE_NON_LIVE" in result.stdout
    assert result.stderr == ""


@pytest.mark.parametrize("forbidden", ("ZN", " GC "))
def test_smoke_text_does_not_render_excluded_contracts(forbidden: str) -> None:
    smoke = build_operator_cockpit_launch_smoke(project_root=PROJECT_ROOT)
    text = render_operator_cockpit_launch_smoke(smoke)

    assert forbidden not in text
