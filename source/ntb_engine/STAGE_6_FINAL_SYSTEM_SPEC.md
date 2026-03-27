# STAGE 6: Final Consolidated System Specification

## LLM-Driven Simulated Futures Trading System

---

# 1. Objective and Non-Goals

## Objective

Build a disciplined, fail-closed, LLM-driven workflow that evaluates market data for six futures contracts and produces structured trade decisions for a simulated trading challenge. The system prioritizes reliability, testability, and risk discipline over trade frequency.

## Non-Goals

- This system does not predict the market. It makes structured, evidence-based directional assessments of varying quality.
- This system does not claim trading edge. Edge can only be assessed after 100+ completed trades with statistical methods.
- This system does not replace human judgment. It is an analytical assistant that produces structured outputs for operator review.
- This system does not execute trades. It produces trade proposals that the operator manually executes.
- This system is not designed for live trading. It is specifically built for a simulated challenge environment.

---

# 2. Challenge Rules and Operator Decisions

## Challenge Constants

| Parameter | Value |
|-----------|-------|
| Starting balance | $50,000 |
| ES max position | 2 contracts |
| NQ max position | 2 contracts |
| CL max position | 2 contracts |
| ZN max position | 4 contracts |
| 6E max position | 4 contracts |
| MGC max position | 12 contracts |

## Operator Decisions (Binding)

### Risk Parameters
| Rule | Value |
|------|-------|
| Per-trade max dollar risk | $1,450 |
| Daily loss stop | $10,000 |
| Max aggregate open risk | $40,000 |
| Profit target | $400,000 |
| Max trailing drawdown | N/A |
| Trailing drawdown measurement | N/A |
| Minimum reward-to-risk | 1.5:1 (HIGH confidence), 2.0:1 (MEDIUM confidence) |

### Position Rules
| Rule | Value |
|------|-------|
| Multiple products simultaneously | YES, per-contract limits (ES:2, NQ:2, CL:2, ZN:4, 6E:4, MGC:12) |
| Opposite-direction flip | NOT ALLOWED |
| Scale-in | NOT ALLOWED |
| Scale-out | YES, max 2 targets, 50/50 split (position size > 1 only) |
| Partial exits | YES, pre-planned only |
| Trailing stop | YES, mechanical only |

### Trading Session Rules
| Contract | Allowed Hours (ET) |
|----------|-------------------|
| ES | 09:30 – 15:45 |
| NQ | 09:30 – 15:45 |
| CL | 09:00 – 14:15 |
| ZN | 08:20 – 14:45 |
| 6E | 08:00 – 12:00 |
| MGC | 08:20 – 13:15 |

Overnight holds: **PROHIBITED** — all positions flat by session close.

### Event Risk
| Rule | Value |
|------|-------|
| Event lockout | 15 min before, 5 min after Tier-1 releases |
| Hold through events | NO (or stop ≤ $725) |

### Re-Entry and Trade Limits
| Rule | Value |
|------|-------|
| Re-entry after stop-out | YES, 30-min cooldown, new signal required |
| Max trades/day (all contracts) | 60 |
| Max trades/day (per contract) | 3 |
| NO_TRADE valid all day | YES |

### Execution Assumptions
| Contract | Slippage (per side) | Commissions |
|----------|---------------------|-------------|
| ES | 1 tick | $0 |
| NQ | 1 tick | $0 |
| CL | 2 ticks | $0 |
| ZN | 1 tick | $0 |
| 6E | 1 tick | $0 |
| MGC | 1 tick | $0 |

### Holding Time Limits
| Class | Max Hold |
|-------|----------|
| Scalp | 15 minutes |
| Intraday swing | 2 hours |
| Session hold | 4 hours |

---

# 3. Contract-by-Contract Market Data Requirements

## Shared market_packet Fields (All Contracts)

All contracts require: timestamp, contract, session_type, current_price, session_open, prior_day_high, prior_day_low, prior_day_close, overnight_high, overnight_low, current_session_vah/val/poc, previous_session_vah/val/poc, vwap, session_range, avg_20d_session_range, cumulative_delta, current_volume_vs_average, opening_type, event_calendar_remainder, cross_market_context, data_quality_flags.

## Contract-Specific Extensions

| Contract | Mandatory Extensions | Key Drivers |
|----------|---------------------|-------------|
| **ES** | breadth, index_cash_tone | Value migration, breadth confirmation, opening type, VWAP |
| **NQ** | relative_strength_vs_es | ES relative strength, megacap leadership, tech sensitivity |
| **CL** | eia_timing, realized_volatility_context | Volatility regime, EIA proximity, liquidity/sweep dynamics |
| **ZN** | cash_10y_yield, treasury_auction_schedule, macro_release_context | Yield context, post-data sensitivity, auction schedule |
| **6E** | asia_high_low, london_high_low, ny_high_low_so_far, dxy_context, europe_initiative_status | Session initiative sequence, DXY correlation |
| **MGC** | dxy_context, yield_context, macro_fear_catalyst_summary | Dollar/yield regime, fear catalysts, swing volume |

## Upstream-Computed Fields (Cannot Be Inferred by LLM)

avg_20d_session_range, current_volume_vs_average, cumulative_delta, session_range, vwap, all VAH/VAL/POC values, relative_strength_vs_es (NQ), realized_volatility_context (CL), session high/low boundaries (6E), opening_type, key_hvns, key_lvns.

## Evidentiary-Only Visual Inputs

Chart images support the LLM's read but must not override structured numeric fields. Images are confirmatory evidence only.

---

# 4. Workflow Architecture

## 5-Stage Sequential Pipeline

```
market_packet → Stage A → Stage B → Stage C → Stage D → Stage E
                 │          │          │          │          │
            Sufficiency  Market    Setup      Risk       Logging
              Gate        Read    Construct   Auth
```

### Stage A: Sufficiency Gate (Contract-Specific)
- Validates market_packet completeness, staleness, challenge_state, event lockout, session hours
- Outputs: READY | NEED_INPUT | INSUFFICIENT_DATA | EVENT_LOCKOUT
- Never reads the market or forms opinions

### Stage B: Contract Market Read (Contract-Specific)
- Produces structured market analysis with regime, bias, levels, evidence_score, confidence_band
- evidence_score is quality-of-evidence (1–10), NOT probability
- confidence_band: LOW (1–3), MEDIUM (4–6), HIGH (7–10)
- NO_TRADE from Stage B → hard pipeline termination (skip C/D, go to E)

### Stage C: Setup Construction (Shared)
- Translates analysis into entry/stop/target/sizing or NO_TRADE
- Hard gates: LOW confidence → NO_TRADE; MEDIUM requires R:R ≥ 2.0; HIGH requires R:R ≥ 1.5
- Conflicting signals cap: ≥2 conflicts → evidence_score ≤ 6; ≥3 conflicts → evidence_score ≤ 4
- Sizing math is deterministic and transparent

### Stage D: Risk & Challenge Authorization (Shared)
- 13 mandatory risk checks, all reported
- Decisions: APPROVED | REJECTED | REDUCED
- Never re-reads market or adjusts the setup
- Validates only — does not trade

### Stage E: Logging & Decision Record (Shared)
- Complete pipeline trace for every run, regardless of outcome
- Append-only, self-contained JSON records

## Pipeline Termination Points

| Exit | Stage | Outcome | Logged |
|------|-------|---------|--------|
| Data insufficient | A | INSUFFICIENT_DATA | Stage A output only |
| Data incomplete | A | NEED_INPUT | Stage A output + missing field list |
| Event lockout | A | EVENT_LOCKOUT | Stage A output + event detail |
| Market unclear | B | NO_TRADE | A + B outputs |
| No viable setup | C | NO_TRADE | A + B + C outputs |
| Risk gate rejects | D | REJECTED | Full trace |
| Risk gate reduces | D | REDUCED | Full trace with adjusted size |
| Trade approved | D | APPROVED | Full trace — only path to execution |

## Key Architecture Rules
- Later stages never reinterpret earlier-stage outputs
- One contract at a time through the pipeline
- Update challenge_state after each APPROVED decision before running next contract
- NO_TRADE is the expected majority outcome (60–80% of evaluations)

---

# 5. Inter-Stage JSON Contracts

## Schema Inventory

| Schema | Producer | Consumer |
|--------|----------|----------|
| challenge_state | Operator | Stage A, D |
| contract_metadata | Config | Stage C, D |
| market_packet | Operator | Stage A |
| contract_specific_extension | Operator | Stage A, B |
| attached_visuals | Operator | Stage A, B |
| sufficiency_gate_output | Stage A | Stage B, E |
| contract_analysis | Stage B | Stage C, E |
| proposed_setup | Stage C | Stage D, E |
| risk_authorization | Stage D | Stage E |
| logging_record | Stage E | Evaluation |
| post_trade_review_record | Post-execution | Evaluation |

## Schema Design Principles
- **Provenance**: Every stage output includes a `stage` field identifying its producer
- **Timestamps**: Each output has its own timestamp
- **Contract ID**: Every output includes `contract` to prevent cross-contamination
- **Null discipline**: Fields marked `nullable: false` must never be null
- **decision_critical vs informational**: Clearly separated in every schema
- **Validation rules**:
  - evidence_score ↔ confidence_band consistency enforced
  - risk_authorization must contain exactly 13 checks
  - risk_dollars = max risk (full position at stop, worst case)
  - event_lockout_detail populated when status = EVENT_LOCKOUT

## Key Schema Additions from Audits
- `EVENT_LOCKOUT` status and `event_lockout_detail` field (Stage 3A)
- `checks_count` const field in risk_authorization (Stage 3A)
- `market_regime_at_entry` and `confidence_band_at_entry` in post_trade_review_record (Stage 3A)
- `last_trade_direction_by_contract` in challenge_state (Stage 4A)

*Full JSON schemas are in STAGE_3_SCHEMA_SET.md with corrections from STAGE_3A_APPROVED_SCHEMA_SET.md.*

---

# 6. Prompt Inventory

| # | Prompt | Stages Covered | Scope |
|---|--------|---------------|-------|
| 1 | Master Doctrine | Injected into all | Shared |
| 2 | ES Sufficiency + Market Read | A + B | ES-specific |
| 3 | NQ Sufficiency + Market Read | A + B | NQ-specific |
| 4 | CL Sufficiency + Market Read | A + B | CL-specific |
| 5 | ZN Sufficiency + Market Read | A + B | ZN-specific |
| 6 | 6E Sufficiency + Market Read | A + B | 6E-specific |
| 7 | MGC Sufficiency + Market Read | A + B | MGC-specific |
| 8 | Setup Construction | C | Shared |
| 9 | Risk & Challenge Authorization | D | Shared |

## Contract Prompt Differentiation

| Contract | Unique Analytical Framework |
|----------|---------------------------|
| **ES** | Value migration, breadth divergence, index cash tone, opening type initiative |
| **NQ** | Relative strength vs ES, megacap leadership concentration, tech-sector sensitivity, higher beta |
| **CL** | Volatility regime awareness, EIA timing/reaction, DOM/liquidity sweep dynamics, 2-tick slippage, geopolitical headlines. Strictest sufficiency gate. |
| **ZN** | Macro-driven primary. Yield context, post-data sensitivity windows, treasury auction positioning, Fed proximity. Hard block if macro data released but context missing. |
| **6E** | Session-sequenced (Asia → London → NY). DXY correlation. Hard block without session segmentation. Thin liquidity after 11:00 ET. |
| **MGC** | Macro-regime asset (DXY + yield). Fear catalyst awareness. Hard block without both DXY and yield context. High position count (up to 12). |

## Prompt Corrections Applied (from Stage 4A Red-Team)

- Entry price defaults to current_price (market order), not limit at key_levels
- Targets must correspond to identified key_levels (no stretching for R:R)
- Conflicting signals → evidence_score cap enforced
- Session wind-down flag (<30 min remaining)
- Stale analysis check (300 seconds) in Stage C
- Stage C rationale must reference only contract_analysis fields
- Max stop distance guidelines per contract
- CL: post-EIA settling period (15 min), evidence_score cap at 5
- ZN: worked tick math example, auction proximity caps evidence at 6
- 6E: London close thin liquidity flag after 11:00 ET
- NO_TRADE frequency expectation (60–80%) in Master Doctrine

*Full prompt text is in STAGE_4_PROMPT_SET.md with corrections from STAGE_4A_APPROVED_PROMPT_SET.md.*

---

# 7. Runtime Decision Flow

## Operator Workflow Per Evaluation

1. **Assemble market_packet** for the target contract (structured fields + images)
2. **Update challenge_state** (balance, P&L, open positions, trade counts)
3. **Run Pipeline** (Stages A → B → C → D → E)
4. **Review output**:
   - If TRADE_APPROVED → execute the trade manually per proposed_setup
   - If TRADE_REDUCED → execute with adjusted size
   - If NO_TRADE, REJECTED, INSUFFICIENT_DATA, or EVENT_LOCKOUT → no action, review reasons
5. **Log** the complete decision record
6. **Update challenge_state** if a trade was approved
7. **Repeat** for next contract if desired

## Multi-Contract Sequencing
- One contract at a time
- Update challenge_state between runs
- APPROVED = "open" for aggregate risk calculation immediately
- Do not lower standards because previous contracts returned NO_TRADE

---

# 8. Risk Controls

## Layered Risk Defense

| Layer | Control | Where Enforced |
|-------|---------|---------------|
| **Data quality** | Staleness check (5 min / 3 min CL), required field validation | Stage A |
| **Event risk** | Tier-1 lockout (15 min before, 5 min after), EVENT_LOCKOUT status | Stage A + D |
| **Session risk** | Allowed hours check, session wind-down flag | Stage A |
| **Evidence quality** | evidence_score → confidence_band gating, conflicting signal caps | Stage B + C |
| **Setup quality** | Minimum R:R (1.5 or 2.0), max stop distance, target anchoring | Stage C |
| **Per-trade risk** | $1,450 max risk including slippage | Stage C + D |
| **Daily risk** | $10,000 daily loss stop | Stage D |
| **Aggregate risk** | $40,000 max open risk across all positions | Stage D |
| **Position limits** | Contract-specific max sizes (ES:2, NQ:2, CL:2, ZN:4, 6E:4, MGC:12) | Stage D |
| **Trade frequency** | 60/day total, 3/day per contract | Stage D |
| **Cooldown** | 30-min after stop-out, no flip reversals | Stage D |
| **Overnight** | All positions flat by session close | Stage D |

## Fail-Closed Defaults
- Missing data → NEED_INPUT or INSUFFICIENT_DATA (never estimate)
- Unclear market read → NO_TRADE
- Marginal setup → NO_TRADE
- Any risk check fails → REJECTED
- Event proximity → EVENT_LOCKOUT

---

# 9. Logging and Evaluation Framework

## Logging
- Every pipeline run produces a complete `logging_record` regardless of outcome
- Records are append-only, self-contained JSON, queryable by contract/date/decision/stage
- Chart images archived with record_id-based filenames

## Performance Metrics
- Win rate, expectancy, actual R:R, MAE, MFE, hold time
- Segmented by: contract, setup class, market regime, confidence band, time-of-day

## Failure Taxonomy
1. **Data Sufficiency Failures** → fix Stage A gates
2. **Prompt Reasoning Failures** → fix Stage B/C prompt constraints
3. **Risk-Gate Failures** → fix Stage D logic
4. **Execution-Quality Failures** → adjust slippage/timing assumptions
5. **Expected variance** → not a failure, normal market outcome

## Sample Size Requirements
- Schema compliance: 20 runs
- Pattern observation: 50 runs
- Preliminary performance: 50 completed trades
- Statistical confidence: 100+ completed trades

## Pause Triggers
- Daily loss stop hit 2 days in one week
- 5 consecutive losses on any contract
- Any risk gate bypass
- Any schema violation
- Rolling 20-trade expectancy < -$50/trade
- NO_TRADE rate below 40%
- Actual slippage > 2× assumed on >50% of trades

*Full evaluation framework is in STAGE_5_VALIDATION_FRAMEWORK.md.*

---

# 10. Known Limitations

1. **Visual evidence is secondary**: The LLM cannot reliably extract precise numeric values from chart images. All decision-critical data must be in structured fields.

2. **Opening type classification is subjective**: The system depends on operator-computed opening type. Different operators may classify differently.

3. **Cross-market data is optional**: If the operator cannot provide cross-market readings (ZN direction, DXY, etc.), the system proceeds but with reduced confidence. This is a data gap, not a system defect.

4. **Cumulative delta computation varies by platform**: Different platforms compute delta differently. The operator must confirm their platform's method.

5. **Volume profile export**: If the operator's platform cannot export HVN/LVN levels numerically, those fields must be null, degrading data quality.

6. **Unscheduled events are not covered**: The event lockout only handles scheduled Tier-1 releases. Unscheduled Fed communications, geopolitical events, or flash crashes are not protected against.

7. **LLM reasoning is non-deterministic**: The same inputs may produce slightly different outputs across runs. This is inherent to LLM-based systems.

8. **evidence_score is model self-assessment**: There is no external validation that evidence_score correlates with actual trade outcome until sufficient sample sizes are achieved.

9. **Session wind-down is a soft flag**: The 30-minute session wind-down flag limits setup class but doesn't hard-block trading.

10. **Micro Gold (MGC) sizing math**: With $1.00/tick and up to 12 contracts, small errors in stop distance have proportionally larger effects. Extra care required.

---

# 11. Open Questions

1. **Opening type classification rules**: Should a deterministic rule set be defined for opening type, or is operator judgment acceptable?

2. **6E London session inclusion**: Should 6E allowed hours be extended to 2:00 AM ET (London open) for operators who want to trade the London session?

3. **Cross-rate data for 6E**: Should EUR/GBP or EUR/JPY be added to the 6E extension schema, or is DXY sufficient?

4. **Semiconductor sector tone for NQ**: Should a semiconductor sector index be added to the NQ extension schema?

5. **Post-EIA settling period for CL**: The 15-minute post-EIA evidence cap is a recommendation. Should this be a hard block instead?

6. **Trailing stop mechanics**: The trailing stop is defined as "mechanical only" but the specific rule (e.g., trail to breakeven after 1R) is not codified. Should it be?

7. **Image archival format**: What format and resolution should chart images be archived in for replay testing?

8. **Challenge_state update mechanism**: How does the operator update challenge_state in practice? Manual entry? Platform API? This affects staleness and accuracy.

---

# 12. Implementation Priorities

## Phase 1: Core Infrastructure (Implement First)
1. **Schema validation layer**: Validate all JSON inputs/outputs against approved schemas at every stage boundary
2. **challenge_state management**: Build a reliable mechanism for tracking balance, P&L, positions, and trade counts
3. **Contract metadata config**: Static configuration for all 6 contracts (tick size, dollar/tick, etc.)
4. **Logging infrastructure**: Append-only JSON log storage with query capability

## Phase 2: Pipeline Execution
5. **Prompt orchestration**: Sequential execution of Stage A → B → C → D with output passing
6. **Stage A implementation**: Sufficiency gate with all checks (staleness, fields, events, session, challenge_state)
7. **Stage B implementation**: Contract-specific market read prompts with structured output parsing
8. **Stage C implementation**: Setup construction with deterministic sizing math verification
9. **Stage D implementation**: 13-check risk authorization with completeness verification

## Phase 3: Evaluation and Ops
10. **Post-trade review recording**: Link trade outcomes back to logging records
11. **Performance dashboard**: Win rate, expectancy, R:R by contract/setup/regime
12. **Failure taxonomy classification tool**: Semi-automated classification of losses
13. **Pause trigger monitoring**: Automated alerts when thresholds are breached

## Phase 4: Hardening
14. **Replay testing harness**: Re-run historical pipeline evaluations with archived inputs
15. **A/B testing framework**: Compare prompt versions on the same input data
16. **Upstream data pipeline**: Automate market_packet assembly from platform data

---

# Artifact Index

| Artifact | File | Status |
|----------|------|--------|
| Operator decisions | STAGE_0_FINAL_OPERATOR_DECISIONS.md | Approved |
| Data sufficiency spec | STAGE_1_DATA_SUFFICIENCY_SPEC.md | Approved |
| Workflow architecture (raw) | STAGE_2_WORKFLOW_ARCHITECTURE.md | Superseded by 2A |
| Workflow architecture (approved) | STAGE_2A_APPROVED_WORKFLOW_ARCHITECTURE.md | Approved with corrections |
| JSON schemas (raw) | STAGE_3_SCHEMA_SET.md | Superseded by 3A |
| JSON schemas (approved) | STAGE_3A_APPROVED_SCHEMA_SET.md | Approved with fixes |
| Prompt set (raw) | STAGE_4_PROMPT_SET.md | Superseded by 4A |
| Prompt set (approved) | STAGE_4A_APPROVED_PROMPT_SET.md | Approved with fixes |
| Validation framework | STAGE_5_VALIDATION_FRAMEWORK.md | Approved |
| Final system spec | STAGE_6_FINAL_SYSTEM_SPEC.md | This document |

---

# Unresolved Contradictions

**None identified.** All contradictions found during audit stages (2A, 3A, 4A) were resolved with targeted corrections. The corrections are documented in the respective audit artifacts and summarized in this document.

---

*This specification is implementation-review ready. Prior approved decisions from all stages have been preserved. No redesign has been applied during consolidation.*
