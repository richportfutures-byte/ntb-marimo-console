from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from ninjatradebuilder.cli import run_cli as run_runtime_cli
from ninjatradebuilder.packet_compiler.cli import run_cli as run_compile_cli
from ninjatradebuilder.packet_compiler.mgc import compile_mgc_packet
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
    return compile_mgc_packet(
        _load_json("mgc_historical_input.valid.json") if historical_input is None else historical_input,
        _load_json("mgc_overlay.assisted.valid.json") if overlay is None else overlay,
        _load_json("mgc_extension.valid.json") if extension_input is None else extension_input,
        compiled_at_iso=compiled_at_iso,
    )


def _valid_contract_analysis(contract: str) -> dict:
    return {
        "$schema": "contract_analysis_v1",
        "stage": "contract_market_read",
        "contract": contract,
        "timestamp": "2026-01-14T15:06:00Z",
        "market_regime": "range_bound",
        "directional_bias": "bullish",
        "key_levels": {
            "support_levels": [2049.6],
            "resistance_levels": [2053.8],
            "pivot_level": 2051.2,
        },
        "evidence_score": 5,
        "confidence_band": "MEDIUM",
        "value_context": {
            "relative_to_prior_value_area": "inside",
            "relative_to_current_developing_value": "inside_value",
            "relative_to_vwap": "above",
            "relative_to_prior_day_range": "inside",
        },
        "structural_notes": "MGC fixture-backed compile path remains balanced.",
        "outcome": "NO_TRADE",
        "conflicting_signals": ["macro fear catalyst remains neutral"],
        "assumptions": [],
    }


def test_compile_mgc_packet_builds_valid_packet() -> None:
    artifact = _compile_packet(compiled_at_iso="2026-01-14T15:10:00Z")

    packet = artifact.packet
    validated = validate_historical_packet(packet.model_dump(by_alias=True, mode="json"))

    assert validated.market_packet.contract == "MGC"
    assert validated.market_packet.current_price == 2054.3
    assert validated.market_packet.current_session_poc == 2051.2
    assert validated.market_packet.opening_type == "Open-Test-Drive"
    assert validated.contract_specific_extension.dxy_context == "weakening"
    assert validated.contract_specific_extension.yield_context == "falling"
    assert validated.contract_specific_extension.macro_fear_catalyst_summary == "none"
    assert (
        artifact.provenance["field_provenance"]["market_packet.current_price"]["source"]
        == "historical_input"
    )
    assert (
        artifact.provenance["field_provenance"]["contract_specific_extension.dxy_context"]["source"]
        == "upstream_extension"
    )


def test_compile_mgc_packet_accepts_minimal_overlay_fixture() -> None:
    overlay = _load_json("mgc_overlay.assisted.valid.json")

    assert set(overlay.keys()) == {"contract", "challenge_state", "opening_type"}


def test_compile_mgc_packet_extension_fixture_contains_fixture_backed_fields() -> None:
    extension_input = _load_json("mgc_extension.valid.json")

    assert set(extension_input.keys()) == {
        "contract",
        "dxy_context",
        "yield_context",
        "swing_penetration_volume_summary",
        "macro_fear_catalyst_summary",
    }


def test_compile_mgc_packet_fails_closed_when_challenge_state_is_missing() -> None:
    overlay = _load_json("mgc_overlay.assisted.valid.json")
    overlay.pop("challenge_state")

    with pytest.raises(ValueError, match="challenge_state"):
        _compile_packet(overlay=overlay)


def test_compile_mgc_packet_fails_closed_when_opening_type_is_missing() -> None:
    overlay = _load_json("mgc_overlay.assisted.valid.json")
    overlay.pop("opening_type")

    with pytest.raises(ValueError, match="opening_type"):
        _compile_packet(overlay=overlay)


def test_compile_mgc_packet_does_not_auto_derive_opening_type() -> None:
    overlay = _load_json("mgc_overlay.assisted.valid.json")
    overlay.pop("opening_type")
    historical_input = _load_json("mgc_historical_input.valid.json")
    historical_input["session_open"] = 2045.0
    historical_input["current_price"] = 2058.8

    with pytest.raises(ValueError, match="opening_type"):
        _compile_packet(historical_input=historical_input, overlay=overlay)


def test_compile_mgc_packet_fails_closed_on_malformed_historical_input() -> None:
    historical_input = _load_json("mgc_historical_input.valid.json")
    historical_input["current_session_val"] = 2054.0
    historical_input["current_session_poc"] = 2052.0
    historical_input["current_session_vah"] = 2051.0

    with pytest.raises(ValueError, match="current session profile levels"):
        _compile_packet(historical_input=historical_input)


def test_compile_mgc_packet_fails_closed_on_malformed_extension_input() -> None:
    extension_input = _load_json("mgc_extension.valid.json")
    extension_input["macro_fear_catalyst_summary"] = ""

    with pytest.raises(ValueError, match="at least 1 character"):
        _compile_packet(extension_input=extension_input)


def test_compile_mgc_packet_does_not_auto_derive_dxy_context() -> None:
    extension_input = _load_json("mgc_extension.valid.json")
    extension_input.pop("dxy_context")

    with pytest.raises(ValueError, match="dxy_context"):
        _compile_packet(extension_input=extension_input)


def test_compile_mgc_packet_does_not_auto_derive_yield_context() -> None:
    extension_input = _load_json("mgc_extension.valid.json")
    extension_input.pop("yield_context")

    with pytest.raises(ValueError, match="yield_context"):
        _compile_packet(extension_input=extension_input)


def test_compile_mgc_packet_does_not_auto_derive_macro_fear_catalyst_summary() -> None:
    extension_input = _load_json("mgc_extension.valid.json")
    extension_input.pop("macro_fear_catalyst_summary")

    with pytest.raises(ValueError, match="macro_fear_catalyst_summary"):
        _compile_packet(extension_input=extension_input)


def test_compile_mgc_packet_keeps_optional_swing_penetration_summary_fixture_backed() -> None:
    extension_input = _load_json("mgc_extension.valid.json")
    extension_input.pop("swing_penetration_volume_summary")

    artifact = _compile_packet(extension_input=extension_input)

    assert artifact.packet.contract_specific_extension.swing_penetration_volume_summary is None


def test_compiler_cli_writes_mgc_packet_and_provenance(tmp_path: Path) -> None:
    output_path = tmp_path / "mgc.packet.json"
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = run_compile_cli(
        [
            "--contract",
            "MGC",
            "--historical-input",
            str(FIXTURES_DIR / "mgc_historical_input.valid.json"),
            "--overlay",
            str(FIXTURES_DIR / "mgc_overlay.assisted.valid.json"),
            "--extension-input",
            str(FIXTURES_DIR / "mgc_extension.valid.json"),
            "--output",
            str(output_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    summary = json.loads(stdout.getvalue())
    assert summary["contract"] == "MGC"
    assert output_path.is_file()
    assert output_path.with_suffix(".provenance.json").is_file()
    validate_historical_packet(json.loads(output_path.read_text()))


def test_compiled_mgc_packet_runs_through_existing_cli(monkeypatch, tmp_path: Path) -> None:
    output_path = tmp_path / "mgc.packet.json"
    compile_exit_code = run_compile_cli(
        [
            "--contract",
            "MGC",
            "--historical-input",
            str(FIXTURES_DIR / "mgc_historical_input.valid.json"),
            "--overlay",
            str(FIXTURES_DIR / "mgc_overlay.assisted.valid.json"),
            "--extension-input",
            str(FIXTURES_DIR / "mgc_extension.valid.json"),
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
            return _valid_contract_analysis("MGC")

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
    assert summary["contract"] == "MGC"
    assert summary["termination_stage"] == "contract_market_read"
    assert summary["final_decision"] == "NO_TRADE"
