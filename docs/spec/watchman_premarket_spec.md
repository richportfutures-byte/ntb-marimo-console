# NinjaTradeBuilder — Watchman Layer + Pre-Market Brief: Full Specification

## Document Purpose

This document is the authoritative specification for the Watchman Layer and Pre-Market Condition Framework added to NinjaTradeBuilder. It is written for LLM ingest, code generation, and system implementation. Every section is self-contained. All schema references use dot-notation (e.g., `prior_day.high`). All behavioral rules are stated as explicit constraints, not general descriptions.

---

## 1. System Context

### 1.1 Existing Core Pipeline

NinjaTradeBuilder runs structured market data through a 5-stage sequential pipeline across six futures contracts — ES, NQ, CL, ZN, 6E, and MGC — and produces fully documented, JSON-schema-validated trade proposals.

Pipeline stages:
- **Stage A (Sufficiency Gate)** — validates completeness, field-level staleness (5-min max; 3-min for CL), session hours, challenge state, and Tier-1 event lockout before forming any opinion. Missing data returns `NEED_INPUT` or `INSUFFICIENT_DATA`. Never estimates.
- **Stage B (Market Read)** — produces structured analysis with `evidence_score` (1–10) and confidence band. NO_TRADE at Stage B hard-terminates the pipeline.
- **Stage C (Setup Construction)** — enforces R:R minimums (1.5:1 for HIGH confidence, 2.0:1 for MEDIUM). LOW confidence is automatic NO_TRADE. Conflicting signals mechanically cap evidence_score (2 conflicts → cap 6; 3 conflicts → cap 4). Targets must anchor to identified key levels.
- **Stage D (Risk Authorization)** — 13 mandatory checks: per-trade max ($1,450), daily loss stop ($10,000), aggregate open risk cap ($40,000), per-contract position limits, 60 trades/day total, 3/day per contract, 30-min cooldown after stop-out, overnight flat enforcement, event proximity re-check. Validates only. Never re-reads market.
- **Stage E (Logging)** — appends complete audit record for every run regardless of outcome.

The system is calibrated to return NO_TRADE on 60–80% of evaluations. That is the design.

### 1.2 Per-Contract Analytical Frameworks (Stage B)

Each contract has its own prompt, required data extensions, and causal logic:

| Contract | Primary Causal Drivers |
|---|---|
| ES | Value migration, breadth divergence, index cash tone, opening type initiative |
| NQ | Relative strength vs. ES, megacap leadership concentration, tech-sector beta amplification |
| CL | Volatility regime (compressed/expanded), EIA timing and reaction windows, DOM sweep dynamics |
| ZN | Macro-primary framing, yield context, treasury auction schedule proximity |
| 6E | Asia→London→NY session sequence, DXY correlation, thin liquidity flag after 11:00 ET |
| MGC | DXY + yield dual-dependency, fear catalyst overlay, deterministic sizing math |

### 1.3 What This Spec Adds

1. **Watchman Layer** — a cross-cutting operator-narrative layer that generates pre-market structural briefs, enforces narrative discipline (every sentence maps to a schema field), and scores "market readiness" of all operator-facing output.
2. **Pre-Market Brief Capability** — a scheduled, per-contract process that consumes prior-day and overnight packets, computes a `PreMarketPacket`, and produces a `PreMarketBrief` with structural setups, contract-specific causal framing, and explicit schema-driven query triggers.

Non-goals (this iteration):
- No auto-execution. Operator pulls the trigger manually.
- No intraday continuous narration. Layer is pre-RTH only, plus deterministic on-demand re-runs.

---

## 2. Architecture Overview

### 2.1 New Components

1. **Watchman Orchestrator** — schedules pre-market runs per contract; gathers data into PreMarketPackets; orchestrates LLM brief generation; runs validation and scoring.
2. **Pre-Market Data Aggregator** — reads raw data sources (historical session stats, overnight data, macro/event calendars, breadth, DXY, yields); normalizes into `PreMarketPacket` per contract.
3. **Pre-Market Brief Generator (LLM-backed)** — uses contract-specific prompts and shared Thesis Registry to emit structured natural language briefs. Each contract sounds distinct because its causal framework is distinct.
4. **Watchman Validator & Scorer** — post-generation deterministic checks; produces `WatchmanScores`.
5. **Thesis Registry** — per-contract named thesis definitions shared between Stage B and Watchman, preventing drift between pre-market narrative and live pipeline decision logic.
6. **Persistence & Audit** — `PreMarketBrief` + `PreMarketPacket` + `WatchmanScores` appended to JSONL per contract per session.

### 2.2 Data Flow

```
[Scheduled Trigger: 08:00 ET]
        |
        v
[Pre-Market Data Aggregator]
  - Prior-day session loader
  - Overnight session loader
  - Macro/event loader (Tier-1, EIA, auctions)
  - Volatility/session-sequence calculators
        |
        v
[PreMarketPacket] (validated against contract-specific JSON Schema)
        |
        v
[Watchman Orchestrator]
  - Load Thesis Registry for contract
  - Build contract-specific LLM prompt
  - Call LLM → raw brief JSON
        |
        v
[Watchman Validator & Scorer]
  - Field coverage check
  - Trigger determinism check
  - Contract voice check
  - Risk language check
        |
        v
[PreMarketBrief] → JSONL audit log
        |
        v
[CLI / Python API] → Operator reads brief before RTH
        |
        v
[Operator observes market, waits for query_trigger condition]
        |
        v
[Stage A → B → C → D → E pipeline] (unchanged)
```

---

## 3. Data Schemas

### 3.1 PreMarketPacket

Purpose: normalized input to Watchman per contract per session. This is a superset schema; per-contract subsets are enforced by individual JSON Schemas.

```json
{
  "contract": "ES",
  "session_date": "YYYY-MM-DD",
  "timezone": "America/New_York",
  "prior_day": {
    "high": null,
    "low": null,
    "close": null,
    "poc": null,
    "vah": null,
    "val": null,
    "session_range": null
  },
  "overnight": {
    "high": null,
    "low": null,
    "volume": null,
    "session_profile": {
      "vah": null,
      "val": null,
      "poc": null
    }
  },
  "current_session": {
    "initial_balance_levels": {
      "ib_high": null,
      "ib_low": null
    },
    "vah": null,
    "val": null,
    "poc": null
  },
  "macro_context": {
    "tier1_events": [
      {
        "name": null,
        "timestamp": null,
        "importance": null
      }
    ],
    "eia_timing": null,
    "treasury_auction_schedule": [],
    "macro_release_context": null
  },
  "cross_asset": {
    "breadth": {
      "prior_close_advancers_pct": null,
      "current_advancers_pct": null
    },
    "index_cash_tone": null,
    "dxy": null,
    "cash_10y_yield": null
  },
  "volatility_context": {
    "realized_volatility_context": null,
    "avg_20d_session_range": null,
    "current_volume_vs_average": null
  },
  "session_sequence": {
    "asia_complete": null,
    "london_complete": null,
    "ny_pending": null
  },
  "metadata": {
    "packet_version": "pmkt_v1",
    "generated_at": null,
    "provenance": []
  }
}
```

### 3.2 PreMarketBrief

Purpose: output from Watchman per contract per session. Persisted to JSONL and surfaced via CLI and Python API.

```json
{
  "contract": "ES",
  "session_date": "YYYY-MM-DD",
  "as_of": null,
  "structural_setups": [
    {
      "id": "string — unique setup identifier",
      "summary": "string — one sentence",
      "description": "string — full narrative, all numerics tied to named fields",
      "fields_used": [
        "dot.notation.field.path"
      ],
      "contract_framework_labels": [
        "string — e.g. value_migration, breadth_divergence"
      ],
      "stage_b_thesis_links": [
        "string — named thesis from Thesis Registry"
      ],
      "query_triggers": [
        {
          "id": "string",
          "logic": "string — short predicate name",
          "description": "string — full trigger description in plain language",
          "observable_conditions": [
            "string — boolean predicate on operator-visible data"
          ],
          "fields_used": [
            "dot.notation.field.path"
          ]
        }
      ],
      "warnings": [
        "string — explicit conditions that suppress or invalidate the thesis"
      ]
    }
  ],
  "global_guidance": [
    "string — session-level directives for the operator"
  ],
  "watchman_scores": {
    "structural_anchor_score": null,
    "contract_voice_score": null,
    "risk_language_score": null,
    "hallucination_risk_score": null,
    "overall_market_readiness": null
  },
  "status": "READY | NEEDS_REVIEW | FAILED",
  "version": "pmkt_brief_v1"
}
```

### 3.3 WatchmanScores

All values 0.0–1.0. Higher is better except `hallucination_risk_score` (lower is better).

| Field | Definition |
|---|---|
| `structural_anchor_score` | Fraction of numeric/level claims in description that map to a named schema field |
| `contract_voice_score` | Coverage of required contract-specific causal elements (see §6) |
| `risk_language_score` | Presence and correctness of NO_TRADE/NEEDS_REVIEW risk caveats |
| `hallucination_risk_score` | Fraction of claims referencing undefined fields or unobservable conditions |
| `overall_market_readiness` | Aggregated score; weights: structural_anchor 0.35, contract_voice 0.30, risk_language 0.20, (1 - hallucination_risk) 0.15 |

---

## 4. Watchman Layer: Full Design

### 4.1 Responsibilities

1. Turn `PreMarketPacket` into contract-specific natural language that mirrors Stage B's analytical framework.
2. Enforce narrative discipline post-generation.
3. Score `WatchmanScores`.
4. Normalize output for CLI and Python API.

### 4.2 Narrative Rules (Hard Constraints)

The following constraints are enforced by the Watchman Validator. Any brief that fails them is marked `NEEDS_REVIEW` or discarded:

- **Rule N1**: Every numeric level appearing in `description` must map to a named field in `fields_used`.
- **Rule N2**: Every structural assertion ("price is below value", "sellers controlled into close") must list its source fields in `fields_used`.
- **Rule N3**: All `query_trigger.observable_conditions` must be boolean predicates expressible from streaming data the operator can see on their platform in real time.
- **Rule N4**: No speculative scenarios ("price might reach", "if the market decides to"). All conditions are stated as observable facts or explicit conditionals with named field thresholds.
- **Rule N5**: Brief must not assert Stage B will return TRADE or NO_TRADE before the operator has queried with live data. It may state the thesis activation conditions only.
- **Rule N6**: Warnings section must explicitly state any condition that suppresses the thesis (event lockout, auction proximity cap, thin liquidity regime, etc.).

### 4.3 LLM Prompting Strategy

**System role template (all contracts):**
> You are the Watchman for contract {CONTRACT}. Your role is to articulate the Stage B analytical framework as a pre-RTH structural brief. You must only speak about facts present in the provided PreMarketPacket JSON and explicitly defined derivations. You must output a valid PreMarketBrief JSON. You must follow all narrative rules N1–N6.

**Shared constraints block (injected into all prompts):**
- Reference the Thesis Registry entries for this contract.
- State every numeric level by its schema field name on first use.
- State query triggers as observable conditions on streaming data.
- Use present-tense conditional language ("long thesis activates only if X") not predictive language ("price will reach X").
- Warnings must be explicit and appear in the `warnings` array.

**Contract-specific guidance (injected per contract):** see §6.

### 4.4 Fallback Behavior

If LLM returns malformed JSON or fails validation on retry:
- Watchman generates a minimal conservative brief using deterministic templates only (no LLM narrative).
- Status set to `NEEDS_REVIEW`.
- Operator alerted via CLI on next `ntb watchman list` call.

---

## 5. Data Aggregation Mechanisms

### 5.1 Prior-Day Session Loader

**Inputs:** historical OHLC + volume profile data for the prior RTH session.

**Outputs to PreMarketPacket:**
- `prior_day.high`, `prior_day.low`, `prior_day.close`
- `prior_day.poc`, `prior_day.vah`, `prior_day.val`
- `prior_day.session_range` = `prior_day.high - prior_day.low`

**Derived context (computed, not stored raw):**
- Seller/buyer control tag: if `prior_day.close < prior_day.poc`, tag = "seller_control"; if > `prior_day.poc`, tag = "buyer_control".

### 5.2 Overnight Session Loader

**Inputs:** overnight OHLC + volume data from prior RTH close to current RTH open.

**Outputs to PreMarketPacket:**
- `overnight.high`, `overnight.low`, `overnight.volume`
- `overnight.session_profile.vah`, `.val`, `.poc` (if sufficient overnight volume; else null)

### 5.3 Macro/Event Loader

**Inputs:** economic calendar API or static file for session date.

**CL-specific:**
- `macro_context.eia_timing`: ISO8601 timestamp of EIA release if scheduled today; else null.
- Lockout windows computed downstream by Watchman: 15 min before EIA, 5 min after; evidence_score capped at 5 for 15 min post-release.

**ZN-specific:**
- `macro_context.treasury_auction_schedule`: array of upcoming auctions within 3 days.
- `cross_asset.cash_10y_yield`: prior close value.
- Evidence_score capped at 6 if auction within 2 days (enforced by Stage B Thesis Registry entry; stated in pre-market brief).

**All contracts:**
- `macro_context.tier1_events`: array of Tier-1 events for session date with timestamps. Used by Stage A for event lockout; referenced in brief warnings.

### 5.4 Volatility Calculator

**Inputs:** prior 20 sessions' range data.

**Outputs:**
- `volatility_context.avg_20d_session_range` = mean of prior 20 session ranges.
- `volatility_context.realized_volatility_context`: "compressed" if `prior_day.session_range < 0.75 * avg_20d_session_range`; "expanded" if > 1.25; "normal" otherwise.
- `volatility_context.current_volume_vs_average`: overnight or current session volume / average session volume. Populated when available.

### 5.5 Session Sequence Calculator (6E, FX contracts)

**Inputs:** timestamps of current UTC time relative to standard session hours.

**Outputs:**
- `session_sequence.asia_complete`: true if current time > Asia close (typically 03:00 ET).
- `session_sequence.london_complete`: true if current time > London close (typically 11:00–11:30 ET).
- `session_sequence.ny_pending`: true if NY RTH has not opened.

**Hard block rule (6E):** if `london_complete = false` and `ny_pending = true` and session data does not include full London range, brief must include warning that Stage B will hard-block without session segmentation.

---

## 6. Contract-Specific Brief Templates

### 6.1 ES

**Required narrative elements:**
- Prior day high/low/POC/VAH/VAL with exact values.
- Relative close vs POC (buyer/seller control tag).
- Overnight high and how it clusters with prior day levels.
- Breadth regime: `cross_asset.breadth.prior_close_advancers_pct` and what threshold activates long/short bias.
- Index cash tone: pointer to `cross_asset.index_cash_tone` and its role in confirming or diverging from futures.
- Clear long thesis activation: acceptance above identified resistance (2+ 5-min bars, `cumulative_delta` positive, `breadth` > 55%).
- Clear short thesis activation: rejection at resistance band with `cumulative_delta` negative and `index_cash_tone` diverging.
- Query trigger: price touches key level AND directional 5-min bar closes at or beyond it with directional delta.

**Required `contract_framework_labels`:** `value_migration`, `breadth_divergence`, `index_cash_tone`, `opening_type_initiative`.

### 6.2 NQ

**Required narrative elements:**
- NQ vs ES relative levels and divergence.
- Megacap leadership concentration: pointer to relevant field (or note if unavailable in packet).
- Beta regime: whether NQ is amplifying or lagging ES direction.
- Long/short thesis framed around relative strength, not absolute level breakouts.
- Query trigger tied to relative strength confirmation, not just absolute price.

**Required `contract_framework_labels`:** `relative_strength_vs_es`, `megacap_leadership`, `tech_beta_amplification`.

### 6.3 CL

**Required narrative elements:**
- `macro_context.eia_timing`: if today, state exact lockout windows (15 min before, 5 min after release; capped evidence_score for 15 min post-release).
- `volatility_context.realized_volatility_context`: state compressed/expanded/normal vs `avg_20d_session_range`.
- Explicit gate: "Absent range expansion with `current_volume_vs_average` > 1.2, compressed volatility regime will produce NO_TRADE."
- Query trigger: range expansion confirmed plus volume threshold crossed.
- DOM sweep dynamics pointer if available in packet.

**Required `contract_framework_labels`:** `volatility_regime`, `eia_timing_lockout`, `dom_sweep_dynamics`.

**Strictest sufficiency gate:** CL staleness threshold is 3 minutes (vs 5 for all others). This must be stated in the brief.

### 6.4 ZN

**Required narrative elements:**
- `cross_asset.cash_10y_yield` prior close with exact value.
- `macro_context.treasury_auction_schedule`: if auction within 2 days, state "evidence_score capped at 6 until auction clears, per Stage A rules."
- Basis-point threshold for query trigger: "if yield moves > N bps from prior close on Tier-1 release, update `macro_release_context` with actual print and direction vs. expectation, then query."
- Explicit: "Without `macro_release_context` populated, Stage A returns NEED_INPUT."
- Macro-primary framing: yield context is causal driver; price structure is secondary.

**Required `contract_framework_labels`:** `macro_primary`, `yield_context`, `auction_schedule_proximity`.

### 6.5 6E

**Required narrative elements:**
- State which sessions are complete: `session_sequence.asia_complete`, `session_sequence.london_complete`.
- DXY correlation: pointer to `cross_asset.dxy` and directional relationship.
- Hard block warning if session sequence is incomplete.
- Thin liquidity warning after 11:00 ET with explicit "queries after 11:00 ET carry thin liquidity flag; Stage B confidence band degrades."
- Query trigger anchored to NY inheriting directional London move with DXY confirmation.

**Required `contract_framework_labels`:** `session_sequence`, `dxy_correlation`, `thin_liquidity_flag`.

### 6.6 MGC

**Required narrative elements:**
- DXY level and direction: `cross_asset.dxy`.
- Yield level and direction: `cross_asset.cash_10y_yield`.
- Fear catalyst overlay: any active Tier-1 events creating risk-off environment.
- Dual-dependency rule: "MGC direction requires DXY and yield to be aligned; divergence between the two constrains Stage B confidence."
- Deterministic sizing math reference: up to 12 contracts; Stage C sizing is deterministic, not discretionary.
- Query trigger tied to DXY + yield alignment and fear catalyst confirmation.

**Required `contract_framework_labels`:** `dxy_yield_dual_dependency`, `fear_catalyst_overlay`, `deterministic_sizing`.

---

## 7. Watchman Validation Engine

All checks run post-LLM generation. Checks are deterministic (no LLM involved).

### 7.1 Field Coverage Check

Algorithm:
1. Parse `structural_setups[*].description` and extract all numeric values and level names.
2. For each extracted value, verify it appears in `fields_used` mapped to a valid dot-notation path in the `PreMarketPacket`.
3. For any derived value (e.g., "6-point resistance cluster"), verify a derivation formula is stated explicitly in the brief or in the Thesis Registry.
4. Fail condition: any numeric claim with no field mapping → `structural_anchor_score` penalized; if > 2 unanchored claims → status `NEEDS_REVIEW`.

### 7.2 Trigger Determinism Check

Algorithm:
1. Parse each `query_trigger.observable_conditions` entry.
2. Verify each condition is expressible as a boolean predicate on one of: live price stream, `cumulative_delta`, `cross_asset.breadth.current_advancers_pct`, `cross_asset.index_cash_tone`, or other explicitly listed streaming data fields.
3. Fail condition: any trigger condition that requires inference or judgment beyond a threshold comparison → flag for manual review.

### 7.3 Contract Voice Check

Per-contract checklist (see §6 for requirements). For each required `contract_framework_label`:
- Verify it appears in `contract_framework_labels` array.
- Verify corresponding narrative element appears in `description`.
- `contract_voice_score` = fraction of required labels present and described.

### 7.4 Risk Language Check

Algorithm:
1. Verify `warnings` array is non-empty.
2. Verify at least one warning states a condition under which Stage B will likely return NO_TRADE or NEED_INPUT.
3. Verify event lockout conditions are stated if any Tier-1 events exist in `macro_context.tier1_events`.
4. `risk_language_score` = 1.0 if all three pass; deductions per missing element.

### 7.5 Status Assignment

| Condition | Status |
|---|---|
| All checks pass, `overall_market_readiness` >= 0.85 | READY |
| One or more checks fail, `overall_market_readiness` >= 0.65 | NEEDS_REVIEW |
| LLM failure, schema parse failure, or `overall_market_readiness` < 0.65 | FAILED → fallback to deterministic brief |

---

## 8. Thesis Registry

### 8.1 Purpose

Prevents drift between Watchman pre-market narrative and Stage B live decision logic. Stage B and Watchman both consume the same Thesis Registry entries for a contract.

### 8.2 Structure Per Thesis Entry

```json
{
  "thesis_id": "es_long_above_resistance_cluster",
  "contract": "ES",
  "direction": "LONG",
  "activation_conditions": [
    {
      "field": "current_price_stream",
      "operator": ">=",
      "reference": "prior_day.high",
      "confirmation_bars": 2,
      "bar_timeframe": "5m"
    },
    {
      "field": "cumulative_delta",
      "operator": ">",
      "value": 0
    },
    {
      "field": "cross_asset.breadth.current_advancers_pct",
      "operator": ">",
      "value": 0.55
    }
  ],
  "evidence_score_contribution": 3,
  "framework_labels": ["value_migration", "breadth_divergence"],
  "description": "Long thesis activates only on acceptance above prior_day.high: two or more 5-minute bars closing above that level with cumulative_delta positive and breadth above 55% advancing."
}
```

### 8.3 Usage

- **Watchman**: loads thesis entries for the contract, uses `description` and `activation_conditions` to populate `stage_b_thesis_links` and `query_triggers` in the PreMarketBrief.
- **Stage B**: loads the same entries to evaluate the live packet. Thesis `activation_conditions` drive the Stage B market read.
- Consistency guarantee: because both consume the same registry, a pre-market brief that says "long thesis activates above 5604 with positive delta and >55% breadth" is guaranteed to match what Stage B actually checks.

---

## 9. APIs and Interfaces

### 9.1 Python API

```python
from ntb.watchman import generate_pre_market_brief, validate_brief, list_briefs

# Generate (or return cached)
brief = generate_pre_market_brief(
    contract="ES",
    session_date="2026-03-25",
    force_regen=False
)

# Validate stored brief
result = validate_brief(contract="ES", session_date="2026-03-25")

# List all briefs for a date
briefs = list_briefs(session_date="2026-03-25")
# Returns: [{"contract": "ES", "status": "READY", "overall_market_readiness": 0.92}, ...]
```

### 9.2 CLI

```
ntb watchman premarket CONTRACT [--date YYYY-MM-DD] [--json]
ntb watchman validate CONTRACT --date YYYY-MM-DD
ntb watchman list --date YYYY-MM-DD
```

**`ntb watchman premarket ES` example output:**
```
ES — Pre-Market Brief (2026-03-25)
Generated: 08:05 ET | Status: READY | Readiness: 0.92

Structure:
  • prior_day_high = 5604, previous_session_vah = 5598, overnight_high = 5601 —
    price is coiling inside a 6-point resistance cluster at the top of prior value.
  • prior_day_close = 5581 vs previous_session_poc = 5589 — sellers had control
    into the close; price is below value.

Stage B thesis:
  • Long thesis activates only on acceptance above 5604: two or more 5-minute bars
    closing above that level with cumulative_delta positive and breadth > 55% advancing.
  • Short thesis activates on rejection at 5598–5604 with cumulative_delta turning
    negative and index_cash_tone diverging from futures.

Query trigger:
  • Price touches 5598 or 5604 AND at least one 5-minute bar closes at or beyond
    that level with directional cumulative_delta. Neither thesis is live at open.

Warnings:
  • Neither long nor short thesis is live at open — price must declare first.

Watchman scores:
  • Structural anchor: 0.95 | Contract voice: 0.93 | Risk language: 0.90
  • Hallucination risk: 0.02 | Overall market readiness: 0.92
```

---

## 10. Storage and Audit

### 10.1 File Structure

```
logs/
  premarket/
    YYYY-MM-DD/
      ES.jsonl
      NQ.jsonl
      CL.jsonl
      ZN.jsonl
      6E.jsonl
      MGC.jsonl
```

### 10.2 JSONL Record Format (one line per run)

```json
{
  "run_id": "uuid",
  "contract": "ES",
  "session_date": "YYYY-MM-DD",
  "generated_at": "ISO8601",
  "pre_market_packet": { "...": "full PreMarketPacket" },
  "pre_market_brief": { "...": "full PreMarketBrief" },
  "watchman_scores": { "...": "WatchmanScores" },
  "llm_metadata": {
    "model": "string",
    "prompt_version": "string",
    "thesis_registry_version": "string",
    "tokens_used": null,
    "latency_ms": null
  },
  "packet_schema_version": "pmkt_v1",
  "brief_schema_version": "pmkt_brief_v1"
}
```

### 10.3 Retention and Queryability

- Append-only. No mutations.
- Queryable by: contract, session_date, status, overall_market_readiness.
- Linked to core pipeline audit logs via `session_date` + `contract` key.

---

## 11. Scheduler Mechanism

### 11.1 Trigger Times (configurable)

| Contract | Default Pre-Market Run Time (ET) | Rationale |
|---|---|---|
| ES | 08:00 | Prior to RTH open; after overnight data settles |
| NQ | 08:00 | Same as ES; NQ brief depends on ES context |
| CL | 08:30 | After EIA schedule confirmed; before energy market open |
| ZN | 07:30 | Before bond market open; yield data available |
| 6E | 07:00 | After London session active; before NY cross |
| MGC | 08:00 | After DXY and yield morning reads available |

### 11.2 Re-Run Triggers

On-demand re-run supported via:
- `ntb watchman premarket CONTRACT --force-regen`
- `generate_pre_market_brief(force_regen=True)`

Automatic re-run triggered if:
- Tier-1 event calendar changes after initial run.
- Overnight session data updates materially (configurable threshold).

---

## 12. Implementation Checklist

### Phase 1: Schemas and Registry

- [ ] JSON Schema: PreMarketPacket (global superset)
- [ ] JSON Schema: PreMarketPacket per contract (required field subsets)
- [ ] JSON Schema: PreMarketBrief
- [ ] JSON Schema: WatchmanScores
- [ ] Thesis Registry: data structure + initial entries for all 6 contracts
- [ ] Thesis Registry: loader and version management

### Phase 2: Data Aggregation

- [ ] Prior-day session loader (OHLC + volume profile)
- [ ] Overnight session loader
- [ ] Macro/event loader (Tier-1 events, EIA schedule, treasury auctions)
- [ ] Volatility calculator (avg_20d_session_range, regime tagging)
- [ ] Session sequence calculator (6E/FX contracts)
- [ ] PreMarketPacket builder (assembles all above into validated JSON)

### Phase 3: Watchman Core

- [ ] LLM prompt templates per contract (system role + shared constraints + contract-specific block)
- [ ] Watchman Orchestrator: schedule hooks, packet build, LLM call, retry logic
- [ ] LLM response parser: raw JSON → PreMarketBrief schema
- [ ] Fallback deterministic brief generator (no LLM)

### Phase 4: Validation and Scoring

- [ ] Field coverage check (Rule N1, N2)
- [ ] Trigger determinism check (Rule N3)
- [ ] Contract voice check (per §6 required labels)
- [ ] Risk language check
- [ ] WatchmanScores computation
- [ ] Status assignment logic

### Phase 5: Storage and Audit

- [ ] JSONL writer: premarket/YYYY-MM-DD/{contract}.jsonl
- [ ] Run ID generation (UUID)
- [ ] Schema versioning in every record
- [ ] Query utility: filter by contract, date, status

### Phase 6: APIs and CLI

- [ ] Python API: `generate_pre_market_brief`
- [ ] Python API: `validate_brief`
- [ ] Python API: `list_briefs`
- [ ] CLI: `ntb watchman premarket`
- [ ] CLI: `ntb watchman validate`
- [ ] CLI: `ntb watchman list`

### Phase 7: Testing

- [ ] Unit tests: schema validation for PreMarketPacket and PreMarketBrief
- [ ] Unit tests: field coverage check with known field-mapped and unanchored inputs
- [ ] Unit tests: trigger determinism check
- [ ] Unit tests: contract voice check per contract
- [ ] Golden brief tests: curated correct briefs per contract as regression targets
- [ ] Guardrail tests: missing fields → brief omits those fields cleanly
- [ ] Integration test: full pipeline from scheduler trigger → JSONL output
- [ ] CI: deterministic smoke checks with no live LLM dependency (mock LLM responses)

---

## 13. Worked Examples

### 13.1 ES Pre-Market Brief (reference narrative)

Input conditions:
- `prior_day.high` = 5604
- `prior_day.vah` = 5598
- `overnight.high` = 5601
- `prior_day.close` = 5581
- `prior_day.poc` = 5589
- `cross_asset.breadth.prior_close_advancers_pct` = 0.55

Output narrative:
> `prior_day_high` = 5,604. `previous_session_vah` = 5,598. `overnight_high` = 5,601. Price is coiling inside a 6-point resistance cluster at the top of prior value. `prior_day_close` = 5,581 relative to `previous_session_poc` = 5,589 — sellers had control into the close; price is below value.
>
> The Stage B long thesis activates only on acceptance above 5,604: two or more 5-minute bars closing above that level with `cumulative_delta` positive and `breadth` above 55% advancing.
>
> The Stage B short thesis activates on a rejection at 5,598–5,604 with `cumulative_delta` turning negative and `index_cash_tone` diverging from futures.
>
> Neither thesis is live at open — price has to declare first.
>
> **Query trigger:** Price touches 5,598 or 5,604 AND one 5-minute bar closes at or beyond that level with `cumulative_delta` directional. That is when you send the updated packet.

### 13.2 ZN Pre-Market Brief (reference narrative)

Input conditions:
- `cross_asset.cash_10y_yield` prior close = 4.42
- `macro_context.treasury_auction_schedule` = 10-year auction in 2 days
- `macro_context.tier1_events` = [CPI at 08:30 ET today]

Output narrative:
> `cash_10y_yield` prior close = 4.42. `treasury_auction_schedule` shows a 10-year auction in 2 days — `evidence_score` is capped at 6 until that auction clears, per Stage A rules.
>
> The ZN read today is macro-primary: if yield moves more than 3 basis points from 4.42 on the CPI release, update `macro_release_context` with the actual print and direction vs. expectation, then query. Without that context populated, Stage A returns `NEED_INPUT`.

### 13.3 CL Pre-Market Brief (reference narrative)

Input conditions:
- `macro_context.eia_timing` = today (EIA scheduled)
- `volatility_context.realized_volatility_context` = "compressed"
- `volatility_context.avg_20d_session_range` = 1.80 (CL points)
- `volatility_context.current_volume_vs_average` = 0.95

Output narrative:
> `eia_timing` = today. Event lockout activates 15 minutes before the release timestamp and clears 5 minutes after. Even after the lockout clears, `evidence_score` is capped at 5 for 15 minutes post-release while the post-EIA reaction settles.
>
> `realized_volatility_context` = compressed vs `avg_20d_session_range`. A range expansion with `current_volume_vs_average` > 1.2 is the structural condition that makes a CL read worth querying today — absent that, the compressed volatility regime will produce NO_TRADE.

---

## 14. Glossary

| Term | Definition |
|---|---|
| PreMarketPacket | Normalized JSON input to Watchman; assembled from prior-day, overnight, macro, cross-asset, and volatility data per contract per session |
| PreMarketBrief | Watchman output: structured natural language briefing with schema-anchored narrative, structural setups, and query triggers |
| WatchmanScores | Deterministic quality scores computed post-generation; gate brief status |
| Thesis Registry | Shared data structure encoding Stage B's per-contract thesis activation conditions; consumed by both Watchman and Stage B |
| Query Trigger | Explicit boolean predicate on operator-observable data that defines when to send a fresh live packet to Stage A |
| Structural Anchor | A numeric level or qualitative state whose source is a named schema field |
| Contract Voice | The set of contract-specific causal elements required to appear in a valid brief |
| Fail-Closed | System behavior where any ambiguity or missing data defaults to no output / NO_TRADE / NEED_INPUT rather than an estimate |
| NEED_INPUT | Stage A return value when required fields are missing or stale |
| NO_TRADE | First-class outcome at Stage B or Stage C indicating conditions do not meet the trade threshold |
| NEEDS_REVIEW | PreMarketBrief status when Watchman validation detects coverage gaps or unanchored claims |
