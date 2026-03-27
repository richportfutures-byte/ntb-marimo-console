from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

from ninjatradebuilder.cli import run_cli


def _valid_contract_analysis() -> dict:
    return {
        "$schema": "contract_analysis_v1",
        "stage": "contract_market_read",
        "contract": "ES",
        "timestamp": "2026-01-14T14:06:00Z",
        "market_regime": "range_bound",
        "directional_bias": "bullish",
        "key_levels": {
            "support_levels": [4485.0],
            "resistance_levels": [4495.0],
            "pivot_level": 4490.0,
        },
        "evidence_score": 6,
        "confidence_band": "MEDIUM",
        "value_context": {
            "relative_to_prior_value_area": "inside",
            "relative_to_current_developing_value": "inside_value",
            "relative_to_vwap": "above",
            "relative_to_prior_day_range": "inside",
        },
        "structural_notes": "Price is holding above pivot with one conflicting signal.",
        "outcome": "NO_TRADE",
        "conflicting_signals": ["conflict"],
        "assumptions": [],
    }


def main() -> int:
    os.environ.setdefault("GEMINI_API_KEY", "ci-placeholder")
    packet_path = Path("tests/fixtures/packets.valid.json")
    if not packet_path.is_file():
        print("Smoke runner could not find tests/fixtures/packets.valid.json", file=sys.stderr)
        return 2

    captured: dict[str, object] = {}

    class FakeGeminiAdapter:
        def __init__(self, *, client, model, timeout_seconds=None, max_retries=0):
            captured["model"] = model
            captured["timeout_seconds"] = timeout_seconds
            captured["max_retries"] = max_retries

        def generate_structured(self, request):
            captured["prompt_id"] = request.prompt_id
            return _valid_contract_analysis()

    import ninjatradebuilder.cli as cli_module

    cli_module.GeminiResponsesAdapter = FakeGeminiAdapter

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = run_cli(
        [
            "--packet",
            str(packet_path),
            "--contract",
            "ES",
        ],
        stdout=stdout,
        stderr=stderr,
        client_factory=lambda config: config,
    )
    if exit_code != 0:
        print(stderr.getvalue(), file=sys.stderr, end="")
        return exit_code

    payload = json.loads(stdout.getvalue())
    assert payload["contract"] == "ES"
    assert payload["termination_stage"] == "contract_market_read"
    assert payload["final_decision"] == "NO_TRADE"
    assert captured["prompt_id"] == 2
    assert captured["timeout_seconds"] == 20
    assert captured["max_retries"] == 1
    print("deterministic_cli_smoke=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
