# Readiness Engine v1

## Purpose

This document defines the standalone readiness contract for pre-decision readiness evaluation.

Readiness is a separate concern from Stage A/B/C packet-compiler outputs. It is implemented as a peer schema (`readiness_engine_output_v1`) and must not extend or reuse `ContractAnalysis`, `SufficiencyGateOutput`, or `ProposedSetup` contracts.

## Scope and compatibility rules

- Frozen packet-compiler v1 behavior is unchanged.
- Stage A+B and Stage C contracts are not reused for readiness.
- Readiness status vocabulary is locked and non-interchangeable.
- Doctrine gates and gate states are locked and non-interchangeable.
- Readiness has escalation authority only and never has trade-authorization authority.
- Readiness output must not be made shape-compatible with Stage C input through coercion, inheritance, or convenience mapping.

## Schema identity

- `$schema`: `readiness_engine_output_v1`
- `stage`: `readiness_engine`
- `authority`: `ESCALATE_ONLY`

## Supported top-level statuses (locked)

- `READY`
- `WAIT_FOR_TRIGGER`
- `LOCKED_OUT`
- `INSUFFICIENT_DATA`

No additional readiness top-level status values are permitted.

## Doctrine gates (locked)

Every readiness result must include exactly one entry for each gate:

1. `data_sufficiency_gate`
2. `context_alignment_gate`
3. `structure_quality_gate`
4. `trigger_gate`
5. `risk_window_gate`
6. `lockout_gate`

## Doctrine gate states (locked)

Allowed gate states:

- `PASS`
- `FAIL`
- `WAIT`

## Status-specific reason enums (locked)

`WAIT_FOR_TRIGGER` reason enum:

- `entry_not_yet_confirmed`
- `pullback_not_complete`
- `breakout_not_confirmed`
- `timing_window_not_open`

`LOCKED_OUT` reason enum:

- `event_lockout_active`
- `session_closed`
- `risk_hard_stop_active`
- `governance_lock_active`

`INSUFFICIENT_DATA` reason enum:

- `missing_required_fields`
- `stale_market_packet`
- `incomplete_contract_extension`
- `invalid_challenge_state`
- `missing_trigger_context`

## Trigger families (v1 only, locked)

Supported `trigger_data.family` values:

- `recheck_at_time`
- `price_level_touch`

`trigger_data` shape requirements:

- `recheck_at_time`
  - `recheck_at_time`: required
  - `price_level`: forbidden

- `price_level_touch`
  - `price_level`: required
  - `recheck_at_time`: forbidden

Fail-closed trigger rule:

- Within the `readiness_engine_output_v1` contract, if `trigger_data` is missing, status must be `INSUFFICIENT_DATA` and `insufficient_data_reasons` must include `missing_trigger_context`.
- Within the `readiness_engine_output_v1` contract, if `trigger_data` is present, `missing_trigger_context` must not appear in `insufficient_data_reasons`.

## Non-interchangeability doctrine

Readiness statuses are disjoint and must not be collapsed, aliased, or substituted.

Required gate-state patterns:

- `READY`
  - all doctrine gates: `PASS`
  - `wait_for_trigger_reason`, `lockout_reason`, `insufficient_data_reasons`, `missing_inputs`: all absent/empty

- `WAIT_FOR_TRIGGER`
  - `trigger_gate`: `WAIT`
  - all other gates: `PASS`
  - `wait_for_trigger_reason`: required
  - `lockout_reason`, `insufficient_data_reasons`, `missing_inputs`: absent/empty

- `LOCKED_OUT`
  - `lockout_gate`: `FAIL`
  - all other gates: `PASS`
  - `lockout_reason`: required
  - `wait_for_trigger_reason`, `insufficient_data_reasons`, `missing_inputs`: absent/empty

- `INSUFFICIENT_DATA`
  - `data_sufficiency_gate`: `FAIL`
  - all other gates: `PASS`
  - `insufficient_data_reasons`: required and non-empty
  - `missing_inputs`: required and non-empty
  - `wait_for_trigger_reason`, `lockout_reason`: absent

## Canonical shape

```json
{
  "$schema": "readiness_engine_output_v1",
  "stage": "readiness_engine",
  "authority": "ESCALATE_ONLY",
  "contract": "ES",
  "timestamp": "2026-03-22T12:00:00Z",
  "status": "WAIT_FOR_TRIGGER",
  "doctrine_gates": [
    {"gate": "data_sufficiency_gate", "state": "PASS", "rationale": "All required fields present."},
    {"gate": "context_alignment_gate", "state": "PASS", "rationale": "Context aligns with doctrine."},
    {"gate": "structure_quality_gate", "state": "PASS", "rationale": "Structure quality acceptable."},
    {"gate": "trigger_gate", "state": "WAIT", "rationale": "Trigger confirmation pending."},
    {"gate": "risk_window_gate", "state": "PASS", "rationale": "Risk window open."},
    {"gate": "lockout_gate", "state": "PASS", "rationale": "No lockout active."}
  ],
  "trigger_data": {
    "family": "recheck_at_time",
    "recheck_at_time": "2026-03-22T12:05:00Z",
    "price_level": null
  },
  "wait_for_trigger_reason": "entry_not_yet_confirmed",
  "lockout_reason": null,
  "insufficient_data_reasons": [],
  "missing_inputs": []
}
```
