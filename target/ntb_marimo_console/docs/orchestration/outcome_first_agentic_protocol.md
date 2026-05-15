# NTB Marimo Console: Outcome-First Agentic Orchestration Protocol

This document is the source-of-truth orchestration override for NTB Marimo Console.

It supersedes older one-command and one-prompt workflow rules whenever those rules slow meaningful app progress.

## Operating Reality

This project now uses capable coding agents:

- Claude Code with Claude Opus 4.7
- Codex with ChatGPT-5.5

These agents may perform multi-step implementation loops inside one prompt:

- inspect relevant repo paths
- identify the first broken seam
- patch code
- add focused regression tests
- run targeted verification
- run bounded diagnostics
- run one bounded sanitized live smoke when explicitly authorized
- commit cleanly
- report exact app behavior changed

The correct unit of work is an outcome-focused implementation slice, not a tiny serial command, unless the operator explicitly asks for terminal rotation or a tiny diagnostic is safer.

## Primary Objective

Every prompt must move the app toward a working fail-closed Marimo operator workstation.

The app is real only when the operator can:

- launch the workstation
- see ES, NQ, CL, 6E, and MGC only
- receive live Schwab futures updates
- see what is live, stale, blocked, missing, or invalidated
- see why each contract is blocked
- manually query only when deterministic preserved-engine conditions justify it
- avoid fabricated data, fixture fallback, hidden decision authority, or trade-execution automation

## Implementation-First Rule

A prompt is valid only if it targets concrete app behavior or the live data path.

Valid targets include:

- live data ingestion
- stream manager state
- receive worker state
- subscription state
- message dispatch
- cache advancement
- LEVELONE_FUTURES freshness
- CHART_FUTURES freshness or blocking
- provider, stream, quote, and chart classification
- cockpit truthfulness
- manual query gate correctness
- runtime lifecycle propagation
- evidence and replay attribution
- exact blocked reason surfacing

Invalid default targets include:

- audit-only work
- readiness-only work
- docs-only work
- broad bookkeeping
- generic inspection or reporting
- broad lint cleanup
- broad test expansion without changed app behavior
- fixture-only proof for a live-path blocker
- migration or handoff busywork unless the repo is actually at a clean migration checkpoint

## Agent Prompt Rules

Prompts must be optimized for the agent being used.

### Claude Code with Claude Opus 4.7

Use autonomous implementation prompts that include:

- observed app state
- expected app behavior
- first likely broken seam
- relevant repo paths
- hard constraints
- focused tests
- targeted verification
- bounded live-smoke authorization when applicable
- final report contract

Do not let Claude stop at diagnosis. It must patch the first broken seam unless a hard safety boundary blocks implementation.

### Codex with ChatGPT-5.5

Use tighter implementation slices that include:

- exact behavior target
- exact files and tests when known
- acceptance criteria
- verification commands
- commit requirement

Do not use broad narrative or speculative future work.

## Live-Path Rule

When the current blocker is live data, runtime freshness, Schwab streaming, receive-worker state, subscription state, or cache advancement, tests alone are not enough.

A valid prompt must require at least one of:

1. a bounded sanitized live smoke if explicitly authorized
2. a bounded diagnostic command the operator can run safely
3. an app or notebook change that exposes the exact sanitized blocker

For live-path work, the result is unacceptable if it only says:

- tests pass
- dry-run pass
- readiness gate pass
- no credentials required

The result must say where live data stops or prove that live data advanced farther.

## Bounded Sanitized Live Smoke Rule

When explicitly authorized, a coding agent may source the existing live env file only as runtime input.

Allowed:

- source .state/secrets/schwab_live.env without printing it
- let the app/runtime read configured token material internally
- run one bounded live diagnostic
- print only sanitized statuses, booleans, counts, age buckets, service names, contract symbols, and blocker codes

Forbidden:

- cat, grep, sed, echo, print, log, or commit secret env contents
- inspect token JSON files
- dump env
- print auth headers, app keys, secrets, tokens, streamer URLs, customer IDs, correl IDs, account IDs, authorization payloads, raw streamer payloads, raw quote values, or raw bar values
- run unbounded live loops
- place orders or access broker/order/account/fill/P&L behavior
- make default launch live
- create fixture fallback after live failure

## Success Standard

A prompt succeeds only if it produces one of:

- operator-visible app behavior now works
- live data advances farther through the path
- exact live-data blocker is surfaced
- cache, freshness, or status classification becomes more truthful
- manual query gating becomes more correct without loosening fail-closed behavior
- the notebook after relaunch should show a materially improved state

A prompt fails even if tests pass when:

- the notebook would still show the same generic blocker
- provider stale remains a catch-all
- quote stale remains despite fresh LEVELONE cache data
- CHART_FUTURES staleness still globally poisons provider or quote freshness
- no live smoke or equivalent diagnostic was run for a live-path blocker
- the final report cannot name the exact broken seam

## Preserved Safety Boundaries

Never violate:

- default launch remains non-live
- live behavior requires explicit opt-in
- no fixture fallback after live failure
- no repeated Schwab login per Marimo refresh
- manual query only
- manual execution only
- preserved engine remains sole decision authority
- no broker/order/execution/account/fill/P&L behavior
- no display/view-model/rendering/evidence/replay code creates QUERY_READY
- stale, missing, unsupported, lockout, invalidated, non-provenance, display-derived, replay-derived, or synthetic state cannot create QUERY_READY
- ES, NQ, CL, 6E, MGC only
- ZN and GC excluded
- MGC is Micro Gold, not GC
- no secrets or raw market data printed

## Final Response Contract For Coding Agents

Every implementation result must include:

- exact broken seam found
- exact code change made
- files changed
- tests added or updated
- verification results
- bounded live smoke result if authorized, or exact reason not run
- what app behavior now works
- what the operator should expect after relaunch
- what remains blocked and why
- whether any sensitive values were printed
- whether default launch remains non-live
- whether fixture fallback after live failure remains impossible
- commit hash
- final git status
- whether migration is actually required

## Handoff Instruction

Every future NTB Marimo Console handoff must either include this document path or include this statement:

`Orchestration source of truth: docs/orchestration/outcome_first_agentic_protocol.md. This supersedes stale one-command/one-prompt workflow rules whenever those rules slow app progress.`

<!-- OPERATOR_FIRST_EXECUTION_BIAS_START -->

## Operator-First Execution Bias

This protocol is now biased toward getting the operator into the live cockpit and testing real workflow behavior.

The default goal is working app behavior, not additional proof artifacts.

The active acceptance target is:

> Can the operator launch the cockpit, see truthful provider/quote/chart/query state, understand the current blocker, and safely continue the manual workflow?

### Default decision rule

Use this order of priority:

1. Launch or inspect the actual operator cockpit.
2. Verify screen truth from the operator's point of view.
3. Fix the observed blocker if the screen lies, blocks real use, or risks unsafe/fake behavior.
4. Start operator testing once the screen tells a coherent truthful story.
5. Defer polish.

### What must not happen

Do not run audit-only, readiness-only, documentation-only, migration-only, or test-only loops unless they directly:

- prevent fake live data,
- prevent unsafe query readiness,
- protect the no-secrets/no-broker/no-auto-execution boundaries,
- or unblock a concrete observed app behavior.

Do not re-prove already proven live plumbing unless the current code change touches that plumbing.

Do not ask for another live smoke when focused tests can validate a display/coherence fix.

Do not block operator testing on polish, old profile names, ugly labels, layout imperfections, or documentation gaps unless they misrepresent live state or prevent safe use.

### Safety boundaries remain non-negotiable

The operator-first bias does not relax safety:

- default launch remains non-live,
- live launch remains explicit opt-in only,
- no fixture fallback after live failure,
- no secrets, tokens, auth headers, streamer URLs, customer IDs, correl IDs, account IDs, raw quote values, raw bar values, or raw streamer payloads printed,
- no broker/order/execution/account/fill/P&L behavior,
- manual query only,
- manual execution only,
- preserved engine remains the sole decision authority,
- display/view-model/rendering/evidence/replay code must never create QUERY_READY,
- stale, missing, unsupported, lockout, invalidated, non-provenance, display-derived, replay-derived, or synthetic state must never produce QUERY_READY,
- final target universe remains ES, NQ, CL, 6E, MGC,
- ZN and GC remain excluded,
- MGC is Micro Gold, not GC.

Safety boundaries are guardrails. They must not be used as an excuse for audit spiral when the next app blocker is observable and fixable.

### Agent selection rule

Use the fastest tool that can safely complete the next concrete step.

- Use Terminal for deterministic repo-rooted edits, launch commands, status checks, and known source-document updates.
- Use Claude Opus for semantic/coherence bugs across app surfaces where the issue is meaning, status consistency, or UI truth.
- Use Codex for repo-scale implementation tickets with explicit tests, verification, and commit requirements.
- Use Sonnet only for narrower scoped implementation where target files and acceptance criteria are already clear.

### Required handoff language

Every future implementation handoff must state:

- what app behavior now works,
- what the operator can now do,
- what actually blocks operator testing, if anything,
- whether the next step is operator testing, code fix, or polish.

If the live cockpit tells a coherent truthful story and manual query remains fail-closed without preserved-engine QUERY_READY provenance, the next step is operator testing, not another audit.

<!-- OPERATOR_FIRST_EXECUTION_BIAS_END -->
