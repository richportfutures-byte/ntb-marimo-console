from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from pathlib import Path

from ninjatradebuilder.cli import run_cli as run_runtime_cli
from ninjatradebuilder.packet_compiler.cli import run_cli as run_compiler_cli


def _valid_contract_analysis() -> dict:
    return {
        "$schema": "contract_analysis_v1",
        "stage": "contract_market_read",
        "contract": "ES",
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
        "structural_notes": "Compiled packet smoke path remains balanced.",
        "outcome": "NO_TRADE",
        "conflicting_signals": ["balance remains intact"],
        "assumptions": [],
    }


def main() -> int:
    os.environ.setdefault("GEMINI_API_KEY", "ci-placeholder")

    historical_input = Path("tests/fixtures/compiler/es_historical_input.valid.json")
    overlay_input = Path("tests/fixtures/compiler/es_overlay.assisted.valid.json")
    calendar_input = Path("tests/fixtures/compiler/es_calendar.valid.json")
    breadth_input = Path("tests/fixtures/compiler/es_breadth.valid.json")
    index_cash_tone_input = Path("tests/fixtures/compiler/es_index_cash_tone.valid.json")
    cumulative_delta_input = Path("tests/fixtures/compiler/es_cumulative_delta.valid.json")
    if (
        not historical_input.is_file()
        or not overlay_input.is_file()
        or not calendar_input.is_file()
        or not breadth_input.is_file()
        or not index_cash_tone_input.is_file()
        or not cumulative_delta_input.is_file()
    ):
        print("Compiler smoke runner could not find ES compiler fixtures", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="ntb-compiler-smoke-") as tmp_dir:
        packet_path = Path(tmp_dir) / "es.packet.json"
        compiler_stdout = io.StringIO()
        compiler_stderr = io.StringIO()
        compile_exit_code = run_compiler_cli(
            [
                "--contract",
                "ES",
                "--historical-input",
                str(historical_input),
                "--overlay",
                str(overlay_input),
                "--calendar-input",
                str(calendar_input),
                "--breadth-input",
                str(breadth_input),
                "--index-cash-tone-input",
                str(index_cash_tone_input),
                "--cumulative-delta-input",
                str(cumulative_delta_input),
                "--output",
                str(packet_path),
            ],
            stdout=compiler_stdout,
            stderr=compiler_stderr,
        )
        if compile_exit_code != 0:
            print(compiler_stderr.getvalue(), file=sys.stderr, end="")
            return compile_exit_code

        class FakeGeminiAdapter:
            def __init__(self, *, client, model, timeout_seconds=None, max_retries=0):
                self.client = client

            def generate_structured(self, request):
                return _valid_contract_analysis()

        import ninjatradebuilder.cli as cli_module

        cli_module.GeminiResponsesAdapter = FakeGeminiAdapter

        runtime_stdout = io.StringIO()
        runtime_stderr = io.StringIO()
        runtime_exit_code = run_runtime_cli(
            [
                "--packet",
                str(packet_path),
            ],
            stdout=runtime_stdout,
            stderr=runtime_stderr,
            client_factory=lambda config: config,
        )
        if runtime_exit_code != 0:
            print(runtime_stderr.getvalue(), file=sys.stderr, end="")
            return runtime_exit_code

        compiler_summary = json.loads(compiler_stdout.getvalue())
        runtime_summary = json.loads(runtime_stdout.getvalue())
        assert compiler_summary["contract"] == "ES"
        assert compiler_summary["packet_schema"] == "historical_packet_v1"
        assert runtime_summary["contract"] == "ES"
        assert runtime_summary["termination_stage"] == "contract_market_read"
        assert runtime_summary["final_decision"] == "NO_TRADE"

    print("deterministic_compiler_runtime_smoke=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
