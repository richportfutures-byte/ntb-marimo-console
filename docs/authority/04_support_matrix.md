# Support Matrix

**Authority document set:** `docs/authority/`  
**This document:** `support_matrix.md`  
**Generated:** 2026-03-28  
**Status:** BINDING

## Contract Status Table

| Contract | Phase Status | Block Type | Phase Closes Without? |
|---|---|---|---|
| ES | Required - THIS PHASE | None | No |
| ZN | Required - THIS PHASE | None | No |
| CL | Required - THIS PHASE | None | No |
| NQ | Deferred beyond this phase | Frozen-engine / deferred-contract gap | Yes |
| 6E | Deferred beyond this phase | Frozen-engine / deferred-contract gap | Yes |
| MGC | Deferred beyond this phase | Frozen-engine / deferred-contract gap | Yes |

## Commissionable Profile Set

The commissionable runtime profiles for this phase are:

- `fixture_es_demo`
- `preserved_es_phase1`
- `preserved_zn_phase1`
- `preserved_cl_phase1`

The phase closes only when the three preserved profiles are commissionable under the documented Windows workflow.

## Supported vs Blocked Profile Policy

1. Supported preserved profiles for this phase are ES, ZN, and CL only.
2. `NQ`, `6E`, and `MGC` remain blocked in the app surface and runtime audit.
3. Blocked contracts must never appear selectable as ready.
4. Blocked contracts must retain readable reason categories in the app surface and acceptance report.
5. No contract is promoted during this phase unless the authority set is amended again.

## Data Source Per Supported Contract

| Contract | Prior-Day OHLC | Volume Profile | Overnight | Macro/Event Context | Volatility | Session Sequence |
|---|---|---|---|---|---|---|
| ES | Truthful preserved artifacts | Truthful preserved artifacts | Truthful preserved artifacts | Truthful preserved artifacts | Truthful preserved artifacts | Truthful preserved artifacts |
| ZN | Truthful preserved artifacts | Truthful preserved artifacts | Truthful preserved artifacts | Truthful preserved artifacts | Truthful preserved artifacts | Truthful preserved artifacts |
| CL | Truthful preserved artifacts | Truthful preserved artifacts | Truthful preserved artifacts | Truthful preserved artifacts, including EIA timing context | Truthful preserved artifacts | Truthful preserved artifacts |

Fixtures or preserved artifacts are acceptable only if they are contract-specific, schema-valid, and would drive the same preserved-engine outcome as the equivalent source artifact already committed in-repo.

## Pre-Market Capability Per Contract For This Phase

| Contract | Pre-Market Brief | Watchman Gate | Supported Status |
|---|---|---|---|
| ES | Required | Validator-driven `mo.stop()` hard gate | Supported |
| ZN | Required | Validator-driven `mo.stop()` hard gate | Supported |
| CL | Required | Validator-driven `mo.stop()` hard gate | Supported |
| NQ | Not required for phase closure | Must remain blocked | Deferred |
| 6E | Not required for phase closure | Must remain blocked | Deferred |
| MGC | Not required for phase closure | Must remain blocked | Deferred |

### Shared Brief Structure Requirements For Supported Profiles

- `PreMarketBrief` is loaded from target-owned preserved artifacts
- at least one structural setup with populated `fields_used`
- at least one `query_trigger` with deterministic `observable_conditions`
- populated `warnings`
- `status` rendered from Validator output, not trusted from raw brief fields

### Contract-Specific Brief Requirements For Supported Profiles

- ES and ZN must use non-overlapping causal vocabulary
- CL on an EIA day must state lockout window times and the 15-minute post-release cap

## Deferred Contract Boundary

`NQ`, `6E`, and `MGC` are deferred from this phase because truthful promotion would require future work beyond the frozen-engine commissioning scope. They remain visible only as blocked candidates with exact reason categories.

## Profile Boundary Policy

1. There is no hidden tiering inside the supported preserved profile set: ES, ZN, and CL must all satisfy the same runtime, gate, evidence, and launch requirements.
2. Deferred contracts do not block this phase from closing.
3. Deferred contracts may not be represented as partially supported.
4. A contract is either supported in this phase or blocked/deferred.
