from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from ninjatradebuilder.cli import run_cli as run_runtime_cli
from ninjatradebuilder.packet_compiler.cli import run_cli as run_compile_cli
from ninjatradebuilder.packet_compiler.nq import compile_nq_packet
from ninjatradebuilder.validation import validate_historical_packet

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "compiler"


def _load_json(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def _compile_packet(
    historical_input: dict | None = None,
    overlay: dict | None = None,
    relative_strength_input: dict | None = None,
    extension_input: dict | None = None,
    *,
    compiled_at_iso: str | None = None,
):
    return compile_nq_packet(
        _load_json("nq_historical_input.valid.json") if historical_input is None else historical_input,
        _load_json("nq_overlay.assisted.valid.json") if overlay is None else overlay,
        _load_json("nq_relative_strength.valid.json")
        if relative_strength_input is None
        else relative_strength_input,
        _load_json("nq_extension.valid.json") if extension_input is None else extension_input,
        compiled_at_iso=compiled_at_iso,
    )


def _valid_contract_analysis(contract: str) -> dict:
    return {
        "$schema": "contract_analysis_v1",
        "stage": "contract_market_read",
        "contract": contract,
        "timestamp": "2026-01-14T15:06:00Z",
        "market_regime": "trending_up",
        "directional_bias": "bullish",
        "key_levels": {
            "support_levels": [18062.25],
            "resistance_levels": [18128.0],
            "pivot_level": 18094.5,
        },
        "evidence_score": 6,
        "confidence_band": "MEDIUM",
        "value_context": {
            "relative_to_prior_value_area": "above",
            "relative_to_current_developing_value": "above_vah",
            "relative_to_vwap": "above",
            "relative_to_prior_day_range": "inside",
        },
        "structural_notes": "NQ fixture-backed compile path remains balanced.",
        "outcome": "NO_TRADE",
        "conflicting_signals": ["earnings event still pending"],
        "assumptions": [],
    }


def test_compile_nq_packet_builds_valid_packet() -> None:
    artifact = _compile_packet(compiled_at_iso="2026-01-14T15:10:00Z")

    packet = artifact.packet
    validated = validate_historical_packet(packet.model_dump(by_alias=True, mode="json"))

    assert validated.market_packet.contract == "NQ"
    assert validated.market_packet.current_price == 18142.0
    assert validated.market_packet.current_session_poc == 18094.5
    assert validated.market_packet.opening_type == "Open-Drive"
    assert validated.contract_specific_extension.relative_strength_vs_es == 1.0019
    assert validated.contract_specific_extension.megacap_leadership_table == {
        "NVDA": "up",
        "MSFT": "up",
        "AAPL": "flat",
    }
    assert (
        artifact.provenance["field_provenance"]["market_packet.current_price"]["source"]
        == "historical_input"
    )
    assert (
        artifact.provenance["field_provenance"]["contract_specific_extension.relative_strength_vs_es"]["source"]
        == "comparative_input"
    )
    assert artifact.provenance["derived_features"]["relative_strength_vs_es"]["value"] == 1.0019


def test_compile_nq_packet_accepts_minimal_overlay_fixture() -> None:
    overlay = _load_json("nq_overlay.assisted.valid.json")

    assert set(overlay.keys()) == {"contract", "challenge_state", "opening_type"}


def test_compile_nq_packet_extension_fixture_no_longer_requires_relative_strength_vs_es() -> None:
    extension_input = _load_json("nq_extension.valid.json")

    assert "relative_strength_vs_es" not in extension_input


def test_compile_nq_packet_extension_fixture_contains_only_remaining_fixture_backed_fields() -> None:
    extension_input = _load_json("nq_extension.valid.json")

    assert set(extension_input.keys()) == {
        "contract",
        "megacap_leadership_table",
    }


def test_compile_nq_packet_derives_relative_strength_vs_es() -> None:
    artifact = _compile_packet()

    assert artifact.packet.contract_specific_extension.relative_strength_vs_es == 1.0019


def test_compile_nq_packet_fails_closed_on_malformed_relative_strength_input() -> None:
    relative_strength_input = _load_json("nq_relative_strength.valid.json")
    relative_strength_input["es_session_open"] = 0.0

    with pytest.raises(ValueError, match="es_session_open must be > 0"):
        _compile_packet(relative_strength_input=relative_strength_input)


def test_compile_nq_packet_fails_closed_on_mismatched_relative_strength_timestamp() -> None:
    relative_strength_input = _load_json("nq_relative_strength.valid.json")
    relative_strength_input["es_timestamp"] = "2026-01-14T15:04:00Z"

    with pytest.raises(ValueError, match="same timestamp"):
        _compile_packet(relative_strength_input=relative_strength_input)


def test_compile_nq_packet_fails_closed_when_challenge_state_is_missing() -> None:
    overlay = _load_json("nq_overlay.assisted.valid.json")
    overlay.pop("challenge_state")

    with pytest.raises(ValueError, match="challenge_state"):
        _compile_packet(overlay=overlay)


def test_compile_nq_packet_fails_closed_when_opening_type_is_missing() -> None:
    overlay = _load_json("nq_overlay.assisted.valid.json")
    overlay.pop("opening_type")

    with pytest.raises(ValueError, match="opening_type"):
        _compile_packet(overlay=overlay)


def test_compile_nq_packet_does_not_auto_derive_opening_type() -> None:
    overlay = _load_json("nq_overlay.assisted.valid.json")
    overlay["opening_type"] = "Open-Auction"

    artifact = _compile_packet(overlay=overlay)

    assert artifact.packet.market_packet.opening_type == "Open-Auction"


def test_compile_nq_packet_fails_closed_on_malformed_historical_input() -> None:
    historical_input = _load_json("nq_historical_input.valid.json")
    historical_input["current_session_val"] = 18110.0
    historical_input["current_session_poc"] = 18095.0
    historical_input["current_session_vah"] = 18090.0

    with pytest.raises(ValueError, match="current session profile levels"):
        _compile_packet(historical_input=historical_input)


def test_compile_nq_packet_fails_closed_on_malformed_extension_input() -> None:
    extension_input = _load_json("nq_extension.valid.json")
    extension_input["megacap_leadership_table"] = "leaders"

    with pytest.raises(ValueError, match="megacap_leadership_table"):
        _compile_packet(extension_input=extension_input)


def test_compile_nq_packet_does_not_auto_derive_megacap_leadership_table() -> None:
    extension_input = _load_json("nq_extension.valid.json")
    extension_input.pop("megacap_leadership_table")

    artifact = _compile_packet(extension_input=extension_input)

    assert artifact.packet.contract_specific_extension.megacap_leadership_table is None


def test_compiler_cli_writes_nq_packet_and_provenance(tmp_path: Path) -> None:
    output_path = tmp_path / "nq.packet.json"
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = run_compile_cli(
        [
            "--contract",
            "NQ",
            "--historical-input",
            str(FIXTURES_DIR / "nq_historical_input.valid.json"),
            "--overlay",
            str(FIXTURES_DIR / "nq_overlay.assisted.valid.json"),
            "--relative-strength-input",
            str(FIXTURES_DIR / "nq_relative_strength.valid.json"),
            "--extension-input",
            str(FIXTURES_DIR / "nq_extension.valid.json"),
            "--output",
            str(output_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    summary = json.loads(stdout.getvalue())
    assert summary["contract"] == "NQ"
    assert output_path.is_file()
    assert output_path.with_suffix(".provenance.json").is_file()
    validate_historical_packet(json.loads(output_path.read_text()))


def test_compiled_nq_packet_runs_through_existing_cli(monkeypatch, tmp_path: Path) -> None:
    output_path = tmp_path / "nq.packet.json"
    compile_exit_code = run_compile_cli(
        [
            "--contract",
            "NQ",
            "--historical-input",
            str(FIXTURES_DIR / "nq_historical_input.valid.json"),
            "--overlay",
            str(FIXTURES_DIR / "nq_overlay.assisted.valid.json"),
            "--relative-strength-input",
            str(FIXTURES_DIR / "nq_relative_strength.valid.json"),
            "--extension-input",
            str(FIXTURES_DIR / "nq_extension.valid.json"),
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
            return _valid_contract_analysis("NQ")

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
    assert summary["contract"] == "NQ"
    assert summary["termination_stage"] == "contract_market_read"
    assert summary["final_decision"] == "NO_TRADE"
