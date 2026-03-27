from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from ninjatradebuilder.packet_compiler.cli import run_cli as run_compile_cli
from ninjatradebuilder.packet_compiler.models import CLEiaTimingRequest
from ninjatradebuilder.packet_compiler.sources import (
    EIAEiaTimingSource,
    JsonCLEiaTimingRequestSource,
    PacketCompilerSourceError,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "compiler"


def _load_request_fixture() -> Path:
    return FIXTURES_DIR / "cl_eia_request.valid.json"


def test_json_cl_eia_request_source_loads_valid_request() -> None:
    request = JsonCLEiaTimingRequestSource(_load_request_fixture()).load_cl_request()

    assert request.contract == "CL"
    assert request.route == "petroleum/stoc/wstk/data"
    assert request.release_week_ending.isoformat() == "2026-01-09"
    assert request.facets == {"series": ["WCESTUS1"]}


def test_eia_eia_timing_source_maps_scheduled_status(monkeypatch) -> None:
    monkeypatch.setenv("EIA_API_KEY", "test-key")
    request = JsonCLEiaTimingRequestSource(_load_request_fixture()).load_cl_request()
    source = EIAEiaTimingSource(
        request=request,
        fetch_json=lambda url: {"response": {"data": []}},
    )

    eia_timing = source.load_cl_eia_timing()

    assert eia_timing["status"] == "scheduled"
    assert eia_timing["scheduled_time"] == request.scheduled_release_time
    assert eia_timing["minutes_until"] == 85


def test_eia_eia_timing_source_maps_released_status(monkeypatch) -> None:
    monkeypatch.setenv("EIA_API_KEY", "test-key")
    request = CLEiaTimingRequest.model_validate(
        {
            **JsonCLEiaTimingRequestSource(_load_request_fixture()).load_cl_request().model_dump(
                mode="json"
            ),
            "current_session_timestamp": "2026-01-14T16:00:00Z",
        }
    )
    source = EIAEiaTimingSource(
        request=request,
        fetch_json=lambda url: {"response": {"data": [{"period": "2026-01-09", "value": 1}]}},
    )

    eia_timing = source.load_cl_eia_timing()

    assert eia_timing["status"] == "released"
    assert eia_timing["scheduled_time"] == request.scheduled_release_time
    assert eia_timing["minutes_since"] == 30


def test_eia_eia_timing_source_fails_closed_when_api_key_is_missing(monkeypatch) -> None:
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    request = JsonCLEiaTimingRequestSource(_load_request_fixture()).load_cl_request()
    source = EIAEiaTimingSource(
        request=request,
        fetch_json=lambda url: {"response": {"data": []}},
    )

    with pytest.raises(PacketCompilerSourceError, match="EIA_API_KEY"):
        source.load_cl_eia_timing()


def test_eia_eia_timing_source_fails_closed_on_malformed_provider_response(monkeypatch) -> None:
    monkeypatch.setenv("EIA_API_KEY", "test-key")
    request = JsonCLEiaTimingRequestSource(_load_request_fixture()).load_cl_request()
    source = EIAEiaTimingSource(
        request=request,
        fetch_json=lambda url: {"response": {"data": [{"value": 1}]}},
    )

    with pytest.raises(PacketCompilerSourceError, match="period"):
        source.load_cl_eia_timing()


def test_eia_eia_timing_source_fails_closed_on_ambiguous_release_interpretation(monkeypatch) -> None:
    monkeypatch.setenv("EIA_API_KEY", "test-key")
    request = JsonCLEiaTimingRequestSource(_load_request_fixture()).load_cl_request()
    source = EIAEiaTimingSource(
        request=request,
        fetch_json=lambda url: {"response": {"data": [{"period": "2026-01-09", "value": 1}]}},
    )

    with pytest.raises(PacketCompilerSourceError, match="before the scheduled_release_time"):
        source.load_cl_eia_timing()


def test_json_cl_eia_request_source_fails_closed_on_unsupported_request_input(tmp_path: Path) -> None:
    bad_request_path = tmp_path / "bad-cl-eia-request.json"
    bad_request_path.write_text(
        json.dumps(
            {
                "contract": "CL",
                "current_session_timestamp": "2026-01-13T14:05:00Z",
                "scheduled_release_time": "2026-01-14T15:30:00Z",
                "release_week_ending": "2026-01-09",
                "route": "petroleum/stoc/wstk/data",
                "facets": {"series": ["WCESTUS1"]},
            }
        )
    )

    with pytest.raises(PacketCompilerSourceError, match="CL EIA timing request payload was invalid"):
        JsonCLEiaTimingRequestSource(bad_request_path).load_cl_request()


def test_compiler_cli_accepts_cl_eia_branch_with_mocked_source(monkeypatch, tmp_path: Path) -> None:
    class FakeEIAEiaTimingSource:
        def __init__(self, request):
            self.request = request

        def load_cl_eia_timing(self):
            return {
                "status": "scheduled",
                "scheduled_time": "2026-01-14T15:30:00Z",
                "minutes_until": 85,
            }

    monkeypatch.setattr(
        "ninjatradebuilder.packet_compiler.cli.EIAEiaTimingSource",
        FakeEIAEiaTimingSource,
    )
    stdout = io.StringIO()
    stderr = io.StringIO()
    output_path = tmp_path / "cl-eia.packet.json"

    exit_code = run_compile_cli(
        [
            "--contract",
            "CL",
            "--historical-input",
            str(FIXTURES_DIR / "cl_historical_input.valid.json"),
            "--overlay",
            str(FIXTURES_DIR / "cl_overlay.assisted.valid.json"),
            "--extension-input",
            str(FIXTURES_DIR / "cl_extension.valid.json"),
            "--eia-source",
            "eia",
            "--eia-request",
            str(_load_request_fixture()),
            "--output",
            str(output_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    summary = json.loads(stdout.getvalue())
    assert summary["contract"] == "CL"
    assert output_path.is_file()
