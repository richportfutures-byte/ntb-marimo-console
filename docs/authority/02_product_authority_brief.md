# Product Authority Brief

**Authority document set:** `docs/authority/`  
**This document:** `product_authority_brief.md`  
**Generated:** 2026-03-28  
**Status:** BINDING

## One-Sentence Product Definition

NinjaTradeBuilder is a disciplined, Schwab-backed Marimo futures workstation and contract-aware decision partner that tells the operator exactly what the market needs to show before a trade is worth taking, and exactly why it is not when it is not.

## Final Product Target

The final target support universe is:

- `ES`
- `NQ`
- `CL`
- `6E`
- `MGC`

`ZN` is excluded from final target support and may remain only as historical or legacy implementation evidence until explicit cleanup work removes or quarantines it. `GC` is excluded entirely and must not be used as a synonym, alias, display label, or onboarding shortcut for `MGC`. `MGC` is the gold contract for this application.

## Operator Profile

A single experienced intraday futures trader running funded challenge accounts who already understands market profile, order flow, and auction theory.

## Core Job to Be Done

Before taking any intraday futures trade, force a structured evaluation that independently checks whether the setup, the risk authorization, and the market conditions all pass their own quality bars, and refuse to evaluate at all if conditions are premature, data is insufficient, or the market is structurally ambiguous.

The problem being solved is the operator bypassing their own rules when a trade feels obvious.

## Product Vision

### V1 - Engine Change Policy

From Phase 2 onward, the engine is reopened only under these conditions:

- a schema contract breaks
- a stage-logic contradiction is proven by audit
- a risk parameter changes because funded-challenge rules changed
- Thesis Registry drift is confirmed between Watchman narrative and Stage B live-evaluation logic

Every other change, including formatting, UI behavior, logging enhancements, and new-contract addition, is handled outside the engine. Any engine change requires a full re-audit of the affected stage and a versioned commit before use in a live session.

## Permanent Design Principles

Future readers must not misinterpret the following:

1. **A NO_TRADE rate of 60 to 80 percent is not a bug or evidence the system is too conservative.** It is the intended output of a pipeline that treats low-quality conditions as non-events.
2. **The pre-market brief is not a trade signal and does not lower the bar for querying.** It exists to improve timing, not increase frequency.
3. **The system's value is not primarily in the trades it approves.** It is in the discipline it enforces on the ones it does not.

## Architectural North Star

The Marimo app surface is permanently the operator's session workspace and orchestration layer. It owns session flow by rendering pre-market briefs, displaying the Watchman readiness matrix, enforcing the pipeline gate, accepting packet submission, triggering the pipeline on demand, and presenting final outputs.

It never gains decision authority.

The engine remains the sole decision authority. The hidden diagnostic console remains a separate, non-operator surface for bounded traces, logs, and runtime diagnostics only.

## Three-Layer Terminology Lock

| Term | Definition |
|---|---|
| **Console** | Diagnostic panel only. Debug outputs only. Never operator-facing. |
| **App surface / operator workspace** | Deployed Marimo interface used during the session |
| **Engine** | Staged pipeline, Stages A through E, plus Watchman logic. Sole decision authority. |

## What This Document Is Not

This document is not the current-phase requirements spec. Current-phase requirements live in `current_phase_scope_contract.md`. This brief records product identity, permanent principles, and long-run architectural doctrine.
