from __future__ import annotations

import builtins
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import ntb_marimo_console.operator_cockpit_launch as launch_mod
from ntb_marimo_console.operator_cockpit_launch import (
    APP_ENTRYPOINT_RELATIVE,
    DEFAULT_OPERATOR_RUNTIME_MODE,
    LIVE_OPERATOR_RUNTIME_MODE,
    REQUIRED_LIVE_ENV_KEYS,
    build_live_launch_environment,
    build_live_operator_cockpit_launch_smoke,
    build_marimo_launch_command,
    build_operator_cockpit_launch_smoke,
    build_safe_launch_environment,
    format_live_marimo_launch_command,
    format_marimo_launch_command,
    launch_operator_cockpit,
    launch_operator_cockpit_live,
    live_launch_prerequisites,
    main,
    render_live_operator_cockpit_launch_smoke,
    render_operator_cockpit_launch_smoke,
)


def _live_opt_in_env() -> dict[str, str]:
    """Minimal explicit-opt-in env. Credential values are placeholders only;
    nothing here is read as a file or surfaced anywhere."""
    return {
        "PATH": os.environ.get("PATH", ""),
        "NTB_OPERATOR_RUNTIME_MODE": "OPERATOR_LIVE_RUNTIME",
        "SCHWAB_APP_KEY": "placeholder-app-key-not-a-real-secret",
        "SCHWAB_APP_SECRET": "placeholder-app-secret-not-a-real-secret",
        "SCHWAB_TOKEN_PATH": ".state/schwab/token.json",
    }


_FORBIDDEN_OUTPUT_FRAGMENTS = (
    "placeholder-app-key-not-a-real-secret",
    "placeholder-app-secret-not-a-real-secret",
    "Authorization",
    "Bearer",
    "access_token",
    "refresh_token",
    "client_secret",
    "api_key",
    "customerId",
    "correlId",
    "accountId",
    "wss://",
    "streamer-api",
    ".state/secrets",
    "schwab_live.env",
    "QUERY_READY",
)
_FORBIDDEN_AUTOMATION_TOKENS = (
    "order",
    "broker",
    "execution",
    "account",
    "fill",
    "p&l",
    "pnl",
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


# ---------------------------------------------------------------------------
# Explicit opt-in live-observation cockpit launch path
# ---------------------------------------------------------------------------


def test_default_launch_remains_non_live_with_live_path_present() -> None:
    # The new live path must not change default launch behavior.
    env = build_safe_launch_environment(_live_opt_in_env(), project_root=PROJECT_ROOT)
    assert env["NTB_OPERATOR_RUNTIME_MODE"] == DEFAULT_OPERATOR_RUNTIME_MODE
    assert env["NTB_OPERATOR_LIVE_RUNTIME"] == "0"
    assert env["NTB_MARKET_DATA_PROVIDER"] == "disabled"
    assert "SCHWAB_APP_KEY" not in env
    assert "SCHWAB_TOKEN_PATH" not in env

    safe_command = format_marimo_launch_command(project_root=PROJECT_ROOT)
    assert "NTB_OPERATOR_RUNTIME_MODE=SAFE_NON_LIVE" in safe_command
    assert "NTB_OPERATOR_RUNTIME_MODE=OPERATOR_LIVE_RUNTIME" not in safe_command
    assert "NTB_MARKET_DATA_PROVIDER=schwab" not in safe_command


def test_live_launch_prerequisites_require_explicit_opt_in() -> None:
    missing = live_launch_prerequisites({"PATH": os.environ.get("PATH", "")})
    assert missing.ready is False
    assert missing.explicit_runtime_mode_opt_in is False
    assert missing.required_env_keys_present is False
    assert "operator_live_runtime_opt_in_required" in missing.blocking_reasons
    assert "required_live_env_keys_missing" in missing.blocking_reasons

    # Credential keys present but no explicit runtime opt-in: still not ready.
    keys_only = live_launch_prerequisites(
        {key: "placeholder" for key in REQUIRED_LIVE_ENV_KEYS}
    )
    assert keys_only.ready is False
    assert keys_only.required_env_keys_present is True
    assert keys_only.explicit_runtime_mode_opt_in is False
    assert "operator_live_runtime_opt_in_required" in keys_only.blocking_reasons


def test_live_launch_prerequisites_ready_with_explicit_opt_in_and_keys() -> None:
    ready = live_launch_prerequisites(_live_opt_in_env())
    assert ready.ready is True
    assert ready.explicit_runtime_mode_opt_in is True
    assert ready.required_env_keys_present is True
    assert ready.blocking_reasons == ()


def test_live_launch_refuses_fail_closed_and_never_falls_back_to_fixture(monkeypatch) -> None:
    subprocess_calls: list[object] = []
    fixture_calls: list[object] = []

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        subprocess_calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0)

    def fake_fixture_launch(*args, **kwargs):  # type: ignore[no-untyped-def]
        fixture_calls.append((args, kwargs))
        return 0

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(launch_mod, "launch_operator_cockpit", fake_fixture_launch)

    result = launch_operator_cockpit_live(
        base_env={"PATH": os.environ.get("PATH", "")},
        project_root=PROJECT_ROOT,
        python_executable="python",
    )

    assert result == 2
    assert subprocess_calls == []
    assert fixture_calls == []


def test_live_launch_invokes_marimo_with_live_env_when_prerequisites_met(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    fixture_calls: list[object] = []

    def fake_run(command, *, cwd, env, check):  # type: ignore[no-untyped-def]
        calls.append({"command": command, "cwd": cwd, "env": env, "check": check})
        return subprocess.CompletedProcess(command, 0)

    def fake_fixture_launch(*args, **kwargs):  # type: ignore[no-untyped-def]
        fixture_calls.append((args, kwargs))
        return 0

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(launch_mod, "launch_operator_cockpit", fake_fixture_launch)

    result = launch_operator_cockpit_live(
        base_env=_live_opt_in_env(),
        project_root=PROJECT_ROOT,
        python_executable="python",
    )

    assert result == 0
    assert fixture_calls == []
    assert len(calls) == 1
    assert calls[0]["command"] == (
        "python",
        "-m",
        "marimo",
        "run",
        "src/ntb_marimo_console/operator_console_app.py",
    )
    env = calls[0]["env"]
    assert isinstance(env, dict)
    assert env["NTB_OPERATOR_RUNTIME_MODE"] == LIVE_OPERATOR_RUNTIME_MODE
    assert env["NTB_OPERATOR_LIVE_RUNTIME"] == "1"
    assert env["NTB_MARKET_DATA_PROVIDER"] == "schwab"
    # The runtime reads token material internally; the launcher must keep the
    # credential env keys for the child process but never print them.
    assert env["SCHWAB_APP_KEY"] == "placeholder-app-key-not-a-real-secret"


def test_live_launch_failure_does_not_fall_back_to_fixture(monkeypatch) -> None:
    fixture_calls: list[object] = []

    def fake_run(command, *, cwd, env, check):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(command, 3)

    def fake_fixture_launch(*args, **kwargs):  # type: ignore[no-untyped-def]
        fixture_calls.append((args, kwargs))
        return 0

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(launch_mod, "launch_operator_cockpit", fake_fixture_launch)

    result = launch_operator_cockpit_live(
        base_env=_live_opt_in_env(),
        project_root=PROJECT_ROOT,
        python_executable="python",
    )

    assert result == 3
    assert fixture_calls == []


def test_live_launch_environment_keeps_credentials_but_outputs_never_print_them() -> None:
    secret_env = dict(_live_opt_in_env())
    secret_env["SCHWAB_APP_KEY"] = "placeholder-app-key-not-a-real-secret"
    live_env = build_live_launch_environment(secret_env, project_root=PROJECT_ROOT)

    # Child process keeps the credential keys; runtime reads token internally.
    assert live_env["SCHWAB_APP_KEY"] == "placeholder-app-key-not-a-real-secret"
    assert live_env["NTB_OPERATOR_RUNTIME_MODE"] == LIVE_OPERATOR_RUNTIME_MODE
    assert live_env["NTB_OPERATOR_LIVE_RUNTIME"] == "1"
    assert live_env["NTB_MARKET_DATA_PROVIDER"] == "schwab"

    printed = format_live_marimo_launch_command(project_root=PROJECT_ROOT)
    for fragment in _FORBIDDEN_OUTPUT_FRAGMENTS:
        assert fragment not in printed
    assert "NTB_OPERATOR_RUNTIME_MODE=OPERATOR_LIVE_RUNTIME" in printed
    assert "NTB_MARKET_DATA_PROVIDER=schwab" in printed
    assert "marimo run src/ntb_marimo_console/operator_console_app.py" in printed


def test_live_dry_run_smoke_fails_closed_without_opt_in() -> None:
    smoke = build_live_operator_cockpit_launch_smoke(
        project_root=PROJECT_ROOT,
        base_env={"PATH": os.environ.get("PATH", "")},
        python_executable="python",
    )

    assert smoke.smoke_passed is False
    assert smoke.prerequisites_ready is False
    assert smoke.app_importable is False
    assert smoke.live_runtime_fail_closed is True
    assert smoke.default_launch_live is False
    assert "operator_live_runtime_opt_in_required" in smoke.blocking_reasons

    text = render_live_operator_cockpit_launch_smoke(smoke)
    assert "Live-observation cockpit launch smoke: FAIL" in text
    assert "prerequisites_ready=no" in text
    assert "fixture_fallback_after_live_failure=no" in text


def test_live_dry_run_smoke_is_observation_only_and_final_target_only() -> None:
    smoke = build_live_operator_cockpit_launch_smoke(
        project_root=PROJECT_ROOT,
        base_env=_live_opt_in_env(),
        python_executable="python",
    )

    assert smoke.prerequisites_ready is True
    assert smoke.app_importable is True
    assert smoke.primary_cockpit_present is True
    assert smoke.operator_runtime_mode == LIVE_OPERATOR_RUNTIME_MODE
    # No operator-owned manager is registered into the Marimo process yet, so
    # the live runtime status is fail-closed observation-only by design.
    assert smoke.live_runtime_fail_closed is True
    assert smoke.operator_runtime_status != "QUERY_READY"
    assert smoke.default_launch_live is False
    assert smoke.supported_contracts == ("ES", "NQ", "CL", "6E", "MGC")
    assert smoke.mgc_label == "Micro Gold"
    assert smoke.mgc_label != "GC"
    assert smoke.smoke_passed is True


def test_live_dry_run_smoke_text_is_sanitized_final_target_only_and_no_query_ready() -> None:
    smoke = build_live_operator_cockpit_launch_smoke(
        project_root=PROJECT_ROOT,
        base_env=_live_opt_in_env(),
        python_executable="python",
    )
    text = render_live_operator_cockpit_launch_smoke(smoke)

    assert "Live-observation cockpit launch smoke: PASS" in text
    assert "supported_contracts=ES,NQ,CL,6E,MGC" in text
    assert "MGC_label=Micro Gold" in text
    assert "operator_runtime_mode=OPERATOR_LIVE_RUNTIME" in text
    assert "ZN" not in text
    assert " GC " not in text
    for fragment in _FORBIDDEN_OUTPUT_FRAGMENTS:
        assert fragment not in text, f"live smoke text must not surface {fragment!r}"
    lowered = text.lower()
    for token in _FORBIDDEN_AUTOMATION_TOKENS:
        assert token not in lowered, f"live smoke text must not surface automation token {token!r}"


def test_live_smoke_to_dict_exposes_no_broker_order_execution_or_pnl_fields() -> None:
    smoke = build_live_operator_cockpit_launch_smoke(
        project_root=PROJECT_ROOT,
        base_env=_live_opt_in_env(),
        python_executable="python",
    )
    keys = " ".join(smoke.to_dict().keys()).lower()
    for token in _FORBIDDEN_AUTOMATION_TOKENS:
        assert token not in keys


def test_live_dry_run_smoke_does_not_read_secret_or_token_paths(monkeypatch) -> None:
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

    smoke = build_live_operator_cockpit_launch_smoke(
        project_root=PROJECT_ROOT,
        base_env=_live_opt_in_env(),
        python_executable="python",
    )

    assert smoke.prerequisites_ready is True
    assert smoke.smoke_passed is True


def test_main_default_dry_run_remains_non_live(capsys) -> None:
    exit_code = main(["--dry-run"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "Fixture cockpit launch smoke: PASS" in out
    assert "operator_runtime=SAFE_NON_LIVE" in out
    assert "NTB_OPERATOR_RUNTIME_MODE=OPERATOR_LIVE_RUNTIME" not in out
    assert "NTB_MARKET_DATA_PROVIDER=schwab" not in out


def test_main_live_dry_run_without_opt_in_fails_closed(capsys, monkeypatch) -> None:
    for key in ("NTB_OPERATOR_RUNTIME_MODE", "NTB_OPERATOR_LIVE_RUNTIME"):
        monkeypatch.delenv(key, raising=False)
    for key in REQUIRED_LIVE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    exit_code = main(["--live", "--dry-run"])
    out = capsys.readouterr().out

    assert exit_code == 1
    assert "Live-observation cockpit launch smoke: FAIL" in out
    assert "prerequisites_ready=no" in out
    assert "fixture_fallback_after_live_failure=no" in out


def test_main_live_print_command_is_secret_free(capsys) -> None:
    exit_code = main(["--live", "--print-command"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "NTB_OPERATOR_RUNTIME_MODE=OPERATOR_LIVE_RUNTIME" in out
    assert "marimo run src/ntb_marimo_console/operator_console_app.py" in out
    for fragment in _FORBIDDEN_OUTPUT_FRAGMENTS:
        assert fragment not in out


# ---------------------------------------------------------------------------
# Valid Marimo launch target recognition
# ---------------------------------------------------------------------------


def test_operator_app_entrypoint_is_a_marimo_recognized_notebook() -> None:
    """`marimo run` rejected the prior app module as "not a marimo notebook".

    The default and live launch commands both target the same file, so it must
    statically parse as a valid marimo notebook with cells — not merely import
    as a Python module.
    """
    from marimo._ast.load import load_app
    from marimo._ast.parse import parse_notebook

    target = PROJECT_ROOT / APP_ENTRYPOINT_RELATIVE
    notebook = parse_notebook(target.read_text(encoding="utf-8"), str(target))
    assert notebook is not None
    assert notebook.valid is True
    assert notebook.violations == []

    app = load_app(str(target))
    assert app is not None
    cell_names = list(app._cell_manager.names())
    assert cell_names, "marimo notebook target must define at least one cell"


def test_default_and_live_launch_commands_share_the_valid_notebook_target() -> None:
    from marimo._ast.load import load_app

    default_command = build_marimo_launch_command(
        python_executable="python", project_root=PROJECT_ROOT
    )
    target = default_command[-1]
    assert target == APP_ENTRYPOINT_RELATIVE.as_posix()

    safe_text = format_marimo_launch_command(project_root=PROJECT_ROOT)
    live_text = format_live_marimo_launch_command(project_root=PROJECT_ROOT)
    assert f"marimo run {target}" in safe_text
    assert f"marimo run {target}" in live_text

    # The shared target loads as a real marimo notebook.
    assert load_app(str(PROJECT_ROOT / target)) is not None


def test_operator_app_target_imports_without_starting_live_or_reading_secrets(
    monkeypatch,
) -> None:
    """Importing / statically loading the notebook target must not start the
    live runtime, log in to Schwab, or touch secret/token paths."""
    import importlib

    original_read_text = Path.read_text

    def guarded_read_text(self: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
        text = str(self)
        assert ".state/secrets" not in text
        assert "schwab_live.env" not in text
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    app_mod = importlib.import_module("ntb_marimo_console.operator_console_app")
    importlib.reload(app_mod)

    assert getattr(app_mod, "app", None) is not None
    # Helper functions remain importable for the cockpit cells and tests.
    assert callable(app_mod.optional_thesis_reference_from_form)
    assert callable(app_mod.resolve_cockpit_runtime_snapshot_producer)

    from marimo._ast.load import load_app

    target = PROJECT_ROOT / APP_ENTRYPOINT_RELATIVE
    assert load_app(str(target)) is not None
