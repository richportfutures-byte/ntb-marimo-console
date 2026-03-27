# STAGE 2: Workflow Architecture Design

---

## Architecture Decision: Staged Workflow vs Monolithic Prompt

**Recommendation: 5-stage sequential workflow.**

A monolithic prompt would need to simultaneously assess data sufficiency, read market structure, construct a setup, authorize risk, and produce a final decision — all while respecting 6 different contract personalities, event lockouts, position limits, and daily loss stops. This exceeds what a single prompt can do reliably because:

1. **Role confusion** — A single prompt that reads the market AND authorizes risk will inevitably blend market opinion with risk discipline. The risk gate must be independent.
2. **Failure mode ambiguity** — A monolithic prompt that returns NO_TRADE gives no visibility into *why*: was data insufficient? Was the read bearish? Was the setup marginal? Was risk budget exhausted?
3. **Hallucination surface** — The more responsibilities a single prompt has, the more likely it is to fabricate supporting evidence to justify a pre-formed conclusion.
4. **Testability** — Staged outputs allow each stage to be tested, replayed, and audited independently.
5. **Contract specificity** — The market-read stage must differ by contract. Embedding 6 contract personalities into one prompt creates collision risk.

---

## Final Staged Workflow

```
market_packet (input)
       │
       ▼
┌─────────────────────────┐
│  STAGE A: Sufficiency    │  ← Contract-specific
│  Gate                    │
└─────────┬───────────────┘
          │ READY / NEED_INPUT / INSUFFICIENT_DATA
          ▼
┌─────────────────────────┐
│  STAGE B: Contract       │  ← Contract-specific
│  Market Read             │
└─────────┬───────────────┘
          │ contract_analysis
          ▼
┌─────────────────────────┐
│  STAGE C: Setup          │  ← Shared logic
│  Construction            │
└─────────┬───────────────┘
          │ proposed_setup (or NO_TRADE)
          ▼
┌─────────────────────────┐
│  STAGE D: Risk &         │  ← Shared logic
│  Challenge Authorization │
└─────────┬───────────────┘
          │ risk_authorization (APPROVED / REJECTED / REDUCED)
          ▼
┌─────────────────────────┐
│  STAGE E: Logging &      │  ← Shared logic
│  Decision Record         │
└─────────────────────────┘
```

---

## Stage-by-Stage Specification

---

### STAGE A: Sufficiency Gate

| Property | Value |
|----------|-------|
| **Purpose** | Validate that the market_packet contains enough data to proceed with a defensible market read |
| **Shared or contract-specific** | **Contract-specific** — each contract has different required fields and thresholds |
| **Inputs** | Raw `market_packet` + `contract_specific_extension` + `attached_visuals` flags + `challenge_state` |
| **Outputs** | `sufficiency_gate_output` with status READY, NEED_INPUT, or INSUFFICIENT_DATA |
| **Allowed decisions** | READY (proceed), NEED_INPUT (list missing fields), INSUFFICIENT_DATA (halt) |
| **Must never do** | Read the market. Form an opinion on direction. Suggest a trade. Estimate missing values. |
| **Failure behavior** | If any mandatory field is null/missing → NEED_INPUT. If >3 mandatory fields missing or critical context absent → INSUFFICIENT_DATA. If event lockout is active → INSUFFICIENT_DATA with reason "event_lockout". |
| **Pipeline effect** | NEED_INPUT → return to operator with explicit field list. INSUFFICIENT_DATA → pipeline terminates for this contract. Only READY proceeds to Stage B. |

**Contract-specific sufficiency rules:**
- **CL**: If `realized_volatility_context` = "elevated" AND EIA within 30 min → INSUFFICIENT_DATA
- **ZN**: If Tier-1 data released today but `macro_release_context` is empty → INSUFFICIENT_DATA
- **6E**: If `asia_high_low` or `london_high_low` missing during NY session → INSUFFICIENT_DATA
- **MGC**: If both `dxy_context` and `yield_context` missing → INSUFFICIENT_DATA

---

### STAGE B: Contract Market Read

| Property | Value |
|----------|-------|
| **Purpose** | Produce a structured market read for one specific contract using the validated market_packet |
| **Shared or contract-specific** | **Contract-specific** — each contract has its own prompt reflecting its drivers, personality, and session structure |
| **Inputs** | Validated `market_packet` (READY status from Stage A) + `contract_specific_extension` + attached visual evidence |
| **Outputs** | `contract_analysis` containing: market_regime, directional_bias, key_levels, evidence_score, confidence_band, value_context, and structural_notes |
| **Allowed decisions** | Produce a structured analysis. May return NO_TRADE if the read is genuinely unclear or conflicting. May return INSUFFICIENT_DATA if the visual evidence contradicts structured data in a way that cannot be resolved. |
| **Must never do** | Construct a trade setup. Determine position size. Assess portfolio risk. Override structured field values with visual impressions. Claim statistical confidence. |
| **Failure behavior** | If the read is ambiguous → set `confidence_band` = LOW and `directional_bias` = "unclear". Do not force a directional call. If conflicting signals → list conflicts explicitly in `structural_notes`. |

**Key design rules for Stage B:**
- `evidence_score` is a quality-of-evidence score (1–10), NOT a probability of trade success
- `confidence_band` must be LOW, MEDIUM, or HIGH
- If `evidence_score` < 4, the downstream Stage C should interpret this as a strong NO_TRADE signal
- The market read must reference specific levels from structured data, not vague chart impressions
- Contract-specific prompts must reflect real differences:
  - **ES**: Value area migration, breadth confirmation, index cash tone
  - **NQ**: Relative strength vs ES, megacap leadership, tech sensitivity
  - **CL**: Volatility regime, EIA proximity, liquidity/sweep dynamics, DOM asymmetry
  - **ZN**: Yield context, post-data sensitivity, auction schedule, absorption
  - **6E**: Session initiative sequence (Asia → London → NY), DXY context, range extension/reversal
  - **MGC**: Macro fear catalyst, DXY/yield regime, swing penetration volume

---

### STAGE C: Setup Construction

| Property | Value |
|----------|-------|
| **Purpose** | Translate the contract_analysis into a concrete trade setup with entry, stop, targets, and sizing metadata — or determine NO_TRADE |
| **Shared or contract-specific** | **Shared logic** — one prompt handles all contracts using the contract_analysis as input and contract_metadata for sizing math |
| **Inputs** | `contract_analysis` from Stage B + `contract_metadata` (tick size, dollar/tick, point value, max position) + `challenge_state` (balance, daily P&L, open positions) |
| **Outputs** | `proposed_setup` containing: direction, entry_price, stop_price, target_1, target_2 (optional), position_size, risk_dollars, reward_risk_ratio, setup_class, hold_time_estimate, rationale, disqualifiers |
| **Allowed decisions** | Construct a setup if evidence supports it. Return NO_TRADE if: evidence_score < 4, confidence_band = LOW with no confirming structure, R:R < 1.5:1, or conflicting signals dominate. |
| **Must never do** | Override the market read from Stage B. Invent levels not present in contract_analysis. Ignore minimum R:R requirement. Force a trade when evidence is marginal. Determine whether the trade fits within portfolio risk — that is Stage D's job. |
| **Failure behavior** | If the math doesn't work (stop too wide for R:R requirement, position size would be 0) → NO_TRADE with explicit reason. If multiple setups exist → select the one with highest evidence_score and R:R, present only one. |

**Sizing computation rules (must be deterministic):**
```
risk_per_tick = dollar_per_tick
stop_distance_ticks = abs(entry_price - stop_price) / tick_size
raw_risk_dollars = stop_distance_ticks * risk_per_tick * position_size
adjusted_risk_dollars = raw_risk_dollars + (slippage_ticks * 2 * risk_per_tick * position_size)
```
- `adjusted_risk_dollars` must be ≤ `max_risk_per_trade_dollars` ($1,450)
- `position_size` must be ≤ contract's `max_position_size`
- `reward_risk_ratio` must be ≥ 1.5

**Setup classes:**
- **Scalp**: Hold ≤ 15 min, tight stop, quick target
- **Intraday Swing**: Hold 15 min – 2 hrs, structure-based stop
- **Session Hold**: Hold 2–4 hrs, wider stop, larger target

---

### STAGE D: Risk & Challenge Authorization

| Property | Value |
|----------|-------|
| **Purpose** | Independently verify that the proposed_setup is allowed under all risk rules and challenge constraints — or reject/reduce it |
| **Shared or contract-specific** | **Shared logic** — one prompt, same rules for all contracts |
| **Inputs** | `proposed_setup` from Stage C + `challenge_state` (balance, daily P&L, open positions, aggregate risk) + operator decisions from Stage 0 |
| **Outputs** | `risk_authorization` containing: decision (APPROVED / REJECTED / REDUCED), checks_passed, checks_failed, adjusted_position_size (if REDUCED), rejection_reasons |
| **Allowed decisions** | APPROVED (trade may proceed as specified), REJECTED (trade is blocked with reasons), REDUCED (position size lowered to fit constraints) |
| **Must never do** | Re-read the market. Form an opinion on whether the trade idea is good. Override the market analysis. Suggest a different entry or direction. Adjust the stop loss. It validates — it does not trade. |
| **Failure behavior** | If any check fails → REJECTED. If position size must be reduced to fit aggregate risk → REDUCED with new size. If challenge_state data is missing → REJECTED with reason "challenge_state_incomplete". |

**Checks performed (in order):**

| # | Check | Rule | On Fail |
|---|-------|------|---------|
| 1 | Daily loss stop | daily_realized_pnl + proposed risk ≤ daily_loss_stop ($10,000) | REJECTED |
| 2 | Per-trade risk cap | adjusted_risk_dollars ≤ $1,450 | REJECTED or REDUCED |
| 3 | Aggregate open risk | current_open_risk + proposed risk ≤ $40,000 | REJECTED or REDUCED |
| 4 | Position size limit | position_size ≤ contract max | REDUCED |
| 5 | Per-contract position limit | open positions on this contract < contract max_position_size | REJECTED |
| 6 | Max trades today (all) | trades_today_all < 60 | REJECTED |
| 7 | Max trades today (contract) | trades_today_contract < 3 | REJECTED |
| 8 | Event lockout | No Tier-1 event within lockout window | REJECTED |
| 9 | Cooldown after stop-out | If stopped out on this contract, ≥ 30 min elapsed | REJECTED |
| 10 | Opposite-direction flip | Not a flip of a just-closed position | REJECTED |
| 11 | Session hours | Current time within allowed hours for contract | REJECTED |
| 12 | Overnight hold risk | If setup hold_time_estimate would extend past session close → REJECTED | REJECTED |
| 13 | Minimum R:R | reward_risk_ratio ≥ 1.5 | REJECTED |

---

### STAGE E: Logging & Decision Record

| Property | Value |
|----------|-------|
| **Purpose** | Create a complete decision record for every pipeline run, regardless of outcome |
| **Shared or contract-specific** | **Shared logic** |
| **Inputs** | All prior stage outputs: sufficiency_gate_output, contract_analysis, proposed_setup, risk_authorization, plus challenge_state and timestamps |
| **Outputs** | `logging_record` containing: full pipeline trace, final_decision, all intermediate outputs, timestamps, data_quality_flags |
| **Allowed decisions** | None — this is a recording stage only |
| **Must never do** | Override any prior decision. Modify any prior output. Add trading commentary. |
| **Failure behavior** | If any prior stage output is missing → log what is available and flag the gap |

**The logging record is the input to post-trade evaluation (Stage 5 framework).**

---

## Cross-Cutting Architecture Decisions

### What is shared across all contracts
- Setup construction logic (Stage C)
- Risk authorization logic (Stage D)
- Logging structure (Stage E)
- Challenge constants and operator decisions
- Terminology and status enums (READY, NEED_INPUT, NO_TRADE, INSUFFICIENT_DATA)
- Sizing math formula

### What must differ by contract
- Sufficiency gate thresholds and required fields (Stage A)
- Market read prompt — drivers, session awareness, cross-market context (Stage B)
- Contract metadata (tick size, dollar/tick, point value, max size)
- Slippage assumptions
- Allowed trading hours
- Contract-specific extensions in market_packet

### Confidence: numeric, banded, or both
**Both.** `evidence_score` is numeric (1–10) for granularity in logging and evaluation. `confidence_band` is categorical (LOW/MEDIUM/HIGH) for decision gating. The mapping:
- 1–3 → LOW
- 4–6 → MEDIUM
- 7–10 → HIGH

`evidence_score` is a quality-of-evidence score. It answers: "How good is the data and structural picture I'm seeing?" It does NOT answer: "How likely is the trade to win?"

### How to avoid fake probabilistic precision
- Never use "70% probability of success" language
- `evidence_score` must be explicitly labeled as evidence quality, not win probability
- `confidence_band` must be described as the LLM's confidence in its read, not in the trade outcome
- Statistical claims are reserved exclusively for the evaluation layer (Stage 5) after sufficient sample sizes

### Multiple candidate trades or only one
**Only one.** The system evaluates one contract at a time through the pipeline. If the operator wants to evaluate multiple contracts, they run the pipeline separately for each. The risk gate (Stage D) handles aggregate risk across open positions.

### Preserve prior-stage outputs or allow reinterpretation
**Preserve verbatim.** Each stage receives the prior stage's output as structured JSON and must not reinterpret, rephrase, or override it. Stage C receives Stage B's `contract_analysis` and must use the levels, bias, and evidence_score as given. Stage D receives Stage C's `proposed_setup` and must not re-trade the market. This is enforced by:
1. Explicit "must never do" constraints in each prompt
2. Schema validation between stages
3. Provenance fields in every output

---

## Pipeline Termination Points

| Termination Point | Stage | Outcome | What Gets Logged |
|------------------|-------|---------|-----------------|
| Data insufficient | A | INSUFFICIENT_DATA | sufficiency_gate_output only |
| Data incomplete | A | NEED_INPUT | sufficiency_gate_output with missing field list |
| Market read unclear | B | NO_TRADE (optional) | sufficiency + contract_analysis |
| No viable setup | C | NO_TRADE | sufficiency + analysis + NO_TRADE reason |
| Risk gate rejects | D | REJECTED | Full pipeline trace including rejection reasons |
| Risk gate reduces | D | REDUCED | Full pipeline trace with adjusted size |
| Trade approved | D | APPROVED | Full pipeline trace — this is the only path to execution |

**Every termination point produces a logging record. NO_TRADE and REJECTED are normal, expected outcomes — not errors.**

---

## Operator Acceptance Checklist (Stage 2)

- [x] Architecture is staged (5 stages), not monolithic
- [x] Sufficiency gate occurs before market read
- [x] Setup construction is separate from risk authorization
- [x] Event lockout placement is explicit (Stage A and Stage D both check)
- [x] Later stages are prevented from silently rewriting earlier logic
- [x] NO_TRADE and INSUFFICIENT_DATA are preserved as first-class outcomes
- [x] Stage boundaries are crisp with explicit "must never do" constraints
- [x] Fail-closed behavior is the default at every stage
- [x] No prompts have been written yet

**Stage 2 Status: COMPLETE — Ready for Architecture Defect Audit (Stage 2A).**
