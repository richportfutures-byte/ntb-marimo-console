# NTB Marimo Console Antigravity Rule

## Mission

Deliver a live-data-ready, observation-only Marimo operator workstation for explicit testing.

The workstation must let the operator:
- Launch the cockpit.
- See ES, NQ, CL, 6E, and MGC only.
- See what is live, what is blocked, why it is blocked, and whether the preserved pipeline can be manually queried.
- Consume real Schwab live data only through explicit live opt-in.
- Track LEVELONE_FUTURES and CHART_FUTURES separately per contract.
- Keep missing, stale, partial, unsupported, replay-derived, synthetic, display-derived, or unproven states fail-closed.
- Review bounded cockpit/evidence/replay records without those records becoming trade signals.

## Autonomous Live-Data Proof Loop

Use the latest committed checkpoint and latest live rehearsal JSON/result as source of truth.

Repeat:
1. Identify the current live-data blocker.
2. If the blocker is app-side, fix it and commit.
3. If live evidence is required, run or request the exact safe explicit live command.
4. Interpret returned live output and continue.
5. Stop only when:
   - the live-data-ready observation workstation is honestly achieved
   - a provider/entitlement limitation is proven and recorded
   - a safety boundary prevents continuation
   - operator input/live output is required

Do not wait for micro-prompts when the next implementation slice is clear.
Do not turn implementation work into audit-only or documentation-only work.

## Hard Boundaries

- Observation-only.
- No broker/order/execution/account/fill/P&L behavior.
- Manual query only.
- Manual execution only.
- Preserved engine remains the sole decision authority.
- Live data may arm, block, invalidate, or annotate a query, but may not approve trades.
- Do not make default launch live.
- Live behavior must remain explicit opt-in.
- No fixture fallback after live failure.
- No repeated Schwab login per Marimo refresh.
- Marimo refresh/render must read from cache and must not reconnect/re-login.
- Preserve the 15-second minimum refresh floor.
- Preserve ES, NQ, CL, 6E, and MGC only.
- Preserve ZN and GC exclusion.
- MGC is Micro Gold. Do not map it to GC.
- Display/view-model/rendering code must not create QUERY_READY.
- Stale, missing, unsupported, lockout, invalidated, non-provenance, display-derived, replay-derived, or synthetic states must never produce QUERY_READY.
- Do not touch source/ntb_engine unless explicitly necessary. Ask first if required.

## Secret and Live Credential Handling

Allowed:
- A bounded live rehearsal or live cockpit command may source `.state/secrets/schwab_live.env` only as shell environment setup for that single command.
- Use `set +x` before sourcing the env file.
- The app/runtime may read the configured token path internally after explicit live opt-in.

Not allowed:
- Do not open, cat, grep, sed, parse, summarize, print, paste, or commit `.state/secrets/schwab_live.env`.
- Do not open, cat, grep, sed, parse, summarize, print, paste, or commit token files.
- Do not run `env`, `printenv`, shell debug tracing, verbose auth logging, or anything that could dump environment variables.
- Do not print credentials, auth headers, app keys, token JSON, streamer URLs, customer IDs, correl IDs, account IDs, authorization payloads, raw quote values, raw bar values, or raw streamer payloads.
- Do not record raw market values.

## Verification Discipline

Use targeted verification, not broad suites by default.

Expected checks for changed code:
- Relevant targeted pytest files for changed surfaces.
- `python3 scripts/launch_operator_cockpit.py --dry-run`
- `python3 scripts/launch_operator_cockpit.py --print-command`
- `PYTHONPATH=src:../../source/ntb_engine/src:. uv run python scripts/run_operator_live_runtime_rehearsal.py --readiness-gate`
- `python3 -m compileall` on changed Python files
- `git diff --check`
- Ruff on changed Python files if available
- `git status` before and after commit

Commit when verification passes.
Do not push unless explicitly directed.
Do not commit partial or unsafe work unless explicitly directed.

## Current Known Blocker

Current checkpoint should include `a99350c`.

The live cockpit runtime start/register lifecycle is wired. The current blocker is:

No default live Schwab client-factory builder is registered. The live cockpit can start/register a runtime, but without a default builder it still fails closed at `client_factory_unavailable`.

The next implementation objective is:

Extract the proven Schwab live client-factory chain from rehearsal/probe scripts into reusable app-owned `src/` code and register it as the default builder for live cockpit runtime startup, so the explicit `--live` cockpit can connect real data without test injection.

## Compaction / Context Recovery

After compaction or context loss, restate in 8 bullets max:
- repo and HEAD
- current goal
- latest live evidence
- active blocker
- next implementation slice
- safety boundaries
- tests to run
- commit criteria

Then continue implementation.
