from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from ninjatradebuilder.cli import run_cli as run_runtime_cli
from ninjatradebuilder.packet_compiler.cli import run_cli as run_compile_cli
from ninjatradebuilder.packet_compiler.sixe import compile_six_e_packet
from ninjatradebuilder.validation import validate_historical_packet

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "compiler"


def _load_json(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def _compile_packet(
    historical_input: dict | None = None,
    overlay: dict | None = None,
    extension_input: dict | None = None,
    *,
    compiled_at_iso: str | None = None,
):
    return compile_six_e_packet(
        _load_json("6e_historical_input.valid.json") if historical_input is None else historical_input,
        _load_json("6e_overlay.assisted.valid.json") if overlay is None else overlay,
        _load_json("6e_extension.valid.json") if extension_input is None else extension_input,
        compiled_at_iso=compiled_at_iso,
    )


def _valid_contract_analysis(contract: str) -> dict:
    return {
        "$schema": "contract_analysis_v1",
        "stage": "contract_market_read",
        "contract": contract,
        "timestamp": "2026-01-14T14:06:00Z",
        "market_regime": "range_bound",
        "directional_bias": "bullish",
        "key_levels": {
            "support_levels": [1.0899],
            "resistance_levels": [1.0914],
            "pivot_level": 1.09065,
        },
        "evidence_score": 5,
        "confidence_band": "MEDIUM",
        "value_context": {
            "relative_to_prior_value_area": "inside",
            "relative_to_current_developing_value": "inside_value",
            "relative_to_vwap": "above",
            "relative_to_prior_day_range": "inside",
        },
        "structural_notes": "6E fixture-backed compile path remains balanced.",
        "outcome": "NO_TRADE",
        "conflicting_signals": ["session remains balanced near London high"],
        "assumptions": [],
    }


def test_compile_six_e_packet_builds_valid_packet() -> None:
    artifact = _compile_packet(compiled_at_iso="2026-01-14T14:10:00Z")

    packet = artifact.packet
    validated = validate_historical_packet(packet.model_dump(by_alias=True, mode="json"))

    assert validated.market_packet.contract == "6E"
    assert validated.market_packet.current_price == 1.09125
    assert validated.market_packet.current_session_poc == 1.09065
    assert validated.market_packet.opening_type == "Open-Auction"
    assert validated.contract_specific_extension.dxy_context == "weakening"
    assert validated.contract_specific_extension.europe_initiative_status == "Europe drove higher"
    assert validated.contract_specific_extension.asia_high_low.high == 1.0892
    assert validated.contract_specific_extension.asia_high_low.low == 1.0876
    assert validated.contract_specific_extension.london_high_low.high == 1.0914
    assert validated.contract_specific_extension.london_high_low.low == 1.0886
    assert validated.contract_specific_extension.ny_high_low_so_far.high == 1.0916
    assert validated.contract_specific_extension.ny_high_low_so_far.low == 1.0898
    assert (
        artifact.provenance["field_provenance"]["market_packet.current_price"]["source"]
        == "historical_input"
    )
    assert (
        artifact.provenance["field_provenance"]["contract_specific_extension.asia_high_low"]["source"]
        == "derived_from_historical_input"
    )
    assert (
        artifact.provenance["field_provenance"]["contract_specific_extension.london_high_low"]["field"]
        == "london_bars"
    )
    assert (
        artifact.provenance["field_provenance"]["contract_specific_extension.ny_high_low_so_far"]["field"]
        == "ny_bars"
    )
    assert (
        artifact.provenance["field_provenance"]["contract_specific_extension.dxy_context"]["source"]
        == "upstream_extension"
    )
    assert artifact.provenance["derived_features"]["asia_high_low"] == {"high": 1.0892, "low": 1.0876}
    assert artifact.provenance["derived_features"]["london_high_low"] == {"high": 1.0914, "low": 1.0886}
    assert artifact.provenance["derived_features"]["ny_high_low_so_far"] == {
        "high": 1.0916,
        "low": 1.0898,
    }


def test_compile_six_e_packet_accepts_minimal_overlay_fixture() -> None:
    overlay = _load_json("6e_overlay.assisted.valid.json")

    assert set(overlay.keys()) == {"contract", "challenge_state", "opening_type"}


def test_compile_six_e_packet_accepts_minimal_extension_fixture() -> None:
    extension = _load_json("6e_extension.valid.json")

    assert set(extension.keys()) == {"contract", "dxy_context", "europe_initiative_status"}


def test_compile_six_e_packet_fails_closed_when_challenge_state_is_missing() -> None:
    overlay = _load_json("6e_overlay.assisted.valid.json")
    overlay.pop("challenge_state")

    with pytest.raises(ValueError, match="challenge_state"):
        _compile_packet(overlay=overlay)


def test_compile_six_e_packet_fails_closed_when_opening_type_is_missing() -> None:
    overlay = _load_json("6e_overlay.assisted.valid.json")
    overlay.pop("opening_type")

    with pytest.raises(ValueError, match="opening_type"):
        _compile_packet(overlay=overlay)


def test_compile_six_e_packet_does_not_auto_derive_opening_type() -> None:
    overlay = _load_json("6e_overlay.assisted.valid.json")
    overlay.pop("opening_type")
    historical_input = _load_json("6e_historical_input.valid.json")
    historical_input["session_open"] = 1.0887
    historical_input["current_price"] = 1.0919

    with pytest.raises(ValueError, match="opening_type"):
        _compile_packet(historical_input=historical_input, overlay=overlay)


def test_compile_six_e_packet_fails_closed_on_malformed_historical_input() -> None:
    historical_input = _load_json("6e_historical_input.valid.json")
    historical_input["current_session_val"] = 1.0911
    historical_input["current_session_poc"] = 1.0909
    historical_input["current_session_vah"] = 1.0907

    with pytest.raises(ValueError, match="current session profile levels"):
        _compile_packet(historical_input=historical_input)


def test_compile_six_e_packet_fails_closed_when_asia_bars_are_missing() -> None:
    historical_input = _load_json("6e_historical_input.valid.json")
    historical_input.pop("asia_bars")

    with pytest.raises(ValueError, match="asia_bars"):
        _compile_packet(historical_input=historical_input)


def test_compile_six_e_packet_fails_closed_on_unordered_session_segments() -> None:
    historical_input = _load_json("6e_historical_input.valid.json")
    historical_input["london_bars"][0]["timestamp"] = "2026-01-14T01:30:00Z"

    with pytest.raises(ValueError, match="Asia before London"):
        _compile_packet(historical_input=historical_input)


def test_compile_six_e_packet_fails_closed_on_malformed_extension_input() -> None:
    extension_input = _load_json("6e_extension.valid.json")
    extension_input["europe_initiative_status"] = ""

    with pytest.raises(ValueError, match="at least 1 character"):
        _compile_packet(extension_input=extension_input)


def test_compile_six_e_packet_does_not_auto_derive_dxy_context() -> None:
    extension_input = _load_json("6e_extension.valid.json")
    extension_input.pop("dxy_context")

    with pytest.raises(ValueError, match="dxy_context"):
        _compile_packet(extension_input=extension_input)


def test_compile_six_e_packet_does_not_auto_derive_europe_initiative_status() -> None:
    extension_input = _load_json("6e_extension.valid.json")
    extension_input.pop("europe_initiative_status")

    with pytest.raises(ValueError, match="europe_initiative_status"):
        _compile_packet(extension_input=extension_input)


def test_compiler_cli_writes_six_e_packet_and_provenance(tmp_path: Path) -> None:
    output_path = tmp_path / "6e.packet.json"
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = run_compile_cli(
        [
            "--contract",
            "6E",
            "--historical-input",
            str(FIXTURES_DIR / "6e_historical_input.valid.json"),
            "--overlay",
            str(FIXTURES_DIR / "6e_overlay.assisted.valid.json"),
            "--extension-input",
            str(FIXTURES_DIR / "6e_extension.valid.json"),
            "--output",
            str(output_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    summary = json.loads(stdout.getvalue())
    assert summary["contract"] == "6E"
    assert output_path.is_file()
    assert output_path.with_suffix(".provenance.json").is_file()
    validate_historical_packet(json.loads(output_path.read_text()))


def test_compiled_six_e_packet_runs_through_existing_cli(monkeypatch, tmp_path: Path) -> None:
    output_path = tmp_path / "6e.packet.json"
    compile_exit_code = run_compile_cli(
        [
            "--contract",
            "6E",
            "--historical-input",
            str(FIXTURES_DIR / "6e_historical_input.valid.json"),
            "--overlay",
            str(FIXTURES_DIR / "6e_overlay.assisted.valid.json"),
            "--extension-input",
            str(FIXTURES_DIR / "6e_extension.valid.json"),
            "--output",
            str(output_path),
        ]
    )

    assert compile_exit_code == 0
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    stdout = io.StringIO()
    stderr = io.StringIO()

    class FakeGeminiAdapter:
        def __init__(self, *, client, model, timeout_seconds=None, max_retries=0):
            self.client = client

        def generate_structured(self, request):
            return _valid_contract_analysis("6E")

    monkeypatch.setattr("ninjatradebuilder.cli.GeminiResponsesAdapter", FakeGeminiAdapter)

    exit_code = run_runtime_cli(
        [
            "--packet",
            str(output_path),
        ],
        stdout=stdout,
        stderr=stderr,
        client_factory=lambda config: config,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    summary = json.loads(stdout.getvalue())
    assert summary["contract"] == "6E"
    assert summary["termination_stage"] == "contract_market_read"
    assert summary["final_decision"] == "NO_TRADE"
