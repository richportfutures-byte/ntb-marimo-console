# NTB Marimo Console — Companion Blueprint

**Status:** proposal / roadmap document
**Audience:** project owner, future implementers
**Scope boundary:** no order placement, no broker connection, no account access. Manual-only execution preserved at all layers.

---

## Executive summary

The NTB Marimo Console is a no-execution decision and audit companion for a discretionary futures trader. The five-contract universe (ES, NQ, CL, 6E, MGC) is in place, the live Schwab data path is structurally verified through R30, and the preserved engine produces rich, multi-stage decision output today.

The dominant gap is not missing features — **it is unsurfaced computation**. The engine already emits structured narrative (market-structure prose, multi-sentence trade rationale, named risk checks with detail strings, evidence scores, confidence bands). The view-model layer at [`viewmodels/models.py:78-85`](../src/ntb_marimo_console/viewmodels/models.py) strips that narrative down to status enums before the UI surface ever sees it. The fix is to widen the view model and render what the engine already computes — work measured in days, not weeks.

The single genuine scope expansion is an **active-trade management surface**: once the trader has manually filled, the app needs to know what trade is on (operator-input, no broker connection) so the engine can continuously evaluate the open position against its original thesis and emit invalidation alerts, trail-stop suggestions, time-stop warnings, and partial-take cues.

The third track is **stability hardening** — token auto-refresh, streamer reconnect, managed receive thread, watchdog. Non-negotiable for any reliable live use; orthogonal to the feature work.

This document lays out all three tracks as a single coherent roadmap, with file references to existing infrastructure each item leverages, and a UX style map for how the resulting tool should look and flow.

---

## Design philosophy

Three principles, derived from the codebase as it stands today.

**1. Manual-only execution is permanent.** Every prompt, every authority doc, every test reinforces this. The companion never connects to a broker, never places an order, never tracks account state. Trade execution happens in NinjaTrader / Tradovate / wherever the trader prefers. The companion's job is to make that human decision better-informed and better-audited.

**2. Narrative-first.** A signal without reasoning is not actionable for a discretionary trader. The companion's value compounds when it explains *why* — why a setup is forming, why the engine is bullish, why this particular risk check failed, why the active thesis is degrading. The infrastructure to produce that narrative is largely built; rendering it is the leverage point.

**3. Fail-closed, no silent fallbacks.** The codebase already enforces this rigorously. Live failures block readiness; fixture data does not paper over live gaps. Any new work preserves this — particularly the active-trade surface, where a stale data feed must visibly invalidate management suggestions rather than silently emit guidance based on stale state.

---

## Roadmap — 9 initiatives

Items 1-5 surface existing engine output. Items 6-8 add new functionality. Item 9 is stability hardening on a separate track.

---

### Initiative 1 — Render engine narrative in the Decision Review surface

**The gap.** [`decision_review.py:6-26`](../src/ntb_marimo_console/ui/surfaces/decision_review.py) renders a `PipelineTraceVM` ([`viewmodels/models.py:78-85`](../src/ntb_marimo_console/viewmodels/models.py)) that contains only `contract`, `termination_stage`, `final_decision`, and four stage-status enums. The engine produces far richer output that never reaches this surface.

**What's already built.** [`source/ntb_engine/src/ninjatradebuilder/schemas/outputs.py:340-507`](../../../source/ntb_engine/src/ninjatradebuilder/schemas/outputs.py) defines:

- `ContractAnalysis.structural_notes` — narrative prose on market structure
- `ContractAnalysis.evidence_score` (1–10) and derived `confidence_band` (LOW / MEDIUM / HIGH)
- `ContractAnalysis.conflicting_signals[]` and `ContractAnalysis.assumptions[]`
- `ProposedSetup.rationale` — multi-sentence thesis explanation
- `ProposedSetup.disqualifiers[]` — invalidation factors
- `ProposedSetup.sizing_math` — full risk-sizing breakdown (stop_distance_ticks, risk_per_tick, adjusted_risk_dollars, etc.)
- `RiskAuthorization.checks[]` — 13 named risk checks each with `passed: bool` and `detail: str`

**What changes.** Widen `PipelineTraceVM` to carry these fields. Update the engine→view-model mapper to populate them. Expand `decision_review.py` to render them, organized as:

1. **Decision summary** — the existing state names (preserved)
2. **Engine reasoning** — `structural_notes`, `confidence_band`, `evidence_score`, conflicting signals
3. **Trade thesis** — `rationale`, entry/stop/targets, sizing math
4. **Risk authorization** — the 13 risk checks with pass/fail and detail strings, expandable
5. **What would invalidate this** — `disqualifiers[]` as a checklist

**Why this materially helps the trader.** A discretionary trader cannot act on `final_decision = "TRADE_APPROVED"`. They need to know the engine sees breadth holding above 65%, ES rejecting the weekly low, and DXY weakening — and that the setup invalidates if breadth falls below 55% or ES closes below the prior swing. That information exists in the engine output today; rendering it converts the app from a signal printer into a thesis explainer. This is the single highest-leverage initiative on the list.

**Effort.** Medium. View-model widening + mapper update + surface expansion. No new computation, no new data paths.

**Risk.** Low. Pure presentation layer change. Existing tests on the engine output remain valid; new tests cover the widened view model.

---

### Initiative 2 — Trigger transition narrative

**The gap.** Workstation state machines emit state enums (`DORMANT`, `APPROACHING`, `TOUCHED`, `ARMED`, `QUERY_READY`, `INVALIDATED`) and numeric fields (`distance_to_trigger_ticks`, `last_price`). The trader sees state names, not prose. There is no narrator that explains *why* a transition occurred.

**What's already built.**

- All five workstations emit state transitions deterministically: [`es_live_workstation.py`](../src/ntb_marimo_console/live_workstation/es_live_workstation.py) (734 lines), [`nq_live_workstation.py`](../src/ntb_marimo_console/live_workstation/nq_live_workstation.py) (1303 lines), [`cl_live_workstation.py`](../src/ntb_marimo_console/live_workstation/cl_live_workstation.py) (1045 lines), [`sixe_live_workstation.py`](../src/ntb_marimo_console/live_workstation/sixe_live_workstation.py) (1368 lines), [`mgc_live_workstation.py`](../src/ntb_marimo_console/live_workstation/mgc_live_workstation.py) (1327 lines).
- Each workstation tracks blocking_reasons tuples like `("awaiting_trigger_touch",)` and `("confirmation_incomplete",)`.
- [`evidence_replay.py`](../src/ntb_marimo_console/evidence_replay.py) already logs every state transition with full context.

**What changes.** Add a deterministic narrator (one module, one function per contract) that takes a transition (prior state, new state, current context, blocking reasons) and emits a one-line operator-facing prose summary. Examples:

- `DORMANT → APPROACHING`: *"ES approaching 5604.50 trigger; 8 ticks away; breadth aligned at 67%."*
- `APPROACHING → TOUCHED`: *"ES touched 5604.50; awaiting bar confirmation."*
- `TOUCHED → ARMED`: *"ES bar confirmation in; query armed; review premarket thesis."*
- `ARMED → QUERY_READY`: *"ES query ready — operator may submit."*
- `* → INVALIDATED`: *"ES invalidated — breadth fell to 54%; below the 55% threshold."*

These are pure functions of state + context — no new logic, no new data, just a renderer.

**Why this materially helps the trader.** Glancing at "ARMED" tells the trader nothing about whether the conditions look strong or whether they're surviving on a thread. The narrative converts state machines into situational awareness. This is the difference between a dashboard and a copilot.

**Effort.** Medium. Per-contract narrator functions, plus a renderer hook in the trigger surface. The contracts share enough structure that one base narrator + per-contract overrides is feasible.

**Risk.** Low. Pure presentation; deterministic; no new state.

---

### Initiative 3 — Audit/Replay UI

**The gap.** [`audit_replay.py:6-25`](../src/ntb_marimo_console/ui/surfaces/audit_replay.py) is a stub. It returns `{"surface": "Audit/Replay", "mode": "fixture_or_stub", "stage_e_live_backend": False, "trace_summary": {...}}`. The backend is complete; the UI is not.

**What's already built.** [`evidence_replay.py`](../src/ntb_marimo_console/evidence_replay.py) (670 lines) records a comprehensive event log with these event types:

- Stream lifecycle: `stream_connected`, `stream_disconnected`, `subscription_added`
- Data quality: `quote_stale`, `quote_recovered`
- Bar lifecycle: `bar_closed`
- Trigger lifecycle: `trigger_approaching`, `trigger_touched`, `trigger_armed`, `trigger_query_ready`, `trigger_invalidated`
- Decision lifecycle: `query_submitted`, `pipeline_result`
- Operator: `operator_note_added`, `session_reset`

Each event carries: `event_id`, `timestamp`, `contract`, `profile_id`, `event_type`, `setup_id`, `trigger_id`, `live_snapshot_ref`, `premarket_brief_ref`, `pipeline_run_id`, `operator_note`, `source`, `data_quality`, `redaction_status`.

**What changes.** Build the surface to render this event log as:

1. **Timeline view** — horizontal scrub bar with event markers color-coded by category, click to jump
2. **Event detail panel** — selecting an event shows full context, including the live snapshot at that moment
3. **Filter panel** — by event type, by contract, by time window
4. **Decision drill-down** — clicking a `pipeline_result` event opens the full Stage A-D narrative (same renderer as Initiative 1, replayed at that point)

**Why this materially helps the trader.** Post-trade learning is where discretionary traders extract real edge. *"At 14:32 the trigger touched; at 14:34 the engine approved; I waited until 14:38 and missed by 3 ticks — what changed in those 4 minutes?"* That review is impossible today because the data is logged but not browseable. With the timeline surface, every session becomes a postmortem source.

**Effort.** Medium-large. Real UI work — interactive timeline, filtering, detail rendering. Marimo's reactive cells support this but the surface itself is non-trivial.

**Risk.** Low. Read-only over an existing event log. No new data paths.

---

### Initiative 4 — Operator notes UI

**The gap.** Operator notes can be attached to events and run history rows, but there is no input UI in Phase 1.

**What's already built.**

- [`evidence_replay.py`](../src/ntb_marimo_console/evidence_replay.py) defines the `operator_note_added` event type and records `operator_note` on every event.
- [`viewmodels/models.py:89-97`](../src/ntb_marimo_console/viewmodels/models.py) `RunHistoryRowVM` carries a `notes: str` field.
- The data model is end-to-end ready.

**What changes.** Add a notes input on:
- The Decision Review surface — *"Why did I take this / pass this trade?"*
- Each timeline event in Audit/Replay — *"This is where I lost focus; remember to check breadth here next time."*
- Run history rows — searchable post-session annotations.

**Why this materially helps the trader.** Discretionary trading edges live in patterns the trader notices but doesn't yet codify. *"I take more losses on the third NQ trigger of the morning"* is impossible to see without notes attached to specific events. Once notes are first-class, the data is there to mine — and eventually feed back into pre-market prep.

**Effort.** Small. UI input + persistence wiring. Backend exists.

**Risk.** Trivial.

---

### Initiative 5 — Performance review surface

**The gap.** [`performance_review.py`](../src/ntb_marimo_console/performance_review.py) (1019 lines) is a complete module for tracking outcomes (fills, P&L, win/loss, by-contract performance). No surface renders it in Phase 1.

**What's already built.** The full module — data model, persistence, analysis. By line count it's the largest single module in the console after the workstations.

**What changes.** Build the surface. Possible cuts:
- By-contract performance card (win rate, avg R, expectancy per contract)
- By-setup-class card (scalp vs. intraday_swing vs. session_hold performance)
- By-time-of-day heatmap (when does this trader actually have edge?)
- By-disqualifier card (which engine warnings, when ignored, lead to losses?)
- Streak / drawdown indicators

**Why this materially helps the trader.** A trader without edge analytics is flying blind. The interesting cuts aren't gross P&L — they're *"my expectancy on CL is positive but my expectancy on 6E is negative"* or *"every loss in the last month came after I overrode a high-confidence engine REJECT."* The data exists; the rendering is missing.

**Note on scope.** Since the app does not connect to a broker, fills must be manually logged by the operator (either as part of run history or via the Operator Notes input from Initiative 4). The performance review then aggregates over those logged outcomes. This is consistent with the manual-only execution boundary.

**Effort.** Medium. Surface design + chart components within Marimo cells.

**Risk.** Low. Leverages an existing module.

---

### Initiative 6 — Active-trade management surface ⭐ (largest scope expansion)

**The gap.** This is the one genuine missing feature. Once the trader has manually filled, the app has no concept that a position is on. The original thesis is not re-evaluated against current price. Disqualifiers are not monitored. Time-in-trade is not tracked. There is no "is my trade still healthy?" view.

**What's already built (and how it's leveraged).**

- The engine's `ProposedSetup.disqualifiers[]` lists the exact factors that would invalidate a trade. These are already structured strings the engine generates per-decision.
- `ProposedSetup.hold_time_estimate_minutes` provides a baseline for time-stop warnings.
- `ProposedSetup.target_1` and `target_2` exist for multi-leg scaling.
- `ProposedSetup.entry_price` and `stop_price` are already engine output.
- Live workstation snapshots provide current price, current state, current context — i.e., everything needed to re-evaluate disqualifiers in real time.
- [`evidence_replay.py`](../src/ntb_marimo_console/evidence_replay.py) can absorb new event types (`trade_opened`, `trade_managed`, `thesis_degraded`, `trade_closed`) without architectural change.

**What changes.**

**6a — Operator-input trade form.** A small surface where the trader logs a fill: contract, direction, entry, stop, target_1, target_2, size, timestamp. Pre-populated from the engine's `ProposedSetup` if a query is QUERY_READY for that contract. Optional manual override.

**6b — Active-trade card.** Once a trade is logged, render:
- Position summary: entry/stop/target/size, time-in-trade, distance to each target in ticks
- Unrealized result (pure math from current_price - entry_price * size, **NOT** broker-fed)
- **Thesis-health indicator**: green / amber / red
  - Green = all original disqualifiers still passing
  - Amber = one disqualifier within 1 standard deviation of breach
  - Red = at least one disqualifier breached, OR `hold_time_estimate_minutes` exceeded by 50%, OR price violated stop
- Suggested action banner — generated text like *"Move stop to break-even: target_1 within 4 ticks"* or *"Thesis degrading: breadth fell from 67% to 58%; consider scaling out"* or *"Time-stop warning: trade open 65 minutes; engine estimated 45-min hold"*

**6c — Continuous evaluation.** A loop (driven by the same managed receive thread from Initiative 9) re-evaluates `disqualifiers[]` against current state every bar close. Emits `trade_managed`, `thesis_degraded`, `thesis_invalidated` events into the existing replay log.

**6d — Manual close.** Operator logs the exit (price, timestamp, reason). Triggers `trade_closed` event. Feeds the performance review surface from Initiative 5.

**Why this materially helps the trader.** This is the difference between *"I have a setup"* and *"I have a copilot."* The hardest part of discretionary trading is staying in winners and exiting losers before they run. The companion already knows the original thesis; it can keep watching. A trader who gets a *"breadth fell below 55%; original thesis invalidated"* alert at minute 22 of a CL trade has been handed back the cognitive bandwidth to read the next setup.

**Effort.** Large — the largest item on this list. Form + active-trade card + continuous evaluator + new event types + integration with replay and performance surfaces. Roughly 3–4 prompts of work.

**Risk.** Low-to-medium. The data sources are all already structured. The primary risks are:
- UX clarity (suggestion fatigue if alerts fire too often)
- Stale-data hygiene (if streamer is degraded, the active-trade view must visibly mark itself stale rather than emit guidance based on a frozen quote)

The fail-closed philosophy already in the codebase is the right anchor for both risks.

---

### Initiative 7 — Anchor input UI for NQ / 6E / MGC

**The gap.** NQ workstations need an ES anchor; 6E and MGC need a DXY value. These are operator-supplied (`source: "manual_operator_input"` per workstation contracts) but Phase 1 has no UI for inputting them.

**What's already built.** All three workstation files have full anchor data structures: `NQAnchor`, `SixEDXYState`, `MGCDXYState`. They're consumed by the QUERY_READY logic. The contract is "operator supplies; workstation evaluates."

**What changes.** Two design options worth weighing:

**Option A — Manual input UI.** Form fields per contract on the Trigger surface or a small contextual panel on each contract card. Operator types in DXY value once or twice a session. Time cost: ~5 seconds per update.

**Option B — Auto-fetch from streamer.** Subscribe to ES (already subscribed) and a DXY proxy through Schwab's level-one feed. Compute deltas. Push into anchor state automatically.

Option B is more elegant but introduces a new data dependency (DXY proxy availability through Schwab futures levelone). Option A is what the codebase architecture currently expects and is the safer choice — particularly because manual entry preserves the operator's read of "is the DXY signal clean or fakeable right now."

Recommend starting with Option A; revisit Option B only if manual entry is friction in practice.

**Why this materially helps the trader.** Today the NQ/6E/MGC workstations are technically functional but require the trader to stash anchor numbers in their head or on paper. A purpose-built input field with last-update timestamp converts that into a one-glance check.

**Effort.** Small (Option A). Medium (Option B).

**Risk.** Trivial (Option A). Low (Option B).

---

### Initiative 8 — Premarket brief enrichment (optional)

**The gap.** [`premarket_brief.py`](../src/ntb_marimo_console/ui/surfaces/premarket_brief.py) renders `setup_summaries[]` and `warnings[]` from a fixture-backed brief artifact. The shape is reasonable but shallow relative to the full pre-market workup an experienced trader does manually.

**What's already built.** Per-contract fixture briefs with structured setup descriptions and invalidation warnings. Loader at [`premarket_artifact_store.py`](../src/ntb_marimo_console/premarket_artifact_store.py).

**What could be added.** This is genuinely optional and depends on whether the trader wants the app to handle their full pre-market or whether they prefer to keep that workflow manual. Possibilities:

- **Overnight session summary**: Globex range, volume profile, value area
- **Key level register**: PDH/PDL, weekly H/L, monthly value-area, prior-session VWAP
- **Scheduled news/events** for the day with proximity warnings
- **Anchor reads**: opening ES level, opening DXY, opening crude (if trading equities)
- **Prior-session post-mortem**: what happened in yesterday's actual trades, what setups fired, what was missed

These are all data-additions to the brief artifact + corresponding renderer cuts. Engine logic doesn't change. Whether it's worth the work depends on whether the trader currently does this manually somewhere else and would benefit from consolidation.

**Why this materially helps the trader (if pursued).** A consolidated pre-market brief — engine setup thesis + structural levels + scheduled risk + prior-session review — turns 30 minutes of pre-market prep into a 5-minute review. The compounding benefit is that all of it is then in the audit trail.

**Effort.** Medium-large if all of the above. Small if just one or two cuts.

**Risk.** Low. Additive content.

---

### Initiative 9 — Stability hardening ⚙️ (separate track, blocks live use)

**The gap.** The live data path is structurally complete (R30 verified) but lacks runtime resilience. Long sessions die at token expiry. Network blips kill the streamer with no recovery. The receive loop is operator-driven, so a blocked handler drops ticks. There is no watchdog and no alerting on degraded state.

**What's already built.** The R29 [`OperatorSchwabStreamerSession`](../src/ntb_marimo_console/schwab_streamer_session.py) handles login/subscribe/logout cleanly with full sanitization. The R27 launcher ([`operator_live_runtime.py`](../src/ntb_marimo_console/operator_live_runtime.py)) opens exactly once per opt-in, never per Marimo refresh — that invariant must be preserved.

**What changes.**

**9a — Token auto-refresh.** Use the refresh_token already validated by the hardened OAuth contract (commit `3e19df8`). Refresh access_token before expiry without operator intervention. Documented as "downstream-step candidate" in R29; this completes that step.

**9b — Streamer reconnect with backoff.** On websocket close, attempt reconnect with exponential backoff (e.g., 1s, 2s, 5s, 15s, 60s, then fail-closed and surface). Re-subscribe to all five contracts on reconnect. Emit `stream_reconnected` event into replay log.

**9c — Managed receive thread.** Spawn a background thread (or asyncio task) that drives `dispatch_one()` continuously and pushes ticks into the existing manager cache. Operator no longer drives the loop; their handler is invoked from the cache, decoupled from network rate.

**9d — Watchdog / heartbeat.** Track time-since-last-tick per contract. If any contract goes quiet for more than (say) 30 seconds during RTH, mark it stale and surface in the session header. Existing `quote_stale` event in [`evidence_replay.py`](../src/ntb_marimo_console/evidence_replay.py) is the right backbone.

**9e — Degraded-state alerting.** Visual + optional system notification on degraded state (token refresh fail, reconnect exhausted, contract quote stale). No SMS/email — local notification is the safe scope.

**Why this materially helps the trader.** Without these, the companion is a daytime-only manually-restarted tool. With these, it's something a trader can leave running through a full session. This is the difference between "useful when I remember to check it" and "in the background, watching."

**Effort.** Medium per item; large in aggregate (5 sub-items).

**Risk.** Medium. Live data path is already structurally proven, but adding a managed thread + reconnect logic + token refresh introduces real concurrency considerations. Test coverage must include simulated network failure, simulated token expiry, and explicit non-regression for the "no repeated login per Marimo refresh" invariant.

---

## Suggested execution order

```
Stability      |■■■■■|              ← Initiative 9 (blocks reliable live use)
Surface narrative      |■■|         ← Initiative 1 (highest leverage)
Trigger prose             |■■|      ← Initiative 2
Anchor inputs                |■|    ← Initiative 7 (small)
Operator notes                |■|   ← Initiative 4 (small)
Audit/Replay UI                  |■■■|  ← Initiative 3
Performance review               |■■|   ← Initiative 5
Premarket enrichment                |■■| ← Initiative 8 (optional)
Active-trade ⭐                       |■■■■| ← Initiative 6 (largest)
```

**Rationale.**

1. **Stability first.** No feature work is meaningful if the data feed dies mid-session. This unlocks every subsequent item.
2. **Initiative 1 next.** Highest single leverage point — the engine narrative is already there, surfacing it transforms the app's character.
3. **Initiatives 2, 4, 7 are quick wins.** Trigger prose, operator notes, anchor inputs — each is small and additive. Do them in any order between bigger pieces.
4. **Initiatives 3 and 5 are mid-sized.** Audit/Replay and Performance Review both surface existing modules. Order by which gives the trader more value first — likely Replay if heavy backtesting culture, Performance if focused on edge analytics.
5. **Initiative 8 is optional.** Decide based on whether premarket consolidation is a real workflow gap or a nice-to-have.
6. **Initiative 6 last.** It's the largest and most novel. Doing it last means the surrounding tooling (replay, notes, performance) is in place to give it a strong feedback loop.

---

## What is intentionally NOT in this roadmap

To make the boundary explicit:

- **No order placement.** Anywhere. Ever.
- **No broker/account connection.** Schwab streaming is the only Schwab integration; no orders endpoint, no account endpoint, no positions endpoint.
- **No auto-execution from engine signals.** The trader always acts on their own platform.
- **No SMS/email/external alerting.** Local notifications only. Out-of-band channels expand the attack surface and the maintenance burden.
- **No remote audit sink.** Local JSONL + local replay surface. If remote audit is ever required, it becomes a separate scoped initiative with its own threat model.
- **No expansion of the contract universe.** ES, NQ, CL, 6E, MGC. ZN and GC remain out — actively rejected at multiple layers.
- **No fixture fallback after live failure.** Existing invariant. Preserved.
- **No automated decision authority outside the preserved engine.** Existing invariant. Preserved.

---

# Style map — visual structure and flow

How the app should look and feel for an experienced trader.

## Information architecture

The trader's cognitive load shifts across five session phases. The UI should foreground different content in each:

```
PRE-SESSION  →  PRE-OPEN  →  LIVE  →  IN-TRADE  →  POST-SESSION
   |             |            |          |              |
   v             v            v          v              v
Premarket    Workstations  Active     Active-Trade   Performance
brief +      arming;       triggers;  monitor +      review +
levels +     readiness     decision   thesis-health  audit replay
news         matrix        review     panel
```

## Layout — four-zone structure

Marimo renders cells stacked vertically by default, but for a dense trading companion the right metaphor is a **fixed four-zone shell**:

```
┌──────────────────────────────────────────────────────────────────────┐
│  TOP BAR  — phase chip · clock · session timer · health · manual-only │
├────────┬───────────────────────────────────────┬─────────────────────┤
│        │                                       │                     │
│  LEFT  │                                       │   RIGHT             │
│  RAIL  │         CENTER                        │   NARRATIVE         │
│        │         FOCUS                         │   PANEL             │
│ 5 con- │         SURFACE                       │                     │
│ tract  │                                       │  what's happening   │
│ cards  │  (premarket / workstation /           │  engine reasoning   │
│        │   decision / active-trade,            │  invalidation       │
│ ES     │   based on phase + selection)         │  operator notes     │
│ NQ     │                                       │                     │
│ CL     │                                       │                     │
│ 6E     │                                       │                     │
│ MGC    │                                       │                     │
│        │                                       │                     │
├────────┴───────────────────────────────────────┴─────────────────────┤
│  BOTTOM TIMELINE  — replay scrubber + event markers                  │
└──────────────────────────────────────────────────────────────────────┘
```

## Top bar

Dense, always-visible session state.

| Element | Content | Visual |
|---|---|---|
| Phase chip | PRE-SESSION / PRE-OPEN / LIVE / IN-TRADE / POST-SESSION | Color-coded pill |
| Clock | local time + session time-elapsed | Mono digits |
| Health indicators | token age · stream state · data freshness · stale-quote count | Tri-state pips: green / amber / red |
| Manual-only badge | "Manual execution only" reminder | Subtle but persistent |

## Left rail — contract roster (5 cards stacked vertically)

Each card a compact 5-row block. At-a-glance state for all 5 contracts at all times. **This is the heart of the dashboard.**

```
┌───────────────────────┐
│ ES         5604.50    │  ← symbol big, current price big
│ ▶ ARMED               │  ← state badge with icon
│ 4t to trigger         │  ← distance to trigger
│ ✓ anchors  ⚠ event    │  ← contextual pips (anchors aligned, event risk)
│ ──────────────────    │  ← active-trade indicator strip (visible if in trade)
└───────────────────────┘
```

**State color language** (single source of truth across the entire app):

| State | Color | Treatment |
|---|---|---|
| DORMANT | Cool gray (#3a4150) | Muted, low contrast |
| APPROACHING | Amber (#d4a017) | Solid |
| TOUCHED | Bright amber (#f5b800) | Solid |
| ARMED | Saturated amber (#ffb000) | Subtle pulse |
| QUERY_READY | Bright green (#15a163) | Strong pulse |
| IN_TRADE | Cool blue (#2e74d6) | Solid, distinct from QUERY_READY |
| THESIS_DEGRADING | Orange (#e07b00) | Solid + warning icon |
| INVALIDATED | Red (#c0392b) | Solid |
| STALE_DATA | Striped pattern over base color | Visible degradation |

Click a card → center surface focuses on that contract.

## Center focus surface

Content depends on session phase + selected contract:

**PRE-SESSION + any contract** → Premarket Brief
- Setup thesis (engine narrative)
- Key levels (when Initiative 8 lands)
- Disqualifiers as a checklist
- Scheduled events (when Initiative 8 lands)

**LIVE + DORMANT/APPROACHING** → Workstation Detail
- State machine progression (visual: dot path through DORMANT→APPROACHING→TOUCHED→ARMED→QUERY_READY)
- Current state's blocking reasons in plain prose (Initiative 2)
- Live observables (quote, distance, last bar)
- Anchor inputs UI (Initiative 7)

**LIVE + QUERY_READY** → Decision Review
- The full Initiative 1 render: state summary, engine reasoning, trade thesis, risk authorization, invalidation checklist
- "Submit Query" action button
- Notes input

**IN-TRADE** → Active-Trade Monitor (Initiative 6)
- Position summary card at top
- Thesis-health indicator (large, prominent)
- Suggested-action banner
- Live disqualifier monitor
- Time-in-trade clock

**POST-SESSION** → Performance + Replay
- Today's results card
- Audit replay timeline (default focused on most recent decision)

## Right narrative panel

Always visible. The "voice" of the engine.

Three sections, top-to-bottom:

1. **What's happening now** — The most recent transition narrative for the selected contract (Initiative 2). One-line, prominent.
2. **Engine reasoning** — `structural_notes`, evidence score, confidence band, conflicting signals (Initiative 1). Collapsible.
3. **Operator notes** — Free-text input + recent notes for this contract (Initiative 4).

If a trade is active:

4. **Thesis status** (replaces "what's happening") — *"Thesis intact. Breadth holding 65%. Time in trade 22m."* or *"Thesis degrading: breadth 56% (was 67%). Stop within 6t."*

## Bottom timeline

Horizontal event timeline (Initiative 3). Each event a small marker color-coded by category (stream / trigger / decision / trade / operator-note). Hover for one-line summary; click to drill in (replaces center surface temporarily). Filter chips above the timeline. Scrub bar to "replay" the session at any timestamp.

## Typography and density

- **Mono type for all numerics** (prices, distances, timestamps). Consistent decimals.
- **Sans-serif for prose.** Comfortable reading size (15–17px) for narrative — *the narrative is the product*, not a footnote.
- **Compact but never cramped.** Traders work with high information density; 8–12px padding inside cards is right, not 24.
- **Bold reserved for state changes**, not headers.

## Motion

Restraint, not flourish.

- State transitions: 150ms color crossfade, no movement.
- Pulses: only on QUERY_READY and degraded-state alerts. Slow (1.5s cycle).
- New events on the timeline: brief flash, then settle.
- No confetti, no unnecessary animations. A trading companion that draws attention to itself is broken.

## Phase-aware default focus

When the trader opens the app:

- Pre-market hours → centers on Premarket Brief for first contract that matches today's traded list (operator-configurable)
- During market hours → centers on the highest-state contract (QUERY_READY > ARMED > TOUCHED > APPROACHING > DORMANT)
- During an active trade → automatically shifts to the Active-Trade Monitor for that contract; left-rail card pulses
- Post-session → centers on Performance Review with replay timeline expanded

## Accessibility / discipline

- High-contrast color tokens; state language must be readable in bright light
- All state communicated by **shape + color**, never color alone (icons on every state badge)
- Keyboard shortcuts: `1-5` switches contract, `D` decision review, `T` trigger detail, `A` active-trade, `R` replay, `N` add note
- No modals — all panels inline; modal interactions break flow during fast markets

---

## Closing note

The companion is closer to its full vision than the surface gaps suggest. The largest single act of acceleration is not building new logic — it is rendering the logic that already exists. Initiatives 1 and 2, executed cleanly, would change the character of the app within a week. Initiative 6 is the only piece of genuinely ambitious new product. Everything else is connective tissue.

Boundary discipline holds the whole thing together: the manual-only execution invariant, fail-closed semantics, and the preserved engine as sole decision authority. Each initiative above respects all three. The trader gets a copilot, not a stepson.
