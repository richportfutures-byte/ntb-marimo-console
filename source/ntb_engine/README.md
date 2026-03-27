# NinjaTradeBuilder

NinjaTradeBuilder is a staged futures-evaluation runtime for a simulated trading challenge. It validates structured market packets, runs contract-specific Stage A+B analysis plus shared Stage C/D decision logic, and fails closed through strict schema validation rather than forcing trades or improvising around missing data.

## Current Status

- Priority 1 behavioral baseline is frozen and validated on the canonical contract edge-case matrix.
- The repo is installable as a Python package.
- Thin operator CLIs exist for local pipeline execution and operator-invoked readiness verification.
- Gemini execution uses bounded timeout and retry policy with clear failure output.
- Local JSONL per-run audit logging exists.
- GitHub Actions now runs install, test, and deterministic CLI smoke checks on push and PR.

This is a controlled Python/operator deployment surface. It is not a full production deployment stack.

## Quick Install

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

## Minimal CLI Example

```bash
export GEMINI_API_KEY=your_existing_key
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ninjatradebuilder.cli \
  --packet tests/fixtures/packets.valid.json \
  --contract ES \
  --audit-log ./logs/ninjatradebuilder.audit.jsonl
```

If `--packet` is already a single `historical_packet_v1` JSON object, omit `--contract`.

## Readiness Verification Harness

The repo now includes an operator-invoked readiness verification CLI for the frozen `readiness_engine_output_v1` contract. It is intended for disciplined human-triggered verification runs and audit capture, not CI, not autonomous monitoring, and not background polling.

Example single-contract runtime-input verification:

```bash
export GEMINI_API_KEY=your_existing_key
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ninjatradebuilder.readiness_verify \
  --runtime-input-file tests/fixtures/readiness/zn_runtime_inputs.valid.json \
  --trigger-file tests/fixtures/readiness/zn_recheck_trigger.valid.json \
  --contract ZN
```

Example all-contract packet-bundle sweep:

```bash
export GEMINI_API_KEY=your_existing_key
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ninjatradebuilder.readiness_verify \
  --packet-file tests/fixtures/packets.valid.json \
  --trigger-file tests/fixtures/readiness/zn_recheck_trigger.valid.json \
  --all-contracts
```

Artifacts default to `./artifacts/readiness-verification/<timestamp>.json` unless `--artifact-file` is provided. CI still does **not** run live Gemini readiness verification.

## Required Environment Variables

- `GEMINI_API_KEY`

Optional runtime policy variables:

- `NINJATRADEBUILDER_GEMINI_MODEL`
- `NINJATRADEBUILDER_GEMINI_TIMEOUT_SECONDS`
- `NINJATRADEBUILDER_GEMINI_MAX_RETRIES`
- `NINJATRADEBUILDER_GEMINI_RETRY_INITIAL_DELAY_SECONDS`
- `NINJATRADEBUILDER_GEMINI_RETRY_MAX_DELAY_SECONDS`

## Key Docs

- Operator quickstart: [docs/operator-quickstart.md](docs/operator-quickstart.md)
- Priority 1 conformance baseline: [docs/priority-1-conformance-baseline.md](docs/priority-1-conformance-baseline.md)
- Deployment and integration readiness: [docs/deployment-integration-readiness.md](docs/deployment-integration-readiness.md)
- User workflow narrative: [docs/user-workflow-narrative.md](docs/user-workflow-narrative.md)

## Architecture Summary

- `src/ninjatradebuilder/schemas/`: strict input, packet, and stage-output models
- `src/ninjatradebuilder/prompt_assets.py`: prompt registry for Prompts 1-9
- `src/ninjatradebuilder/runtime.py`: prompt execution, contract enforcement, and boundary validation
- `src/ninjatradebuilder/pipeline.py`: official Stage A -> D orchestration entrypoint
- `src/ninjatradebuilder/gemini_adapter.py`: Gemini structured-output adapter with bounded provider policy
- `src/ninjatradebuilder/cli.py`: thin operator-facing CLI

## Known Limits

- No service wrapper or HTTP deployment surface
- No persistent audit sink beyond local JSONL operator logs
- No aggregated metrics or broader observability layer
- No database, queue, or hosted logging integration
- No live Gemini execution in CI

## CI

GitHub Actions runs a thin smoke workflow on every push and pull request:

- editable package install
- full test suite
- deterministic CLI smoke path with no live Gemini dependency
