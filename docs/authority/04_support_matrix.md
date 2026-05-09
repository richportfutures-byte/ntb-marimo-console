# Support Matrix

**Authority document set:** `docs/authority/`  
**This document:** `support_matrix.md`  
**Generated:** 2026-03-28  
**Status:** BINDING

## Contract Status Table

| Contract | Final Target Status | Current App-Profile Status | R00 Classification |
|---|---|---|---|
| ES | Required final target | Supported today through fixture and preserved profiles | Retain current profile; future live workstation upgrades required |
| NQ | Required final target | Supported today through preserved profile foundation | Retain profile foundation; future live workstation upgrades required |
| CL | Required final target | Supported today through preserved profile | Retain current profile; future live workstation upgrades required |
| 6E | Required final target | Supported today through preserved profile foundation | Retain profile foundation; future live workstation upgrades required |
| MGC | Required final target | Supported today through preserved profile foundation | Retain profile foundation; gold contract for this application |
| ZN | Excluded from final target support | Not exposed as a target app runtime profile | May remain as source-engine history or fixture data only |
| GC | Excluded | Not present as supported runtime profile or engine schema contract | Exclusion guard required; not a synonym for `MGC` |

## Final Target Universe

The final supported target contracts are:

- `ES`
- `NQ`
- `CL`
- `6E`
- `MGC`

`MGC` is the gold contract for this application. `GC` is excluded and must not be used as a synonym, alias, profile name, label, or substitute for `MGC`.

## Current Runtime Profile Set

The current target runtime profile registry contains:

- `fixture_es_demo`
- `preserved_es_phase1`
- `preserved_nq_phase1`
- `preserved_6e_phase1`
- `preserved_mgc_phase1`
- `preserved_cl_phase1`

This current registry is factual baseline, not final target authority. `ZN` is excluded and is no longer exposed as a target app runtime profile.

## Supported vs Onboarding vs Excluded Policy

1. `ES`, `NQ`, `CL`, `6E`, and `MGC` are currently app-profile-supported through fixture-safe profile foundations and require future live workstation upgrades.
2. `MGC` is the Micro Gold profile foundation for this application.
3. `NQ`, `6E`, and `MGC` must not be described as engine-missing contracts; the engine schema includes them today.
4. `MGC` must remain truthfully classified as a fixture-safe foundation, not live networking, order, or authorization support.
5. `ZN` may remain only as source-engine history, fixture data, or excluded-contract guard evidence.
6. `ZN` must not be presented as final target support.
7. `GC` must remain excluded and must not appear as supported, onboarded, or synonymous with `MGC`.

## Data Source Expectations Per Final Target Contract

| Contract | Prior-Day OHLC | Volume Profile | Overnight | Macro/Event Context | Volatility | Session Sequence |
|---|---|---|---|---|---|---|
| ES | Required truthful source | Required truthful source | Required truthful source | Required truthful source | Required truthful source | Required truthful source |
| NQ | Required truthful source | Required truthful source | Required truthful source | Required truthful source | Required truthful source | Required truthful source |
| CL | Required truthful source | Required truthful source | Required truthful source | Required truthful source, including EIA timing context | Required truthful source | Required truthful source |
| 6E | Required truthful source | Required truthful source | Required truthful source | Required truthful source | Required truthful source | Required truthful source |
| MGC | Required truthful source | Required truthful source | Required truthful source | Required truthful source, including dollar/yield/fear-catalyst context | Required truthful source | Required truthful source |

Fixtures, preserved artifacts, or live provider outputs are acceptable only when they are contract-specific, schema-valid, truthfully labeled, and fail closed when unavailable or malformed.

## Pre-Market Capability Per Contract

| Contract | Pre-Market Brief | Watchman Gate | Final Target Status |
|---|---|---|---|
| ES | Required for final target | Validator-driven `mo.stop()` hard gate | Required; current preserved profile exists |
| NQ | Required for final target | Validator-driven `mo.stop()` hard gate | Required; current preserved profile foundation exists |
| CL | Required for final target | Validator-driven `mo.stop()` hard gate | Required; current preserved profile exists |
| 6E | Required for final target | Validator-driven `mo.stop()` hard gate | Required; current preserved profile foundation exists |
| MGC | Required for final target | Validator-driven `mo.stop()` hard gate | Required; current preserved profile foundation exists |
| ZN | Not final target | Must not appear as final supported target | Excluded/historical |
| GC | Not final target | Must not appear as supported or as `MGC` synonym | Excluded |

### Shared Brief Structure Requirements For Final Target Profiles

- `PreMarketBrief` is loaded from target-owned truthful artifacts or future truthful live sources
- at least one structural setup with populated `fields_used`
- at least one `query_trigger` with deterministic `observable_conditions`
- populated `warnings`
- `status` rendered from Validator output, not trusted from raw brief fields

### Contract-Specific Brief Requirements For Final Target Profiles

- ES and NQ must use distinct index-market causal vocabulary
- CL on an EIA day must state lockout window times and the 15-minute post-release cap
- 6E must preserve session-sequence context and DXY sensitivity
- MGC must preserve dollar, yield, and macro fear-catalyst context and must be labeled `MGC`

## Required Onboarding Boundary

`MGC` now has a preserved profile and deterministic DXY/yield/fear-catalyst live workstation read-model foundation. That foundation does not authorize trades, make default launch live, wire live Schwab startup, infer numeric macro context from text, map to `GC`, or make absolute MGC price action sufficient by itself.

`NQ` now has a preserved profile and deterministic ES-relative live workstation read-model foundation. That foundation does not authorize trades, make default launch live, wire live Schwab startup, or make absolute NQ price action sufficient by itself.

`6E` now has a preserved profile and deterministic DXY/session-sequence live workstation read-model foundation. That foundation does not authorize trades, make default launch live, wire live Schwab startup, infer numeric DXY from text, or make absolute 6E price action sufficient by itself.

## Exclusion Boundary

`ZN` is excluded from final target support. Existing `ZN` engine code, fixtures, tests, or preserved runtime profile references may remain only when clearly historical or current-state factual.

`GC` is excluded. It must not be added to supported contract lists, runtime profiles, profile templates, UI labels, fixture directories, or docs as an alias for `MGC`.
