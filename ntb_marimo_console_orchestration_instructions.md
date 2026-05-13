# NTB Marimo Console Orchestration Instructions

## 0A.1 Active Project

Active project:  
**NTB Marimo Console**

Active repo:  
`/Users/stu/Projects/ntb-marimo-console`

Working directory for Codex (Windsurf):  
`/Users/stu/Projects/ntb-marimo-console`

GitHub repo:  
`richportfutures-byte/ntb-marimo-console`

Default branch:  
`main`

Current final target universe:

- `ES`
- `NQ`
- `CL`
- `6E`
- `MGC`

Excluded final target contracts:

- `ZN`
- `GC`

Product doctrine:

The app is a fail-closed Marimo operator workstation for an experienced intraday futures trader. Live data may arm, block, invalidate, or annotate a query, but the preserved engine remains the sole decision authority. Execution remains manual only.

MGC is the supported gold product. GC is excluded and must not be used as a synonym for MGC.

ZN may exist as historical or legacy code or fixtures, but it must not be re-promoted into final target support without a later explicit authority amendment.

---

## 0A.2 Numbered Response Format

Every orchestration response must start with a number.

Use this for Terminal commands:

```text
1. Terminal
```

Then provide one bash/zsh command block:

```bash
cd /Users/stu/Projects/ntb-marimo-console && git status --short
```

Use this for Codex prompts:

```text
2. Codex

Effort: Medium/High/Xtra High
```

Then provide one prompt block:

```text
PROMPT ### - TITLE
Effort: Medium/High/Xtra High
Risk: Medium
Commit Counter: N since last migration
Migration Rule: safe to continue / migrate before this prompt / migrate after this prompt
Roadmap Step: R##
...
```

Use this for a migration handoff:

```text
3. Migration Handoff
```

Then provide one handoff block only.

---

## 0A.3 No Extra Prompt Variants

Do not provide:

- "Option A / Option B"
- "Here are three possible prompts"
- "You could also ask Codex..."
- a second speculative follow-up prompt
- an unrequested future step after the active prompt

The only exception is when the user explicitly asks for alternatives.

---

## 0A.4 Codex Prompt Header Contract

Every Codex implementation prompt must begin exactly with this structure:

```text
PROMPT ### - TITLE
Effort: Medium/High/Xtra High
Risk: Low/Medium/High
Commit Counter: N since last migration
Migration Rule: migrate before this prompt / safe to continue / migrate after this prompt
Roadmap Step: R##
```

Definitions:

`PROMPT ###` must increment monotonically within the roadmap.

`TITLE` must be specific and action-oriented.

Effort should be:

- `Medium` for bounded tests, docs, small wiring, and narrow view-model changes.
- `High` for multi-file implementation, runtime/profile changes, app-surface wiring, cache behavior, and live-observable integration.
- `Xtra High` for architecture-sensitive, failure-sensitive, streaming, authorization, data-integrity, or cross-runtime changes.

Risk should be:

- `Low` for docs/tests or isolated non-runtime changes.
- `Medium` for runtime behavior, launch behavior, cache behavior, refresh behavior, UI binding, profile selection, and app-surface gating.
- `High` for auth, live provider behavior, streaming, data integrity, credential/token handling, fail-closed live behavior, or rule-state changes.

Commit Counter resets to `0` after migration.

Migration Rule must follow the rules in section `0A.5`.

Roadmap Step must match the current roadmap checkpoint.

---

## 0A.5 Migration Rules

Use these migration rules in every prompt:

- Risk `High`: migrate before running unless the current chat is fresh.
- Commit Counter `>= 3`: migrate after the next clean commit.
- Risk `Medium` + Commit Counter `>= 2`: migrate after the next clean commit.
- Risk `Low`: safe to continue if status is clean.
- Never migrate in the middle of an implementation step.
- Migrate only at clean roadmap checkpoints.

A clean checkpoint means:

```text
git status --short is clean
targeted verification for the completed step passes
git diff --check passes before commit
changed Python files pass Ruff when Python files changed
current roadmap step is committed
next roadmap step has not started
no live credential/token state was inspected or printed
no default-live launch behavior was introduced
```

For major release or migration checkpoints, expected verification should include the relevant project acceptance set.

Canonical acceptance verification (from target/ntb_marimo_console):

```bash
cd /Users/stu/Projects/ntb-marimo-console/target/ntb_marimo_console && PYTHONPATH=src .venv/bin/python -m pytest tests/ --tb=short
```

---

## 0A.6 Required Prompt Body Sections

Every Codex implementation prompt must include these sections in this order:

```text
Repo
Current checkpoint
Goal
Primary question
Start with
Hard constraints
Audit or implementation scope
Tests
Commit message
Final response must include
```

Do not omit hard constraints.

Do not bury constraints in prose.

---

## 0A.7 Required Hard Constraints For All Prompts

Every implementation prompt must include these global constraints unless the user explicitly re-charters the project:

```text
Hard constraints
- Do not modify files outside the repo working tree.
- Do not inspect, print, paste, commit, or expose .state/secrets/schwab_live.env.
- Do not print credentials, token contents, auth headers, app keys, secrets, token JSON, streamer URLs, customer IDs, correl IDs, account IDs, or authorization payloads.
- Do not add broker/order/execution/account/fill/P&L behavior.
- Do not make default launch live.
- Preserve fixture-safe default tests and default launch behavior.
- Preserve no fixture fallback after live failure.
- Preserve the 15-second minimum refresh floor.
- Preserve manual-only execution.
- Preserve fail-closed behavior.
- Preserve the final target universe: ES, NQ, CL, 6E, MGC.
- Preserve excluded final target contracts: ZN, GC.
- Do not describe MGC as GC.
- Do not map MGC to GC or GC to MGC.
- Do not re-promote ZN into final target support.
```

Add step-specific constraints as needed.

For stream/auth/live-provider work, also include:

```text
- Live behavior must remain explicitly opt-in.
- Use fixture/mocked clients for default tests.
- Do not require Schwab credentials for CI or default test runs.
- Do not open repeated Schwab logins per Marimo refresh.
- Do not introduce a second decision authority outside the preserved engine.
```

---

## 0A.8 Terminal Command Discipline

Terminal commands should be:

- single numbered item
- copy-paste ready
- repo-rooted when relevant
- safe to run
- deterministic when possible
- not destructive unless explicitly required and explained

Do not provide multiple terminal commands in separate blocks unless the user explicitly asks for a batch.

When multiple shell operations are required, combine them with `&&` only if they form one safe atomic diagnostic or verification command.

Canonical repo-root diagnostic:

```bash
cd /Users/stu/Projects/ntb-marimo-console && pwd && git branch --show-current && git status --short && git log -1 --oneline
```

---

## 0A.9 Verification Discipline

During implementation:

- use targeted tests first
- run broad verification only at final checkpoints or when the changed surface requires it
- do not repeatedly run expensive verification unless a relevant code path changed
- always run `git diff --check` before commit
- always check `git status --short` before and after commit
- do not commit unless verification passes or the user explicitly authorizes a partial commit
- run Ruff only on changed Python files when broad Ruff has known unrelated pre-existing failures
- do not perform unrelated lint cleanup unless the prompt explicitly scopes it

Preferred verification pattern:

```text
1. git status --short at start
2. targeted pytest slice for changed behavior
3. git diff --check
4. Ruff on changed Python files, if any
5. git status --short before commit
6. commit
7. git status --short after commit
```

Canonical targeted test command:

```bash
cd /Users/stu/Projects/ntb-marimo-console/target/ntb_marimo_console && PYTHONPATH=src .venv/bin/python -m pytest tests/TEST_FILE.py -v --tb=short
```

Canonical full suite verification:

```bash
cd /Users/stu/Projects/ntb-marimo-console/target/ntb_marimo_console && PYTHONPATH=src .venv/bin/python -m pytest tests/ --tb=short
```

---

## 0A.10 Final Codex Response Contract

Every Codex final response after a prompt must include:

```text
- files changed
- tests added/updated
- verification results
- commit hash
- final git status
- whether migration is required before the next roadmap step
```

For readiness gates, also include:

```text
- what was verified
- what was fixed
- whether the next roadmap step is justified or premature
```

For live/stream/auth steps, also include:

```text
- whether any live credentials were required
- whether any live credential/token/URL/customer/correl/account values were printed
- whether default launch remains non-live
- whether fixture-safe behavior remains intact
- whether no fixture fallback after live failure remains intact
```

---

## 0A.11 Handoff Block Contract

When migration is required, the handoff must be concise and must include:

```text
CONTEXT HANDOFF - NTB Marimo Console

Repo:
Current branch:
Current clean checkpoint:
Working tree:
Last completed roadmap step:
Recent commits:
Current product doctrine:
Non-negotiable boundaries:
Current implementation state:
Verification passed:
Known issues:
Next roadmap step:
Next prompt title:
Hard constraints:
Expected verification:
Next commit message:
Migration status:
```

Do not include unnecessary narrative history.

Correct handoff heading:

```text
CONTEXT HANDOFF - NTB Marimo Console
```

---

## 0A.12 Stop Conditions

Stop and request one diagnostic command only when:

- `git status` is dirty and the intended ownership of changes is unclear
- tests fail in an unrelated area and the failure source is unknown
- live credential/token state is needed but cannot be checked safely
- a prompt would require changing the no-execution/manual-only boundary
- a prompt would require modifying a donor repo or unrelated repo
- a roadmap step is no longer aligned with observed repo reality
- a step would require re-promoting ZN into final target support
- a step would require adding GC or treating GC as equivalent to MGC
- a live-provider step would require printing credentials, tokens, auth headers, streamer URLs, customer IDs, correl IDs, or account identifiers
- a live-data feature would bypass preserved-engine decision authority
- a missing field or stale quote could still produce `QUERY_READY`

---

## 0A.13 User-Output Rotation

The expected loop is:

```text
Assistant gives one numbered Terminal command or one numbered Codex prompt.
User runs it and pastes the output.
Assistant reads the output.
Assistant gives the next numbered item only.
```

Do not skip ahead.

Do not bundle multiple future prompts.

Do not provide speculative next steps after the active prompt unless the user explicitly asks.

---

## 0A.14 Current Known Checkpoint

Repo:  
`/Users/stu/Projects/ntb-marimo-console`

Branch:  
`main`

Current clean checkpoint:  
`03717fc Cut NTB Marimo Console release candidate`

Working tree:  
Clean

Last completed roadmap step:  
`R19 - Release Candidate`

Environment status:  
`ninjatradebuilder` engine installed in target venv. Full test suite passes (1193/1193).

Recent commits:

- `03717fc Cut NTB Marimo Console release candidate`
- `110f09a Add performance review layer`
- `e2f6178 Consolidate release test harness`
- `295f291 Record five-contract live rehearsal result`
- `31e5e9c Prepare five-contract live rehearsal dry run`
- `b5a1e46 Wire cockpit evidence replay`
- `cb79576 Onboard MGC runtime profile`
- `87441c0 Onboard 6E runtime profile`
- `d8fdd17 Onboard NQ runtime profile`

Current implementation state:

- R00 through R19 are complete and committed on main.
- Five-contract universe (ES, NQ, CL, 6E, MGC) is fully onboarded with preserved profiles.
- Watchman brief validator (18+ checks) and pipeline query gate (12 fail-closed conditions) are operational.
- Trigger state machine, trigger transition narrative, and evidence replay are implemented.
- Performance review layer (Initiative 5) is implemented.
- Viewmodel narrative widening (Initiative 1) is implemented.
- Schwab streamer session can login and subscribe but D3 rehearsal received zero market data frames.
- Release candidate was cut at `03717fc` as fixture-safe personal workstation candidate.

D3 live rehearsal result (partial/fail-closed):

- `live_login_succeeded`: yes
- `live_subscribe_succeeded`: yes
- `subscribed_contracts_count`: 5
- `market_data_received`: no
- `received_contracts_count`: 0

Known issues:

- D3 live rehearsal proves login/subscribe plumbing but not market data delivery.
- No managed receive thread, reconnect/backoff, or watchdog exists.
- Token auto-refresh during a live session is not implemented.
- Active-trade management surface (Initiative 6) is not implemented.
- Operator notes input (Initiative 4) is not implemented.
- Anchor input UI for cross-asset contracts (Initiative 7) is not implemented.
- Audit/Replay timeline surface (Initiative 3) has backend only, no UI timeline.

Next roadmap step:  
`R20 - Schwab Data Delivery Diagnostic`

Next prompt title:  
`PROMPT 001 - Diagnose Schwab Market Data Delivery Gap`

Expected next commit message:  
`Add Schwab data delivery diagnostic`

Migration status:  
Fresh orchestration session. No migration required.

---

## 0A.15 Post-RC Functional Roadmap

The original R00–R19 roadmap is complete. The following post-RC roadmap covers remaining work to reach a fully functional live trading workstation:

```text
R20 Schwab Data Delivery Diagnostic
R21 Token Auto-Refresh Lifecycle
R22 Streamer Reconnect With Backoff
R23 Managed Receive Thread
R24 Per-Contract Watchdog Heartbeat
R25 Degraded-State Alerting In UI
R26 Active-Trade Data Model
R27 Active-Trade Thesis Health Monitor
R28 Active-Trade Marimo Surface
R29 Anchor Input UI (NQ/6E/MGC cross-asset)
R30 Operator Notes Input Surface
R31 Audit/Replay Timeline Surface
R32 Premarket Brief Enrichment
```

Grouping:

- R20: Data delivery gap diagnosis (prerequisite for all live work)
- R21–R25: Stability hardening (Initiative 9) — migrate after R25
- R26–R28: Active-trade management (Initiative 6) — migrate after R28
- R29–R32: Remaining UX initiatives (Initiatives 3, 4, 7, 8) — migrate as needed

---

## 0A.16 Codex Environment Notes (Windsurf)

Codex is accessed via Windsurf IDE with GPT-5.5.

Windsurf workspace must be opened at:  
`/Users/stu/Projects/ntb-marimo-console`

Python virtual environment:  
`target/ntb_marimo_console/.venv/`

Python execution pattern:  
`cd target/ntb_marimo_console && PYTHONPATH=src .venv/bin/python`

Test execution pattern:  
`cd target/ntb_marimo_console && PYTHONPATH=src .venv/bin/python -m pytest tests/ --tb=short`

Codex should not read, print, or reference any files under `.state/secrets/`.

All Schwab-sensitive values must be redacted in any output.
