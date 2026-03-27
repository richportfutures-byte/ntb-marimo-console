# NinjaTradeBuilder Prioritized Edge-Case Validation Matrix

## Purpose

This document defines the smallest high-value scenario set remaining after the branch achieved:

- prompt-boundary correctness
- schema conformance
- narrow live end-to-end validation

The goal is not broad combinatorial testing. The goal is to target the contract-specific doctrine surfaces that still carry the most semantic risk.

## Priority model

Priority 1 means a scenario is both contract-specific and materially different from the canonical clean path.

Priority 2 means the scenario is important but lower leverage than the top-tier edge cases.

Priority 3 means the scenario is useful only after the higher-value set has been completed.

---

## Priority 1 scenarios

### 1. CL near EIA or elevated volatility

Contract: `CL`

Why this matters:
- CL has the most dangerous volatility and event-sensitive Stage A/B doctrine.
- The contract-specific prompt includes special handling for elevated volatility, EIA timing, event lockout, and post-release settling.

Scenario targets:
- `realized_volatility_context = "elevated"`
- `eia_timing.status = "scheduled"` with `minutes_until <= 30`
- `eia_timing.status = "released"` with `minutes_since < 15`
- `dom_liquidity_summary` materially influences the read

Expected behaviors to validate:
- `INSUFFICIENT_DATA` when elevated vol is too close to scheduled EIA
- `EVENT_LOCKOUT` when event timing enters configured lockout window
- evidence cap under post-release settling
- evidence cap when DOM materially contributes to the read

### 2. ZN near auction or macro release

Contract: `ZN`

Why this matters:
- ZN has the strongest macro- and auction-sensitive doctrine branch.
- It is structurally different from ES/NQ/CL.

Scenario targets:
- `treasury_auction_schedule` inside 60-minute window
- recent Tier-1 release with missing or weak `macro_release_context`
- post-release structure still forming

Expected behaviors to validate:
- `auction_proximity_risk` data-quality flag
- `INSUFFICIENT_DATA` when macro release context is missing after release
- reduced evidence under auction proximity or immediate post-data ambiguity
- valid `NO_TRADE` when post-data structure is not mature

### 3. 6E missing session segmentation or post-11:00 thin liquidity

Contract: `6E`

Why this matters:
- 6E relies on session segmentation more explicitly than the other contracts.
- You already proved one `NO_TRADE` path, but not the structural data-quality edge cases.

Scenario targets:
- missing `asia_high_low`
- missing `london_high_low`
- `dxy_context = null`
- evaluation after 11:00 ET

Expected behaviors to validate:
- `INSUFFICIENT_DATA` for missing session segmentation
- `NEED_INPUT` for missing DXY context
- `london_close_thin_liquidity` data-quality flag after 11:00 ET
- lower-confidence or `NO_TRADE` read under thin liquidity conditions

### 4. MGC DXY/yield contradiction and fear-catalyst activation

Contract: `MGC`

Why this matters:
- MGC is macro-driver dependent in a way that is distinct from the other contracts.
- Contradiction logic and catalyst activation are meaningful semantic risk points.

Scenario targets:
- `dxy_context` contradicts price direction
- `yield_context` contradicts price direction
- `macro_fear_catalyst_summary != "none"`
- both `dxy_context` and `yield_context` missing

Expected behaviors to validate:
- evidence cap when DXY and yields both contradict price
- `NEED_INPUT` when fear-catalyst summary is absent
- `INSUFFICIENT_DATA` when macro drivers are missing
- valid instability-aware `NO_TRADE` when macro conflict dominates

### 5. NQ relative-strength divergence and megacap earnings risk

Contract: `NQ`

Why this matters:
- NQ’s contract-specific doctrine is driven by relative strength and megacap concentration.
- It is one of the most likely areas for live semantic drift.

Scenario targets:
- `relative_strength_vs_es` weak or contradictory
- fragile `megacap_leadership_table`
- megacap earnings due today or after close

Expected behaviors to validate:
- `NO_TRADE` when relative strength and leadership are too fragile
- `megacap_earnings_risk` data-quality flag
- lower confidence or reduced evidence under fragile leadership

### 6. ES divergence-driven NO_TRADE

Contract: `ES`

Why this matters:
- ES is the canonical contract, but you have not yet explicitly proven its main doctrine divergence branches.

Scenario targets:
- breadth diverges from price
- `index_cash_tone` diverges from price
- `cumulative_delta` diverges from price
- `current_volume_vs_average` weak

Expected behaviors to validate:
- `NO_TRADE` when divergence dominates
- reduced evidence under weak volume
- structurally valid contract analysis with fail-closed outcome

---

## Priority 2 scenarios

### 7. Shared Stage A event lockout boundary

Contracts: one index contract plus one macro-sensitive contract

Why this matters:
- Event lockout is a common fail-closed termination path and should be validated on more than one contract family.

Expected behaviors:
- `EVENT_LOCKOUT` termination
- populated `event_lockout_detail`
- valid full sufficiency output shape

### 8. Shared stale-packet boundary

Contracts: one fast-moving contract and one slower macro contract

Why this matters:
- Staleness behavior is a real deployment risk if upstream data delivery degrades.

Expected behaviors:
- stale packet rejection or downgrade according to threshold
- no accidental progression to later stages

### 9. Shared Stage C setup-construction staleness or weak-read termination

Why this matters:
- Stage C already passes narrow validation, but staleness and weak-confidence no-trade paths are meaningful operational conditions.

Expected behaviors:
- `NO_TRADE` for stale market read
- `NO_TRADE` for weak confidence or unclear directional bias

---

## Priority 3 scenarios

### 10. Repeated live stability sampling

Why this matters:
- Useful only after the high-value doctrine edges are tested.

Expected behaviors:
- same scenario remains schema-stable across multiple runs
- no provider drift into invalid boundary or payload shape

### 11. Additional regime label coverage

Why this matters:
- Lower leverage than doctrine-specific edge cases.

Expected behaviors:
- valid use of less-common `market_regime` and `directional_bias` labels under appropriate packets

---

## Recommended execution order

1. CL near EIA or elevated volatility
2. ZN near auction or macro release
3. 6E missing session segmentation or post-11:00 thin liquidity
4. MGC DXY/yield contradiction and fear-catalyst activation
5. NQ relative-strength divergence and megacap earnings risk
6. ES divergence-driven `NO_TRADE`

## Stop condition

Stop edge-case expansion when:
- all Priority 1 scenarios have either passed or produced a clearly bounded doctrine-level limitation
- no new schema or chaining defects appear
- remaining issues are semantic judgment questions rather than runtime correctness questions

At that point the next phase should be deployment integration, not continued prompt-boundary iteration.
