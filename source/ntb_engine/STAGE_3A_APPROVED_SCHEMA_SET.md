# STAGE 3A: Schema Defect Audit

---

## 1. Critical Schema Defects

### DEFECT 1: `proposed_setup.risk_dollars` computation may be ambiguous for scale-out trades

**Location**: `proposed_setup` schema, `risk_dollars` field.

**Problem**: The `risk_dollars` field is described as "Total risk in dollars including slippage." But for a scale-out trade (position_size = 2, with 50/50 split at target_1 and target_2), the total risk if the stop is hit is the full position at the stop. However, if target_1 is hit first and only half remains, the risk on the remaining half is different. The schema does not clarify whether `risk_dollars` represents:
- (a) Max risk: full position at stop (worst case — no targets hit)
- (b) Expected risk: weighted by probability of partial fills

**Fix**: Define `risk_dollars` as **(a) max risk — full position at stop, worst case.** This is the only fail-safe interpretation. Add a clarifying note to the schema description.

**Severity**: Critical — Stage D's risk checks depend on this value being unambiguous.

### DEFECT 2: `confidence_band` / `evidence_score` consistency is stated but not enforced in schema

**Location**: `contract_analysis` schema.

**Problem**: The schema says evidence_score 1–3 maps to LOW, 4–6 to MEDIUM, 7–10 to HIGH. But the schema itself has no mechanism to enforce this — both fields are independently set. If the LLM returns `evidence_score: 3` with `confidence_band: MEDIUM`, it's a logical violation but not a structural schema error.

**Fix**: Add an explicit `validation_rule` note to the schema requiring that:
- `evidence_score` 1–3 → `confidence_band` MUST be "LOW"
- `evidence_score` 4–6 → `confidence_band` MUST be "MEDIUM"
- `evidence_score` 7–10 → `confidence_band` MUST be "HIGH"

This rule must be enforced in the schema validation layer at runtime (not just documented).

**Severity**: Critical — the hard confidence gate in Stage C depends on this consistency.

### DEFECT 3: `sufficiency_gate_output` does not include the event calendar data it used for EVENT_LOCKOUT

**Location**: `sufficiency_gate_output` schema.

**Problem**: When Stage A returns EVENT_LOCKOUT, the `disqualifiers` field says why, but there's no structured field showing which specific event triggered the lockout (event name, time, minutes_until). This makes post-hoc audit difficult — the operator cannot verify whether the lockout was correct without re-examining the market_packet.

**Fix**: Add an `event_lockout_detail` field:
```json
"event_lockout_detail": {
  "type": "object",
  "properties": {
    "event_name": { "type": "string" },
    "event_time": { "type": "string", "format": "date-time" },
    "minutes_until": { "type": "integer" },
    "lockout_type": { "type": "string", "enum": ["pre_event", "post_event"] }
  },
  "nullable": true,
  "description": "Populated only when status = EVENT_LOCKOUT. Identifies the specific event."
}
```

**Severity**: Medium-high — needed for operational audit but does not break runtime logic.

### DEFECT 4: `risk_authorization.checks` array does not enforce ordering or completeness

**Location**: `risk_authorization` schema.

**Problem**: The `checks` array is defined as a list of objects with `check_id`, `check_name`, `passed`, and `detail`. But the schema does not enforce that all 13 checks are present, nor that they appear in the defined order. If the LLM skips check #8 (event lockout), the schema won't catch it.

**Fix**: Add a `validation_rule` requiring that the `checks` array must contain exactly 13 entries with `check_id` values 1 through 13, in order. Alternatively, define the 13 checks as named fields rather than an array — but this is more rigid than necessary. The simpler fix: add a `checks_count` field with `const: 13` as a runtime validation anchor.

**Severity**: Critical — a missing risk check could silently approve a trade that should have been rejected.

### DEFECT 5: `post_trade_review_record` has no field for the market regime at time of trade

**Location**: `post_trade_review_record` schema.

**Problem**: The review record captures entry, exit, P&L, MAE, MFE, etc. But it does not include the `market_regime` or `confidence_band` from the original `contract_analysis`. This makes regime-specific performance analysis (required by Stage 5) impossible without joining back to the logging_record.

**Fix**: Add two fields to `post_trade_review_record`:
```json
"market_regime_at_entry": { "type": "string", "enum": ["trending_up", "trending_down", "range_bound", "breakout", "breakdown", "choppy", "unclear"], "nullable": false },
"confidence_band_at_entry": { "type": "string", "enum": ["LOW", "MEDIUM", "HIGH"], "nullable": false }
```

These are denormalized from the logging_record for evaluation convenience.

**Severity**: Medium — evaluation can still work via joins, but denormalization prevents fragile cross-record lookups.

---

## 2. Recommended Fixes

| # | Defect | Fix | Impact |
|---|--------|-----|--------|
| 1 | `risk_dollars` ambiguity | Define as max risk (full position at stop, worst case). Add clarifying description. | Prevents Stage D from under-counting risk |
| 2 | `confidence_band`/`evidence_score` consistency | Add explicit validation_rule to schema. Enforce at runtime. | Prevents broken confidence gating in Stage C |
| 3 | Missing event lockout detail | Add `event_lockout_detail` object to `sufficiency_gate_output` | Enables operational audit of lockout decisions |
| 4 | Unvalidated checks array | Add `checks_count` const field (value: 13) to `risk_authorization`. Runtime validator must verify all 13 check_ids present. | Prevents silent check omission |
| 5 | Missing regime in review record | Add `market_regime_at_entry` and `confidence_band_at_entry` to `post_trade_review_record` | Enables regime-specific performance analysis without joins |

### Additional Minor Fixes

| # | Issue | Fix |
|---|-------|-----|
| 6 | `opening_type` enum includes `NOT_YET_CLASSIFIED` but this is not in the terminology lock | Add `NOT_YET_CLASSIFIED` to the global terminology lock. This is a necessary addition since sessions < 30 min cannot be classified. |
| 7 | `cross_market_context` in `market_packet` is typed as `object` with no defined shape | Add a recommended shape with keys like `related_market`, `direction`, `note`. This doesn't need to be strictly enforced since it varies by contract, but a reference shape aids consistency. |
| 8 | `logging_record.final_decision` enum includes `TRADE_APPROVED` and `TRADE_REDUCED` but `proposed_setup.outcome` uses `SETUP_PROPOSED` | These are intentionally different (logging reflects the final pipeline outcome, not the stage-specific outcome). Document this mapping explicitly to prevent confusion. |

---

## 3. Safe-to-Proceed Verdict

### **SAFE_TO_PROCEED_WITH_FIXES**

The schema set is structurally sound. The 5-stage architecture maps cleanly to the schemas. Provenance, timestamps, and contract identifiers are consistent. Null behavior is well-controlled. The terminology lock is respected.

The 5 critical/medium-high fixes above must be applied before proceeding to Stage 4:
- Fixes 1, 2, 4 are critical (affect runtime correctness)
- Fixes 3, 5 are needed for operational audit and evaluation
- Fixes 6–8 are minor clarifications

No fixes require restructuring the schemas. All are additive field additions or description clarifications.

---

## 4. Cleaned Schema Notes

### Applied corrections to the schema set:

#### `proposed_setup` — risk_dollars clarification
```json
"risk_dollars": {
  "type": "number",
  "description": "MAX risk in dollars: full position at stop price, worst case (no targets hit), including slippage on both sides. This is the conservative bound used by Stage D for risk authorization. Must be ≤ max_risk_per_trade_dollars.",
  "nullable": true,
  "decision_critical": true
}
```

#### `contract_analysis` — validation rule added
```
VALIDATION RULE: evidence_score and confidence_band must be consistent:
  - evidence_score 1-3 → confidence_band MUST be "LOW"
  - evidence_score 4-6 → confidence_band MUST be "MEDIUM"  
  - evidence_score 7-10 → confidence_band MUST be "HIGH"
A mismatch is a schema violation and must be caught by the runtime validation layer.
```

#### `sufficiency_gate_output` — event_lockout_detail added
```json
"event_lockout_detail": {
  "type": "object",
  "properties": {
    "event_name": { "type": "string" },
    "event_time": { "type": "string", "format": "date-time" },
    "minutes_until": { "type": "integer" },
    "lockout_type": { "type": "string", "enum": ["pre_event", "post_event"] }
  },
  "nullable": true,
  "description": "Populated only when status = EVENT_LOCKOUT. Identifies the triggering event for audit purposes."
}
```

#### `risk_authorization` — completeness anchor added
```json
"checks_count": {
  "type": "integer",
  "const": 13,
  "description": "Must always be 13. Runtime validator must verify that checks array contains exactly 13 entries with check_id values 1-13 in order.",
  "nullable": false,
  "decision_critical": true
}
```

#### `post_trade_review_record` — regime fields added
```json
"market_regime_at_entry": {
  "type": "string",
  "enum": ["trending_up", "trending_down", "range_bound", "breakout", "breakdown", "choppy", "unclear"],
  "description": "Denormalized from contract_analysis at time of trade approval.",
  "nullable": false
},
"confidence_band_at_entry": {
  "type": "string",
  "enum": ["LOW", "MEDIUM", "HIGH"],
  "description": "Denormalized from contract_analysis at time of trade approval.",
  "nullable": false
}
```

#### Terminology lock update
Add to global terminology:
- `NOT_YET_CLASSIFIED` — valid value for `opening_type` when session is < 30 minutes old
- `EVENT_LOCKOUT` — valid status for sufficiency gate (already in corrected architecture, now formally in terminology lock)

#### Logging-to-setup outcome mapping (documentation)
```
Stage C outcome → Logging final_decision mapping:
  SETUP_PROPOSED + Stage D APPROVED  → TRADE_APPROVED
  SETUP_PROPOSED + Stage D REDUCED   → TRADE_REDUCED
  SETUP_PROPOSED + Stage D REJECTED  → TRADE_REJECTED
  NO_TRADE (from Stage B or C)       → NO_TRADE
  Stage A INSUFFICIENT_DATA          → INSUFFICIENT_DATA
  Stage A NEED_INPUT                 → NEED_INPUT
  Stage A EVENT_LOCKOUT              → EVENT_LOCKOUT
```

---

## Operator Acceptance Checklist (Stage 3A)

- [x] Contradictions are real and specific (not stylistic)
- [x] Recommended fixes are minimal and concrete (5 critical + 3 minor)
- [x] Verdict is clear: SAFE_TO_PROCEED_WITH_FIXES
- [x] Cleaned schema notes provide copy-paste-ready corrections
- [x] No prompts have been written yet

**Stage 3A Status: SAFE_TO_PROCEED_WITH_FIXES — Corrections applied above. This corrected schema set flows to Stage 4.**
