from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Iterable, Mapping
from io import BytesIO
from typing import Any
from wsgiref.simple_server import make_server

from .cli import _build_client, _normalize_for_json
from .config import DEFAULT_GEMINI_MODEL, ConfigError, GeminiStartupConfig, load_gemini_startup_config
from .gemini_adapter import GeminiAdapterError, GeminiResponsesAdapter
from .readiness_adapter import build_readiness_runtime_inputs_from_packet
from .runtime import run_readiness

ClientFactory = Callable[[GeminiStartupConfig], Any]

READINESS_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>NinjaTradeBuilder Readiness</title>
    <style>
      body { font-family: sans-serif; margin: 2rem; max-width: 1200px; }
      h1 { margin-bottom: 0.5rem; }
      .grid { display: grid; gap: 1rem; grid-template-columns: 1fr 1fr; }
      textarea { width: 100%; min-height: 18rem; font-family: monospace; font-size: 0.9rem; }
      .full { grid-column: 1 / -1; }
      button { padding: 0.75rem 1.25rem; font-size: 1rem; }
      pre { background: #f5f5f5; padding: 1rem; overflow: auto; min-height: 12rem; }
      label { display: block; font-weight: 600; margin-bottom: 0.35rem; }
      .error { color: #a00000; }
    </style>
  </head>
  <body>
    <h1>Readiness Engine</h1>
    <p>Paste or load either packet JSON or readiness runtime input JSON, plus readiness trigger JSON, then submit to the local readiness endpoint.</p>
    <form id="readiness-form">
      <div class="grid">
        <div>
          <label for="packet-file">Packet File</label>
          <input id="packet-file" type="file" accept=".json,application/json">
        </div>
        <div>
          <label for="packet-text">Packet JSON</label>
          <textarea id="packet-text" spellcheck="false"></textarea>
        </div>
        <div>
          <label for="runtime-input-file">Runtime Input File</label>
          <input id="runtime-input-file" type="file" accept=".json,application/json">
        </div>
        <div>
          <label for="trigger-file">Trigger File</label>
          <input id="trigger-file" type="file" accept=".json,application/json">
        </div>
        <div>
          <label for="runtime-input-text">Runtime Input JSON</label>
          <textarea id="runtime-input-text" spellcheck="false"></textarea>
        </div>
        <div>
          <label for="trigger-text">Trigger JSON</label>
          <textarea id="trigger-text" spellcheck="false"></textarea>
        </div>
        <div class="full">
          <button type="submit">Run readiness</button>
        </div>
        <div class="full">
          <label for="response-output">Validated Readiness JSON Response</label>
          <pre id="response-output"></pre>
        </div>
      </div>
    </form>
    <script>
      function wireFileInput(fileInputId, textareaId) {
        const fileInput = document.getElementById(fileInputId);
        const textarea = document.getElementById(textareaId);
        fileInput.addEventListener("change", async () => {
          const file = fileInput.files[0];
          if (!file) {
            return;
          }
          textarea.value = await file.text();
        });
      }

      wireFileInput("packet-file", "packet-text");
      wireFileInput("runtime-input-file", "runtime-input-text");
      wireFileInput("trigger-file", "trigger-text");

      document.getElementById("readiness-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        const responseOutput = document.getElementById("response-output");
        responseOutput.className = "";

        try {
          const packetText = document.getElementById("packet-text").value.trim();
          const runtimeInputText = document.getElementById("runtime-input-text").value.trim();
          const readinessTrigger = JSON.parse(document.getElementById("trigger-text").value);
          const requestPayload = {
            readiness_trigger: readinessTrigger
          };
          if (packetText) {
            requestPayload.packet = JSON.parse(packetText);
          } else {
            requestPayload.runtime_inputs = JSON.parse(runtimeInputText);
          }
          const response = await fetch("/api/readiness", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(requestPayload)
          });
          const payload = await response.json();
          responseOutput.textContent = JSON.stringify(payload, null, 2);
          if (!response.ok) {
            responseOutput.className = "error";
          }
        } catch (error) {
          responseOutput.className = "error";
          responseOutput.textContent = JSON.stringify(
            { error: String(error) },
            null,
            2
          );
        }
      });
    </script>
  </body>
</html>
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ninjatradebuilder.readiness_web",
        description="Serve a local readiness web interface.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--model", default=DEFAULT_GEMINI_MODEL)
    return parser


def _read_request_json(environ: Mapping[str, Any]) -> Mapping[str, Any]:
    content_length_raw = environ.get("CONTENT_LENGTH", "0")
    try:
        content_length = int(content_length_raw or "0")
    except ValueError as exc:
        raise ValueError("Request content length is invalid.") from exc

    body = environ["wsgi.input"].read(content_length)
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Request body did not contain valid JSON.") from exc

    if not isinstance(payload, Mapping):
        raise ValueError("Request body must decode to a JSON object.")
    return payload


def _json_response(start_response: Callable[[str, list[tuple[str, str]]], Any], status: str, payload: Mapping[str, Any]) -> list[bytes]:
    body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    start_response(
        status,
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ],
    )
    return [body]


def _html_response(start_response: Callable[[str, list[tuple[str, str]]], Any]) -> list[bytes]:
    body = READINESS_HTML.encode("utf-8")
    start_response(
        "200 OK",
        [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ],
    )
    return [body]


def build_readiness_web_app(
    *,
    model: str = DEFAULT_GEMINI_MODEL,
    client_factory: ClientFactory | None = None,
) -> Callable[[Mapping[str, Any], Callable[[str, list[tuple[str, str]]], Any]], Iterable[bytes]]:
    def app(
        environ: Mapping[str, Any],
        start_response: Callable[[str, list[tuple[str, str]]], Any],
    ) -> Iterable[bytes]:
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/")

        if method == "GET" and path == "/":
            return _html_response(start_response)

        if method == "POST" and path == "/api/readiness":
            try:
                payload = _read_request_json(environ)
                runtime_inputs = payload.get("runtime_inputs")
                packet = payload.get("packet")
                readiness_trigger = payload.get("readiness_trigger")
                if not isinstance(readiness_trigger, Mapping):
                    raise ValueError("readiness_trigger must be a JSON object.")
                if (runtime_inputs is None) == (packet is None):
                    raise ValueError(
                        "Request must include exactly one of runtime_inputs or packet."
                    )
                if packet is not None:
                    if not isinstance(packet, Mapping):
                        raise ValueError("packet must be a JSON object.")
                    runtime_inputs = build_readiness_runtime_inputs_from_packet(packet)
                elif not isinstance(runtime_inputs, Mapping):
                    raise ValueError("runtime_inputs must be a JSON object.")

                config = load_gemini_startup_config(model=model)
                adapter = GeminiResponsesAdapter(
                    client=_build_client(config, client_factory),
                    model=config.model,
                    timeout_seconds=config.timeout_seconds,
                    max_retries=config.max_retries,
                )
                result = run_readiness(
                    runtime_inputs=runtime_inputs,
                    readiness_trigger=readiness_trigger,
                    model_adapter=adapter,
                )
                return _json_response(
                    start_response,
                    "200 OK",
                    _normalize_for_json(result.validated_output),
                )
            except (ConfigError, ValueError) as exc:
                return _json_response(start_response, "400 Bad Request", {"error": str(exc)})
            except (GeminiAdapterError, ImportError) as exc:
                return _json_response(start_response, "502 Bad Gateway", {"error": str(exc)})

        return _json_response(start_response, "404 Not Found", {"error": "Not found."})

    return app


def run_server(argv: list[str] | None = None, *, client_factory: ClientFactory | None = None) -> int:
    args = build_parser().parse_args(argv)
    app = build_readiness_web_app(model=args.model, client_factory=client_factory)
    with make_server(args.host, args.port, app) as server:
        print(
            f"Readiness web interface listening on http://{args.host}:{args.port}",
            flush=True,
        )
        server.serve_forever()
    return 0


def main() -> int:
    return run_server()


if __name__ == "__main__":
    raise SystemExit(main())
