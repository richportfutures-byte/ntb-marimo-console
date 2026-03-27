# STAGE 3: JSON Schemas and Inter-Stage Contracts

---

## Schema-to-Architecture Mapping

| Schema | Produced By | Consumed By | Purpose |
|--------|------------|-------------|---------|
| `challenge_state` | Operator (external) | Stage A, Stage D | Current account state and risk budget |
| `contract_metadata` | Operator (static config) | Stage C, Stage D | Contract specs for sizing math |
| `market_packet` | Operator (external) | Stage A | Raw market data input |
| `contract_specific_extension` | Operator (external) | Stage A, Stage B | Contract-specific data fields |
| `attached_visuals` | Operator (external) | Stage A, Stage B | Flags for which charts are attached |
| `sufficiency_gate_output` | Stage A | Stage B, Stage E | Data validation result |
| `contract_analysis` | Stage B | Stage C, Stage E | Structured market read |
| `proposed_setup` | Stage C | Stage D, Stage E | Trade setup or NO_TRADE |
| `risk_authorization` | Stage D | Stage E | Authorization decision |
| `logging_record` | Stage E | Evaluation framework | Complete pipeline trace |
| `post_trade_review_record` | Post-execution | Evaluation framework | Actual trade outcome |

---

## 1. challenge_state

```json
{
  "$schema": "challenge_state_v1",
  "description": "Current account and position state. Provided by operator before each pipeline run.",
  "required": ["current_balance", "daily_realized_pnl", "max_risk_per_trade_dollars", "daily_loss_stop_dollars", "minimum_reward_to_risk", "event_lockout_minutes_before", "event_lockout_minutes_after", "max_position_size_by_contract", "max_trades_per_day", "max_trades_per_contract_per_day", "cooldown_after_stopout_minutes", "current_open_positions", "trades_today_all", "trades_today_by_contract", "profit_target_dollars"],
  "properties": {
    "current_balance": {
      "type": "number",
      "description": "Current account balance in dollars. MANDATORY.",
      "nullable": false,
      "decision_critical": true
    },
    "daily_realized_pnl": {
      "type": "number",
      "description": "Today's realized P&L in dollars (negative if losing). MANDATORY.",
      "nullable": false,
      "decision_critical": true
    },
    "max_risk_per_trade_dollars": {
      "type": "number",
      "description": "Maximum risk allowed per trade in dollars. Default: 1450.",
      "nullable": false,
      "decision_critical": true
    },
    "daily_loss_stop_dollars": {
      "type": "number",
      "description": "Maximum daily loss before shutdown in dollars. Default: 10000.",
      "nullable": false,
      "decision_critical": true
    },
    "minimum_reward_to_risk": {
      "type": "number",
      "description": "Minimum acceptable reward-to-risk ratio. Default: 1.5.",
      "nullable": false,
      "decision_critical": true
    },
    "event_lockout_minutes_before": {
      "type": "integer",
      "description": "Minutes before Tier-1 event to lock out new entries. Default: 15.",
      "nullable": false,
      "decision_critical": true
    },
    "event_lockout_minutes_after": {
      "type": "integer",
      "description": "Minutes after Tier-1 event to lock out new entries. Default: 5.",
      "nullable": false,
      "decision_critical": true
    },
    "max_position_size_by_contract": {
      "type": "object",
      "description": "Map of contract -> max position size. Per-contract limits replace global concurrent position cap. Default: ES:2, NQ:2, CL:2, ZN:4, 6E:4, MGC:12.",
      "nullable": false,
      "decision_critical": true
    },
    "max_trades_per_day": {
      "type": "integer",
      "description": "Maximum total trades allowed today. Default: 60.",
      "nullable": false,
      "decision_critical": true
    },
    "max_trades_per_contract_per_day": {
      "type": "integer",
      "description": "Maximum trades on any single contract today. Default: 3.",
      "nullable": false,
      "decision_critical": true
    },
    "cooldown_after_stopout_minutes": {
      "type": "integer",
      "description": "Minutes to wait after a stop-out before re-entry on the same contract. Default: 30.",
      "nullable": false,
      "decision_critical": true
    },
    "current_open_positions": {
      "type": "array",
      "description": "List of currently open positions. Each entry has contract, direction, size, entry_price, current_risk_dollars. Empty array if flat.",
      "nullable": false,
      "items": {
        "type": "object",
        "properties": {
          "contract": { "type": "string", "enum": ["ES", "NQ", "CL", "ZN", "6E", "MGC"] },
          "direction": { "type": "string", "enum": ["LONG", "SHORT"] },
          "size": { "type": "integer" },
          "entry_price": { "type": "number" },
          "current_risk_dollars": { "type": "number" }
        }
      },
      "decision_critical": true
    },
    "trades_today_all": {
      "type": "integer",
      "description": "Total completed + open trades today across all contracts.",
      "nullable": false,
      "decision_critical": true
    },
    "trades_today_by_contract": {
      "type": "object",
      "description": "Map of contract -> trade count today.",
      "nullable": false,
      "decision_critical": true
    },
    "last_stopout_time_by_contract": {
      "type": "object",
      "description": "Map of contract -> ISO-8601 timestamp of last stop-out. Null per contract if no stop-out today.",
      "nullable": true,
      "decision_critical": true
    }
  }
}
```

**Field notes:**
- All fields are mandatory except `last_stopout_time_by_contract` (null means no stop-out today)
- `current_open_positions` may be an empty array (operator is flat) but must not be null
- `trades_today_by_contract` keys are the 6 contract symbols; values default to 0

---

## 2. contract_metadata

```json
{
  "$schema": "contract_metadata_v1",
  "description": "Static contract specifications. One per contract, loaded from config.",
  "required": ["contract", "tick_size", "dollar_per_tick", "point_value", "max_position_size", "slippage_ticks", "allowed_hours_start_et", "allowed_hours_end_et"],
  "properties": {
    "contract": {
      "type": "string",
      "enum": ["ES", "NQ", "CL", "ZN", "6E", "MGC"],
      "description": "Contract symbol.",
      "nullable": false,
      "decision_critical": true
    },
    "tick_size": {
      "type": "number",
      "description": "Minimum price increment.",
      "nullable": false,
      "decision_critical": true
    },
    "dollar_per_tick": {
      "type": "number",
      "description": "Dollar value of one tick movement.",
      "nullable": false,
      "decision_critical": true
    },
    "point_value": {
      "type": "number",
      "description": "Dollar value of one full point.",
      "nullable": false,
      "decision_critical": true
    },
    "max_position_size": {
      "type": "integer",
      "description": "Maximum contracts allowed per position.",
      "nullable": false,
      "decision_critical": true
    },
    "slippage_ticks": {
      "type": "integer",
      "description": "Assumed slippage per side in ticks.",
      "nullable": false,
      "decision_critical": true
    },
    "allowed_hours_start_et": {
      "type": "string",
      "description": "Earliest allowed entry time in ET. Format: HH:MM.",
      "nullable": false,
      "decision_critical": true
    },
    "allowed_hours_end_et": {
      "type": "string",
      "description": "Latest allowed entry time in ET. Format: HH:MM.",
      "nullable": false,
      "decision_critical": true
    }
  }
}
```

**Reference values:**

| Contract | tick_size | dollar_per_tick | point_value | max_position_size | slippage_ticks | hours_start | hours_end |
|----------|-----------|----------------|-------------|-------------------|----------------|-------------|-----------|
| ES | 0.25 | 12.50 | 50.00 | 2 | 1 | 09:30 | 15:45 |
| NQ | 0.25 | 5.00 | 20.00 | 2 | 1 | 09:30 | 15:45 |
| CL | 0.01 | 10.00 | 1000.00 | 2 | 2 | 09:00 | 14:15 |
| ZN | 0.015625 | 15.625 | 1000.00 | 4 | 1 | 08:20 | 14:45 |
| 6E | 0.00005 | 6.25 | 125000.00 | 4 | 1 | 08:00 | 12:00 |
| MGC | 0.10 | 1.00 | 10.00 | 12 | 1 | 08:20 | 13:15 |

---

## 3. market_packet (shared)

```json
{
  "$schema": "market_packet_v1",
  "description": "Shared market data input for all contracts. Assembled by operator before pipeline run.",
  "required": ["timestamp", "contract", "session_type", "current_price", "session_open", "prior_day_high", "prior_day_low", "prior_day_close", "overnight_high", "overnight_low", "current_session_vah", "current_session_val", "current_session_poc", "previous_session_vah", "previous_session_val", "previous_session_poc", "vwap", "session_range", "avg_20d_session_range", "cumulative_delta", "current_volume_vs_average", "opening_type", "event_calendar_remainder"],
  "properties": {
    "timestamp": {
      "type": "string",
      "format": "date-time",
      "description": "ISO-8601 timestamp when packet was assembled. Used for staleness check.",
      "nullable": false,
      "decision_critical": true
    },
    "contract": {
      "type": "string",
      "enum": ["ES", "NQ", "CL", "ZN", "6E", "MGC"],
      "nullable": false,
      "decision_critical": true
    },
    "session_type": {
      "type": "string",
      "enum": ["RTH", "ETH", "GLOBEX"],
      "description": "Current session type.",
      "nullable": false,
      "decision_critical": true
    },
    "current_price": { "type": "number", "nullable": false, "decision_critical": true },
    "session_open": { "type": "number", "nullable": false, "decision_critical": true },
    "prior_day_high": { "type": "number", "nullable": false, "decision_critical": true },
    "prior_day_low": { "type": "number", "nullable": false, "decision_critical": true },
    "prior_day_close": { "type": "number", "nullable": false, "decision_critical": true },
    "overnight_high": { "type": "number", "nullable": false, "decision_critical": true },
    "overnight_low": { "type": "number", "nullable": false, "decision_critical": true },
    "current_session_vah": { "type": "number", "nullable": false, "decision_critical": true },
    "current_session_val": { "type": "number", "nullable": false, "decision_critical": true },
    "current_session_poc": { "type": "number", "nullable": false, "decision_critical": true },
    "previous_session_vah": { "type": "number", "nullable": false, "decision_critical": true },
    "previous_session_val": { "type": "number", "nullable": false, "decision_critical": true },
    "previous_session_poc": { "type": "number", "nullable": false, "decision_critical": true },
    "vwap": { "type": "number", "nullable": false, "decision_critical": true },
    "session_range": {
      "type": "number",
      "description": "Current session high minus low. Precomputed.",
      "nullable": false,
      "decision_critical": true
    },
    "avg_20d_session_range": {
      "type": "number",
      "description": "20-day average session range. Precomputed.",
      "nullable": false,
      "decision_critical": true
    },
    "cumulative_delta": {
      "type": "number",
      "description": "Session cumulative delta. Precomputed from bid/ask attribution.",
      "nullable": false,
      "decision_critical": true
    },
    "current_volume_vs_average": {
      "type": "number",
      "description": "Ratio of current session volume to 20-day average at this time. Precomputed.",
      "nullable": false,
      "decision_critical": false
    },
    "opening_type": {
      "type": "string",
      "enum": ["Open-Drive", "Open-Test-Drive", "Open-Rejection-Reverse", "Open-Auction", "NOT_YET_CLASSIFIED"],
      "description": "Opening type classification. NOT_YET_CLASSIFIED if session is < 30 minutes old.",
      "nullable": false,
      "decision_critical": true
    },
    "major_higher_timeframe_levels": {
      "type": "array",
      "items": { "type": "number" },
      "description": "Key levels from daily/weekly charts. Max 5.",
      "nullable": true,
      "decision_critical": false
    },
    "key_hvns": {
      "type": "array",
      "items": { "type": "number" },
      "description": "High-volume node price levels. Max 3. Precomputed from volume profile.",
      "nullable": true,
      "decision_critical": false
    },
    "key_lvns": {
      "type": "array",
      "items": { "type": "number" },
      "description": "Low-volume node price levels. Max 3. Precomputed from volume profile.",
      "nullable": true,
      "decision_critical": false
    },
    "singles_excess_poor_high_low_notes": {
      "type": "string",
      "description": "Free-text notes on TPO structure: single prints, excess, poor highs/lows.",
      "nullable": true,
      "decision_critical": false
    },
    "event_calendar_remainder": {
      "type": "array",
      "description": "Remaining scheduled events today. Each entry has name, time (ISO-8601), tier (1 or 2), minutes_until.",
      "items": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "time": { "type": "string", "format": "date-time" },
          "tier": { "type": "integer", "enum": [1, 2] },
          "minutes_until": { "type": "integer" }
        }
      },
      "nullable": false,
      "decision_critical": true
    },
    "cross_market_context": {
      "type": "object",
      "description": "Directional readings for related markets. Keys vary by contract.",
      "nullable": true,
      "decision_critical": false
    },
    "data_quality_flags": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Flags for known data issues. E.g., 'vwap_may_be_stale', 'delta_source_unverified'.",
      "nullable": true,
      "decision_critical": false
    }
  }
}
```

---

## 4. contract_specific_extension

```json
{
  "$schema": "contract_specific_extension_v1",
  "description": "Contract-specific fields that extend the shared market_packet. Only the relevant contract block is populated.",
  "oneOf": [
    {
      "contract": "ES",
      "required": ["breadth", "index_cash_tone"],
      "properties": {
        "breadth": { "type": "string", "description": "Market breadth reading (e.g., 'positive +1200', 'negative -800'). Precomputed.", "nullable": false, "decision_critical": true },
        "index_cash_tone": { "type": "string", "enum": ["bullish", "bearish", "choppy", "flat"], "description": "SPX cash session tone.", "nullable": false, "decision_critical": true }
      }
    },
    {
      "contract": "NQ",
      "required": ["relative_strength_vs_es"],
      "properties": {
        "relative_strength_vs_es": { "type": "number", "description": "NQ % change / ES % change. >1 = NQ leading. Precomputed.", "nullable": false, "decision_critical": true },
        "megacap_leadership_table": { "type": "object", "description": "Top 5 megacap tickers with intraday direction. Optional.", "nullable": true, "decision_critical": false }
      }
    },
    {
      "contract": "CL",
      "required": ["eia_timing", "realized_volatility_context"],
      "properties": {
        "eia_timing": { "type": "string", "description": "'today HH:MM', 'not_today', or 'already_released'.", "nullable": false, "decision_critical": true },
        "oil_specific_headlines": { "type": "string", "description": "OPEC, geopolitical, inventory headline summary.", "nullable": true, "decision_critical": false },
        "liquidity_sweep_summary": { "type": "string", "description": "Recent liquidity sweep observations.", "nullable": true, "decision_critical": false },
        "dom_liquidity_summary": { "type": "string", "description": "Bid/ask stack asymmetry from DOM snapshot.", "nullable": true, "decision_critical": false },
        "realized_volatility_context": { "type": "string", "enum": ["elevated", "normal", "compressed"], "description": "Current vs 20-day realized volatility. Precomputed.", "nullable": false, "decision_critical": true }
      }
    },
    {
      "contract": "ZN",
      "required": ["cash_10y_yield", "treasury_auction_schedule", "macro_release_context"],
      "properties": {
        "cash_10y_yield": { "type": "number", "description": "Current 10-year Treasury yield.", "nullable": false, "decision_critical": true },
        "treasury_auction_schedule": { "type": "string", "description": "'today HH:MM [maturity]' or 'not_today'.", "nullable": false, "decision_critical": true },
        "macro_release_context": { "type": "string", "description": "What released today, actual vs expected, market reaction.", "nullable": false, "decision_critical": true },
        "absorption_summary": { "type": "string", "description": "Buyer/seller absorption at key levels.", "nullable": true, "decision_critical": false }
      }
    },
    {
      "contract": "6E",
      "required": ["asia_high_low", "london_high_low", "ny_high_low_so_far", "dxy_context", "europe_initiative_status"],
      "properties": {
        "asia_high_low": { "type": "object", "properties": { "high": { "type": "number" }, "low": { "type": "number" } }, "nullable": false, "decision_critical": true },
        "london_high_low": { "type": "object", "properties": { "high": { "type": "number" }, "low": { "type": "number" } }, "nullable": false, "decision_critical": true },
        "ny_high_low_so_far": { "type": "object", "properties": { "high": { "type": "number" }, "low": { "type": "number" } }, "nullable": false, "decision_critical": true },
        "dxy_context": { "type": "string", "enum": ["strengthening", "weakening", "range-bound"], "nullable": false, "decision_critical": true },
        "europe_initiative_status": { "type": "string", "description": "Europe drove higher/lower/was range-bound.", "nullable": false, "decision_critical": true }
      }
    },
    {
      "contract": "MGC",
      "required": ["dxy_context", "yield_context", "macro_fear_catalyst_summary"],
      "properties": {
        "dxy_context": { "type": "string", "enum": ["strengthening", "weakening", "range-bound"], "nullable": false, "decision_critical": true },
        "yield_context": { "type": "string", "enum": ["rising", "falling", "stable"], "nullable": false, "decision_critical": true },
        "swing_penetration_volume_summary": { "type": "string", "description": "Volume behavior at recent swing highs/lows.", "nullable": true, "decision_critical": false },
        "macro_fear_catalyst_summary": { "type": "string", "description": "'none' or brief description of active fear catalyst.", "nullable": false, "decision_critical": true }
      }
    }
  ]
}
```

---

## 5. attached_visuals

```json
{
  "$schema": "attached_visuals_v1",
  "description": "Flags indicating which chart images are attached to this pipeline run.",
  "properties": {
    "daily_chart_attached": { "type": "boolean", "nullable": false },
    "higher_timeframe_chart_attached": { "type": "boolean", "nullable": false },
    "tpo_chart_attached": { "type": "boolean", "nullable": false },
    "volume_profile_attached": { "type": "boolean", "nullable": false },
    "execution_chart_attached": { "type": "boolean", "nullable": false },
    "footprint_chart_attached": { "type": "boolean", "nullable": false },
    "dom_snapshot_attached": { "type": "boolean", "nullable": false }
  }
}
```

---

## 6. sufficiency_gate_output

```json
{
  "$schema": "sufficiency_gate_output_v1",
  "description": "Output of Stage A: Sufficiency Gate. Determines whether the market_packet is complete enough to proceed.",
  "required": ["stage", "contract", "timestamp", "status", "missing_inputs", "disqualifiers", "data_quality_flags", "staleness_check"],
  "properties": {
    "stage": {
      "type": "string",
      "const": "sufficiency_gate",
      "description": "Provenance: which stage produced this output.",
      "nullable": false
    },
    "contract": { "type": "string", "enum": ["ES", "NQ", "CL", "ZN", "6E", "MGC"], "nullable": false },
    "timestamp": { "type": "string", "format": "date-time", "description": "When this gate was evaluated.", "nullable": false },
    "status": {
      "type": "string",
      "enum": ["READY", "NEED_INPUT", "INSUFFICIENT_DATA", "EVENT_LOCKOUT"],
      "description": "Gate result. READY = proceed. NEED_INPUT = list missing fields. INSUFFICIENT_DATA = halt, data too thin. EVENT_LOCKOUT = halt, event window active.",
      "nullable": false,
      "decision_critical": true
    },
    "missing_inputs": {
      "type": "array",
      "items": { "type": "string" },
      "description": "List of missing field names. Empty if READY.",
      "nullable": false
    },
    "disqualifiers": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Reasons for INSUFFICIENT_DATA or EVENT_LOCKOUT. E.g., 'CL elevated vol + EIA within 30 min'.",
      "nullable": false
    },
    "data_quality_flags": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Passed through from market_packet, plus any new flags discovered during validation.",
      "nullable": true
    },
    "staleness_check": {
      "type": "object",
      "properties": {
        "packet_age_seconds": { "type": "integer", "description": "Age of market_packet at evaluation time." },
        "stale": { "type": "boolean", "description": "True if packet exceeds staleness threshold." },
        "threshold_seconds": { "type": "integer", "description": "Staleness threshold used (300 general, 180 for CL elevated vol)." }
      },
      "nullable": false,
      "decision_critical": true
    },
    "challenge_state_valid": {
      "type": "boolean",
      "description": "Whether challenge_state passed completeness validation.",
      "nullable": false,
      "decision_critical": true
    }
  }
}
```

---

## 7. contract_analysis

```json
{
  "$schema": "contract_analysis_v1",
  "description": "Output of Stage B: Contract Market Read. Structured analysis of one contract.",
  "required": ["stage", "contract", "timestamp", "market_regime", "directional_bias", "key_levels", "evidence_score", "confidence_band", "value_context", "structural_notes", "outcome"],
  "properties": {
    "stage": {
      "type": "string",
      "const": "contract_market_read",
      "nullable": false
    },
    "contract": { "type": "string", "enum": ["ES", "NQ", "CL", "ZN", "6E", "MGC"], "nullable": false },
    "timestamp": { "type": "string", "format": "date-time", "nullable": false },
    "outcome": {
      "type": "string",
      "enum": ["ANALYSIS_COMPLETE", "NO_TRADE"],
      "description": "ANALYSIS_COMPLETE = read produced a usable result. NO_TRADE = read is genuinely unclear; pipeline terminates after logging.",
      "nullable": false,
      "decision_critical": true
    },
    "market_regime": {
      "type": "string",
      "enum": ["trending_up", "trending_down", "range_bound", "breakout", "breakdown", "choppy", "unclear"],
      "description": "Current session regime assessment.",
      "nullable": false,
      "decision_critical": true
    },
    "directional_bias": {
      "type": "string",
      "enum": ["bullish", "bearish", "neutral", "unclear"],
      "description": "Net directional read. 'unclear' is a valid and honest answer.",
      "nullable": false,
      "decision_critical": true
    },
    "key_levels": {
      "type": "object",
      "description": "Reference levels identified from structured data.",
      "properties": {
        "support_levels": { "type": "array", "items": { "type": "number" }, "description": "Max 3, ordered nearest to farthest." },
        "resistance_levels": { "type": "array", "items": { "type": "number" }, "description": "Max 3, ordered nearest to farthest." },
        "pivot_level": { "type": "number", "description": "Primary decision level. Nullable if none identified.", "nullable": true }
      },
      "nullable": false,
      "decision_critical": true
    },
    "evidence_score": {
      "type": "integer",
      "minimum": 1,
      "maximum": 10,
      "description": "Quality-of-evidence score. NOT a probability of trade success. 1 = very poor evidence quality. 10 = exceptional evidence quality. Measures how clear, consistent, and actionable the market picture is.",
      "nullable": false,
      "decision_critical": true
    },
    "confidence_band": {
      "type": "string",
      "enum": ["LOW", "MEDIUM", "HIGH"],
      "description": "Categorical confidence in the read. LOW = evidence_score 1-3. MEDIUM = 4-6. HIGH = 7-10. LOW forces NO_TRADE in Stage C.",
      "nullable": false,
      "decision_critical": true
    },
    "value_context": {
      "type": "object",
      "description": "Where price sits relative to value.",
      "properties": {
        "relative_to_prior_value_area": { "type": "string", "enum": ["above", "inside", "below"] },
        "relative_to_current_developing_value": { "type": "string", "enum": ["above_vah", "inside_value", "below_val"] },
        "relative_to_vwap": { "type": "string", "enum": ["above", "at", "below"] },
        "relative_to_prior_day_range": { "type": "string", "enum": ["above", "inside", "below"] }
      },
      "nullable": false,
      "decision_critical": true
    },
    "structural_notes": {
      "type": "string",
      "description": "Free-text notes on market structure, conflicts, or notable observations. Must reference specific levels from structured data.",
      "nullable": false,
      "decision_critical": false
    },
    "conflicting_signals": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Explicit list of conflicting evidence. Empty if signals are aligned.",
      "nullable": true,
      "decision_critical": false
    },
    "assumptions": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Any assumptions made during the read. E.g., 'assumed overnight high as resistance because no volume profile data at that level'.",
      "nullable": true,
      "decision_critical": false
    }
  }
}
```

**Key constraint**: `evidence_score` and `confidence_band` must be consistent. If `evidence_score` is 3 and `confidence_band` is HIGH, that is a schema violation.

---

## 8. proposed_setup

```json
{
  "$schema": "proposed_setup_v1",
  "description": "Output of Stage C: Setup Construction. A concrete trade setup or NO_TRADE decision.",
  "required": ["stage", "contract", "timestamp", "outcome"],
  "properties": {
    "stage": {
      "type": "string",
      "const": "setup_construction",
      "nullable": false
    },
    "contract": { "type": "string", "enum": ["ES", "NQ", "CL", "ZN", "6E", "MGC"], "nullable": false },
    "timestamp": { "type": "string", "format": "date-time", "nullable": false },
    "outcome": {
      "type": "string",
      "enum": ["SETUP_PROPOSED", "NO_TRADE"],
      "description": "SETUP_PROPOSED = a trade is constructible. NO_TRADE = evidence insufficient, R:R inadequate, or confidence too low.",
      "nullable": false,
      "decision_critical": true
    },
    "no_trade_reason": {
      "type": "string",
      "description": "Required if outcome = NO_TRADE. Specific reason.",
      "nullable": true,
      "decision_critical": true
    },
    "direction": {
      "type": "string",
      "enum": ["LONG", "SHORT"],
      "description": "Required if outcome = SETUP_PROPOSED.",
      "nullable": true,
      "decision_critical": true
    },
    "entry_price": { "type": "number", "nullable": true, "decision_critical": true },
    "stop_price": { "type": "number", "nullable": true, "decision_critical": true },
    "target_1": { "type": "number", "description": "Primary target. Required if SETUP_PROPOSED.", "nullable": true, "decision_critical": true },
    "target_2": { "type": "number", "description": "Secondary scale-out target. Null if position_size = 1.", "nullable": true, "decision_critical": true },
    "position_size": {
      "type": "integer",
      "description": "Number of contracts. Must be ≤ contract max_position_size.",
      "nullable": true,
      "decision_critical": true
    },
    "risk_dollars": {
      "type": "number",
      "description": "Total risk in dollars including slippage. Must be ≤ max_risk_per_trade_dollars.",
      "nullable": true,
      "decision_critical": true
    },
    "reward_risk_ratio": {
      "type": "number",
      "description": "Blended R:R using scale-out targets. Must be ≥ minimum_reward_to_risk.",
      "nullable": true,
      "decision_critical": true
    },
    "setup_class": {
      "type": "string",
      "enum": ["scalp", "intraday_swing", "session_hold"],
      "description": "Categorization for hold-time and evaluation grouping.",
      "nullable": true,
      "decision_critical": false
    },
    "hold_time_estimate_minutes": {
      "type": "integer",
      "description": "Expected hold time in minutes. Used by Stage D to check session-close risk.",
      "nullable": true,
      "decision_critical": true
    },
    "rationale": {
      "type": "string",
      "description": "Brief explanation referencing key_levels and evidence from contract_analysis.",
      "nullable": true,
      "decision_critical": false
    },
    "disqualifiers": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Factors that weaken the setup but did not trigger NO_TRADE. E.g., 'volume below average', 'conflicting delta'.",
      "nullable": true,
      "decision_critical": false
    },
    "sizing_math": {
      "type": "object",
      "description": "Transparent sizing computation for audit.",
      "properties": {
        "stop_distance_ticks": { "type": "number" },
        "risk_per_tick": { "type": "number" },
        "raw_risk_dollars": { "type": "number" },
        "slippage_cost_dollars": { "type": "number" },
        "adjusted_risk_dollars": { "type": "number" },
        "blended_target_distance_ticks": { "type": "number" },
        "blended_reward_dollars": { "type": "number" }
      },
      "nullable": true,
      "decision_critical": true
    }
  }
}
```

**Conditional requirements:**
- If `outcome` = "SETUP_PROPOSED": all fields from `direction` through `sizing_math` are required (non-null)
- If `outcome` = "NO_TRADE": only `no_trade_reason` is required; all setup fields should be null

---

## 9. risk_authorization

```json
{
  "$schema": "risk_authorization_v1",
  "description": "Output of Stage D: Risk & Challenge Authorization. Validates proposed_setup against all risk rules.",
  "required": ["stage", "contract", "timestamp", "decision", "checks"],
  "properties": {
    "stage": {
      "type": "string",
      "const": "risk_authorization",
      "nullable": false
    },
    "contract": { "type": "string", "enum": ["ES", "NQ", "CL", "ZN", "6E", "MGC"], "nullable": false },
    "timestamp": { "type": "string", "format": "date-time", "nullable": false },
    "decision": {
      "type": "string",
      "enum": ["APPROVED", "REJECTED", "REDUCED"],
      "description": "APPROVED = trade may proceed as specified. REJECTED = trade is blocked. REDUCED = position size lowered.",
      "nullable": false,
      "decision_critical": true
    },
    "checks": {
      "type": "array",
      "description": "Ordered list of all 13 risk checks with pass/fail status.",
      "items": {
        "type": "object",
        "properties": {
          "check_id": { "type": "integer" },
          "check_name": { "type": "string" },
          "passed": { "type": "boolean" },
          "detail": { "type": "string", "description": "Computation or reason for pass/fail." }
        }
      },
      "nullable": false,
      "decision_critical": true
    },
    "rejection_reasons": {
      "type": "array",
      "items": { "type": "string" },
      "description": "List of reasons if REJECTED. Empty if APPROVED.",
      "nullable": false
    },
    "adjusted_position_size": {
      "type": "integer",
      "description": "New position size if REDUCED. Null if APPROVED or REJECTED.",
      "nullable": true,
      "decision_critical": true
    },
    "adjusted_risk_dollars": {
      "type": "number",
      "description": "New risk amount if REDUCED. Null otherwise.",
      "nullable": true,
      "decision_critical": true
    },
    "remaining_daily_risk_budget": {
      "type": "number",
      "description": "How much daily loss budget remains after this trade (if approved/reduced).",
      "nullable": true,
      "decision_critical": false
    },
    "remaining_aggregate_risk_budget": {
      "type": "number",
      "description": "How much aggregate open risk budget remains after this trade.",
      "nullable": true,
      "decision_critical": false
    }
  }
}
```

---

## 10. logging_record

```json
{
  "$schema": "logging_record_v1",
  "description": "Output of Stage E: Complete decision record for every pipeline run, regardless of outcome.",
  "required": ["record_id", "contract", "pipeline_start_timestamp", "pipeline_end_timestamp", "final_decision", "termination_stage", "stages_completed"],
  "properties": {
    "record_id": {
      "type": "string",
      "description": "Unique identifier for this pipeline run. Format: {contract}_{ISO-date}_{sequence}.",
      "nullable": false
    },
    "contract": { "type": "string", "enum": ["ES", "NQ", "CL", "ZN", "6E", "MGC"], "nullable": false },
    "pipeline_start_timestamp": { "type": "string", "format": "date-time", "nullable": false },
    "pipeline_end_timestamp": { "type": "string", "format": "date-time", "nullable": false },
    "final_decision": {
      "type": "string",
      "enum": ["TRADE_APPROVED", "TRADE_REDUCED", "TRADE_REJECTED", "NO_TRADE", "INSUFFICIENT_DATA", "NEED_INPUT", "EVENT_LOCKOUT"],
      "description": "The terminal outcome of this pipeline run.",
      "nullable": false,
      "decision_critical": true
    },
    "termination_stage": {
      "type": "string",
      "enum": ["sufficiency_gate", "contract_market_read", "setup_construction", "risk_authorization"],
      "description": "Which stage produced the terminal decision.",
      "nullable": false
    },
    "stages_completed": {
      "type": "array",
      "items": { "type": "string" },
      "description": "List of stage names that completed before termination."
    },
    "sufficiency_gate_output": { "type": "object", "description": "Full Stage A output. Always present.", "nullable": false },
    "contract_analysis": { "type": "object", "description": "Full Stage B output. Null if pipeline terminated at Stage A.", "nullable": true },
    "proposed_setup": { "type": "object", "description": "Full Stage C output. Null if pipeline terminated before Stage C.", "nullable": true },
    "risk_authorization": { "type": "object", "description": "Full Stage D output. Null if pipeline terminated before Stage D.", "nullable": true },
    "challenge_state_snapshot": { "type": "object", "description": "challenge_state at time of pipeline run.", "nullable": false },
    "market_packet_snapshot": { "type": "object", "description": "market_packet that was evaluated.", "nullable": false },
    "data_quality_flags": { "type": "array", "items": { "type": "string" }, "nullable": true }
  }
}
```

---

## 11. post_trade_review_record

```json
{
  "$schema": "post_trade_review_record_v1",
  "description": "Recorded after a trade is closed. Links back to the logging_record that produced the trade.",
  "required": ["review_id", "logging_record_id", "contract", "direction", "entry_price", "exit_price", "position_size", "realized_pnl", "mae_ticks", "mfe_ticks", "hold_time_minutes", "exit_type"],
  "properties": {
    "review_id": { "type": "string", "nullable": false },
    "logging_record_id": {
      "type": "string",
      "description": "Links to the logging_record that authorized this trade.",
      "nullable": false
    },
    "contract": { "type": "string", "enum": ["ES", "NQ", "CL", "ZN", "6E", "MGC"], "nullable": false },
    "direction": { "type": "string", "enum": ["LONG", "SHORT"], "nullable": false },
    "entry_price": { "type": "number", "nullable": false },
    "exit_price": { "type": "number", "nullable": false },
    "actual_entry_slippage_ticks": { "type": "number", "description": "Actual slippage at entry vs intended entry_price.", "nullable": false },
    "actual_exit_slippage_ticks": { "type": "number", "description": "Actual slippage at exit.", "nullable": false },
    "position_size": { "type": "integer", "nullable": false },
    "realized_pnl": { "type": "number", "description": "Actual P&L in dollars after slippage and commissions.", "nullable": false },
    "mae_ticks": {
      "type": "number",
      "description": "Maximum Adverse Excursion in ticks. How far the trade went against before exit.",
      "nullable": false
    },
    "mfe_ticks": {
      "type": "number",
      "description": "Maximum Favorable Excursion in ticks. How far the trade went in favor before exit.",
      "nullable": false
    },
    "hold_time_minutes": { "type": "integer", "nullable": false },
    "exit_type": {
      "type": "string",
      "enum": ["target_1_hit", "target_2_hit", "stop_hit", "trailing_stop_hit", "time_exit", "manual_exit", "session_close_exit", "event_lockout_exit"],
      "nullable": false
    },
    "setup_class": { "type": "string", "enum": ["scalp", "intraday_swing", "session_hold"], "nullable": false },
    "scale_out_fills": {
      "type": "array",
      "description": "List of partial exit fills if scale-out occurred.",
      "items": {
        "type": "object",
        "properties": {
          "target": { "type": "string", "enum": ["target_1", "target_2"] },
          "fill_price": { "type": "number" },
          "size": { "type": "integer" },
          "pnl": { "type": "number" }
        }
      },
      "nullable": true
    },
    "planned_reward_risk_ratio": { "type": "number", "description": "R:R from proposed_setup.", "nullable": false },
    "actual_reward_risk_ratio": { "type": "number", "description": "Actual R:R achieved.", "nullable": false },
    "operator_notes": { "type": "string", "description": "Free-text operator notes post-trade.", "nullable": true }
  }
}
```

---

## Schema Consistency Rules

1. **Provenance**: Every stage output includes a `stage` field that identifies its producer.
2. **Timestamps**: Every stage output has its own `timestamp` (not inherited from the market_packet).
3. **Contract**: Every stage output includes `contract` to prevent cross-contamination.
4. **Terminology lock**: Status values use only the approved vocabulary: READY, NEED_INPUT, NO_TRADE, INSUFFICIENT_DATA, EVENT_LOCKOUT.
5. **evidence_score**: Explicitly documented as quality-of-evidence, not probability. Range 1–10. Must be consistent with confidence_band.
6. **Null discipline**: Fields marked `nullable: true` may be null. Fields marked `nullable: false` must never be null. Null in a non-nullable field is a schema violation.
7. **decision_critical vs informational**: Fields marked `decision_critical: true` are used in decision logic. Fields marked `decision_critical: false` are for logging, context, and evaluation only.

---

## Operator Acceptance Checklist (Stage 3)

- [x] Schemas are strict and consistent
- [x] Provenance exists on every stage output
- [x] Mandatory fields are obvious (required arrays + nullable flags)
- [x] Null behavior is controlled and documented
- [x] evidence_score is explicitly non-probabilistic
- [x] contract_analysis, proposed_setup, and risk_authorization are cleanly separated
- [x] Sizing math is transparent in proposed_setup
- [x] Risk checks are enumerated in risk_authorization
- [x] Logging record captures full pipeline trace including early terminations
- [x] Post-trade review links back to logging record

**Stage 3 Status: COMPLETE — Ready for Schema Defect Audit (Stage 3A).**
