from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from ninjatradebuilder.cli import run_cli as run_runtime_cli
from ninjatradebuilder.packet_compiler.cli import run_cli as run_compile_cli
from ninjatradebuilder.packet_compiler.es import compile_es_packet
from ninjatradebuilder.validation import validate_historical_packet

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "compiler"


def _load_json(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def _compile_packet(
    historical_input: dict | None = None,
    overlay: dict | None = None,
    calendar_input: dict | None = None,
    breadth_input: dict | None = None,
    index_cash_tone_input: dict | None = None,
    cumulative_delta_input: dict | None = None,
    *,
    compiled_at_iso: str | None = None,
):
    return compile_es_packet(
        _load_json("es_historical_input.valid.json") if historical_input is None else historical_input,
        _load_json("es_overlay.assisted.valid.json") if overlay is None else overlay,
        _load_json("es_calendar.valid.json") if calendar_input is None else calendar_input,
        _load_json("es_breadth.valid.json") if breadth_input is None else breadth_input,
        (
            _load_json("es_index_cash_tone.valid.json")
            if index_cash_tone_input is None
            else index_cash_tone_input
        ),
        (
            _load_json("es_cumulative_delta.valid.json")
            if cumulative_delta_input is None
            else cumulative_delta_input
        ),
        compiled_at_iso=compiled_at_iso,
    )


def _valid_contract_analysis(contract: str) -> dict:
    return {
        "$schema": "contract_analysis_v1",
        "stage": "contract_market_read",
        "contract": contract,
        "timestamp": "2026-01-14T16:01:00Z",
        "market_regime": "range_bound",
        "directional_bias": "bullish",
        "key_levels": {
            "support_levels": [5018.0],
            "resistance_levels": [5032.0],
            "pivot_level": 5025.0,
        },
        "evidence_score": 6,
        "confidence_band": "MEDIUM",
        "value_context": {
            "relative_to_prior_value_area": "inside",
            "relative_to_current_developing_value": "inside_value",
            "relative_to_vwap": "above",
            "relative_to_prior_day_range": "inside",
        },
        "structural_notes": "Session rotated higher but remains balanced.",
        "outcome": "NO_TRADE",
        "conflicting_signals": ["balance remains intact"],
        "assumptions": [],
    }


def test_compile_es_packet_derives_expected_features_and_validates() -> None:
    artifact = _compile_packet(
        overlay=_load_json("es_overlay.assisted.valid.json"),
        compiled_at_iso="2026-01-14T16:05:00Z",
    )

    packet = artifact.packet
    validated = validate_historical_packet(packet.model_dump(by_alias=True, mode="json"))

    assert validated.market_packet.contract == "ES"
    assert validated.market_packet.timestamp.isoformat().replace("+00:00", "Z") == "2026-01-14T16:00:00Z"
    assert validated.market_packet.current_price == 5031.0
    assert validated.market_packet.session_open == 5018.0
    assert validated.market_packet.prior_day_high == 5020.0
    assert validated.market_packet.prior_day_low == 5006.0
    assert validated.market_packet.prior_day_close == 5013.0
    assert validated.market_packet.overnight_high == 5022.0
    assert validated.market_packet.overnight_low == 5008.0
    assert validated.market_packet.current_session_vah == 5025.5
    assert validated.market_packet.current_session_val == 5024.5
    assert validated.market_packet.current_session_poc == 5025.0
    assert validated.market_packet.previous_session_vah == 5015.0
    assert validated.market_packet.previous_session_val == 5014.25
    assert validated.market_packet.previous_session_poc == 5014.5
    assert validated.market_packet.avg_20d_session_range == 42.5
    assert validated.market_packet.cumulative_delta == 10250.0
    assert validated.market_packet.current_volume_vs_average == 1.0314
    assert len(validated.market_packet.event_calendar_remainder) == 2
    assert validated.contract_specific_extension.breadth == "positive +850"
    assert validated.contract_specific_extension.index_cash_tone == "bullish"
    assert validated.market_packet.session_range == 16.0
    assert validated.market_packet.vwap == pytest.approx(5025.5407)
    assert artifact.provenance["field_provenance"]["market_packet.current_price"]["source"] == "historical_bars"
    assert (
        artifact.provenance["field_provenance"]["market_packet.current_session_poc"]["source"]
        == "historical_profile"
    )
    assert artifact.provenance["derived_features"]["current_session_profile"]["poc"] == 5025.0
    assert artifact.provenance["derived_features"]["previous_session_profile"]["val"] == 5014.25
    assert artifact.provenance["derived_features"]["avg_20d_session_range"]["value"] == 42.5
    assert artifact.provenance["derived_features"]["current_volume_vs_average"]["value"] == 1.0314
    assert (
        artifact.provenance["field_provenance"]["market_packet.current_volume_vs_average"]["source"]
        == "historical_lookback"
    )
    assert (
        artifact.provenance["field_provenance"]["market_packet.event_calendar_remainder"]["source"]
        == "upstream_calendar"
    )
    assert (
        artifact.provenance["field_provenance"]["contract_specific_extension.breadth"]["source"]
        == "upstream_breadth"
    )
    assert (
        artifact.provenance["field_provenance"]["contract_specific_extension.index_cash_tone"]["source"]
        == "upstream_index_cash_tone"
    )
    assert (
        artifact.provenance["field_provenance"]["market_packet.cumulative_delta"]["source"]
        == "upstream_cumulative_delta"
    )
    assert artifact.provenance["derived_features"]["ib_high"]["value"] == 5028.0
    assert artifact.provenance["derived_features"]["ib_low"]["value"] == 5016.0
    assert artifact.provenance["derived_features"]["ib_range"]["value"] == 12.0
    assert artifact.provenance["derived_features"]["weekly_open"]["value"] == 4998.0


def test_compile_es_packet_overlay_assist_derives_safe_defaults() -> None:
    artifact = _compile_packet(compiled_at_iso="2026-01-14T16:05:00Z")

    packet = artifact.packet
    assert packet.attached_visuals.daily_chart_attached is False
    assert packet.attached_visuals.tpo_chart_attached is False
    assert packet.market_packet.major_higher_timeframe_levels is None
    assert packet.market_packet.key_hvns is None
    assert packet.market_packet.key_lvns is None
    assert packet.market_packet.singles_excess_poor_high_low_notes is None
    assert packet.market_packet.cross_market_context is None
    assert packet.market_packet.data_quality_flags == []
    assert artifact.provenance["field_provenance"]["attached_visuals"]["source"] == "overlay_assist"
    assert (
        artifact.provenance["field_provenance"]["market_packet.data_quality_flags"]["source"]
        == "overlay_assist"
    )


def test_es_minimal_overlay_fixture_contains_only_manual_boundary_fields() -> None:
    overlay = _load_json("es_overlay.assisted.valid.json")

    assert set(overlay.keys()) == {"contract", "challenge_state", "opening_type"}


def test_compile_es_packet_accepts_minimal_manual_overlay_fixture() -> None:
    artifact = _compile_packet(compiled_at_iso="2026-01-14T16:05:00Z")

    assert artifact.packet.market_packet.current_session_poc == 5025.0
    assert artifact.packet.market_packet.previous_session_poc == 5014.5
    assert artifact.packet.market_packet.avg_20d_session_range == 42.5
    assert artifact.packet.market_packet.current_volume_vs_average == 1.0314


def test_compile_es_packet_keeps_opening_type_manual_and_records_manual_provenance() -> None:
    artifact = _compile_packet(compiled_at_iso="2026-01-14T16:05:00Z")

    assert artifact.packet.market_packet.opening_type == "Open-Auction"
    assert (
        artifact.provenance["field_provenance"]["market_packet.opening_type"]["source"]
        == "manual_overlay"
    )


def test_compile_es_packet_fails_closed_when_required_manual_field_is_missing() -> None:
    overlay = _load_json("es_overlay.assisted.valid.json")
    overlay.pop("challenge_state")

    with pytest.raises(ValueError, match="challenge_state"):
        _compile_packet(overlay=overlay)


def test_compile_es_packet_sources_event_calendar_from_dedicated_input() -> None:
    artifact = _compile_packet()

    assert artifact.packet.market_packet.event_calendar_remainder[0].name == "CPI"
    assert artifact.packet.market_packet.event_calendar_remainder[1].minutes_until == 120


def test_compile_es_packet_fails_closed_when_calendar_input_is_missing() -> None:
    with pytest.raises(ValueError, match="event_calendar_remainder"):
        _compile_packet(calendar_input={})


def test_compile_es_packet_fails_closed_when_calendar_input_is_malformed() -> None:
    calendar = _load_json("es_calendar.valid.json")
    calendar["event_calendar_remainder"][0]["minutes_until"] = 10

    with pytest.raises(ValueError, match="Released events require minutes_since"):
        _compile_packet(calendar_input=calendar)


def test_compile_es_packet_sources_breadth_from_dedicated_input() -> None:
    artifact = _compile_packet()

    assert artifact.packet.contract_specific_extension.breadth == "positive +850"


def test_compile_es_packet_fails_closed_when_breadth_input_is_missing() -> None:
    with pytest.raises(ValueError, match="breadth"):
        _compile_packet(breadth_input={})


def test_compile_es_packet_fails_closed_when_breadth_input_is_malformed() -> None:
    with pytest.raises(ValueError, match="at least 1 character"):
        _compile_packet(breadth_input={"contract": "ES", "breadth": ""})


def test_compile_es_packet_sources_index_cash_tone_from_dedicated_input() -> None:
    artifact = _compile_packet()

    assert artifact.packet.contract_specific_extension.index_cash_tone == "bullish"


def test_compile_es_packet_fails_closed_when_index_cash_tone_input_is_missing() -> None:
    with pytest.raises(ValueError, match="index_cash_tone"):
        _compile_packet(index_cash_tone_input={})


def test_compile_es_packet_fails_closed_when_index_cash_tone_input_is_malformed() -> None:
    with pytest.raises(
        ValueError, match="Input should be 'bullish', 'bearish', 'choppy' or 'flat'"
    ):
        _compile_packet(index_cash_tone_input={"contract": "ES", "index_cash_tone": "up"})


def test_compile_es_packet_sources_cumulative_delta_from_dedicated_input() -> None:
    artifact = _compile_packet()

    assert artifact.packet.market_packet.cumulative_delta == 10250.0


def test_compile_es_packet_fails_closed_when_cumulative_delta_input_is_missing() -> None:
    with pytest.raises(ValueError, match="cumulative_delta"):
        _compile_packet(cumulative_delta_input={})


def test_compile_es_packet_fails_closed_when_cumulative_delta_input_is_malformed() -> None:
    with pytest.raises(ValueError, match="cumulative_delta"):
        _compile_packet(cumulative_delta_input={"contract": "ES", "cumulative_delta": "bad"})


def test_compile_es_packet_fails_closed_when_opening_type_is_missing() -> None:
    overlay = _load_json("es_overlay.assisted.valid.json")
    overlay.pop("opening_type")

    with pytest.raises(ValueError, match="opening_type"):
        _compile_packet(overlay=overlay)


def test_compile_es_packet_fails_closed_when_profile_input_is_missing() -> None:
    historical_input = _load_json("es_historical_input.valid.json")
    historical_input.pop("current_rth_volume_profile")

    with pytest.raises(ValueError, match="current_rth_volume_profile"):
        _compile_packet(historical_input=historical_input)


def test_compile_es_packet_fails_closed_when_lookback_input_is_missing() -> None:
    historical_input = _load_json("es_historical_input.valid.json")
    historical_input.pop("prior_20_rth_sessions")

    with pytest.raises(ValueError, match="prior_20_rth_sessions"):
        _compile_packet(historical_input=historical_input)


def test_compile_es_packet_fails_closed_when_volume_baseline_input_is_missing() -> None:
    historical_input = _load_json("es_historical_input.valid.json")
    historical_input.pop("prior_20_rth_observed_volumes")

    with pytest.raises(ValueError, match="prior_20_rth_observed_volumes"):
        _compile_packet(historical_input=historical_input)


def test_compile_es_packet_rejects_duplicate_profile_prices() -> None:
    historical_input = _load_json("es_historical_input.valid.json")
    historical_input["current_rth_volume_profile"][1]["price"] = historical_input[
        "current_rth_volume_profile"
    ][0]["price"]

    with pytest.raises(ValueError, match="current_rth_volume_profile must not contain duplicate prices"):
        _compile_packet(historical_input=historical_input)


def test_compile_es_packet_rejects_insufficient_profile_levels() -> None:
    historical_input = _load_json("es_historical_input.valid.json")
    historical_input["prior_rth_volume_profile"] = historical_input["prior_rth_volume_profile"][:2]

    with pytest.raises(ValueError, match="prior_rth_volume_profile must contain at least three price levels"):
        _compile_packet(historical_input=historical_input)


def test_compile_es_packet_rejects_insufficient_20_session_lookback() -> None:
    historical_input = _load_json("es_historical_input.valid.json")
    historical_input["prior_20_rth_sessions"] = historical_input["prior_20_rth_sessions"][:19]

    with pytest.raises(ValueError, match="prior_20_rth_sessions must contain exactly 20 completed sessions"):
        _compile_packet(historical_input=historical_input)


def test_compile_es_packet_rejects_duplicate_lookback_session_dates() -> None:
    historical_input = _load_json("es_historical_input.valid.json")
    historical_input["prior_20_rth_sessions"][1]["session_date"] = historical_input["prior_20_rth_sessions"][0]["session_date"]

    with pytest.raises(ValueError, match="prior_20_rth_sessions must not contain duplicate session_date values"):
        _compile_packet(historical_input=historical_input)


def test_compile_es_packet_rejects_last_lookback_session_mismatch() -> None:
    historical_input = _load_json("es_historical_input.valid.json")
    historical_input["prior_20_rth_sessions"][-1]["high"] = 5021.0

    with pytest.raises(ValueError, match="last prior_20_rth_sessions entry must match prior_rth_bars high/low"):
        _compile_packet(historical_input=historical_input)


def test_compile_es_packet_rejects_insufficient_20_session_volume_baseline() -> None:
    historical_input = _load_json("es_historical_input.valid.json")
    historical_input["prior_20_rth_observed_volumes"] = historical_input[
        "prior_20_rth_observed_volumes"
    ][:19]

    with pytest.raises(
        ValueError,
        match="prior_20_rth_observed_volumes must contain exactly 20 completed sessions",
    ):
        _compile_packet(historical_input=historical_input)


def test_compile_es_packet_rejects_duplicate_20_session_volume_baseline_dates() -> None:
    historical_input = _load_json("es_historical_input.valid.json")
    historical_input["prior_20_rth_observed_volumes"][1]["session_date"] = historical_input[
        "prior_20_rth_observed_volumes"
    ][0]["session_date"]

    with pytest.raises(
        ValueError,
        match="prior_20_rth_observed_volumes must not contain duplicate session_date values",
    ):
        _compile_packet(historical_input=historical_input)


def test_compile_es_packet_rejects_misaligned_20_session_volume_baseline_dates() -> None:
    historical_input = _load_json("es_historical_input.valid.json")
    historical_input["prior_20_rth_observed_volumes"][12]["session_date"] = "2026-01-03"

    with pytest.raises(
        ValueError,
        match="prior_20_rth_observed_volumes must use the same 20 session dates as prior_20_rth_sessions",
    ):
        _compile_packet(historical_input=historical_input)


def test_compile_es_packet_rejects_nonpositive_20_session_observed_volume() -> None:
    historical_input = _load_json("es_historical_input.valid.json")
    historical_input["prior_20_rth_observed_volumes"][0]["observed_volume"] = 0.0

    with pytest.raises(ValueError, match="observed_volume > 0"):
        _compile_packet(historical_input=historical_input)


def test_compile_es_packet_rejects_unsorted_current_rth_bars() -> None:
    historical_input = _load_json("es_historical_input.valid.json")
    historical_input["current_rth_bars"] = list(reversed(historical_input["current_rth_bars"]))

    with pytest.raises(ValueError, match="current_rth_bars must be strictly timestamp-ascending"):
        _compile_packet(historical_input=historical_input)


def test_compile_es_packet_rejects_duplicate_timestamps_within_bar_set() -> None:
    historical_input = _load_json("es_historical_input.valid.json")
    historical_input["overnight_bars"][1]["timestamp"] = historical_input["overnight_bars"][0][
        "timestamp"
    ]

    with pytest.raises(ValueError, match="overnight_bars must not contain duplicate timestamps"):
        _compile_packet(historical_input=historical_input)


def test_compile_es_packet_rejects_current_rth_bars_across_multiple_dates() -> None:
    historical_input = _load_json("es_historical_input.valid.json")
    historical_input["current_rth_bars"][-1]["timestamp"] = "2026-01-15T16:00:00Z"

    with pytest.raises(ValueError, match="current_rth_bars must all fall on one session date"):
        _compile_packet(historical_input=historical_input)


def test_compile_es_packet_rejects_overnight_overlap_with_current_session() -> None:
    historical_input = _load_json("es_historical_input.valid.json")
    historical_input["overnight_bars"][-1]["timestamp"] = "2026-01-14T14:30:00Z"

    with pytest.raises(ValueError, match="overnight_bars must end before current_rth_bars begin"):
        _compile_packet(historical_input=historical_input)


def test_compile_es_packet_rejects_weekly_open_after_current_session_start() -> None:
    historical_input = _load_json("es_historical_input.valid.json")
    historical_input["weekly_open_bar"]["timestamp"] = "2026-01-14T14:31:00Z"

    with pytest.raises(
        ValueError, match="weekly_open_bar timestamp must not be after the first current_rth_bar"
    ):
        _compile_packet(historical_input=historical_input)


def test_compile_es_packet_rejects_insufficient_initial_balance_support() -> None:
    historical_input = _load_json("es_historical_input.valid.json")
    historical_input["current_rth_bars"] = historical_input["current_rth_bars"][:1]

    with pytest.raises(
        ValueError,
        match="Current RTH bars must contain at least two bars inside the first 60 minutes",
    ):
        _compile_packet(historical_input=historical_input)


def test_compiler_cli_writes_packet_and_provenance(tmp_path: Path) -> None:
    output_path = tmp_path / "packet.json"
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = run_compile_cli(
        [
            "--historical-input",
            str(FIXTURES_DIR / "es_historical_input.valid.json"),
            "--overlay",
            str(FIXTURES_DIR / "es_overlay.assisted.valid.json"),
            "--calendar-input",
            str(FIXTURES_DIR / "es_calendar.valid.json"),
            "--breadth-input",
            str(FIXTURES_DIR / "es_breadth.valid.json"),
            "--index-cash-tone-input",
            str(FIXTURES_DIR / "es_index_cash_tone.valid.json"),
            "--cumulative-delta-input",
            str(FIXTURES_DIR / "es_cumulative_delta.valid.json"),
            "--output",
            str(output_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    summary = json.loads(stdout.getvalue())
    assert summary["contract"] == "ES"
    assert summary["packet_path"] == str(output_path)
    assert output_path.is_file()
    assert output_path.with_suffix(".provenance.json").is_file()
    validate_historical_packet(json.loads(output_path.read_text()))


def test_compiled_packet_runs_through_existing_cli(monkeypatch, tmp_path: Path) -> None:
    output_path = tmp_path / "packet.json"
    compile_exit_code = run_compile_cli(
        [
            "--historical-input",
            str(FIXTURES_DIR / "es_historical_input.valid.json"),
            "--overlay",
            str(FIXTURES_DIR / "es_overlay.assisted.valid.json"),
            "--calendar-input",
            str(FIXTURES_DIR / "es_calendar.valid.json"),
            "--breadth-input",
            str(FIXTURES_DIR / "es_breadth.valid.json"),
            "--index-cash-tone-input",
            str(FIXTURES_DIR / "es_index_cash_tone.valid.json"),
            "--cumulative-delta-input",
            str(FIXTURES_DIR / "es_cumulative_delta.valid.json"),
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
            return _valid_contract_analysis("ES")

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
    output = stdout.getvalue()
    assert '"contract": "ES"' in output
    assert '"termination_stage": "contract_market_read"' in output
    assert '"final_decision": "NO_TRADE"' in output
