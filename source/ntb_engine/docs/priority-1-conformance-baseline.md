# Priority 1 Conformance Baseline

Branch: `stagea-stageb-es`

This note freezes the current Priority 1 behavioral baseline after live validation on the canonical contract-specific edge cases.

## Canonical scenarios

- `CL` near EIA / elevated volatility -> `sufficiency_gate` / `INSUFFICIENT_DATA`
- `ZN` near auction or macro release -> `sufficiency_gate` / `EVENT_LOCKOUT`
- `6E` post-11:00 thin liquidity -> `contract_market_read` / `NO_TRADE`
- `MGC` DXY/yield contradiction plus fear-catalyst activation -> `contract_market_read` / `NO_TRADE`
- `NQ` weak relative strength plus megacap earnings risk -> `contract_market_read` / `NO_TRADE`
- `ES` breadth/delta divergence -> `contract_market_read` / `NO_TRADE`

## Resolved Priority 1 failure classes

- Stage A lockout shape drift:
  live event-lockout outputs drifted away from the required nested schema object.
- Stage B contradictory-driver permissiveness for `MGC`:
  contradictory DXY/yield drivers under an active fear catalyst were too permissive and needed explicit fail-closed guidance.
- Stage B relative-strength plus earnings-risk permissiveness for `NQ`:
  weak `relative_strength_vs_es` plus fragile megacap earnings context needed explicit fail-closed guidance.

## Guardrail

This matrix is the current Priority 1 behavioral baseline.

Do not broaden prompt hardening, adapter reinforcement, or doctrine wording without new failing evidence from a concrete scenario.

Future work should expand scenario coverage first, then harden only where new regressions or doctrine-level misses are actually observed.
