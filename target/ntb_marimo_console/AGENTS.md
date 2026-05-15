# Agent Instructions

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
