# NTB Marimo Console Claude Code Guidance

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

Use the latest live rehearsal JSON/result as the source of truth.

Repeat this loop:
1. Identify the current live-data blocker.
2. If the blocker is app-side, fix it and commit.
3. If the blocker requires live evidence, provide the exact safe explicit live command for the operator to run.
4. When the operator provides live output, interpret it and continue.
5. Stop only when:
   - the live-data-ready observation workstation is honestly achieved
   - a provider/entitlement limitation is proven and recorded
   - a safety boundary prevents continuation
   - operator input/live output is required

Do not wait for micro-prompts when the next implementation slice is clear.

## Current Product Boundaries

- Observation-only.
- No broker/order/execution/account/fill/P&L behavior.
- Manual query only.
- Manual execution only.
- Preserved engine remains the sole decision authority.
- Live data may arm, block, invalidate, or annotate a query, but may not approve trades.
- Do not make default launch live.
- Live behavior must remain explicit opt-in.
- No fixture fallback after live failure.
- Preserve fixture-safe default tests and default launch behavior.
- Preserve the 15-second minimum refresh floor.
- Preserve ES, NQ, CL, 6E, and MGC only.
- Preserve ZN and GC exclusion.
- MGC is Micro Gold. Do not map it to GC.
- Do not touch source/ntb_engine unless explicitly necessary. Ask first if required.
- Do not turn implementation work into audit-only or documentation-only work.

## Secret and Live Credential Handling

Live data access requires local env/token material, but secret material must stay local and uninspected.

Allowed:
- A bounded live rehearsal command may source `.state/secrets/schwab_live.env` only as shell environment setup for that single command.
- Use `set +x` before sourcing the env file.
- The app/runtime script may read the configured token path internally to authenticate.

Not allowed:
- Do not open, cat, grep, sed, parse, summarize, print, paste, or commit `.state/secrets/schwab_live.env`.
- Do not open, cat, grep, sed, parse, summarize, print, paste, or commit token files.
- Do not run `env`, `printenv`, shell debug tracing, verbose auth logging, or any command that could dump environment variables.
- Do not print credentials, auth headers, app keys, token JSON, streamer URLs, customer IDs, correl IDs, account IDs, authorization payloads, raw quote values, raw bar values, or raw streamer payloads.
- Do not record raw market values.

Sanitized output may include booleans and status fields such as:
- token_file_present=yes/no
- token_fresh=yes/no
- market_data_received=yes/no
- chart_data_received=yes/no
- values_printed=no

## Live-Run Reporting Contract

Every live rehearsal JSON/report should include, when possible:
- requested_duration_seconds
- effective_duration_seconds
- actual_observed_duration_seconds
- early_exit_reason
- LEVELONE_FUTURES status per ES/NQ/CL/6E/MGC
- CHART_FUTURES status per ES/NQ/CL/6E/MGC
- chart_completed_five_minute_contracts_count
- repeated_login_on_refresh
- values_printed

Classify live results honestly:
- PASS only if real five-contract LEVELONE_FUTURES and required CHART completed-bar proof are satisfied.
- PARTIAL / FAIL-CLOSED if some real live proof exists but required chart/service/readiness proof is missing.
- FAIL-CLOSED if live startup/auth/subscription/data delivery fails safely.

Do not record dry-run output as live proof.
Do not treat LEVELONE_FUTURES success as CHART_FUTURES success.
Do not treat subscription success as data delivery success.
Do not treat partial/building bars as completed confirmation.

## Git and Verification Discipline

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

## Compaction Recovery

After compaction or context reset, restate in 8 bullets max:
- repo and HEAD
- current goal
- latest live evidence
- active blocker
- next implementation slice
- safety boundaries
- tests to run
- commit criteria

Then continue implementation.
Do not restart broad audits.

## Stop Conditions

Stop and ask for operator input only when:
- live output is required
- a safety boundary would be crossed
- source/ntb_engine must be changed
- secrets/token contents would need inspection
- working tree is dirty and ownership is unclear
- provider/entitlement behavior cannot be diagnosed without another live run
