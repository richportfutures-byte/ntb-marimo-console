# STAGE 0: Rule Completion and Hidden Assumptions

## 1. Missing Challenge Rules

| # | Rule | Status | Recommended Default | Rationale |
|---|------|--------|-------------------|-----------|
| 1 | **Per-trade max dollar risk** | REQUIRED_TO_DEFINE | $1,450 | Operator-defined risk-per-trade for this challenge. Sized to allow meaningful position sizes across all contracts. |
| 2 | **Daily loss stop** | REQUIRED_TO_DEFINE | $10,000 | Operator-defined daily loss limit. Allows multiple full-risk trades before shutdown. |
| 3 | **Max open risk across all positions** | REQUIRED_TO_DEFINE | $40,000 | Operator-defined aggregate exposure cap. Allows large concurrent exposure across all contracts. |
| 4 | **Multiple products held simultaneously** | REQUIRED_TO_DEFINE | YES — per-contract max positions (ES:2, NQ:2, CL:2, ZN:4, 6E:4, MGC:12) | Concurrent positions allowed up to each contract's max position size. No global cap — aggregate risk rule #3 governs total exposure. |
| 5 | **Opposite-direction flips allowed immediately** | REQUIRED_TO_DEFINE | NO — must flatten first, wait for next signal cycle | Prevents revenge-trading disguised as a reversal. Forces the system to re-evaluate from scratch. |
| 6 | **Allowed trading hours by contract** | REQUIRED_TO_DEFINE | See table below | Avoids illiquid hours and aligns with each contract's primary session. |
| 7 | **Event lockout window** | REQUIRED_TO_DEFINE | 15 minutes before and 5 minutes after any scheduled Tier-1 economic release | Prevents entering into binary-event volatility. |
| 8 | **Trades held through scheduled events** | REQUIRED_TO_DEFINE | NO — must be flat before any Tier-1 event within the lockout window, or have a stop that limits risk to ≤ $725 | Protects against event-driven gap risk. Half of per-trade max risk. |
| 9 | **Slippage assumptions** | REQUIRED_TO_DEFINE | 1 tick per side for ES, NQ, ZN, 6E; 2 ticks per side for CL; 1 tick per side for MGC | Reflects realistic fill quality in simulation. CL gets wider due to spread volatility. |
| 10 | **Commission assumptions** | REQUIRED_TO_DEFINE | $0 (most sim challenges do not charge commissions) | Simplifies P&L math. If the challenge charges commissions, update this. |
| 11 | **Partial exits allowed** | REQUIRED_TO_DEFINE | YES — but only as pre-planned scale-out targets defined before entry | Allows structured profit-taking. Prevents ad-hoc exit decisions. |
| 12 | **Scale-in allowed** | REQUIRED_TO_DEFINE | NO | Adding to positions increases risk unpredictably. Not suitable for a disciplined sim challenge. |
| 13 | **Scale-out allowed** | REQUIRED_TO_DEFINE | YES — max 2 scale-out targets, defined at entry time | Structured exits improve reward capture without introducing discretionary drift. |
| 14 | **System can choose NO_TRADE all day** | REQUIRED_TO_DEFINE | YES — NO_TRADE is always a valid and preferred outcome | The system must never be forced to trade. Doing nothing is a legitimate decision. |
| 15 | **Re-entry same direction after stop-out** | REQUIRED_TO_DEFINE | YES — but only if a new independent signal cycle fires, with a 30-minute cooldown after stop-out | Prevents immediate re-entry chasing. Requires fresh evidence. |
| 16 | **Minimum reward-to-risk requirement** | REQUIRED_TO_DEFINE | 1.5:1 minimum, 2:1 preferred | Ensures positive expectancy math is achievable. Below 1.5:1 the system must return NO_TRADE. |
| 17 | **Maximum intended holding time by setup class** | RECOMMENDED_DEFAULT | Scalp: ≤ 15 min; Intraday swing: 15 min–2 hrs; Session hold: 2–4 hrs | Prevents indefinite holds that expose the account to drift and event risk. |
| 18 | **Overnight holds prohibited** | REQUIRED_TO_DEFINE | YES — all positions must be flat by session close | Eliminates overnight gap risk in a sim challenge context. |
| 19 | **Max trades per day** | RECOMMENDED_DEFAULT | 60 total across all contracts | High daily limit — overtrading is managed by per-trade risk and daily loss stop rather than trade count. |
| 20 | **Max trades per contract per day** | RECOMMENDED_DEFAULT | 3 per contract | Prevents obsessive re-engagement with one market. |
| 21 | **Trailing stop behavior** | RECOMMENDED_DEFAULT | Allowed only as a pre-defined mechanical rule (e.g., trail to breakeven after 1R achieved) | Prevents discretionary stop-widening. |

### Allowed Trading Hours by Contract

| Contract | Allowed Window (ET) | Rationale |
|----------|-------------------|-----------|
| **ES** | 9:30 AM – 3:45 PM | RTH primary session. Avoids illiquid open/close. |
| **NQ** | 9:30 AM – 3:45 PM | Same as ES — equity index. |
| **CL** | 9:00 AM – 2:15 PM | Covers pit session open through afternoon. Avoids settlement volatility. |
| **ZN** | 8:20 AM – 2:45 PM | Covers cash bond session plus post-data reaction windows. |
| **6E** | 8:00 AM – 12:00 PM (or 2:00 AM – 12:00 PM if London session included) | Best liquidity during London/NY overlap. Default to NY hours only. |
| **MGC** | 8:20 AM – 1:15 PM | Covers COMEX session. Avoids thin afternoon. |

---

## 2. Recommended Defaults Summary

All recommended defaults are listed in the table above. The key design philosophy:

- **Risk-first**: Every rule constrains risk before considering opportunity.
- **Fail-closed**: When in doubt, the default is NO_TRADE or FLAT.
- **No discretionary override**: The system cannot widen stops, add to losers, or override lockout windows.
- **Structured exits only**: Scale-out targets are set at entry, not improvised.
- **Cooldown after adversity**: 30-minute cooldown after stop-out before re-entry.

---

## 3. High-Impact Assumptions

These assumptions, if changed, would materially alter prompt architecture, risk gate behavior, sizing logic, or evaluation methodology:

### A. Assumptions that alter prompt architecture
| Assumption | Impact if changed |
|-----------|------------------|
| Multiple concurrent positions allowed | If NO → eliminates portfolio-level risk aggregation logic entirely |
| Scale-out allowed | If NO → simplifies exit logic to single-target; changes setup_construction prompt |
| Contract-specific trading hours | If uniform → contract-specific intake prompts lose session-awareness requirements |

### B. Assumptions that alter risk gate behavior
| Assumption | Impact if changed |
|-----------|------------------|
| Daily loss stop amount | Directly changes when the system shuts down for the day |
| Max open aggregate risk | Changes whether the risk gate blocks new entries when existing positions are open |
| Event lockout window duration | Changes how aggressively the system avoids scheduled data |
| Per-trade risk cap | Changes position sizing math for every contract |

### C. Assumptions that alter sizing logic
| Assumption | Impact if changed |
|-----------|------------------|
| Slippage assumptions per contract | Directly affects achievable R:R and net risk calculation |
| Commission assumptions | Changes breakeven math |
| Minimum reward-to-risk ratio | Changes which setups the system is allowed to take |

### D. Assumptions that alter evaluation methodology
| Assumption | Impact if changed |
|-----------|------------------|
| Max trades per day | Changes sample-size accumulation rate and overtrading detection thresholds |
| NO_TRADE as valid all-day outcome | If NO → evaluation must treat zero-trade days as failures rather than discipline |
| Overnight holds | If allowed → introduces gap-risk tracking and overnight P&L attribution |

---

## 4. Final Operator Decision Sheet

Fill in your decisions below. Items marked **[DEFAULT ACCEPTED]** use the recommended default. Change any you disagree with.

```
OPERATOR DECISION SHEET
========================

RISK PARAMETERS
1.  Per-trade max dollar risk:          $1,450              [OPERATOR SET]
2.  Daily loss stop:                    $10,000             [OPERATOR SET]
3.  Max open aggregate risk:            $40,000             [OPERATOR SET]
4.  Minimum reward-to-risk:             1.5:1               [DEFAULT ACCEPTED]

POSITION RULES
5.  Multiple products simultaneously:   YES, per-contract limits (ES:2, NQ:2, CL:2, ZN:4, 6E:4, MGC:12) [OPERATOR SET]
6.  Opposite-direction flip allowed:    NO                  [DEFAULT ACCEPTED]
7.  Scale-in allowed:                   NO                  [DEFAULT ACCEPTED]
8.  Scale-out allowed:                  YES, max 2 targets  [DEFAULT ACCEPTED]
9.  Partial exits allowed:              YES, pre-planned    [DEFAULT ACCEPTED]
10. Trailing stop allowed:              YES, mechanical only [DEFAULT ACCEPTED]

TRADING SESSION RULES
11. Overnight holds:                    PROHIBITED          [DEFAULT ACCEPTED]
12. ES allowed hours (ET):             9:30 AM – 3:45 PM   [DEFAULT ACCEPTED]
13. NQ allowed hours (ET):             9:30 AM – 3:45 PM   [DEFAULT ACCEPTED]
14. CL allowed hours (ET):             9:00 AM – 2:15 PM   [DEFAULT ACCEPTED]
15. ZN allowed hours (ET):             8:20 AM – 2:45 PM   [DEFAULT ACCEPTED]
16. 6E allowed hours (ET):             8:00 AM – 12:00 PM  [DEFAULT ACCEPTED]
17. MGC allowed hours (ET):            8:20 AM – 1:15 PM   [DEFAULT ACCEPTED]

EVENT RISK
18. Event lockout window:               15 min before, 5 min after Tier-1 releases [DEFAULT ACCEPTED]
19. Hold through events:                NO (or stop ≤ $725) [OPERATOR SET]

RE-ENTRY AND TRADE LIMITS
20. Re-entry after stop-out:            YES, 30-min cooldown, new signal required  [DEFAULT ACCEPTED]
21. Max trades per day (all contracts): 60                  [OPERATOR SET]
22. Max trades per contract per day:    3                   [DEFAULT ACCEPTED]
23. NO_TRADE valid all day:             YES                 [DEFAULT ACCEPTED]

EXECUTION ASSUMPTIONS
24. Slippage — ES:                      1 tick/side          [DEFAULT ACCEPTED]
25. Slippage — NQ:                      1 tick/side          [DEFAULT ACCEPTED]
26. Slippage — CL:                      2 ticks/side         [DEFAULT ACCEPTED]
27. Slippage — ZN:                      1 tick/side          [DEFAULT ACCEPTED]
28. Slippage — 6E:                      1 tick/side          [DEFAULT ACCEPTED]
29. Slippage — MGC:                     1 tick/side          [DEFAULT ACCEPTED]
30. Commissions:                        $0                   [DEFAULT ACCEPTED]

HOLDING TIME LIMITS
31. Scalp max hold:                     15 minutes           [DEFAULT ACCEPTED]
32. Intraday swing max hold:            2 hours              [DEFAULT ACCEPTED]
33. Session hold max:                   4 hours              [DEFAULT ACCEPTED]

CHALLENGE TARGETS
34. Profit target:                      $400,000             [OPERATOR SET]
35. Max trailing drawdown:              N/A                  [OPERATOR SET]
36. Trailing drawdown measurement:      N/A                  [OPERATOR SET]
```

---

## Operator Acceptance Checklist (Stage 0)

- [x] Missing rules are explicit and actionable
- [x] Recommended defaults are concrete with rationale
- [x] High-impact assumptions are separated from lower-impact ones
- [x] A usable final operator decision sheet is included
- [x] No workflow design, prompts, or schemas have been produced

**Stage 0 Status: COMPLETE — Ready for operator review and acceptance.**
