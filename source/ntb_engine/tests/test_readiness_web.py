from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from ninjatradebuilder.readiness_web import build_readiness_web_app

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "readiness"
PACKETS_FIXTURE = Path(__file__).parent / "fixtures" / "packets.valid.json"


def _start_response_capture() -> tuple[dict[str, Any], Any]:
    captured: dict[str, Any] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = headers

    return captured, start_response


def _packet_payload(contract: str) -> dict[str, Any]:
    packets_fixture = json.loads(PACKETS_FIXTURE.read_text())
    return {
        "$schema": "historical_packet_v1",
        "challenge_state": packets_fixture["shared"]["challenge_state"],
        "attached_visuals": packets_fixture["shared"]["attached_visuals"],
        "contract_metadata": packets_fixture["contracts"][contract]["contract_metadata"],
        "market_packet": packets_fixture["contracts"][contract]["market_packet"],
        "contract_specific_extension": packets_fixture["contracts"][contract]["contract_specific_extension"],
    }


def _expected_readiness_output(contract: str) -> dict[str, Any]:
    timestamp = "2026-01-14T15:05:00Z"
    if contract in {"CL", "6E"}:
        timestamp = "2026-01-14T14:05:00Z"
    return {
        "$schema": "readiness_engine_output_v1",
        "stage": "readiness_engine",
        "authority": "ESCALATE_ONLY",
        "contract": contract,
        "timestamp": timestamp,
        "status": "WAIT_FOR_TRIGGER",
        "doctrine_gates": [
            {
                "gate": "data_sufficiency_gate",
                "state": "PASS",
                "rationale": "Inputs are complete.",
            },
            {
                "gate": "context_alignment_gate",
                "state": "PASS",
                "rationale": "Context remains aligned.",
            },
            {
                "gate": "structure_quality_gate",
                "state": "PASS",
                "rationale": "Structure remains acceptable.",
            },
            {
                "gate": "trigger_gate",
                "state": "WAIT",
                "rationale": "Waiting for the recheck time.",
            },
            {
                "gate": "risk_window_gate",
                "state": "PASS",
                "rationale": "Risk window remains open.",
            },
            {
                "gate": "lockout_gate",
                "state": "PASS",
                "rationale": "No lockout is active.",
            },
        ],
        "trigger_data": {
            "family": "recheck_at_time",
            "recheck_at_time": "2026-01-14T15:15:00Z",
            "price_level": None,
        },
        "wait_for_trigger_reason": "timing_window_not_open",
        "lockout_reason": None,
        "insufficient_data_reasons": [],
        "missing_inputs": [],
    }


def test_readiness_web_root_serves_basic_html_page() -> None:
    app = build_readiness_web_app(client_factory=lambda config: config)
    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": "/",
        "CONTENT_LENGTH": "0",
        "wsgi.input": io.BytesIO(b""),
    }
    response_capture, start_response = _start_response_capture()

    response_body = b"".join(app(environ, start_response)).decode("utf-8")

    assert response_capture["status"] == "200 OK"
    assert "<title>NinjaTradeBuilder Readiness</title>" in response_body
    assert 'id="packet-text"' in response_body
    assert 'id="runtime-input-text"' in response_body
    assert 'id="trigger-text"' in response_body
    assert 'id="response-output"' in response_body


def test_readiness_web_endpoint_executes_zn_fixture_path(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    runtime_inputs = json.loads((FIXTURES_DIR / "zn_runtime_inputs.valid.json").read_text())
    readiness_trigger = json.loads((FIXTURES_DIR / "zn_recheck_trigger.valid.json").read_text())
    expected_output = json.loads((FIXTURES_DIR / "zn_wait_for_trigger.expected.json").read_text())
    captured_adapter: dict[str, Any] = {}

    class FakeGeminiAdapter:
        def __init__(self, *, client, model, timeout_seconds=None, max_retries=0):
            captured_adapter["client"] = client
            captured_adapter["model"] = model

        def generate_structured(self, request):
            captured_adapter["prompt_id"] = request.prompt_id
            captured_adapter["rendered_prompt"] = request.rendered_prompt
            return expected_output

    monkeypatch.setattr("ninjatradebuilder.readiness_web.GeminiResponsesAdapter", FakeGeminiAdapter)

    app = build_readiness_web_app(client_factory=lambda config: config)
    request_body = json.dumps(
        {
            "runtime_inputs": runtime_inputs,
            "readiness_trigger": readiness_trigger,
        }
    ).encode("utf-8")
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/api/readiness",
        "CONTENT_LENGTH": str(len(request_body)),
        "wsgi.input": io.BytesIO(request_body),
    }
    response_capture, start_response = _start_response_capture()

    response_body = b"".join(app(environ, start_response))

    assert response_capture["status"] == "200 OK"
    assert json.loads(response_body.decode("utf-8")) == expected_output
    assert captured_adapter["client"].api_key == "test-key"
    assert captured_adapter["prompt_id"] == 10
    assert '"contract_specific_macro_state": "auction_sensitive"' in captured_adapter["rendered_prompt"]


def test_readiness_web_endpoint_accepts_zn_packet_input(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    packet = _packet_payload("ZN")
    readiness_trigger = json.loads((FIXTURES_DIR / "zn_recheck_trigger.valid.json").read_text())
    expected_output = json.loads((FIXTURES_DIR / "zn_wait_for_trigger.expected.json").read_text())
    captured_adapter: dict[str, Any] = {}

    class FakeGeminiAdapter:
        def __init__(self, *, client, model, timeout_seconds=None, max_retries=0):
            captured_adapter["client"] = client

        def generate_structured(self, request):
            captured_adapter["prompt_id"] = request.prompt_id
            captured_adapter["rendered_prompt"] = request.rendered_prompt
            return expected_output

    monkeypatch.setattr("ninjatradebuilder.readiness_web.GeminiResponsesAdapter", FakeGeminiAdapter)

    app = build_readiness_web_app(client_factory=lambda config: config)
    request_body = json.dumps(
        {
            "packet": packet,
            "readiness_trigger": readiness_trigger,
        }
    ).encode("utf-8")
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/api/readiness",
        "CONTENT_LENGTH": str(len(request_body)),
        "wsgi.input": io.BytesIO(request_body),
    }
    response_capture, start_response = _start_response_capture()

    response_body = b"".join(app(environ, start_response))

    assert response_capture["status"] == "200 OK"
    assert json.loads(response_body.decode("utf-8")) == expected_output
    assert captured_adapter["client"].api_key == "test-key"
    assert captured_adapter["prompt_id"] == 10
    assert '"contract_specific_macro_state": "auction_sensitive"' in captured_adapter["rendered_prompt"]


def test_readiness_web_endpoint_accepts_es_packet_input(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    packet = _packet_payload("ES")
    readiness_trigger = json.loads((FIXTURES_DIR / "zn_recheck_trigger.valid.json").read_text())
    expected_output = _expected_readiness_output("ES")
    captured_adapter: dict[str, Any] = {}

    class FakeGeminiAdapter:
        def __init__(self, *, client, model, timeout_seconds=None, max_retries=0):
            captured_adapter["client"] = client

        def generate_structured(self, request):
            captured_adapter["prompt_id"] = request.prompt_id
            captured_adapter["rendered_prompt"] = request.rendered_prompt
            return expected_output

    monkeypatch.setattr("ninjatradebuilder.readiness_web.GeminiResponsesAdapter", FakeGeminiAdapter)

    app = build_readiness_web_app(client_factory=lambda config: config)
    request_body = json.dumps(
        {
            "packet": packet,
            "readiness_trigger": readiness_trigger,
        }
    ).encode("utf-8")
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/api/readiness",
        "CONTENT_LENGTH": str(len(request_body)),
        "wsgi.input": io.BytesIO(request_body),
    }
    response_capture, start_response = _start_response_capture()

    response_body = b"".join(app(environ, start_response))

    assert response_capture["status"] == "200 OK"
    assert json.loads(response_body.decode("utf-8")) == expected_output
    assert captured_adapter["client"].api_key == "test-key"
    assert captured_adapter["prompt_id"] == 10
    assert '"contract_specific_macro_state": "breadth_cash_delta_aligned"' in captured_adapter["rendered_prompt"]


def test_readiness_web_endpoint_accepts_nq_packet_input(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    packet = _packet_payload("NQ")
    readiness_trigger = json.loads((FIXTURES_DIR / "zn_recheck_trigger.valid.json").read_text())
    expected_output = _expected_readiness_output("NQ")
    captured_adapter: dict[str, Any] = {}

    class FakeGeminiAdapter:
        def __init__(self, *, client, model, timeout_seconds=None, max_retries=0):
            captured_adapter["client"] = client

        def generate_structured(self, request):
            captured_adapter["prompt_id"] = request.prompt_id
            captured_adapter["rendered_prompt"] = request.rendered_prompt
            return expected_output

    monkeypatch.setattr("ninjatradebuilder.readiness_web.GeminiResponsesAdapter", FakeGeminiAdapter)

    app = build_readiness_web_app(client_factory=lambda config: config)
    request_body = json.dumps(
        {
            "packet": packet,
            "readiness_trigger": readiness_trigger,
        }
    ).encode("utf-8")
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/api/readiness",
        "CONTENT_LENGTH": str(len(request_body)),
        "wsgi.input": io.BytesIO(request_body),
    }
    response_capture, start_response = _start_response_capture()

    response_body = b"".join(app(environ, start_response))

    assert response_capture["status"] == "200 OK"
    assert json.loads(response_body.decode("utf-8")) == expected_output
    assert captured_adapter["client"].api_key == "test-key"
    assert captured_adapter["prompt_id"] == 10
    assert '"contract_specific_macro_state": "relative_strength_leader"' in captured_adapter["rendered_prompt"]


def test_readiness_web_endpoint_accepts_cl_packet_input(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    packet = _packet_payload("CL")
    readiness_trigger = json.loads((FIXTURES_DIR / "zn_recheck_trigger.valid.json").read_text())
    expected_output = _expected_readiness_output("CL")
    captured_adapter: dict[str, Any] = {}

    class FakeGeminiAdapter:
        def __init__(self, *, client, model, timeout_seconds=None, max_retries=0):
            captured_adapter["client"] = client

        def generate_structured(self, request):
            captured_adapter["prompt_id"] = request.prompt_id
            captured_adapter["rendered_prompt"] = request.rendered_prompt
            return expected_output

    monkeypatch.setattr("ninjatradebuilder.readiness_web.GeminiResponsesAdapter", FakeGeminiAdapter)

    app = build_readiness_web_app(client_factory=lambda config: config)
    request_body = json.dumps(
        {
            "packet": packet,
            "readiness_trigger": readiness_trigger,
        }
    ).encode("utf-8")
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/api/readiness",
        "CONTENT_LENGTH": str(len(request_body)),
        "wsgi.input": io.BytesIO(request_body),
    }
    response_capture, start_response = _start_response_capture()

    response_body = b"".join(app(environ, start_response))

    assert response_capture["status"] == "200 OK"
    assert json.loads(response_body.decode("utf-8")) == expected_output
    assert captured_adapter["client"].api_key == "test-key"
    assert captured_adapter["prompt_id"] == 10
    assert '"contract_specific_macro_state": "eia_sensitive"' in captured_adapter["rendered_prompt"]
