# Implementation-First Directive

This project has enough readiness/audit scaffolding for now. Future LLM work must prioritize making the NTB Marimo Console usable as an operator workstation.

## Prime Directive

Every prompt must produce working app behavior, runtime wiring, UI usability, or a concrete bug fix.

If a prompt mostly creates or edits readiness audits, proof-precondition documents, release-candidate prose, evidence taxonomy, or markdown assertion tests, the prompt has failed unless the human explicitly requested that exact artifact.

## Stop Doing This

Do not spend cycles on:

- repeat readiness audits,
- proof-boundary restatements,
- release-candidate prose churn,
- evidence taxonomy rewrites,
- broad defensive bookkeeping,
- markdown tests that mainly assert exact wording,
- documenting that something is unproven when the implementation gap is already known.

These activities are allowed only when they are directly required by a concrete implementation change in the same prompt.

## Do This Instead

Prioritize work that makes the app usable:

- wire missing live/runtime functionality,
- connect data ingestion to app state,
- route normalized chart bars into the bar builder,
- surface quote, chart, freshness, and blocked-state status in Marimo,
- make the operator workflow clear and usable,
- build fixture/mocked full-session dry runs,
- fix bugs that block operator use,
- add focused behavior tests for changed code.

## Current Highest-Value Implementation Path

1. Implement direct `CHART_FUTURES` subscription/parsing in the explicit live runtime path.
2. Normalize live chart frames into bar messages accepted by `ChartFuturesBarBuilder`.
3. Route chart-bar state into live observable snapshots and Marimo surfaces.
4. Show per-contract status for `ES`, `NQ`, `CL`, `6E`, and `MGC`: quote fresh, chart building/complete/missing, query blocked reason.
5. Run a fixture/mocked end-to-end operator-session rehearsal that proves the app can be used without Schwab credentials.
6. Only after the implementation exists, capture sanitized live proof if the human explicitly authorizes it.

## Testing Rule

Run targeted tests for changed or risk-adjacent behavior. Prefer tests that execute code paths over tests that inspect prose.

Good tests:

- parser tests,
- stream-session tests,
- bar-builder tests,
- live observable snapshot tests,
- Marimo surface/rendering tests,
- query-gate fail-closed tests,
- no repeated login / no fixture fallback tests.

Avoid adding tests whose main purpose is to lock down documentation wording.

## Documentation Rule

Documentation is secondary. Update docs only when:

- user-facing operation changed,
- a command/runbook changed,
- a safety-critical boundary would otherwise be misleading,
- the human explicitly requested a proof artifact.

No more audit-only roadmap steps.

## Required Final Answer Shape

Every future implementation prompt should answer these first:

- New working behavior:
- What the operator can now do:
- Targeted tests run:
- Remaining blocker:

If “New working behavior” is empty or mostly says “documented readiness,” the work did not meet this directive.

## Safety Boundaries That Still Apply

- Default launch remains non-live.
- Live behavior remains explicit opt-in.
- Do not inspect or print secrets or token files.
- Do not print credentials, tokens, URLs, customer IDs, correl IDs, account IDs, auth headers, app keys, authorization payloads, raw market values, or raw streamer payloads.
- No broker/order/execution/account/fill/P&L automation.
- Manual query only.
- Manual execution only.
- The preserved engine remains the sole decision authority.
- Final target universe remains `ES`, `NQ`, `CL`, `6E`, `MGC`.
- `ZN` and `GC` remain excluded.
- `MGC` is not `GC`.
- No fixture fallback after live failure.
- Preserve the 15-second minimum refresh floor.

The purpose of these safety boundaries is to keep implementation honest, not to justify endless audit loops.
