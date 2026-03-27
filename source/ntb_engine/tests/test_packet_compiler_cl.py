from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from ninjatradebuilder.cli import run_cli as run_runtime_cli
from ninjatradebuilder.packet_compiler.cl import compile_cl_packet
from ninjatradebuilder.packet_compiler.cli import run_cli as run_compile_cli
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
    return compile_cl_packet(
        _load_json("cl_historical_input.valid.json") if historical_input is None else historical_input,
        _load_json("cl_overlay.assisted.valid.json") if overlay is None else overlay,
        _load_json("cl_extension.valid.json") if extension_input is None else extension_input,
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
            "support_levels": [72.9],
            "resistance_levels": [73.5],
            "pivot_level": 73.08,
        },
        "evidence_score": 5,
        "confidence_band": "MEDIUM",
        "value_context": {
            "relative_to_prior_value_area": "inside",
            "relative_to_current_developing_value": "inside_value",
            "relative_to_vwap": "above",
            "relative_to_prior_day_range": "inside",
        },
        "structural_notes": "CL fixture-backed compile path remains balanced.",
        "outcome": "NO_TRADE",
        "conflicting_signals": ["event risk still pending"],
        "assumptions": [],
    }


def test_compile_cl_packet_builds_valid_packet() -> None:
    artifact = _compile_packet(compiled_at_iso="2026-01-14T14:10:00Z")

    packet = artifact.packet
    validated = validate_historical_packet(packet.model_dump(by_alias=True, mode="json"))

    assert validated.market_packet.contract == "CL"
    assert validated.market_packet.current_price == 73.42
    assert validated.market_packet.current_session_poc == 73.08
    assert validated.market_packet.opening_type == "Open-Auction"
    assert validated.contract_specific_extension.eia_timing.minutes_until == 85
    assert validated.contract_specific_extension.realized_volatility_context == "normal"
    assert (
        validated.contract_specific_extension.oil_specific_headlines
        == "No new OPEC or geopolitical headlines."
    )
    assert (
        validated.contract_specific_extension.liquidity_sweep_summary
        == "Sell-side sweep below the overnight low failed to continue."
    )
    assert (
        validated.contract_specific_extension.dom_liquidity_summary
        == "Bid stack rebuilding near session VWAP."
    )
    assert (
        artifact.provenance["field_provenance"]["market_packet.current_price"]["source"]
        == "historical_input"
    )
    assert (
        artifact.provenance["field_provenance"]["contract_specific_extension.eia_timing"]["source"]
        == "upstream_extension"
    )
    assert (
        artifact.provenance["field_provenance"]["market_packet.opening_type"]["source"]
        == "manual_overlay"
    )
    assert (
        artifact.provenance["field_provenance"]["contract_specific_extension.realized_volatility_context"]["source"]
        == "historical_input"
    )
    assert (
        artifact.provenance["field_provenance"]["contract_specific_extension.oil_specific_headlines"]["source"]
        == "upstream_extension"
    )
    assert (
        artifact.provenance["field_provenance"]["contract_specific_extension.liquidity_sweep_summary"]["source"]
        == "upstream_extension"
    )
    assert (
        artifact.provenance["field_provenance"]["contract_specific_extension.dom_liquidity_summary"]["source"]
        == "upstream_extension"
    )
    assert artifact.provenance["derived_features"]["realized_volatility_context"]["value"] == "normal"


def test_compile_cl_packet_accepts_minimal_overlay_fixture() -> None:
    overlay = _load_json("cl_overlay.assisted.valid.json")

    assert set(overlay.keys()) == {"contract", "challenge_state", "opening_type"}


def test_compile_cl_packet_extension_fixture_no_longer_requires_realized_volatility_context() -> None:
    extension_input = _load_json("cl_extension.valid.json")

    assert "realized_volatility_context" not in extension_input


def test_compile_cl_packet_extension_fixture_contains_only_remaining_fixture_backed_fields() -> None:
    extension_input = _load_json("cl_extension.valid.json")

    assert set(extension_input.keys()) == {
        "contract",
        "eia_timing",
        "oil_specific_headlines",
        "liquidity_sweep_summary",
        "dom_liquidity_summary",
    }


def test_compile_cl_packet_derives_elevated_realized_volatility_context() -> None:
    historical_input = _load_json("cl_historical_input.valid.json")
    historical_input["session_range"] = 2.1
    historical_input["avg_20d_session_range"] = 1.5

    artifact = _compile_packet(historical_input=historical_input)

    assert artifact.packet.contract_specific_extension.realized_volatility_context == "elevated"


def test_compile_cl_packet_derives_compressed_realized_volatility_context() -> None:
    historical_input = _load_json("cl_historical_input.valid.json")
    historical_input["session_range"] = 0.8
    historical_input["avg_20d_session_range"] = 1.6

    artifact = _compile_packet(historical_input=historical_input)

    assert artifact.packet.contract_specific_extension.realized_volatility_context == "compressed"


def test_compile_cl_packet_fails_closed_when_challenge_state_is_missing() -> None:
    overlay = _load_json("cl_overlay.assisted.valid.json")
    overlay.pop("challenge_state")

    with pytest.raises(ValueError, match="challenge_state"):
        _compile_packet(overlay=overlay)


def test_compile_cl_packet_fails_closed_when_opening_type_is_missing() -> None:
    overlay = _load_json("cl_overlay.assisted.valid.json")
    overlay.pop("opening_type")

    with pytest.raises(ValueError, match="opening_type"):
        _compile_packet(overlay=overlay)


def test_compile_cl_packet_does_not_auto_derive_opening_type() -> None:
    overlay = _load_json("cl_overlay.assisted.valid.json")
    overlay["opening_type"] = "Open-Drive"

    artifact = _compile_packet(overlay=overlay)

    assert artifact.packet.market_packet.opening_type == "Open-Drive"


def test_compile_cl_packet_does_not_auto_derive_remaining_qualitative_extension_fields() -> None:
    extension_input = _load_json("cl_extension.valid.json")
    extension_input.pop("oil_specific_headlines")
    extension_input.pop("liquidity_sweep_summary")
    extension_input.pop("dom_liquidity_summary")

    artifact = _compile_packet(extension_input=extension_input)

    assert artifact.packet.contract_specific_extension.oil_specific_headlines is None
    assert artifact.packet.contract_specific_extension.liquidity_sweep_summary is None
    assert artifact.packet.contract_specific_extension.dom_liquidity_summary is None


def test_compile_cl_packet_fails_closed_on_malformed_historical_input() -> None:
    historical_input = _load_json("cl_historical_input.valid.json")
    historical_input["current_session_val"] = 73.2
    historical_input["current_session_poc"] = 73.1
    historical_input["current_session_vah"] = 73.0

    with pytest.raises(ValueError, match="current session profile levels"):
        _compile_packet(historical_input=historical_input)


def test_compile_cl_packet_fails_closed_on_nonpositive_avg_range_for_volatility_derivation() -> None:
    historical_input = _load_json("cl_historical_input.valid.json")
    historical_input["avg_20d_session_range"] = 0.0

    with pytest.raises(ValueError, match="avg_20d_session_range must be > 0"):
        _compile_packet(historical_input=historical_input)


def test_compile_cl_packet_fails_closed_on_malformed_extension_input() -> None:
    extension_input = _load_json("cl_extension.valid.json")
    extension_input["eia_timing"] = {
        "status": "released",
        "scheduled_time": "2026-01-14T15:30:00Z",
    }

    with pytest.raises(ValueError, match="minutes_since"):
        _compile_packet(extension_input=extension_input)


def test_compiler_cli_writes_cl_packet_and_provenance(tmp_path: Path) -> None:
    output_path = tmp_path / "cl.packet.json"
    stdout = io.StringIO()
    stderr = io.StringIO()

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
    assert output_path.with_suffix(".provenance.json").is_file()
    validate_historical_packet(json.loads(output_path.read_text()))


def test_compiled_cl_packet_runs_through_existing_cli(monkeypatch, tmp_path: Path) -> None:
    output_path = tmp_path / "cl.packet.json"
    compile_exit_code = run_compile_cli(
        [
            "--contract",
            "CL",
            "--historical-input",
            str(FIXTURES_DIR / "cl_historical_input.valid.json"),
            "--overlay",
            str(FIXTURES_DIR / "cl_overlay.assisted.valid.json"),
            "--extension-input",
            str(FIXTURES_DIR / "cl_extension.valid.json"),
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
            return _valid_contract_analysis("CL")

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
    assert summary["contract"] == "CL"
    assert summary["termination_stage"] == "contract_market_read"
    assert summary["final_decision"] == "NO_TRADE"
