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

<!-- EXECUTION_RESTRAINT_DIALBACKS_START -->

### Execution Restraint Dial-Backs

The operator-first bias requires dialing back process restraints that slow app delivery without materially improving safety.

These dial-backs apply immediately.

#### 1. Bounded live confirmation is allowed after screen-affecting changes

If a change affects what the operator sees in live mode, one bounded sanitized live confirmation is allowed after targeted tests pass.

Do not debate whether a live check is absolutely necessary when the acceptance question is live operator behavior.

Live confirmation must remain explicit opt-in and sanitized:
- no secrets,
- no token contents,
- no auth headers,
- no streamer URLs,
- no customer IDs,
- no correl IDs,
- no account IDs,
- no raw streamer payloads,
- no raw quote/bar values in terminal output, logs, commits, screenshots, or chat.

#### 2. Local live cockpit display may show market values

The ban on raw quote/bar values applies to terminal output, logs, commits, screenshots, chat, and diagnostic artifacts.

It does not prohibit the local explicitly-launched live cockpit from displaying market values when those values are necessary for operator use.

Do not let redaction rules prevent building a real local workstation display.

#### 3. Continue through same-surface app-owned blockers

Do not stop after one small fix when the next blocker is visible, app-owned, and inside the same surface.

Continue in the same implementation session across same-surface blockers until:
- the cockpit is usable for operator testing,
- targeted verification fails for an unclear reason,
- or a hard safety boundary is reached.

Examples of same-surface blockers:
- header wording contradiction,
- provider/quote/chart label inconsistency,
- primary cockpit identity confusion,
- row-level blocker text confusion,
- next-safe-action missing from the operator table.

#### 4. Inspection exists to enable implementation

Do not produce audit-only or readiness-only output after a concrete blocker is known.

Inspection is allowed only as needed to implement the next working app behavior.

The deliverable is changed operator-visible app behavior, not a readiness conclusion.

#### 5. Verification should match the milestone

Run targeted tests while coding.

At an operator milestone, run the relevant cockpit/readiness/renderer/launch acceptance slice without asking again.

Do not repeatedly run expensive broad verification unless the changed surface requires it.

Do not use lack of broad verification as a reason to avoid fixing an observed operator-screen blocker.

#### 6. Documentation is secondary but allowed when it steers behavior

Docs must not lead implementation.

Docs are allowed when they:
- change future orchestration behavior,
- define the current operator workflow,
- prevent future audit spiral,
- or explain how to run the app safely.

Do not write historical audit documents unless explicitly requested.

#### 7. Internal labels are backlog unless they mislead the operator

Old internal names such as fixture/demo profile names do not block testing by themselves.

They become implementation blockers only when they are the primary live-screen identity or cause the operator to believe live data is fake.

Internal labels may remain in secondary/debug text.

#### 8. source/ntb_engine remains protected, not impossible forever

Default rule: do not modify source/ntb_engine.

If a future blocker is proven to be engine-side, stop and request explicit authorization before crossing that boundary.

Do not use the engine boundary as an excuse to avoid target-app fixes.

#### 9. Safety boundaries are guardrails, not excuses for delay

Keep the real safety boundaries:
- no broker/order/execution/account/fill/P&L behavior,
- no default live launch,
- no fixture fallback after live failure,
- no secrets or sensitive identifiers printed,
- no display/view-model/replay/evidence path creating QUERY_READY,
- preserved engine remains the sole decision authority,
- manual query only,
- manual execution only,
- ES, NQ, CL, 6E, MGC only,
- ZN and GC excluded,
- MGC is Micro Gold, not GC.

Do not use those safety boundaries to justify audit spiral when the next app blocker is observable, target-owned, and fixable.

#### 10. Default implementation rule

If the cockpit screen is incoherent, fix the screen.

If the cockpit screen is coherent and live data works, start operator testing.

If operator testing exposes a real blocker, fix that blocker.

If the issue is only naming, layout, copy, or polish, backlog it unless it causes false interpretation.

If the issue touches secrets, broker execution, fake readiness, or QUERY_READY authority, stop and preserve safety.

<!-- EXECUTION_RESTRAINT_DIALBACKS_END -->


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

<!-- NTB_OPERATOR_FIRST_EXECUTION_START -->

# NTB Operator-First Execution Rules

This repo is currently in Operator Testing Module V0 execution mode.

Default behavior is implementation-first and operator-first:

1. Launch or inspect the actual operator cockpit.
2. Verify screen truth from the operator's point of view.
3. Fix observed app-owned blockers that make the cockpit misleading, confusing, or unusable.
4. Continue through same-surface blockers in the same session when safe.
5. Start operator testing once the screen tells a coherent truthful story.
6. Defer polish.

Do not perform audit-only, readiness-only, documentation-only, migration-only, or proof-for-proof work unless it directly prevents fake live data, protects a hard safety boundary, or unblocks a concrete app behavior.

## Current product target

The immediate product target is Operator Testing Module V0.

The operator must be able to open the notebook and know within 10 seconds:

- whether live runtime is connected,
- whether provider, quote, and chart states are usable,
- which contracts are visible,
- which contracts are blocked,
- why each is blocked,
- whether manual query is enabled or disabled,
- what the next safe operator action is.

The top live notebook surface must prioritize an operator-facing status board, not internal implementation prose.

## Required V0 surface

The top of the notebook should expose:

- title: NTB Live Observation Testing Module or equivalent,
- status: READY_FOR_OPERATOR_TESTING or NOT_READY_FOR_OPERATOR_TESTING,
- runtime state,
- provider state,
- manual query state,
- exactly one top-level blocker,
- exactly one next safe action,
- five contract rows: ES, NQ, CL, 6E, MGC only.

Each contract row must show:

- contract,
- provider,
- quote,
- chart,
- trigger state,
- query gate,
- blocker,
- next safe action.

Internal names such as fixture_es_demo may remain as secondary/debug metadata, but must not be the primary live-screen identity.

## Process restraint dial-backs

Bounded sanitized live confirmation is allowed after screen-affecting changes once targeted tests pass.

The no-raw-values rule applies to terminal output, logs, commits, screenshots, chat, diagnostic artifacts, and test output. It does not prohibit the local explicitly launched live cockpit from displaying market values needed for operator use.

Do not stop after one narrow fix if the next blocker is visible, target-owned, same-surface, and safe to fix.

Inspection exists to enable implementation. The deliverable is changed app behavior, not another readiness conclusion.

At operator milestones, run the relevant cockpit/readiness/renderer/launch acceptance slice without asking for permission again.

Docs are allowed only when they steer future execution or explain the current operator workflow. Do not write historical audit documents unless explicitly requested.

## Hard safety boundaries

These remain non-negotiable:

- no broker/order/execution/account/fill/P&L behavior,
- no default live launch,
- explicit live opt-in only,
- no fixture fallback after live failure,
- no secrets, token contents, auth headers, streamer URLs, customer IDs, correl IDs, account IDs, raw streamer payloads, or raw quote/bar values in terminal/log/chat output,
- manual query only,
- manual execution only,
- preserved engine remains sole decision authority,
- display/view-model/rendering/evidence/replay code must never create QUERY_READY,
- missing, stale, unsupported, lockout, invalidated, non-provenance, display-derived, replay-derived, or synthetic state must never produce QUERY_READY,
- final target universe remains ES, NQ, CL, 6E, MGC,
- ZN and GC remain excluded,
- MGC is Micro Gold, not GC.

Safety boundaries are guardrails. They must not be used as excuses for audit spiral when the next app blocker is observable and fixable.

## Agent usage

Use the fastest tool that can safely complete the next concrete step.

Claude Code Opus:
Use for semantic/coherence work across cockpit, renderer, readiness, and operator workflow. Give mission, success criteria, permissions, and stop conditions. Do not micromanage every file unless necessary.

Codex:
Use for repo-ticket implementation with explicit acceptance criteria, tests, verification, and commit requirements.

Terminal:
Use for deterministic edits, launch commands, status checks, verification, and known source-document updates.

Sonnet:
Use only for narrow scoped implementation where target files and acceptance criteria are already clear.

## Stop conditions

Stop only for real blockers:

- source/ntb_engine change required,
- broker/order/account/fill/P&L boundary would be touched,
- secrets/token contents/raw streamer payloads required,
- unclear tracked dirty files at start,
- missing/stale/display-derived state could create QUERY_READY,
- broader architecture change required.

Do not stop merely because one small same-surface issue was fixed.

<!-- NTB_OPERATOR_FIRST_EXECUTION_END -->
