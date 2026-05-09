# R21/R22 Operator Workstation Launch & Usability Note

This note is the operator-facing summary of the current trader-usability audit. It does not change runtime behavior, default launch mode, stream manager behavior, or operator UI surfaces. It does not authorize trades.

## How To Launch In Non-Live Mode

The default app launch is non-live. Schwab credentials are not required.

POSIX shells, from `target/ntb_marimo_console`:

```bash
NTB_CONSOLE_PROFILE=preserved_es_phase1 \
PYTHONPATH=src .venv/bin/python -m marimo run src/ntb_marimo_console/operator_console_app.py
```

Substitute one of the five final target preserved profiles:

- `preserved_es_phase1` (ES)
- `preserved_nq_phase1` (NQ)
- `preserved_cl_phase1` (CL)
- `preserved_6e_phase1` (6E)
- `preserved_mgc_phase1` (MGC)

`MGC` is Micro Gold and is the gold contract for this application. `MGC` is not `GC`. `GC` is excluded and is not a synonym, alias, or substitute for `MGC`. The legacy/historical `preserved_zn_phase1` profile remains as current-state legacy only and is not part of the final target universe.

For a no-credentials cross-profile sanity check that does not start Marimo, run the canonical non-live acceptance verifier:

```bash
PYTHONPATH=target/ntb_marimo_console/src python3 target/ntb_marimo_console/scripts/verify_non_live_acceptance.py
```

## What The Operator Can Currently Use

For each final target preserved profile (`ES`, `NQ`, `CL`, `6E`, `MGC`) the non-live launch path produces an operator cockpit shell that exposes:

- session header with active contract, profile id, and session date
- five-contract readiness summary with one non-live row each for `ES`, `NQ`, `CL`, `6E`, and `MGC`
- pre-market brief surface with status, setup summaries, and warnings
- readiness matrix with contract status, event risk, and hard-lockout context
- trigger table with declared triggers and validity
- live observable surface with structured snapshot (live market data status defaults to `Market data unavailable` because default launch is non-live)
- query action surface with watchman gate status, live query status, query action status, blocked reasons, status summary, and next action
- session lifecycle, supported profile operations, and recent session evidence surfaces (per the existing acceptance matrix)

Cross-profile non-live launchability is regression-tested by `tests/test_workstation_launch_smoke.py`.

## What Is Still Not Yet Trader-Usable

- Real Schwab live market data is not wired into default launch. It remains explicitly opt-in via the operator-run R18 manual rehearsal and the single-quote Schwab manual live harness. Default launch stays non-live.
- Real five-contract live readiness is not proven by the new summary. The summary is fixture-backed/non-live and intentionally reports live market data as unavailable unless explicit fixture inputs provide otherwise. Real Schwab readiness still requires explicit opt-in and sanitized live proof.
- Real five-contract Schwab live proof remains operator-run and pending. R19 marks the workstation as `CONDITIONALLY READY` until a sanitized real five-contract Schwab live session artifact is reviewed and committed.
- Broker order routing, order placement, fills, account state, and P&L behavior are deliberately absent. Trade execution is manual-only on the operator's own platform.
- Replay, performance review, and proof capture are read-only audit/evidence surfaces and do not authorize trades.

## Trader-Usability Verdict

The current workstation is **partially trader-usable** for personal cockpit use:

- Non-live launch and operator cockpit surfaces work for all five final target preserved profiles.
- The cockpit now includes a fixture-backed five-contract readiness summary, so an operator can see all final target profile ids, startup readiness, market-data availability, query-gate state, blocked reasons, evidence/replay status, and manual-only/preserved-engine boundaries in one place.
- Quote freshness and pipeline gating are wired through fixture-safe paths and fail closed when data is missing, stale, or mismatched.
- Real Schwab live data and real five-contract live readiness remain pending operator-run validation and sanitized proof.

## R22 Summary Surface Status

The R22 fixture-backed summary reads from already-available single-profile startup and surface outputs and renders one row per final target contract with: profile, final-target support status, preflight status, startup readiness, market-data availability, trigger/query state, blocked reasons, evidence/replay status, and manual-only/preserved-engine boundaries.

That surface:

- does not require Schwab credentials,
- does not require live data,
- does not let fixture evidence satisfy real-live proof gates,
- preserves fail-closed behavior,
- preserves manual-only execution,
- preserves the preserved engine as the sole decision authority,
- preserves the 15-second minimum refresh floor,
- preserves the rule that no fixture fallback occurs after live failure,
- preserves the fixture-safe default tests and the default non-live launch.

Real Schwab five-contract live proof remains a separate operator-run gate and is not unblocked by this surface.

## Non-Goals

R21/R22 does not:

- modify default launch mode,
- enable live Schwab traffic by default,
- introduce any broker, order, fill, account, or P&L behavior,
- introduce a second decision authority outside the preserved engine,
- promote replay, performance review, or proof capture into a trade-authorizing surface,
- promote fixture artifacts into real-live proof,
- re-promote `ZN` into final target support,
- map `MGC` to `GC` or `GC` to `MGC`.
