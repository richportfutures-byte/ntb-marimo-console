# STAGE 4A: Prompt Red-Team Audit

---

## 1. Prompt-Level Contradictions

### CONTRADICTION 1: Stage C entry price selection vs "do not invent levels"

**Location**: Setup Construction prompt (Prompt 8), step 2 (ENTRY PRICE).

**Problem**: The prompt says "Select from contract_analysis.key_levels" for entry. But contract_analysis.key_levels contains support_levels, resistance_levels, and pivot_level — these are reference levels, not precise entry triggers. The prompt also says "do not pick an arbitrary price." But what if current_price is between levels? The model must either:
- (a) Use current_price as entry (market order)
- (b) Use a nearby key_level as a limit entry

The prompt doesn't specify which. If (b), the model is constructing a limit-order setup that may never fill. If (a), the entry isn't "from key_levels."

**Fix**: Clarify that entry_price should default to current_price (market entry) with the nearest key_level as structural justification for the trade. The key_levels define *why* the trade makes sense at this location, not a precise limit-entry price. Add: "If current_price is at or near a key_level (within 2× tick_size), use the key_level as entry. Otherwise, use current_price as a market-order entry and note that the entry is between levels."

### CONTRADICTION 2: Stage D Check 10 (opposite-direction flip) references "closed trades" not in challenge_state

**Location**: Risk Authorization prompt (Prompt 9), Check 10.

**Problem**: The check says "If this contract appears in today's closed trades with opposite direction and the most recent close was < 30 minutes ago." But `challenge_state` does not include a `closed_trades_today` field. It has `current_open_positions` and `trades_today_by_contract` (a count), but no history of closed-trade directions. The model cannot execute this check without data that doesn't exist in the schema.

**Fix**: Either:
- (a) Add `recent_closed_trades` to challenge_state schema (list of {contract, direction, close_time}), OR
- (b) Simplify Check 10 to rely on existing data: "If there is a recently stopped-out position (from last_stopout_time_by_contract) on this contract within cooldown period AND the proposed direction is opposite to what was stopped out → REJECTED." This overlaps with Check 9 but adds the direction check.

Recommended: Option (b) — simpler, uses existing schema, and the cooldown check already prevents rapid re-entry. Add a `last_trade_direction_by_contract` field to challenge_state.

### CONTRADICTION 3: Master Doctrine says slippage for MGC is 1 tick but MGC tick value is $1.00

**Location**: Master Doctrine slippage table.

**Problem**: This isn't a contradiction per se, but a practical concern. MGC slippage at 1 tick/side = $1.00/side = $2.00 round-trip per contract. With max 12 contracts, that's $24 total slippage — minimal. But the real question is whether 1 tick is realistic for MGC. Micro gold can have wider spreads during fast markets. This is an operator assumption, not a prompt defect.

**Verdict**: Not a prompt contradiction. Flag for operator awareness but no prompt change needed.

---

## 2. Missing Safeguards

### SAFEGUARD 1: No explicit "end of session" wind-down logic

**Problem**: The prompts check session hours (is current time within allowed hours?) but don't have explicit behavior for the last 30 minutes of the session. A trade entered at 15:30 ET on ES with a 2-hour hold estimate would be caught by Check 12 (overnight hold risk). But a scalp entered at 15:40 ET with a 10-minute hold estimate would technically pass — even though the session effectively closes at 15:45 and the operator needs time to manage the exit.

**Fix**: Add a "session wind-down" rule to each contract prompt's Stage A: "If time remaining in session < 30 minutes, add data_quality_flag 'session_winding_down'. Stage C should treat this as a disqualifier for intraday_swing and session_hold setups, allowing only scalps."

### SAFEGUARD 2: No handling of contradictory evidence_score and structural_notes

**Problem**: Stage B might return evidence_score = 7 (HIGH confidence) but structural_notes lists 3 conflicting signals. There's no safeguard requiring the model to reconcile these — a high evidence_score with many conflicts is suspicious.

**Fix**: Add to each contract prompt's Stage B: "If conflicting_signals contains 2 or more entries, evidence_score must not exceed 6 (MEDIUM confidence ceiling). If conflicting_signals contains 3 or more entries, evidence_score must not exceed 4."

### SAFEGUARD 3: No maximum stop distance guard

**Problem**: Stage C computes sizing from stop distance and risk budget. But there's no guard against absurdly wide stops. A CL trade with a 100-tick stop would compute to position_size = 0 and return NO_TRADE (correct), but a 50-tick stop on ES (12.5 points) is technically valid if position_size = 1 (risk = 50 × $12.50 + $25 slippage = $650 → too high → NO_TRADE). However, a 30-tick stop on ES (7.5 points) at position_size = 1 would be $375 + $25 = $400 — under budget. But a 7.5-point ES stop is not a disciplined intraday trade.

**Fix**: Add maximum stop distance guidelines to Stage C per contract:
- ES: max 16 ticks (4 points, $200/contract)
- NQ: max 40 ticks (10 points, $200/contract)
- CL: max 20 ticks ($0.20, $200/contract)
- ZN: max 16 ticks (16/64 = 0.25 points, $250/contract)
- 6E: max 40 ticks (20 pips, $250/contract)
- MGC: max 50 ticks ($5.00, $50/contract)

These are guardrails, not hard-coded values. If the stop exceeds max, Stage C should flag "stop_distance_unusually_wide" as a disqualifier and cap the setup class at scalp (tighter targets).

### SAFEGUARD 4: No guard against stale contract_analysis flowing to Stage C

**Problem**: Addressed in Stage 2A audit (weakness 2) but not reflected in the prompts. Stage C receives contract_analysis but doesn't check its timestamp against the current time.

**Fix**: Add to Stage C prompt: "Before constructing a setup, verify that contract_analysis.timestamp is within 300 seconds of current time. If stale, return NO_TRADE with reason 'stale_market_read'."

---

## 3. Overreach / Hallucination Risks

### RISK 1: Stage B structural_notes is free-text — hallucination surface

**Problem**: structural_notes is a free-text field where the model describes its read. This is the most likely place for hallucination (inventing levels, claiming patterns not supported by data, narrating a story).

**Mitigation already present**: The prompt says "Reference specific numeric levels from the structured data." But the model could still hallucinate narrative around real levels.

**Additional fix**: Add to each contract prompt: "Every claim in structural_notes must reference at least one specific field from the market_packet or contract_specific_extension. Do not describe patterns, setups, or conditions that cannot be traced to a structured data point."

### RISK 2: Stage B could inflate evidence_score to get through Stage C gates

**Problem**: The model might "want" to produce a trade (LLMs tend toward action/completion) and inflate evidence_score to pass the hard confidence gate in Stage C. This is subtle — the model doesn't have an explicit bias, but its tendency to be helpful may manifest as optimistic scoring.

**Mitigation already present**: Confidence-to-evidence mapping is enforced. Conflicting signals must be listed.

**Additional fix (from Safeguard 2 above)**: Hard cap evidence_score based on conflicting_signals count. This mechanically limits optimistic scoring when conflicts exist.

### RISK 3: Stage C rationale could reconstruct a market narrative not in contract_analysis

**Problem**: Stage C's `rationale` field explains why the setup was chosen. The model could write a compelling narrative that effectively re-reads the market (Stage B's job). This would blur stage boundaries.

**Fix**: Add to Stage C prompt: "rationale must reference only contract_analysis fields and values. Do not re-read the market. Do not add new observations about price action, structure, or context. Your rationale explains how the contract_analysis supports the setup math, not why the market should move in a particular direction."

---

## 4. Overtrading Risks

### RISK 1: No explicit NO_TRADE frequency expectation

**Problem**: The prompts make NO_TRADE a valid outcome but don't set an expectation for how often it should occur. A well-designed conservative system in this challenge should produce NO_TRADE on the majority of evaluations (perhaps 60-80% of the time). Without this expectation, the model might treat NO_TRADE as a failure mode to avoid.

**Fix**: Add to Master Doctrine: "NO_TRADE is the expected outcome for the majority of pipeline runs. A healthy system should return NO_TRADE 60-80% of the time. Producing a trade on every evaluation is a sign of insufficient filtering, not good performance."

### RISK 2: Sequential multi-contract evaluation creates cumulative trade pressure

**Problem**: The operator runs the pipeline for each contract sequentially. If 6 contracts are evaluated in a session, the model gets 6 chances to produce a trade. With a daily trade limit of 60, trade count is not the binding constraint — per-trade risk ($1,450), daily loss stop ($10,000), and aggregate open risk ($40,000) are the real governors. If the operator evaluates multiple times per session, the system relies on risk gates rather than trade-count limits to prevent overexposure.

**Fix**: This is an operator-behavior risk, not a prompt defect. But add to Master Doctrine: "Each pipeline run is independent. Do not lower your standards because previous contracts returned NO_TRADE. Risk discipline, not trade count, is the primary overtrading control."

### RISK 3: Medium confidence trades with 2.0 R:R threshold might be force-fitted

**Problem**: Stage C allows MEDIUM confidence trades if R:R ≥ 2.0. The model might stretch target distances to hit 2.0 R:R on a marginal setup. E.g., target at a "possible resistance level" that's farther away to make the math work.

**Fix**: Add to Stage C: "target prices must be at or near levels identified in contract_analysis.key_levels. If achieving R:R ≥ 2.0 requires placing a target beyond any identified key_level, return NO_TRADE with reason 'no_structural_target_for_required_rr'."

---

## 5. Contract-Specific Weaknesses

### CL Weaknesses
1. **DOM data impermanence not enforced structurally**: The prompt warns "do not rely on DOM snapshot data lasting more than a few minutes" but the model might still weight it heavily in the read. **Fix**: Require that if DOM data is used, evidence_score cannot exceed 7 (preventing DOM from being the deciding factor for a HIGH confidence read).
2. **EIA reaction reading**: After EIA releases ("already_released"), the CL prompt doesn't specify how long to wait before the post-EIA read is reliable. **Fix**: Add "If eia_timing = 'already_released' and the release was < 15 minutes ago, add data_quality_flag 'post_eia_settling' and cap evidence_score at 5 (MEDIUM)."

### ZN Weaknesses
1. **Tick math complexity**: ZN ticks are 1/64 of a point. The prompt doesn't provide explicit examples of stop distance computation in 32nds/64ths. **Fix**: Add a worked example: "Example: ZN at 110'16 (110 and 16/32 = 110.5), stop at 110'12 (110 and 12/32 = 110.375). Distance = 0.125 points = 8 ticks (0.125 / 0.015625). Risk per contract = 8 × $15.625 = $125."
2. **Auction proximity**: The prompt flags auction proximity but doesn't downgrade confidence. **Fix**: "If data_quality_flag includes 'auction_proximity_risk', cap evidence_score at 6 (MEDIUM)."

### 6E Weaknesses
1. **Thin liquidity after 11:00 ET**: The prompt mentions this but doesn't hard-block. **Fix**: "After 11:00 ET, add data_quality_flag 'london_close_thin_liquidity'. Stage C should only accept scalp setups after this time."
2. **EUR cross-rate missing from schema**: The prompt mentions EUR/GBP or EUR/JPY as cross-market context, but the 6E extension schema doesn't include these. **Fix**: These are "preferred" not "required" — acceptable as-is, but the prompt should not reference them unless the schema supports them. Remove the EUR cross-rate mention from the prompt, or add optional fields to the extension schema.

### NQ Weaknesses
1. **Megacap earnings surprise risk**: The prompt mentions checking for after-hours earnings but the event_calendar_remainder schema only has Tier-1 and Tier-2 events. Earnings aren't necessarily in the event calendar. **Fix**: Add "If megacap_leadership_table shows a company with earnings due today/after-close, add data_quality_flag 'megacap_earnings_risk'. Cap hold_time_estimate to scalp-only for NQ."
2. **Relative strength regime shift**: The prompt says "note if relative_strength_vs_es is rapidly changing" but gives no threshold. **Fix**: This is informational, not decision-critical. Acceptable as-is.

---

## 6. Recommended Wording Fixes

| # | Location | Current | Fix |
|---|----------|---------|-----|
| 1 | Stage C, Entry Price | "Select from contract_analysis.key_levels" | "Use current_price as entry (market order). The nearest key_level provides structural justification for why entry at this location is defensible. If current_price is more than 2× avg_20d_session_range from the nearest supporting key_level, return NO_TRADE." |
| 2 | Stage D, Check 10 | References "today's closed trades" | "If last_stopout_time_by_contract shows a stop-out on this contract within cooldown period AND the proposed direction would be opposite to the last trade direction (from last_trade_direction_by_contract), REJECTED." Add last_trade_direction_by_contract to challenge_state. |
| 3 | Master Doctrine | No NO_TRADE frequency guidance | Add: "NO_TRADE is the expected majority outcome. Producing trades on every evaluation indicates insufficient filtering." |
| 4 | Stage C | No target anchoring rule | "Targets must correspond to key_levels from contract_analysis. Targets beyond identified levels are not allowed." |
| 5 | All contract prompts, Stage B | No conflicting_signals → evidence_score cap | "If conflicting_signals ≥ 2, evidence_score ≤ 6. If conflicting_signals ≥ 3, evidence_score ≤ 4." |
| 6 | Stage C | No stale analysis check | "Verify contract_analysis.timestamp is within 300 seconds. If stale, NO_TRADE." |
| 7 | All contract prompts, Stage A | No session wind-down | "If time remaining in session < 30 minutes, flag 'session_winding_down'. Stage C restricts to scalp-only." |
| 8 | CL prompt | No post-EIA settling period | "If EIA released < 15 min ago, cap evidence_score at 5." |
| 9 | ZN prompt | No tick math example | Add worked ZN tick math example. |
| 10 | Stage C, rationale | No anti-re-read constraint | "rationale must reference only contract_analysis fields. Do not add new market observations." |
| 11 | Stage C | No max stop distance guard | Add per-contract max stop distance guidelines. |

---

## Schema Addition Required

Based on Contradiction 2, add to `challenge_state` schema:

```json
"last_trade_direction_by_contract": {
  "type": "object",
  "description": "Map of contract -> last trade direction today ('LONG' or 'SHORT'). Null per contract if no trade today.",
  "nullable": true,
  "decision_critical": true
}
```

---

## Final Verdict

### **DEPLOYABLE_WITH_FIXES**

The prompt set is structurally sound and well-aligned with the architecture and schemas. The contract-specific prompts are genuinely distinct. The stage boundaries are maintained. Fail-closed behavior is the default.

The 11 wording fixes above should be applied before deployment:
- **Fixes 1, 2** are critical (resolve contradictions)
- **Fixes 3, 4, 5, 6** are important (close overtrading and hallucination paths)
- **Fixes 7–11** are recommended (harden edge cases)

No rewrite is required. The fixes are additive wording changes within existing prompt structures.

---

## Corrected Prompt Notes (Summary of Applied Fixes)

### Master Doctrine additions:
```
- NO_TRADE is the expected majority outcome (60-80% of evaluations). Producing trades on every evaluation indicates insufficient filtering, not good performance.
- Each pipeline run is independent. Do not lower standards because previous contracts returned NO_TRADE.
```

### All contract prompts, Stage B addition:
```
- If conflicting_signals contains ≥ 2 entries, evidence_score must not exceed 6 (MEDIUM ceiling).
- If conflicting_signals contains ≥ 3 entries, evidence_score must not exceed 4 (LOW ceiling).
- Every claim in structural_notes must reference at least one specific field from market_packet or contract_specific_extension.
```

### All contract prompts, Stage A addition:
```
- If time remaining in session < 30 minutes, add data_quality_flag "session_winding_down".
```

### Stage C additions:
```
- Entry price defaults to current_price (market order). Key_levels provide structural justification, not limit-entry prices.
- Targets must correspond to key_levels from contract_analysis. Targets placed beyond all identified levels are not allowed.
- Verify contract_analysis.timestamp is within 300 seconds. If stale, return NO_TRADE with reason "stale_market_read".
- rationale must reference only contract_analysis fields and values. Do not add new market observations.
- Max stop distance guidelines per contract: ES 16 ticks, NQ 40 ticks, CL 20 ticks, ZN 16 ticks, 6E 40 ticks, MGC 50 ticks. Exceeding max → flag "stop_distance_unusually_wide".
```

### Stage D addition:
```
- Check 10 uses last_trade_direction_by_contract (new challenge_state field) instead of closed trade history.
```

### CL prompt addition:
```
- If eia_timing = "already_released" and release was < 15 minutes ago, cap evidence_score at 5 (MEDIUM).
```

### ZN prompt addition:
```
- Worked tick math example included.
- If data_quality_flag includes "auction_proximity_risk", cap evidence_score at 6 (MEDIUM).
```

### 6E prompt addition:
```
- After 11:00 ET, add data_quality_flag "london_close_thin_liquidity". Stage C restricts to scalp-only.
```

---

## Operator Acceptance Checklist (Stage 4A)

- [x] Real runtime failure modes are surfaced (11 specific issues)
- [x] Overtrading risk is explicitly addressed (3 risks, all with fixes)
- [x] Contract-specific weak points identified for CL, ZN, 6E, NQ
- [x] Verdict is decisive: DEPLOYABLE_WITH_FIXES
- [x] One schema addition required (last_trade_direction_by_contract)
- [x] All fixes are additive — no rewrite needed

**Stage 4A Status: DEPLOYABLE_WITH_FIXES — Corrections noted above. This corrected prompt set flows to Stage 5.**
