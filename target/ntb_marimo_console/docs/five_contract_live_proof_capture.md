# Five-Contract Live Proof Capture

This runbook documents the R20 proof-capture foundation for the R19 real-live proof gap.

The capture script is an artifact generator. It does not change default launch behavior, app workflow behavior, CI behavior, or the canonical non-live harness. It does not open Schwab access by itself.

## Fixture-Safe Default

Run from `target/ntb_marimo_console`:

```bash
PYTHONPATH=src python3 scripts/capture_five_contract_live_proof.py
```

Equivalent explicit fixture commands:

```bash
PYTHONPATH=src python3 scripts/capture_five_contract_live_proof.py --fixture
PYTHONPATH=src python3 scripts/capture_five_contract_live_proof.py --dry-run
```

Fixture output is sanitized JSON and is safe for tests. It includes `fixture_verification: FIXTURE_PASS`, but its `proof_verdict` remains `MANUAL_REQUIRED`. A fixture artifact must not be used as real-live proof.

## Manual Live Artifact Path

Live proof artifact creation requires explicit `--live` and explicit operator attestations. The script refuses live mode when any required observation is missing.

Template command shape:

```bash
PYTHONPATH=src python3 scripts/capture_five_contract_live_proof.py \
  --live \
  --operator-attested-live \
  --levelone-observed ES,NQ,CL,6E,MGC \
  --chart-observed ES,NQ,CL,6E,MGC \
  --one-connection-observed \
  --no-relogin-observed \
  --no-fixture-fallback-observed \
  --fail-closed-query-readiness-observed \
  --manual-only-execution-observed \
  --preserved-engine-authority-observed \
  --sensitive-output-reviewed \
  --output docs/live_proof/five_contract_live_proof_REVIEWED_RUN_ID.json
```

Use `--levelone-blocked` or `--chart-blocked` for any final target contract that was attempted but not observed. A live artifact only reaches `PASS` when all five final target contracts are observed for both `LEVELONE_FUTURES` and `CHART_FUTURES`, and every required discipline assertion is supplied. `LEVELONE_FUTURES` observations must not be reused as `CHART_FUTURES` observations.

## What The Artifact Contains

The JSON artifact includes:

- schema name and version
- generation timestamp
- mode: `fixture` or `live`
- final target contracts: `ES`, `NQ`, `CL`, `6E`, `MGC`
- excluded contracts: `ZN`, `GC`
- per-contract `LEVELONE_FUTURES` and `CHART_FUTURES` rows
- one-connection discipline observation
- repeated-refresh/no-relogin observation
- no-fixture-fallback-after-live-failure assertion
- fail-closed query-readiness assertion
- manual-only execution assertion
- preserved-engine authority assertion
- sensitive-output scan result
- proof verdict: `PASS`, `PARTIAL`, `FAIL`, or `MANUAL_REQUIRED`
- limitations

## Current Automation Boundary

The existing Schwab market-data live harness remains a manual, opt-in, single-symbol `LEVELONE_FUTURES` smoke path. The operator live runtime rehearsal can request and route `CHART_FUTURES` bar events through the explicit runtime path, but that implementation is not a live proof until an operator runs it and records sanitized direct chart evidence.

Because of that boundary, this R20 path does not add a new live Schwab chart streamer or refactor the live harness. It creates a repository-safe manual artifact template so the operator can record a reviewed five-contract rehearsal without committing raw live material. A future `CHART_FUTURES` artifact must be backed by direct chart-futures evidence, not by the recorded `LEVELONE_FUTURES` result.

## Safety Invariants

- Fixture mode is the default.
- Real-live artifact creation requires explicit `--live`.
- The script does not read private environment files.
- The script does not accept or print live credential material.
- The script writes an output file only after sanitizer checks pass.
- Fixture output cannot satisfy the real-live proof gate.
- Default launch remains non-live.
- CI remains fixture-safe.
- No fixture fallback after live failure remains represented as a required assertion.
- The preserved engine remains the only decision authority.
- Execution remains manual-only.

## R19 Status

This foundation does not mark R19 READY. A bounded five-contract `LEVELONE_FUTURES` live result is now recorded, but `CHART_FUTURES` delivery, full live-session Marimo usability, entitlement and rollover robustness, and production release readiness remain unproven.
