# STAGE 5: Validation, Logging, and Evaluation Framework

---

## Preamble: Prompt Quality ≠ Trading Edge

This framework must be understood with one critical distinction:

- **Prompt quality** measures whether the system reliably produces well-structured, schema-compliant, logically consistent decisions that respect all risk rules. This can be assessed from Day 1 with small samples.
- **Trading edge** measures whether the system's approved trades produce positive expectancy over a statistically meaningful sample. This requires 50–100+ trades minimum and cannot be assessed from a handful of decisions.

This evaluation framework addresses both, but never conflates them.

---

## 1. Logging Schema for Every Decision

Every pipeline run produces a `logging_record` (defined in Stage 3 schemas). This section specifies the minimum logging requirements beyond the schema.

### 1.1 What Must Be Logged

| Category | Fields | When |
|----------|--------|------|
| **Pipeline metadata** | record_id, contract, pipeline_start_timestamp, pipeline_end_timestamp, final_decision, termination_stage, stages_completed | Every run |
| **Input snapshot** | market_packet (full), contract_specific_extension, attached_visuals, challenge_state | Every run |
| **Stage A output** | sufficiency_gate_output (full JSON) | Every run |
| **Stage B output** | contract_analysis (full JSON) | Only if Stage A = READY |
| **Stage C output** | proposed_setup (full JSON) | Only if Stage B = ANALYSIS_COMPLETE |
| **Stage D output** | risk_authorization (full JSON) | Only if Stage C = SETUP_PROPOSED |
| **Data quality flags** | Aggregated from all stages | Every run |
| **Timing** | Duration of each stage in milliseconds | Every run |

### 1.2 Log Storage Requirements

- Logs must be append-only (never overwritten)
- Each log entry must be a self-contained JSON document
- Logs must be queryable by: contract, date, final_decision, termination_stage, evidence_score, confidence_band, setup_class
- Minimum retention: entire challenge duration + 30 days post-challenge

---

## 2. Minimum Fields Required for Historical Replay Testing

To replay a past decision and evaluate whether the system would produce the same output:

| Field | Purpose |
|-------|---------|
| market_packet (full) | Reproduce Stage A + B inputs |
| contract_specific_extension | Reproduce contract-specific read |
| challenge_state | Reproduce Stage C + D risk context |
| attached_visuals flags | Know which charts were available (images themselves must be archived separately) |
| all stage outputs | Compare replayed outputs to originals |
| timestamp | Ensure replay uses correct temporal context |

**Image archival**: Chart images should be saved with filenames matching record_id + stage (e.g., `ES_2025-03-21_001_daily_chart.png`). Without archived images, replay testing of Stage B is limited to structured-data-only evaluation.

---

## 3. Minimum Fields Required for Live-Sim Review

During live simulation, the operator needs a quick-review dashboard. Minimum fields per decision:

| Field | What It Shows |
|-------|---------------|
| contract | Which market |
| final_decision | TRADE_APPROVED, NO_TRADE, REJECTED, etc. |
| evidence_score + confidence_band | How strong the read was |
| directional_bias | What direction the system saw |
| entry_price, stop_price, target_1 | The proposed setup (if any) |
| risk_dollars | How much was at risk |
| reward_risk_ratio | Whether the math justified the trade |
| rejection_reasons (if any) | Why the risk gate blocked it |
| no_trade_reason (if any) | Why no setup was constructed |
| data_quality_flags | Any concerns about input quality |

---

## 4. Performance Measurement Methodology

### 4.1 Win Rate

```
win_rate = trades_with_positive_realized_pnl / total_completed_trades
```

- Count only completed trades (not open positions)
- Breakeven trades (realized_pnl = 0) count as losses
- Report separately by contract, setup_class, and market_regime_at_entry

**What this tells you**: Raw win percentage. Meaningless without expectancy context.

### 4.2 Expectancy

```
expectancy = (win_rate × avg_win_dollars) - (loss_rate × avg_loss_dollars)
```

Or equivalently:
```
expectancy = total_realized_pnl / total_completed_trades
```

- Report in dollars per trade
- Report separately by contract, setup_class, market_regime_at_entry, confidence_band_at_entry

**What this tells you**: Average P&L per trade. The single most important metric. Positive expectancy ≠ proven edge (see sample size section).

### 4.3 Average Reward-to-Risk Actually Achieved

```
actual_avg_rr = mean(actual_reward_risk_ratio) across all completed trades
```

Compare to:
```
planned_avg_rr = mean(planned_reward_risk_ratio) across all completed trades
```

**What this tells you**: Whether the system captures what it plans. If planned R:R averages 2.0 but actual averages 0.8, the system is consistently failing to reach targets. This indicates:
- Targets are too ambitious
- Stop placement is too tight (getting stopped before target)
- Market reads are directionally correct but timing is poor

### 4.4 MAE (Maximum Adverse Excursion)

```
avg_mae_ticks = mean(mae_ticks) across all completed trades
```

Report distribution (10th, 25th, 50th, 75th, 90th percentile).

**What this tells you**: How far trades go against before resolving. High MAE even on winning trades = poor entry timing. High MAE on losing trades = stops may be too wide.

### 4.5 MFE (Maximum Favorable Excursion)

```
avg_mfe_ticks = mean(mfe_ticks) across all completed trades
```

Report distribution.

**What this tells you**: How far trades go in favor before exit. If MFE is consistently much higher than actual exit distance, the system is exiting too early. If MFE ≈ actual exit on losers, the market briefly touched the direction but reversed — timing issue.

### 4.6 Hold Time

```
avg_hold_time = mean(hold_time_minutes) across all completed trades
```

Report by setup_class. Compare to planned hold_time_estimate_minutes.

**What this tells you**: Whether planned hold times are realistic. Also detects trades that overstay their expected window.

### 4.7 Setup-Family Performance

Group trades by `setup_class` (scalp, intraday_swing, session_hold) and report:
- Count, win rate, expectancy, avg actual R:R for each class

**What this tells you**: Whether certain setup types consistently outperform or underperform. If scalps have 60% win rate but negative expectancy (small wins, bigger losses), the system should avoid scalps.

### 4.8 Regime-Specific Performance

Group trades by `market_regime_at_entry` and report:
- Count, win rate, expectancy for each regime

**What this tells you**: Whether the system performs well in trending markets but fails in choppy/range-bound, or vice versa. This directly informs whether the system should increase/decrease NO_TRADE frequency in certain regimes.

### 4.9 Time-of-Day Performance

Bucket trades by entry hour (e.g., 08:00–09:00, 09:00–10:00, ...) and report:
- Count, win rate, expectancy per bucket

**What this tells you**: Whether certain hours consistently produce better/worse results. May inform tightening allowed trading windows.

### 4.10 Contract-Specific Performance

Report all metrics above per contract (ES, NQ, CL, ZN, 6E, MGC).

**What this tells you**: Whether the system is competent on some contracts and not others. If CL has 30% win rate with negative expectancy across 20+ trades, the system should be paused on CL and re-audited.

---

## 5. Failure Taxonomy

Every poor outcome must be classified into exactly one failure category. This enables targeted fixes.

### 5.1 Data Sufficiency Failures

**Definition**: The pipeline produced a trade, but the input data was later determined to be inadequate.

**Indicators**:
- data_quality_flags were present but ignored
- A required field was present but stale
- Visual evidence contradicted structured data (post-hoc review)

**Root cause**: Sufficiency gate (Stage A) was too permissive, OR data quality flags weren't acted on.

**Fix target**: Tighten Stage A rules.

### 5.2 Prompt Reasoning Failures

**Definition**: The data was sufficient, but the LLM produced a flawed market read or setup construction.

**Indicators**:
- contract_analysis.directional_bias was wrong (market went opposite)
- evidence_score was high but the trade was a clear loser
- structural_notes referenced data correctly but the conclusion was wrong
- Conflicting signals were present but evidence_score was not capped

**Root cause**: LLM reasoning error within Stage B or Stage C.

**Fix target**: Tighten prompt constraints, add more explicit decision rules, strengthen conflicting_signals → evidence_score caps.

### 5.3 Risk-Gate Failures

**Definition**: The risk gate (Stage D) should have blocked the trade but didn't, OR blocked a trade it shouldn't have.

**Indicators**:
- A check was passed that should have failed (math error)
- A check was skipped (checks_count < 13)
- challenge_state was stale or incorrect

**Root cause**: Stage D logic error or stale challenge_state.

**Fix target**: Fix Stage D check logic, improve challenge_state freshness.

### 5.4 Execution-Quality Failures

**Definition**: The system's decision was correct, but execution degraded the outcome.

**Indicators**:
- actual_entry_slippage_ticks >> assumed slippage_ticks
- Exit at a worse price than planned (slippage at stop, gap through stop)
- Hold time exceeded estimate, forcing a suboptimal exit

**Root cause**: Market microstructure, not system logic.

**Fix target**: Adjust slippage assumptions, tighten max hold times, avoid low-liquidity periods.

### 5.5 Classification Decision Tree

```
Was the input data sufficient?
  NO → Data Sufficiency Failure
  YES ↓
Was the market read reasonable given the data?
  NO → Prompt Reasoning Failure
  YES ↓
Did the risk gate function correctly?
  NO → Risk-Gate Failure
  YES ↓
Did execution match the plan?
  NO → Execution-Quality Failure
  YES → Outcome was within expected variance (not a failure — could still be a losing trade)
```

---

## 6. Minimum Sample Size and Testing Structure

### 6.1 Minimum Sample Sizes for Claims

| Claim | Minimum Sample | Confidence Level |
|-------|---------------|-----------------|
| "The system produces schema-compliant outputs" | 20 pipeline runs | High — structural validation |
| "The system respects all risk rules" | 20 APPROVED trades | High — mechanical verification |
| "The system's NO_TRADE rate is appropriate" | 50 pipeline runs | Medium — pattern observation |
| "The system has positive expectancy" | 50 completed trades | Low — directionally suggestive only |
| "The system has statistically significant positive expectancy" | 100+ completed trades | Medium — approaching meaningful |
| "The system has a reliable edge on contract X" | 30+ trades on that contract | Low — minimum viable per-contract |
| "Setup class Y outperforms class Z" | 20+ trades per class | Low — suggestive only |
| "The system works in regime X" | 15+ trades in that regime | Very low — preliminary only |

### 6.2 Testing Phases

**Phase 1: Structural Validation (Days 1–5, ~20 pipeline runs)**
- Verify schema compliance
- Verify risk gate catches all constraint violations
- Verify NO_TRADE fires appropriately
- Verify termination paths work (INSUFFICIENT_DATA, EVENT_LOCKOUT, etc.)
- No performance claims

**Phase 2: Pattern Observation (Days 5–15, ~50 pipeline runs)**
- Observe NO_TRADE frequency (target: 60–80%)
- Observe evidence_score distribution
- Observe which contracts reach Stage C vs terminate early
- Begin tracking performance metrics but make no claims
- Identify any systematic biases (always bullish, always bearish, etc.)

**Phase 3: Preliminary Performance (After 50+ completed trades)**
- Report win rate, expectancy, actual R:R by contract and setup class
- Identify worst-performing contracts or setup classes
- Apply failure taxonomy to losing trades
- Still cannot claim statistical significance

**Phase 4: Statistical Confidence (After 100+ completed trades)**
- Compute confidence intervals on expectancy
- Determine if positive expectancy is likely real or noise
- Per-contract and per-regime breakdowns become slightly more meaningful
- This is the earliest point at which the system can legitimately claim "evidence of edge"

### 6.3 The Statistical Reality

With 50 trades and a true win rate of 55%, the 95% confidence interval for the observed win rate is approximately 41%–69%. This is too wide to distinguish from 50/50. Even 100 trades narrows it only to approximately 45%–65%. Meaningful claims about trading edge require either:
- Very large sample sizes (200+ trades), OR
- Very high win rates (65%+) with favorable R:R, OR
- Extremely consistent expectancy across contracts and regimes

**The system should never claim edge from fewer than 100 completed trades.**

---

## 7. What This System Still Cannot Legitimately Claim

1. **It cannot claim to predict market direction.** It can claim to make structured, evidence-based directional assessments of varying quality.

2. **It cannot claim statistical significance from a single challenge period.** A 10-day sim challenge with 20 trades is a tiny sample.

3. **It cannot claim its evidence_score correlates with win rate** until that correlation is measured over 100+ trades and found to be statistically significant.

4. **It cannot claim regime detection is accurate** until regime labels are validated against actual market behavior post-hoc.

5. **It cannot claim CL or 6E competency** without contract-specific sample sizes of 30+ trades each.

6. **It cannot claim the NO_TRADE filter adds value** until trades that were taken are compared to a hypothetical "take everything" baseline.

7. **It cannot claim prompt improvements are genuine improvements** without A/B testing or sequential comparison with sufficient samples.

8. **It cannot claim the system is "ready for live trading."** This is a simulated challenge system. The gap between sim and live includes: real slippage, partial fills, emotional pressure, technology failures, and market impact.

---

## 8. Operator Review Checklist

### Daily Review (end of each trading day)

- [ ] Review all logging_records from today
- [ ] For each APPROVED trade: was the outcome consistent with the read? Classify any loss using the failure taxonomy.
- [ ] For each NO_TRADE: was it genuinely the right call, or did a good setup get filtered out?
- [ ] For each REJECTED: was the rejection correct? Did the risk gate catch a real violation?
- [ ] Check: did the system produce any trades on contracts where evidence was thin?
- [ ] Check: did the system respect all session-hour limits?
- [ ] Check: were all event lockouts correctly applied?
- [ ] Update challenge_state for tomorrow.

### Weekly Review (end of each trading week)

- [ ] Compute running win rate, expectancy, actual R:R (total and per-contract)
- [ ] Review NO_TRADE frequency — is it in the 60–80% range?
- [ ] Review evidence_score distribution — is the system scoring honestly or inflating?
- [ ] Review failure taxonomy distribution — which failure type is most common?
- [ ] Identify any contract that has ≥3 consecutive losses → flag for deeper review
- [ ] Review data_quality_flags — are the same flags recurring? Fix upstream data issues.
- [ ] Check for prompt reasoning drift — are later-week reads systematically different from early-week?

### Milestone Review (after Phase 3: 50+ completed trades)

- [ ] Full performance report by contract, setup class, regime, time-of-day
- [ ] Failure taxonomy breakdown with top 3 failure modes
- [ ] MAE/MFE analysis — are entries/exits well-timed?
- [ ] Hold time analysis — are planned hold times realistic?
- [ ] Comparison of planned vs actual R:R — is the system capturing what it expects?
- [ ] Decision: continue, tighten parameters, pause specific contracts, or re-audit

---

## 9. Top Failure Modes to Watch By Contract

### CL (Crude Oil)
1. **EIA gap-through-stop**: CL moves violently on inventory data. Even with EVENT_LOCKOUT, if the lockout window is miscalculated or the release is rescheduled, the system could be exposed.
2. **Slippage exceeding assumptions**: CL's 2-tick slippage assumption may be optimistic during fast markets. Monitor actual_entry_slippage_ticks and actual_exit_slippage_ticks.
3. **Volatility regime misclassification**: If realized_volatility_context says "normal" but CL is actually in a breakout, the sufficiency gate won't tighten appropriately.
4. **DOM-driven hallucination**: The model overweighting a DOM snapshot that changes seconds later.

### ZN (10-Year Treasury Note)
1. **Post-data drift**: ZN continues repositioning for 30–60 minutes after major data releases. Trading too soon after a release may catch the wrong side of the follow-through.
2. **Auction-day dampened setups**: On Treasury auction days, ZN often compresses before the auction. Technical setups may trigger but fail to follow through until after the auction results.
3. **Yield curve shift misread**: If the 2Y-10Y curve is shifting (steepening/flattening) while the 10Y yield is flat, ZN's price behavior may not match a simple yield direction read.
4. **Tick math errors**: ZN's 1/64-point ticks are error-prone. A 1/32 misinterpretation doubles the stop distance and halves the position size.

### 6E (Euro FX)
1. **Thin liquidity after 11:00 ET**: Volume drops as London closes. Setups that trigger after 11:00 are more likely to fail or slip.
2. **Session reversal whipsaws**: NY session reversals of London initiative can trigger entry, then reverse again. These whipsaws are common in 6E and not well-handled by the current framework.
3. **DXY correlation break**: If DXY moves and 6E doesn't (or vice versa), the cross-market signal is noise, not signal. The system may still trust the DXY read.
4. **ECB surprise risk**: Unscheduled ECB communications can gap 6E. No event lockout covers unscheduled events.

### NQ (E-mini Nasdaq-100)
1. **Megacap earnings gap**: A single megacap reporting after-hours can gap NQ the next morning. If the system is holding or evaluating NQ near close, this is a risk.
2. **Relative strength regime shift**: NQ can shift from leading to lagging ES intraday. A read based on early relative strength may be invalidated by midday.
3. **Higher beta stops**: NQ's higher volatility means stops need to be wider than ES for the same structure. If the system uses ES-like stop distances on NQ, stop-outs will be excessive.
4. **Semiconductor sector sensitivity**: NQ is concentrated in tech. A semiconductor-specific selloff (e.g., export ban, earnings miss) can move NQ independently of ES. The system doesn't currently track semiconductor sector tone.

---

## 10. Criteria for Pausing Deployment and Re-Auditing the System

### Immediate Pause Triggers (any one triggers pause)

| Trigger | Threshold | Action |
|---------|-----------|--------|
| Daily loss stop hit | 2 days in the same week | Pause all trading. Review failure taxonomy for those days. |
| 5 consecutive losses | Any contract, any period | Pause that contract. Review all 5 trades for common failure mode. |
| Risk gate bypass | Any trade approved that should have been rejected | Immediate full system pause. Audit Stage D logic. |
| Schema violation | Any stage output fails schema validation | Pause and fix. Do not resume until validation passes. |
| Expectancy turns negative | After 30+ trades, rolling 20-trade expectancy < -$50/trade | Pause and review. Possible prompt reasoning degradation. |
| NO_TRADE rate drops below 40% | Over any 20-pipeline-run window | System is overtrading. Tighten Stage C confidence gates. |
| Actual slippage consistently exceeds assumptions | >50% of trades with slippage > 2× assumed | Update slippage assumptions. Recalculate sizing math. |

### Scheduled Re-Audit Points

| When | What |
|------|------|
| After Phase 1 (20 runs) | Structural audit — are schemas respected? Are gates firing correctly? |
| After Phase 2 (50 runs) | Pattern audit — is NO_TRADE rate appropriate? Is evidence_score distribution reasonable? |
| After Phase 3 (50 trades) | Performance audit — is expectancy positive? Which contracts/setups are weakest? |
| After Phase 4 (100 trades) | Statistical audit — is there evidence of genuine edge? Should any contract be dropped? |
| Weekly | Operator review checklist (section 8) |

### Re-Audit Scope

When a pause is triggered, the re-audit should:
1. Classify all recent failures using the failure taxonomy
2. Identify the single most impactful failure mode
3. Propose the minimum fix (prompt wording change, schema tightening, or sufficiency gate adjustment)
4. Re-run 10 historical pipeline evaluations with the fix to verify it would have changed outcomes
5. Only resume after the fix is applied and verified

**Do not make multiple changes simultaneously.** Change one thing, measure, then change the next. Otherwise you cannot attribute improvement to any specific fix.

---

## Operator Acceptance Checklist (Stage 5)

- [x] Evidence quality is separated from statistical validity throughout
- [x] Failure taxonomy exists with 5 categories and a classification decision tree
- [x] Pause criteria exist with specific numeric thresholds
- [x] Contract-specific failure modes are explicit for CL, ZN, 6E, NQ
- [x] Review process is operational (daily, weekly, milestone checklists)
- [x] Sample size requirements are honest and conservative
- [x] "What this system cannot claim" section prevents overclaiming
- [x] Performance metrics are comprehensive (win rate, expectancy, MAE, MFE, hold time, regime, time-of-day, contract)
- [x] Logging requirements are sufficient for both replay and live review
- [x] Re-audit process is defined with single-variable change discipline

**Stage 5 Status: COMPLETE — Ready for Final Consolidation (Stage 6).**
