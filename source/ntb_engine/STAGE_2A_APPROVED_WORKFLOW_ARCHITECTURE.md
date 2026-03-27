# STAGE 2A: Architecture Defect Audit

---

## 1. Critical Defects

### DEFECT 1: Event lockout is checked in two places with no defined precedence

**Location**: Stage A (Sufficiency Gate) and Stage D (Risk Authorization) both check event lockout.

**Problem**: Stage A checks event lockout as part of sufficiency ("if event lockout is active → INSUFFICIENT_DATA"). Stage D also checks event lockout as check #8. If Stage A passes but the event window shifts (e.g., a release is rescheduled or the operator's calendar updates between stages), Stage D might still reject. This is acceptable — but the reverse is dangerous: if Stage A blocks on event lockout, it reports INSUFFICIENT_DATA, which conflates "data is genuinely missing" with "data is fine but we're in a lockout window." These are different failure modes with different operator responses.

**Severity**: Critical — mixes two distinct failure reasons under one status code.

### DEFECT 2: No explicit handling for stale market_packet

**Location**: Stage A (Sufficiency Gate).

**Problem**: The sufficiency gate checks whether fields are present but does not check whether the `timestamp` on the market_packet is stale. If the operator submits a packet that is 20 minutes old, the system would evaluate it as READY. Stale data in fast-moving markets (especially CL) can lead to decisions based on prices that no longer exist.

**Severity**: Critical — could produce trades against an outdated market picture.

### DEFECT 3: challenge_state is consumed at Stage A and Stage D but no stage validates it

**Location**: Architecture-wide.

**Problem**: `challenge_state` (balance, daily P&L, open positions) is referenced at Stage A (for context) and Stage D (for authorization). But no stage explicitly validates that `challenge_state` itself is complete and current. If `daily_realized_pnl` is null or `current_open_positions` is stale, Stage D's risk math is unreliable.

**Severity**: Critical — risk gate operates on unvalidated inputs.

---

## 2. Hidden Ambiguities

### AMBIGUITY 1: Who classifies opening_type?

The architecture assumes `opening_type` arrives in the market_packet as a structured field. Stage 1 lists it as "must be computed upstream." But the classification rules (Open-Drive, Open-Test-Drive, Open-Rejection-Reverse, Open-Auction) are subjective and require at least 15–30 minutes of price action. **Who computes this?** If the operator computes it manually, it's a human judgment call. If it's rule-based, the rules need to be defined. If the LLM infers it from the 5-minute chart, then it's not truly an upstream-computed field.

**Impact**: Medium — incorrect opening_type classification could bias the market read.

### AMBIGUITY 2: How does the operator run the pipeline for multiple contracts?

The architecture says "the system evaluates one contract at a time." But it doesn't specify:
- Does the operator run all 6 contracts every session?
- In what order?
- Can the operator run ES, get APPROVED, then run NQ, and the aggregate risk check in Stage D accounts for the now-pending ES trade?
- When does a "pending" approved trade become an "open" position in challenge_state?

**Impact**: Medium — aggregate risk math in Stage D depends on accurate open-position tracking.

### AMBIGUITY 3: What happens when Stage B returns NO_TRADE?

Stage B can optionally return NO_TRADE if the market read is "genuinely unclear." But the architecture doesn't specify whether this means:
- (a) Pipeline terminates — skip Stage C and D, go straight to Stage E logging
- (b) Stage C receives the analysis with a NO_TRADE flag and makes the final call

Option (a) is cleaner and consistent with fail-closed philosophy. But it needs to be explicit.

### AMBIGUITY 4: Scale-out target handling in Stage C

The operator decisions allow 2 scale-out targets. Stage C outputs `target_1` and `target_2`. But the architecture doesn't specify:
- Is `position_size` the full size, with partial exits at target_1 and target_2?
- What fraction exits at each target?
- Does Stage D authorize the full position or each tranche separately?

**Impact**: Medium — affects sizing math and risk calculation.

---

## 3. Failure-Path Weaknesses

### WEAKNESS 1: Stage B confidence_band = LOW does not guarantee NO_TRADE

The architecture says "If `evidence_score` < 4, the downstream Stage C should interpret this as a strong NO_TRADE signal." The word "should" is not fail-closed. Stage C could still construct a setup on a LOW confidence read if the price action looks clean. This is a soft gate, not a hard gate.

**Fix needed**: Define a hard threshold. If `confidence_band` = LOW, Stage C MUST return NO_TRADE. If MEDIUM, Stage C may proceed but must meet all other criteria. Only HIGH gives Stage C full latitude.

### WEAKNESS 2: No timeout on pipeline execution

If the operator runs Stage A → B → C → D sequentially over 15 minutes, the market may have moved significantly between Stage A's validation and Stage D's authorization. There is no max-age check on prior-stage outputs.

**Impact**: Low in practice (operator likely runs quickly), but architecturally it's an open failure path.

### WEAKNESS 3: Stage D does not verify that proposed_setup levels are still valid

Stage D validates risk math and challenge constraints. But it does not check whether `entry_price` from Stage C is still near the current market price. If the market moved 2% between Stage C and Stage D, the entry may be stale.

**Impact**: Medium — a stale entry price could make the trade unexecutable or change its risk profile.

---

## 4. Recommended Corrections

### CORRECTION 1: Separate event lockout from data insufficiency in Stage A

Add a new status: `EVENT_LOCKOUT` as a distinct return from Stage A, separate from INSUFFICIENT_DATA. This preserves diagnostic clarity.

Updated Stage A outputs:
- `READY` — proceed to Stage B
- `NEED_INPUT` — list missing fields
- `INSUFFICIENT_DATA` — data is genuinely insufficient
- `EVENT_LOCKOUT` — data may be fine but an event window is active

Pipeline effect: Both INSUFFICIENT_DATA and EVENT_LOCKOUT terminate the pipeline. The difference is in logging and operator response.

### CORRECTION 2: Add staleness check to Stage A

Add a mandatory check: if `market_packet.timestamp` is more than **5 minutes old**, return `NEED_INPUT` with reason "stale_packet" and request a refreshed packet. For CL specifically, reduce this to **3 minutes** during high-volatility periods.

### CORRECTION 3: Add challenge_state validation to Stage A

Stage A should validate `challenge_state` completeness before proceeding:
- `current_balance` must not be null
- `daily_realized_pnl` must not be null
- `current_open_positions` must be a valid list (may be empty)
- If any is missing → `NEED_INPUT` with the missing challenge_state fields listed

### CORRECTION 4: Make Stage B → NO_TRADE a hard pipeline termination

If Stage B returns NO_TRADE, the pipeline skips Stage C and Stage D and proceeds directly to Stage E (logging). Stage C never sees a NO_TRADE analysis.

### CORRECTION 5: Define hard confidence gate for Stage C

Add explicit rule to Stage C:
- If `confidence_band` = LOW → Stage C MUST return NO_TRADE
- If `confidence_band` = MEDIUM → Stage C may proceed only if `evidence_score` ≥ 5 AND R:R ≥ 2.0
- If `confidence_band` = HIGH → Stage C may proceed under normal rules (R:R ≥ 1.5)

### CORRECTION 6: Define scale-out mechanics

Add to Stage C specification:
- Default split: 50% at target_1, 50% at target_2
- If position_size = 1 (minimum), no scale-out — single target only
- Stage D authorizes the full position size; scale-out is an execution plan, not a risk-gate concern
- R:R calculation uses the blended target: (0.5 × target_1_distance + 0.5 × target_2_distance) / stop_distance

### CORRECTION 7: Clarify multi-contract pipeline sequencing

Add to architecture:
- The operator runs the pipeline for one contract at a time
- After Stage D returns APPROVED, the operator must update `challenge_state` to reflect the new pending position BEFORE running the pipeline for the next contract
- A trade is considered "open" in challenge_state as soon as Stage D returns APPROVED (not when the order fills)
- This ensures aggregate risk is always current

---

## 5. Architecture Approval Verdict

### **APPROVE_WITH_CORRECTIONS**

The architecture is fundamentally sound. The 5-stage pipeline with clear separation of concerns (sufficiency → read → setup → risk → log) is the right design. The fail-closed philosophy is consistently applied. Contract-specific logic is correctly isolated in Stages A and B.

The 7 corrections above are required before proceeding to schema design:
- Corrections 1–3 are critical (fix real defects)
- Corrections 4–5 are important (close failure-open paths)
- Corrections 6–7 are necessary (resolve ambiguities that would block schema design)

None of the corrections require redesigning the architecture. They are additive clarifications and one new status code.

---

## Corrected Architecture Summary (incorporating all corrections)

### Stage A: Sufficiency Gate (corrected)
- **New output status**: READY | NEED_INPUT | INSUFFICIENT_DATA | EVENT_LOCKOUT
- **New check**: market_packet.timestamp staleness (5 min general, 3 min for CL in elevated vol)
- **New check**: challenge_state completeness validation
- **Event lockout**: Now returns EVENT_LOCKOUT instead of INSUFFICIENT_DATA

### Stage B: Contract Market Read (corrected)
- **NO_TRADE from Stage B**: Hard pipeline termination — skips Stage C and D, goes to Stage E
- No other changes

### Stage C: Setup Construction (corrected)
- **Hard confidence gate**:
  - LOW → must return NO_TRADE
  - MEDIUM → may proceed only if evidence_score ≥ 5 AND R:R ≥ 2.0
  - HIGH → normal rules (R:R ≥ 1.5)
- **Scale-out specification**:
  - Default 50/50 split at target_1 and target_2
  - Position size 1 → no scale-out, single target
  - R:R uses blended target distance
- No other changes

### Stage D: Risk & Challenge Authorization (corrected)
- No structural changes — corrections 1–3 move validation earlier into Stage A
- Stage D still performs all 13 risk checks as specified

### Stage E: Logging & Decision Record (corrected)
- Must log the new EVENT_LOCKOUT status when applicable
- Must support direct logging from Stage B NO_TRADE (without Stage C/D outputs)
- No other changes

### Multi-Contract Sequencing Rule (new)
- One contract at a time
- Update challenge_state after each APPROVED decision before running next contract
- APPROVED = "open" for risk-aggregation purposes

---

## Operator Acceptance Checklist (Stage 2A)

- [x] Critical defects are real, not stylistic noise
- [x] Failure-open risks are identified explicitly
- [x] Corrections are minimal and targeted (7 corrections, no redesign)
- [x] Clear verdict is returned: APPROVE_WITH_CORRECTIONS
- [x] Corrected architecture summary is included for downstream consumption

**Stage 2A Status: APPROVE_WITH_CORRECTIONS — Corrections applied above. This corrected architecture flows to Stage 3.**
