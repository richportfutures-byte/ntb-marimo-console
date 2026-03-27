from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from ninjatradebuilder.cli import run_cli as run_runtime_cli
from ninjatradebuilder.packet_compiler.cli import run_cli as run_compile_cli
from ninjatradebuilder.packet_compiler.zn import compile_zn_packet
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
    return compile_zn_packet(
        _load_json("zn_historical_input.valid.json") if historical_input is None else historical_input,
        _load_json("zn_overlay.assisted.valid.json") if overlay is None else overlay,
        _load_json("zn_extension.valid.json") if extension_input is None else extension_input,
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
            "support_levels": [110.296875],
            "resistance_levels": [110.421875],
            "pivot_level": 110.359375,
        },
        "evidence_score": 5,
        "confidence_band": "MEDIUM",
        "value_context": {
            "relative_to_prior_value_area": "inside",
            "relative_to_current_developing_value": "inside_value",
            "relative_to_vwap": "above",
            "relative_to_prior_day_range": "inside",
        },
        "structural_notes": "ZN fixture-backed compile path remains balanced.",
        "outcome": "NO_TRADE",
        "conflicting_signals": ["auction timing remains ahead"],
        "assumptions": [],
    }


def test_compile_zn_packet_builds_valid_packet() -> None:
    artifact = _compile_packet(compiled_at_iso="2026-01-14T15:10:00Z")

    packet = artifact.packet
    validated = validate_historical_packet(packet.model_dump(by_alias=True, mode="json"))

    assert validated.market_packet.contract == "ZN"
    assert validated.market_packet.current_price == 110.40625
    assert validated.market_packet.current_session_poc == 110.359375
    assert validated.market_packet.opening_type == "Open-Test-Drive"
    assert validated.contract_specific_extension.cash_10y_yield == 4.12
    assert validated.contract_specific_extension.treasury_auction_schedule == "today 13:00 10Y"
    assert (
        artifact.provenance["field_provenance"]["market_packet.current_price"]["source"]
        == "historical_input"
    )
    assert (
        artifact.provenance["field_provenance"]["contract_specific_extension.cash_10y_yield"]["source"]
        == "upstream_extension"
    )


def test_compile_zn_packet_accepts_minimal_overlay_fixture() -> None:
    overlay = _load_json("zn_overlay.assisted.valid.json")

    assert set(overlay.keys()) == {"contract", "challenge_state", "opening_type"}


def test_compile_zn_packet_extension_fixture_contains_provider_and_fixture_backed_fields() -> None:
    extension_input = _load_json("zn_extension.valid.json")

    assert set(extension_input.keys()) == {
        "contract",
        "cash_10y_yield",
        "treasury_auction_schedule",
        "macro_release_context",
        "absorption_summary",
    }


def test_compile_zn_packet_fails_closed_when_challenge_state_is_missing() -> None:
    overlay = _load_json("zn_overlay.assisted.valid.json")
    overlay.pop("challenge_state")

    with pytest.raises(ValueError, match="challenge_state"):
        _compile_packet(overlay=overlay)


def test_compile_zn_packet_fails_closed_when_opening_type_is_missing() -> None:
    overlay = _load_json("zn_overlay.assisted.valid.json")
    overlay.pop("opening_type")

    with pytest.raises(ValueError, match="opening_type"):
        _compile_packet(overlay=overlay)


def test_compile_zn_packet_does_not_auto_derive_opening_type() -> None:
    overlay = _load_json("zn_overlay.assisted.valid.json")
    overlay["opening_type"] = "Open-Drive"

    artifact = _compile_packet(overlay=overlay)

    assert artifact.packet.market_packet.opening_type == "Open-Drive"


def test_compile_zn_packet_fails_closed_on_malformed_historical_input() -> None:
    historical_input = _load_json("zn_historical_input.valid.json")
    historical_input["current_session_val"] = 110.4
    historical_input["current_session_poc"] = 110.35
    historical_input["current_session_vah"] = 110.3

    with pytest.raises(ValueError, match="current session profile levels"):
        _compile_packet(historical_input=historical_input)


def test_compile_zn_packet_fails_closed_on_malformed_extension_input() -> None:
    extension_input = _load_json("zn_extension.valid.json")
    extension_input["treasury_auction_schedule"] = ""

    with pytest.raises(ValueError, match="at least 1 character"):
        _compile_packet(extension_input=extension_input)


def test_compile_zn_packet_does_not_auto_derive_remaining_extension_fields() -> None:
    extension_input = _load_json("zn_extension.valid.json")
    extension_input.pop("absorption_summary")

    artifact = _compile_packet(extension_input=extension_input)

    assert artifact.packet.contract_specific_extension.absorption_summary is None


def test_compile_zn_packet_fails_closed_when_treasury_auction_schedule_is_missing() -> None:
    extension_input = _load_json("zn_extension.valid.json")
    extension_input.pop("treasury_auction_schedule")

    with pytest.raises(ValueError, match="treasury_auction_schedule"):
        _compile_packet(extension_input=extension_input)


def test_compile_zn_packet_fails_closed_when_macro_release_context_is_missing() -> None:
    extension_input = _load_json("zn_extension.valid.json")
    extension_input.pop("macro_release_context")

    with pytest.raises(ValueError, match="macro_release_context"):
        _compile_packet(extension_input=extension_input)


def test_compiler_cli_writes_zn_packet_and_provenance(tmp_path: Path) -> None:
    output_path = tmp_path / "zn.packet.json"
    stdout = io.StringIO()
    stderr = io.StringIO()

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
    assert output_path.with_suffix(".provenance.json").is_file()
    validate_historical_packet(json.loads(output_path.read_text()))


def test_compiled_zn_packet_runs_through_existing_cli(monkeypatch, tmp_path: Path) -> None:
    output_path = tmp_path / "zn.packet.json"
    compile_exit_code = run_compile_cli(
        [
            "--contract",
            "ZN",
            "--historical-input",
            str(FIXTURES_DIR / "zn_historical_input.valid.json"),
            "--overlay",
            str(FIXTURES_DIR / "zn_overlay.assisted.valid.json"),
            "--extension-input",
            str(FIXTURES_DIR / "zn_extension.valid.json"),
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
            return _valid_contract_analysis("ZN")

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
    assert summary["contract"] == "ZN"
    assert summary["termination_stage"] == "contract_market_read"
    assert summary["final_decision"] == "NO_TRADE"
