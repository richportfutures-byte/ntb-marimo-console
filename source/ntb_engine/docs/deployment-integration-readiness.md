# NinjaTradeBuilder Deployment and Integration Readiness

## Purpose

This document formalizes the deployment and integration readiness gates for the current NinjaTradeBuilder branch.

Branch: `stagea-stageb-es`

## Current validated status

The current branch has already demonstrated the following:

- Prompt 2 through Prompt 7 Stage A+B canonical live contract analysis success
- Stage B fail-closed `NO_TRADE` success
- Prompt 8 Stage C `NO_TRADE` and `SETUP_PROPOSED` success
- Prompt 9 Stage D `APPROVED`, `REJECTED`, and `REDUCED` success
- Narrow end-to-end pipeline termination success for:
  - Stage B `NO_TRADE`
  - Stage C `NO_TRADE`
  - Stage D `TRADE_APPROVED`
  - Stage D `TRADE_REDUCED`
- Chained stage-output prompt serialization fix for validated model objects

These results mean the major prompt-boundary, schema-conformance, and chained-runtime risks are materially reduced.

## What is considered ready now

The following areas are considered materially strong for this phase:

- Stage runtime execution and boundary validation
- Contract scope enforcement across runtime inputs
- Gemini structured-output envelope handling
- Strict schema validation for sufficiency, market read, setup, and authorization outputs
- End-to-end final decision mapping for the validated termination paths

## What is not yet production-complete

The following areas still need explicit formalization or validation before production deployment:

1. A single official full-pipeline orchestration entrypoint
2. Startup configuration validation for environment, model selection, and secrets
3. Provider failure policy for timeouts, transient failures, and quota/rate limits
4. Persistence and audit logging implementation around `LoggingRecord`
5. Operational observability, including stage latency, schema-failure counts, and provider error metrics
6. A caller-facing integration surface such as service, CLI, or job contract
7. Release, rollback, and promotion policy
8. A lean but explicit high-risk edge-case scenario suite

## Staging readiness gates

All of the following should pass before a staging deployment is considered ready:

### Gate 1: Full-pipeline entrypoint
- One official orchestration function or service endpoint exists
- It runs Stage A through Stage D in sequence
- It preserves prior stage outputs without reinterpretation
- It returns termination stage and final decision explicitly

### Gate 2: Configuration contract
- Canonical provider secret name is documented
- Model identifier source is documented
- Invalid or missing configuration fails closed at startup
- Environment-specific overrides are documented

### Gate 3: Runtime and provider policy
- Timeout policy is documented
- Retry policy is documented, including deliberate no-retry behavior if chosen
- Provider failures are surfaced with structured error classification
- Non-JSON or boundary-invalid provider outputs fail closed

### Gate 4: Persistence and audit
- Every completed run writes an auditable record or explicit failure record
- Stage outputs, termination stage, and final decision are retained consistently
- Sensitive values are redacted or explicitly approved for retention

### Gate 5: Operational visibility
- Logs include run identifier, contract, termination stage, and final decision
- Metrics exist for provider failures, schema failures, and successful terminations by stage
- Alert thresholds exist for repeated provider failures or validation failures

### Gate 6: Acceptance scenarios
- Stage B `NO_TRADE` end-to-end
- Stage C `NO_TRADE` end-to-end
- Stage D `TRADE_APPROVED` end-to-end
- Stage D `TRADE_REDUCED` end-to-end
- At least one contract-specific high-risk edge case

## Production readiness gates

All staging gates must pass. In addition, the following should be true before production:

### Gate 7: Release discipline
- Versioned release procedure exists
- Rollback procedure exists
- Deployment promotion path is documented
- Smoke test steps are documented

### Gate 8: Integration contract
- Caller request shape is documented
- Caller response shape is documented
- Failure semantics are documented
- Idempotency expectations are documented
- Concurrency expectations are documented

### Gate 9: Governance
- Advisory-only versus execution-adjacent scope is explicitly documented
- Human review requirements are documented
- Kill-switch conditions are documented
- Escalation path for provider or validation instability is documented

## Recommended immediate next steps

1. Formalize the official full-pipeline orchestration entrypoint
2. Add deployment configuration documentation and startup validation
3. Add persistence and structured observability around full runs
4. Run a small high-value live edge-case suite for contract-specific doctrine risks

## Minimum high-value edge-case suite

- ES breadth or delta divergence producing `NO_TRADE`
- NQ relative-strength divergence or megacap earnings risk
- CL near EIA or elevated volatility
- ZN near auction or macro release
- 6E missing session segmentation or post-11:00 thin liquidity
- MGC DXY/yield contradiction or fear-catalyst activation

## Exit criteria for this branch phase

This branch phase should be considered complete when:

- the orchestration entrypoint is formalized
- staging readiness gates are documented and passable
- live end-to-end orchestration succeeds on a small high-value scenario set
- persistence and observability expectations are defined

At that point the next phase is deployment and integration hardening, not additional prompt-boundary work.
