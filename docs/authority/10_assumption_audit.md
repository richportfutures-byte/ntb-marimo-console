# NTB Workstation — Assumption Audit & Product Clarification
**Session Date:** May 17, 2026  
**Purpose:** Clarify and correct nine foundational assumptions about the NTB trading workstation prior to a full engine and pipeline audit. These answers are authoritative and supersede any prior documentation that conflicts with them.

---

## What This App Is For

This is a **professional trading process workstation**. Its job is to make a disciplined intraday process visible, readable, and repeatable — session after session.

The app works when the trader engages with it as a workbench, not a signal light. The most valuable thing this system does is not blocking bad trades. It is **building a professional trading process** — one that creates positive feedback loops so the trader recognizes, over time, what works and what does not, grounded in real market structure.

The engine is a **discipline surface disguised as a readiness checker**. When it works well, the premarket narrative shapes what the trader is looking for before the session, live monitoring keeps that thesis honest against real price action, the invalidation surface catches when conditions shift — especially mid-trade — and over time the system builds the trader's ability to recognize which triggers work and which do not, because the process is consistent and visible every session. This is not a feature. It is the point.

**The UI's most important job is to make the process impossible to skip and easy to read.** If the surface is hard to parse, the trader routes around it. If it draws the trader in, the feedback loop forms. Everything else — aesthetics, layout, polish — is in service of that one outcome.

---

## What the App Delivers, In Order

### 1. Premarket Orientation
Before the session opens, the trader reads per-contract narratives that spell out what the market structure says to look for today. This is not a checklist. It is a grounded professional briefing that shapes the trader's lens for the entire session. All five target contracts receive a full briefing. The schema is already modeled in the engine — the surface needs to present it clearly, organized, and consistently.

### 2. Live Thesis Monitoring
During the session, the engine watches the contract against the established context — structure, VWAP, value, event risk, trigger proximity. The trader can see whether conditions still support the thesis or whether something has shifted.

### 3. Invalidation and Re-synthesis
When conditions change materially, the engine surfaces a new synthesis. The trader is told: the picture has changed, here is what to look for now. This is most critical when a trade is already on, because the thesis that justified entry may no longer be valid.

### 4. Manual Trade Entry and Active Trade Monitoring
The trader enters the trade manually. The engine then monitors the active position against the established thesis parameters using the live Schwab stream. P&L is a reflection of manual input — not authoritative brokerage data. It is a workstation aid, not a ledger.

---

## UI Surface Architecture

The session flows in two distinct density modes:

**Premarket surface — dense and comprehensive**  
The trader has time. Per-contract collapsible cards, each containing the full narrative briefing grounded in the packet schema. The trader works through each card, confirms the thesis, identifies key levels and triggers. A confirmation interaction records prep completion as part of the audit trail. The premarket surface does not need a hard gate before intraday surfaces become available — but it should be designed so that completing it is the natural path of least resistance. What is confirmed in premarket carries forward as the reference layer underneath the live monitoring view.

**Intraday surface — focused and scannable**  
Once the session is live, cognitive load is high and time is compressed. The monitoring and invalidation surfaces show the right thing immediately — current contract, current thesis state, what changed, what to look for now. This is a glance surface that earns a closer look only when something matters. These are two distinct UI modes, not the same layout scaled up or down.

---

## Assumption Audit — Confirmed and Corrected Answers

### Assumption A — Manual Execution Only
**Status: Confirmed and expanded.**

No automated broker, order, fill, or execution of any kind. This is a hard boundary with no planned change.

However, the app **must include a manual trade entry surface** where the trader inputs the trade. Once entered, the system monitors the active trade against established engine parameters using the live Schwab stream. P&L display is a reflection of manual input — not authoritative account data. The active trade monitoring capability maps to R26–R28 on the roadmap (Active-Trade Data Model, Thesis Health Monitor, Active-Trade Marimo Surface), which are defined but not yet implemented.

---

### Assumption B — Preserved Engine as Sole Decision Authority
**Status: Confirmed.**

The engine's output is the only source of GO / CAUTION / BLOCKED verdicts. The UI renders engine output — it does not produce, override, or supplement verdicts independently. No other layer, including the live feed or the UI itself, has decision authority. The engine arms, annotates, or redirects. The trader decides and executes manually.

---

### Assumption C — Target Contracts: ES, NQ, CL, 6E, MGC
**Status: Confirmed.**

All five contracts are active in the workstation. The premarket surface must present five per-contract briefings in a way that is readable without becoming overwhelming. The information density appropriate for premarket prep is higher than what is appropriate for intraday monitoring — layout should reflect this distinction rather than treating all five contracts identically across both modes.

---

### Assumption D — ZN and GC Excluded
**Status: Confirmed.**

No change. ZN and GC remain excluded from the target contract universe.

---

### Assumption E — Default Launch Behavior
**Status: Corrected. Previous assumption was wrong.**

The live Schwab stream connects when the app starts. There is no non-live default mode, no deferred connection, and no trader-activated live toggle. The live data feed is not optional — it is the prerequisite for every surface in the workstation:

- Without live data, premarket narratives have no current market context
- Without live data, intraday monitoring has nothing to monitor
- Without live data, the invalidation surface has no conditions to detect
- Without live data, the active trade panel has no price to track against

The entire product is inert without the live Schwab stream. Any constraint in the codebase that treats live data as optional, deferred, or mode-gated is incorrect and should be removed.

A persistent, unobtrusive **stream status indicator** (similar to the connection light on standard brokerage platforms) is the appropriate mechanism for communicating feed health. Green when healthy. Changes state visibly if the stream drops. Not a blocker, not a shutdown, not dramatic — just a permanent visible confirmation that data is live.

---

### Assumption F — No Fixture Fallback After Live Failure
**Status: Confirmed and simplified.**

No fixture fallback, no cached data, no silent degradation. If the stream drops, the status indicator changes. The trader knows immediately. Stale data is never presented as live under any circumstances. The response to a stream failure is visibility, not substitution.

---

### Assumption G — Secrets Storage
**Status: Confirmed.**

API keys, Schwab credentials, and tokens are stored in `.state/secrets` or an equivalent local protected path. Never in the repository, never in any publicly accessible location, never hardcoded. This is appropriate and sufficient for a single-operator local workstation. No additional hardening is required unless the deployment model changes to multi-user or cloud-hosted.

---

### Assumption H — Correctness vs. UI Elegance
**Status: Corrected. The assumption set up a false tradeoff.**

Correctness is non-negotiable and takes priority if there is ever a genuine conflict. However, there is no reason to accept a poor UI — the coding agents involved in this project are capable of delivering both correctness and polish simultaneously.

The workstation needs to be trustworthy **and** well-designed, because a polished, readable surface is what makes the trader engage with it as a daily workbench. A surface the trader does not want to use defeats the entire purpose of the feedback loop. Correctness and good design are not in opposition — a well-designed surface that draws the trader into the process **is** operator correctness.

---

### Assumption I — Marimo as Protected Dependency
**Status: Corrected. Marimo is not a protected dependency.**

The friction Marimo has introduced — built-in execution protocols and reactive constraints that coding agents have repeatedly had to work around — is a framework mismatch problem, not a UI polish problem. The agents have not been fighting bad code; they have been fighting Marimo's own rules. That friction is documented and real.

The forthcoming engine and pipeline audit will evaluate the workstation on its own terms and recommend the most workable UI surface for this product. If that surface is not Marimo, Marimo is replaced. The repo name is historical. The decision follows the evidence.

The question the audit must answer is: given what the engine actually produces, what is the cleanest UI surface that delivers the premarket prep, intraday monitoring, and invalidation/re-synthesis experiences — without fighting its own framework?

---

## What the Engine Is Not

The engine is not a punitive blocker. It is a **narrative habit enforcer** — it keeps the trader oriented to the right questions at the right time, grounded in real market structure. The engine's role is to surface what a grounded, professional, industry-recognized process would say to look for. It builds positive feedback loops. It teaches the trader to act like this is a real workbench.

---

## Hard Boundaries — Summary

| Boundary | Status |
|---|---|
| No automated execution of any kind | Hard — no change |
| Engine is sole decision authority | Hard — no change |
| Target contracts: ES, NQ, CL, 6E, MGC | Hard — no change |
| ZN and GC excluded | Hard — no change |
| Live stream connects on launch | Hard — corrected from prior assumption |
| No stale data presented as live | Hard — no change |
| Secrets stored locally, never in repo | Hard — no change |
| Marimo is not a protected dependency | Confirmed — open to replacement |

