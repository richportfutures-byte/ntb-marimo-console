# STAGE 1: Contract-by-Contract Data Sufficiency Specification

---

## A. Contract-by-Contract Specifications

---

### ES (E-mini S&P 500)

**Contract metadata**: Tick size 0.25, $12.50/tick, point value $50.00, max position 2

#### 1. Required Charts
- 5-minute RTH chart (current session, minimum 2 hours visible)
- Daily chart (minimum 20 sessions)

#### 2. Preferred Charts
- 30-minute chart (5-session context)
- TPO/Market Profile chart (current + prior session)
- Volume Profile chart (current session composite)

#### 3. Required Structured Fields
| Field | Type | Mandatory | Notes |
|-------|------|-----------|-------|
| current_price | float | YES | |
| session_open | float | YES | RTH open |
| prior_day_high | float | YES | |
| prior_day_low | float | YES | |
| prior_day_close | float | YES | Settlement |
| overnight_high | float | YES | Globex high |
| overnight_low | float | YES | Globex low |
| vwap | float | YES | Current session VWAP |
| current_session_vah | float | YES | |
| current_session_val | float | YES | |
| current_session_poc | float | YES | |
| previous_session_vah | float | YES | |
| previous_session_val | float | YES | |
| previous_session_poc | float | YES | |
| session_range | float | YES | Current high minus low |
| avg_20d_session_range | float | YES | Must be precomputed |
| cumulative_delta | float | YES | Must be precomputed |
| current_volume_vs_average | float | YES | Ratio, must be precomputed |

#### 4. Required Session References
- RTH open type classification (Open-Drive, Open-Test-Drive, Open-Rejection-Reverse, Open-Auction)
- Whether price is inside or outside prior day's range
- Whether price is inside or outside prior session's value area

#### 5. Required TPO / Market Profile Inputs
- Current session TPO structure type (normal, double-distribution, elongated, compressed)
- Single prints present (yes/no, approximate location)
- Excess at highs/lows (yes/no)
- Poor high/low (yes/no)

#### 6. Required Volume Profile Inputs
- Key HVN levels (max 3 relevant)
- Key LVN levels (max 3 relevant)
- Developing POC migration direction (up/down/flat)

#### 7. Required Order-Flow Inputs
- Cumulative delta trend (positive/negative/divergent from price)
- Volume pace relative to 20-day average

#### 8. Required Volatility Context
- avg_20d_session_range (precomputed)
- Current session range as % of 20-day average
- VIX level (if available, structured field)

#### 9. Required Macro / Event Calendar Context
- Next scheduled Tier-1 release (name, time, minutes until)
- Fed speakers today (yes/no, time)
- Options expiration relevance (standard/quad-witch/none)

#### 10. Required Cross-Market Context
- NQ relative strength vs ES (precomputed ratio or spread)
- Bond market direction (ZN up/down/flat today)
- DXY direction (up/down/flat)

#### 11. ES-Specific Extensions
- Market breadth (advancers/decliners ratio or ADD reading)
- Index cash market tone (SPX trend today: up/down/choppy)

#### 12. READY / NEED_INPUT / INSUFFICIENT_DATA Criteria

| Status | Condition |
|--------|-----------|
| **READY** | All required structured fields present, at least 5-min chart attached, event calendar current, session references computed |
| **NEED_INPUT** | 1–3 required fields missing but obtainable; list them explicitly |
| **INSUFFICIENT_DATA** | >3 required fields missing, OR no chart attached, OR event calendar stale by >1 hour |

---

### NQ (E-mini Nasdaq-100)

**Contract metadata**: Tick size 0.25, $5.00/tick, point value $20.00, max position 2

#### 1. Required Charts
- 5-minute RTH chart (current session, minimum 2 hours visible)
- Daily chart (minimum 20 sessions)

#### 2. Preferred Charts
- 30-minute chart (5-session context)
- TPO/Market Profile chart (current + prior session)

#### 3. Required Structured Fields
Same as ES core fields (current_price through current_volume_vs_average), plus:

| Field | Type | Mandatory | Notes |
|-------|------|-----------|-------|
| relative_strength_vs_es | float | YES | NQ % change / ES % change, precomputed |
| megacap_leadership_table | object | PREFERRED | Top 5 megacap direction if available |

#### 4. Required Session References
Same as ES.

#### 5. Required TPO / Market Profile Inputs
Same as ES.

#### 6. Required Volume Profile Inputs
Same as ES.

#### 7. Required Order-Flow Inputs
Same as ES.

#### 8. Required Volatility Context
- avg_20d_session_range (precomputed, NQ-specific)
- Current session range as % of 20-day average
- VXN level if available

#### 9. Required Macro / Event Calendar Context
Same as ES, plus:
- Any megacap earnings due today or after close (company, time)
- FOMC / tech-sector-specific regulatory news flag

#### 10. Required Cross-Market Context
- ES direction today (leading/lagging NQ)
- Semiconductor sector tone (up/down/flat) if available
- Bond yield direction (rising yields historically pressure NQ)

#### 11. NQ-Specific Extensions
- relative_strength_vs_es (mandatory, precomputed)
- megacap_leadership_table (preferred)

#### 12. READY / NEED_INPUT / INSUFFICIENT_DATA Criteria

| Status | Condition |
|--------|-----------|
| **READY** | All required fields present, relative_strength_vs_es computed, charts attached, event calendar current |
| **NEED_INPUT** | relative_strength_vs_es missing but ES data available to compute it; or 1–3 other fields missing |
| **INSUFFICIENT_DATA** | >3 required fields missing, OR no chart, OR ES data unavailable (cannot assess relative behavior) |

---

### CL (Crude Oil)

**Contract metadata**: Tick size 0.01, $10.00/tick, point value $1,000.00, max position 2

#### 1. Required Charts
- 5-minute chart covering at least 2 hours of current session
- Daily chart (minimum 20 sessions)

#### 2. Preferred Charts
- 15-minute chart (3-session context)
- Footprint / delta chart (current session)
- DOM snapshot (if available)

#### 3. Required Structured Fields
Core fields same as ES, plus:

| Field | Type | Mandatory | Notes |
|-------|------|-----------|-------|
| eia_timing | string | YES | "today HH:MM" or "not today" or "already released" |
| oil_specific_headlines | string | PREFERRED | OPEC, geopolitical, inventory surprises |
| liquidity_sweep_summary | string | PREFERRED | Any recent sweep of resting liquidity noted |
| dom_liquidity_summary | string | PREFERRED | Bid/ask stack asymmetry if DOM attached |
| realized_volatility_context | string | YES | "elevated", "normal", "compressed" relative to 20-day |

#### 4. Required Session References
- RTH open type (same classifications as ES)
- Whether inside or outside prior range
- CL-specific: Whether price is near a weekly pivot or weekly range extreme

#### 5. Required TPO / Market Profile Inputs
Same structure as ES, but CL TPO sessions are shorter; note session segmentation.

#### 6. Required Volume Profile Inputs
Same as ES.

#### 7. Required Order-Flow Inputs
- Cumulative delta (precomputed)
- Footprint chart context (if attached): absorption visible, aggressive buying/selling clusters
- DOM stack imbalance (if DOM snapshot attached)

#### 8. Required Volatility Context
- avg_20d_session_range (precomputed, CL-specific)
- Current realized vol vs 20-day average (ratio)
- OVX level if available

#### 9. Required Macro / Event Calendar Context
- EIA/DOE inventory report timing
- OPEC meeting or quota news flag
- Geopolitical risk flag (Middle East, sanctions, shipping disruptions)

#### 10. Required Cross-Market Context
- DXY direction (inverse correlation)
- Equity market tone (risk-on/risk-off)
- Natural gas direction (energy complex context)

#### 11. READY / NEED_INPUT / INSUFFICIENT_DATA Criteria

| Status | Condition |
|--------|-----------|
| **READY** | All required fields present, EIA timing known, volatility context computed, charts attached |
| **NEED_INPUT** | EIA timing unknown but determinable; or 1–3 fields missing |
| **INSUFFICIENT_DATA** | Volatility context missing, OR >3 fields missing, OR EIA release imminent but timing not confirmed (triggers event lockout ambiguity) |

**CL-Specific Warning**: CL is the most dangerous contract for hallucination because of fast moves, wide slippage, and event-driven gaps. The sufficiency gate must be stricter here. If `realized_volatility_context` = "elevated" AND EIA is within 30 minutes, status must be INSUFFICIENT_DATA regardless of other fields.

---

### ZN (10-Year Treasury Note)

**Contract metadata**: Tick size 1/64 of a point (0.015625), $15.625/tick, point value $1,000.00, max position 4

#### 1. Required Charts
- 5-minute chart (current session, 2+ hours)
- Daily chart (minimum 20 sessions)

#### 2. Preferred Charts
- 30-minute chart (5-session context)
- TPO chart (current + prior session)

#### 3. Required Structured Fields
Core fields same as ES, plus:

| Field | Type | Mandatory | Notes |
|-------|------|-----------|-------|
| cash_10y_yield | float | YES | Current 10Y yield level |
| treasury_auction_schedule | string | YES | "today HH:MM [maturity]" or "not today" |
| macro_release_context | string | YES | What released today, market reaction summary |
| absorption_summary | string | PREFERRED | Buyer/seller absorption at key levels if visible |

#### 4. Required Session References
- RTH open type
- Inside/outside prior range
- ZN-specific: Position relative to recent yield range (high/mid/low of 20-day)

#### 5. Required TPO / Market Profile Inputs
Same as ES.

#### 6. Required Volume Profile Inputs
Same as ES.

#### 7. Required Order-Flow Inputs
- Cumulative delta (precomputed)
- Post-data-release delta shift if relevant (e.g., after CPI, NFP)

#### 8. Required Volatility Context
- avg_20d_session_range (precomputed, ZN-specific)
- MOVE index level if available
- Post-data sensitivity flag ("high" if major release today)

#### 9. Required Macro / Event Calendar Context
- Fed rate decision proximity (days until)
- Today's data releases with actual vs expected
- Treasury auction timing and maturity
- Fed speaker schedule

#### 10. Required Cross-Market Context
- Equity market direction (flight-to-quality indicator)
- DXY direction
- 2Y-10Y spread direction (curve steepening/flattening)

#### 11. READY / NEED_INPUT / INSUFFICIENT_DATA Criteria

| Status | Condition |
|--------|-----------|
| **READY** | All required fields present, yield level known, macro calendar current, auction schedule confirmed |
| **NEED_INPUT** | Macro release context stale (>30 min) or cash yield not yet captured |
| **INSUFFICIENT_DATA** | Cash yield unknown, OR major data release within lockout window with no reaction data, OR >3 fields missing |

**ZN-Specific Warning**: ZN is heavily macro-driven. The data sufficiency gate must hard-block if today's Tier-1 data has already released but `macro_release_context` is empty — the market may have already repriced and the LLM would be reading stale structure.

---

### 6E (Euro FX)

**Contract metadata**: Tick size 0.00005 ($6.25/tick), point value $125,000.00, max position 4

#### 1. Required Charts
- 5-minute chart (current session, 2+ hours)
- Daily chart (minimum 20 sessions)

#### 2. Preferred Charts
- 4-hour chart (session segmentation: Asia, London, NY)
- 30-minute chart

#### 3. Required Structured Fields
Core fields same as ES, plus:

| Field | Type | Mandatory | Notes |
|-------|------|-----------|-------|
| asia_high_low | object | YES | {high: float, low: float} |
| london_high_low | object | YES | {high: float, low: float} |
| ny_high_low_so_far | object | YES | {high: float, low: float} |
| dxy_context | string | YES | "strengthening", "weakening", "range-bound" |
| europe_initiative_status | string | YES | "Europe drove higher/lower/was range-bound" |

#### 4. Required Session References
- Which session range has been tested/broken
- Whether NY session is extending or reversing London initiative
- Inside/outside prior day range

#### 5. Required TPO / Market Profile Inputs
Same structure as ES, but segmented by session (Asia → London → NY).

#### 6. Required Volume Profile Inputs
Same as ES.

#### 7. Required Order-Flow Inputs
- Cumulative delta (precomputed)
- Volume pace relative to session average

#### 8. Required Volatility Context
- avg_20d_session_range (precomputed, 6E-specific)
- Current session range as % of 20-day average
- EVZ (Euro volatility index) if available

#### 9. Required Macro / Event Calendar Context
- ECB rate decision proximity
- Eurozone data releases today (PMI, CPI, GDP)
- US data releases today (affecting DXY)
- Central bank speaker schedule (ECB + Fed)

#### 10. Required Cross-Market Context
- DXY level and intraday direction
- EUR/GBP or EUR/JPY cross-rate behavior if available
- Bond yield differentials (US 10Y vs German 10Y) if available

#### 11. READY / NEED_INPUT / INSUFFICIENT_DATA Criteria

| Status | Condition |
|--------|-----------|
| **READY** | All required fields present, session highs/lows computed, DXY context current, event calendar current |
| **NEED_INPUT** | London session data not yet available (pre-London hours); or DXY context stale |
| **INSUFFICIENT_DATA** | Session segmentation data missing (cannot determine London initiative), OR >3 fields missing, OR approaching ECB decision without timing confirmation |

**6E-Specific Warning**: 6E is session-driven. Without Asia and London range data, the LLM cannot assess NY-session initiative. The sufficiency gate must require session segmentation.

---

### MGC (Micro Gold)

**Contract metadata**: Tick size 0.10, $1.00/tick, point value $10.00, max position 12

#### 1. Required Charts
- 5-minute chart (current session, 2+ hours)
- Daily chart (minimum 20 sessions)

#### 2. Preferred Charts
- 60-minute chart (5-day context)
- Weekly chart (macro trend context)

#### 3. Required Structured Fields
Core fields same as ES, plus:

| Field | Type | Mandatory | Notes |
|-------|------|-----------|-------|
| dxy_context | string | YES | "strengthening", "weakening", "range-bound" |
| yield_context | string | YES | "rising", "falling", "stable" (real yields preferred) |
| swing_penetration_volume_summary | string | PREFERRED | Volume behavior at recent swing highs/lows |
| macro_fear_catalyst_summary | string | YES | "none", or brief description of active fear catalyst |

#### 4. Required Session References
- COMEX session open type
- Inside/outside prior range
- Position relative to weekly range (high/mid/low)

#### 5. Required TPO / Market Profile Inputs
Same as ES.

#### 6. Required Volume Profile Inputs
Same as ES.

#### 7. Required Order-Flow Inputs
- Cumulative delta (precomputed)
- Volume pace relative to session average

#### 8. Required Volatility Context
- avg_20d_session_range (precomputed, MGC-specific)
- GVZ (gold volatility index) if available
- Whether gold is in a trending or mean-reverting regime (precomputed)

#### 9. Required Macro / Event Calendar Context
- Fed rate decision proximity
- CPI/PPI release proximity
- Geopolitical risk flag
- Central bank gold-buying news flag

#### 10. Required Cross-Market Context
- DXY level and direction (inverse correlation)
- US 10Y real yield direction (TIPS yield if available)
- Equity market risk-on/risk-off tone
- Silver direction (precious metals complex)

#### 11. READY / NEED_INPUT / INSUFFICIENT_DATA Criteria

| Status | Condition |
|--------|-----------|
| **READY** | All required fields present, DXY and yield context current, macro fear catalyst assessed, charts attached |
| **NEED_INPUT** | DXY context stale, or yield context not yet captured |
| **INSUFFICIENT_DATA** | Both DXY and yield context missing (cannot assess gold's macro drivers), OR >3 fields missing, OR active geopolitical event with no macro_fear_catalyst_summary |

**MGC-Specific Warning**: Gold is macro-regime-driven. Without DXY and yield context, the LLM is essentially trading blind on MGC. The sufficiency gate must hard-block when both are missing.

---

## B. Normalized Shared market_packet Schema

All six contracts consume this common structure:

```json
{
  "timestamp": "ISO-8601",
  "contract": "ES|NQ|CL|ZN|6E|MGC",
  "session_type": "RTH|ETH|GLOBEX",
  "current_price": 0.0,
  "session_open": 0.0,
  "prior_day_high": 0.0,
  "prior_day_low": 0.0,
  "prior_day_close": 0.0,
  "overnight_high": 0.0,
  "overnight_low": 0.0,
  "current_session_vah": 0.0,
  "current_session_val": 0.0,
  "current_session_poc": 0.0,
  "previous_session_vah": 0.0,
  "previous_session_val": 0.0,
  "previous_session_poc": 0.0,
  "vwap": 0.0,
  "session_range": 0.0,
  "avg_20d_session_range": 0.0,
  "cumulative_delta": 0.0,
  "current_volume_vs_average": 0.0,
  "opening_type": "Open-Drive|Open-Test-Drive|Open-Rejection-Reverse|Open-Auction",
  "major_higher_timeframe_levels": [],
  "key_hvns": [],
  "key_lvns": [],
  "singles_excess_poor_high_low_notes": "",
  "event_calendar_remainder": [],
  "cross_market_context": {},
  "data_quality_flags": []
}
```

---

## C. Contract-Specific market_packet Extensions

These fields exist only in the extension block and differ by contract:

```json
{
  "contract_specific_extension": {
    "ES": {
      "breadth": "",
      "index_cash_tone": ""
    },
    "NQ": {
      "relative_strength_vs_es": 0.0,
      "megacap_leadership_table": {}
    },
    "CL": {
      "eia_timing": "",
      "oil_specific_headlines": "",
      "liquidity_sweep_summary": "",
      "dom_liquidity_summary": "",
      "realized_volatility_context": ""
    },
    "ZN": {
      "cash_10y_yield": 0.0,
      "treasury_auction_schedule": "",
      "macro_release_context": "",
      "absorption_summary": ""
    },
    "6E": {
      "asia_high_low": {"high": 0.0, "low": 0.0},
      "london_high_low": {"high": 0.0, "low": 0.0},
      "ny_high_low_so_far": {"high": 0.0, "low": 0.0},
      "dxy_context": "",
      "europe_initiative_status": ""
    },
    "MGC": {
      "dxy_context": "",
      "yield_context": "",
      "swing_penetration_volume_summary": "",
      "macro_fear_catalyst_summary": ""
    }
  }
}
```

---

## D. What Must Be Computed Upstream

These fields **cannot** be inferred visually by the LLM and must be precomputed numerically before the market_packet is assembled:

| Field | Reason |
|-------|--------|
| `avg_20d_session_range` | Requires historical data aggregation |
| `current_volume_vs_average` | Requires 20-day volume baseline |
| `cumulative_delta` | Requires tick-level bid/ask attribution |
| `session_range` | Simple math but must be computed from actual high/low |
| `vwap` | Requires volume-weighted calculation from session start |
| `current_session_vah`, `val`, `poc` | Require TPO or volume profile computation |
| `previous_session_vah`, `val`, `poc` | Require prior session computation |
| `relative_strength_vs_es` (NQ) | Requires both NQ and ES % change computation |
| `realized_volatility_context` (CL) | Requires rolling volatility calculation |
| `asia_high_low`, `london_high_low` (6E) | Require session-boundary-aware high/low tracking |
| `opening_type` | Requires rule-based classification from first 15-30 minutes of price action |
| `key_hvns`, `key_lvns` | Require volume profile computation |

**Rule**: Any field in this table that is presented as null or missing must trigger `NEED_INPUT`, not silent LLM estimation.

---

## E. What Images Are Evidentiary Only

These visual inputs **support** the LLM's read but **must not be the sole source of truth** for any decision-critical field:

| Visual Input | What It Supports | What It Cannot Replace |
|-------------|-----------------|----------------------|
| Daily chart screenshot | Trend context, support/resistance levels | Precise price levels, exact range values |
| 5-minute chart screenshot | Intraday structure, pattern recognition | Exact VWAP, exact delta, exact volume ratios |
| TPO chart screenshot | Distribution shape, single prints, excess | Precise VAH/VAL/POC values (must be in structured fields) |
| Volume profile screenshot | HVN/LVN visual confirmation | Precise HVN/LVN numeric levels |
| Footprint chart screenshot | Absorption clusters, aggressive activity | Precise cumulative delta values |
| DOM snapshot | Bid/ask stack asymmetry | Reliable liquidity inference (DOM changes rapidly) |

**Rule**: If a structured field is available, the LLM must use the structured field. Images are confirmatory evidence only. The LLM must never override a structured numeric field based on a visual impression from a chart image.

---

## Hidden Assumptions Called Out

1. **Opening type classification** assumes the operator has a consistent rule for categorizing the first 15-30 minutes. If the operator uses a different classification system, this must be reconciled before Stage 2.

2. **Cross-market context** assumes the operator can provide at least directional readings (up/down/flat) for related markets. If only the traded contract's data is available, cross-market fields should be marked null and the sufficiency gate should still allow READY — but confidence_band should be capped at MEDIUM.

3. **Session segmentation for 6E** assumes the operator can define Asia/London/NY session boundaries. If the platform does not support session-boundary tracking, 6E's sufficiency requirements are harder to meet and the contract should be flagged as NEED_INPUT more often.

4. **Volume profile fields** assume the operator's platform can export HVN/LVN levels numerically. If only visual profiles are available, those fields must be null and the LLM must rely on evidentiary images — but this degrades data quality.

5. **Cumulative delta** assumes the platform computes delta from bid/ask attribution. Different platforms compute delta differently. The operator should confirm which method their platform uses and whether it is consistent across contracts.

---

## Operator Acceptance Checklist (Stage 1)

- [x] ES includes value migration, VWAP, opening type, overnight references
- [x] NQ includes ES relative strength and megacap context
- [x] CL includes event timing, tape urgency, volatility, sweep/liquidity context
- [x] ZN includes macro calendar, yield context, post-data sensitivity
- [x] 6E includes session segmentation and DXY context
- [x] MGC includes dollar, yield, and macro fear context
- [x] Upstream-computed fields are separated from image-only evidence
- [x] Each contract is materially distinct
- [x] No prompts, schemas, or architecture have been designed

**Stage 1 Status: COMPLETE — Ready for operator review and acceptance.**
