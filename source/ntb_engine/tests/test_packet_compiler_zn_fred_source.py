from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ninjatradebuilder.packet_compiler.cli import run_cli as run_compile_cli
from ninjatradebuilder.packet_compiler.sources import (
    FREDCash10YYieldSource,
    JsonZNFredCash10YYieldRequestSource,
    PacketCompilerSourceError,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "compiler"


def _load_request_fixture() -> Path:
    return FIXTURES_DIR / "zn_fred_cash_10y_yield_request.valid.json"


def test_json_zn_fred_cash_10y_yield_request_source_loads_valid_request() -> None:
    request = JsonZNFredCash10YYieldRequestSource(_load_request_fixture()).load_zn_request()

    assert request.contract == "ZN"
    assert request.observation_date.isoformat() == "2026-01-14"
    assert request.series_id == "DGS10"


def test_fred_cash_10y_yield_source_maps_valid_yield(monkeypatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    request = JsonZNFredCash10YYieldRequestSource(_load_request_fixture()).load_zn_request()
    source = FREDCash10YYieldSource(
        request=request,
        fetch_json=lambda url: {
            "observations": [{"date": "2026-01-14", "value": "4.18"}],
        },
    )

    result = source.load_zn_cash_10y_yield()

    assert result.contract == "ZN"
    assert result.cash_10y_yield == 4.18


def test_fred_cash_10y_yield_source_fails_closed_when_api_key_is_missing(monkeypatch) -> None:
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    request = JsonZNFredCash10YYieldRequestSource(_load_request_fixture()).load_zn_request()
    source = FREDCash10YYieldSource(
        request=request,
        fetch_json=lambda url: {"observations": [{"date": "2026-01-14", "value": "4.18"}]},
    )

    with pytest.raises(PacketCompilerSourceError, match="FRED_API_KEY"):
        source.load_zn_cash_10y_yield()


def test_fred_cash_10y_yield_source_fails_closed_on_malformed_response(monkeypatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    request = JsonZNFredCash10YYieldRequestSource(_load_request_fixture()).load_zn_request()
    source = FREDCash10YYieldSource(
        request=request,
        fetch_json=lambda url: {"observations": [{"value": "4.18"}]},
    )

    with pytest.raises(PacketCompilerSourceError, match="observation_date"):
        source.load_zn_cash_10y_yield()


def test_fred_cash_10y_yield_source_fails_closed_on_missing_or_ambiguous_value(monkeypatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    request = JsonZNFredCash10YYieldRequestSource(_load_request_fixture()).load_zn_request()

    missing_source = FREDCash10YYieldSource(
        request=request,
        fetch_json=lambda url: {"observations": []},
    )
    with pytest.raises(PacketCompilerSourceError, match="exactly one observation"):
        missing_source.load_zn_cash_10y_yield()

    ambiguous_source = FREDCash10YYieldSource(
        request=request,
        fetch_json=lambda url: {
            "observations": [
                {"date": "2026-01-14", "value": "4.18"},
                {"date": "2026-01-14", "value": "4.19"},
            ]
        },
    )
    with pytest.raises(PacketCompilerSourceError, match="exactly one observation"):
        ambiguous_source.load_zn_cash_10y_yield()


def test_json_zn_fred_cash_10y_yield_request_source_fails_closed_on_unsupported_request_input(
    tmp_path: Path,
) -> None:
    bad_request_path = tmp_path / "bad-zn-fred-request.json"
    bad_request_path.write_text(
        json.dumps(
            {
                "contract": "ZN",
                "observation_date": "2026-01-14",
                "series_id": "",
            }
        )
    )

    with pytest.raises(
        PacketCompilerSourceError,
        match="ZN FRED cash_10y_yield request payload was invalid",
    ):
        JsonZNFredCash10YYieldRequestSource(bad_request_path).load_zn_request()


def test_compiler_cli_accepts_zn_fred_cash_10y_yield_branch_with_mocked_source(
    monkeypatch, tmp_path: Path
) -> None:
    class FakeFREDCash10YYieldSource:
        def __init__(self, request):
            self.request = request

        def load_zn_cash_10y_yield(self):
            return SimpleNamespace(contract="ZN", cash_10y_yield=4.18)

    monkeypatch.setattr(
        "ninjatradebuilder.packet_compiler.cli.FREDCash10YYieldSource",
        FakeFREDCash10YYieldSource,
    )
    stdout = io.StringIO()
    stderr = io.StringIO()
    output_path = tmp_path / "zn-fred.packet.json"

    exit_code = run_compile_cli(
        [
            "--contract",
            "ZN",
            "--historical-input",
            str(FIXTURES_DIR / "zn_historical_input.valid.json"),
            "--overlay",
            str(FIXTURES_DIR / "zn_overlay.assisted.valid.json"),
            "--extension-input",
            str(FIXTURES_DIR / "zn_extension.valid.json"),
            "--cash-10y-yield-source",
            "fred",
            "--fred-request",
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
    assert summary["contract"] == "ZN"
    assert output_path.is_file()
    packet = json.loads(output_path.read_text())
    assert packet["contract_specific_extension"]["cash_10y_yield"] == 4.18
