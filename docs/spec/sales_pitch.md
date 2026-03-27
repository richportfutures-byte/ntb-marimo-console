This is the story of the layer being added now, working it's feature and the thesis into your sales pitch: The system already judges market structure with rigorous, contract-specific analytical depth. The opportunity is to make that same depth visible to the operator as factually-grounded, structure-pointing language — not decoration, not summaries, but direct statements that connect specific schema data points to real market conditions the operator can observe on their own screen.

The pre-market prep is the highest-leverage entry point. Before RTH, the system consumes prior-day data and generates a per-contract condition framework — not scenarios in the speculative sense, but explicitly stated structural setups: what levels matter today, what data points confirm or deny each setup, and — critically — the specific observable conditions that tell the operator it's time to query the pipeline for a live read. Each "reason to query" is derived directly from schema fields: a level touched, a delta threshold crossed, a session sequence completed, an event window cleared.

The narrative thread running through this isn't creative writing. It's the system articulating its own analytical framework in plain language — the same thesis that drives its Stage B market read, expressed as a pre-session briefing that builds the operator's structural awareness so they're not querying blind. An NQ pre-market brief sounds different from a ZN brief because the analytical frameworks are genuinely different — megacap leadership and relative strength versus macro yield context and auction proximity. That contract-specific intelligence should be audible in the language, not buried in JSON fields.

The goal: the operator reads the pre-market output and knows exactly what they're watching for, why it matters structurally, and precisely when to send updated market data for a pipeline decision. The narrative earns its place only if every sentence points at something the operator can verify on their platform right now.

The pre-market output should be grounded in actual schema data points — not hypothetical scenarios, but statements like "prior_day_high is 5604, current_session_vah is 5598, overnight_high is 5601 — price is approaching a cluster of resistance. If price accepts above 5604 (holds for 2+ bars on the execution chart with cumulative_delta positive), that confirms value migration higher and the system's Stage B read will reflect that."

Every statement needs to point at something I can actually observe — a field in the packet, a level on the chart, a timestamp, a value in the extension schema.

The contract-specific differences matter analytically, not aesthetically. ES responds to breadth and cash tone. CL responds to EIA timing and realized volatility. ZN responds to yields and auction schedule. These are the actual causal mechanisms the system operates on.

The "when to query" guidance comes directly from schema fields — specific observable conditions that map to what the system will actually consume, not guesses about what might happen.



Here's the full revised pitch with the new layer woven in:

***

# NinjaTradeBuilder — The Pitch

**Most "AI trading tools" ask a model what to do and execute whatever it says. NinjaTradeBuilder is built on the opposite premise: a staged, fail-closed, LLM-powered decision engine that treats NO_TRADE as a first-class outcome, refuses to improvise around bad data, and now — before the session even opens — tells the operator exactly what they're watching for, why it matters structurally, and precisely when to pull the trigger on a live pipeline read.**

***

## The Engine Under the Hood

NinjaTradeBuilder runs structured market data through a 5-stage sequential pipeline across six futures contracts — ES, NQ, CL, ZN, 6E, and MGC — and produces fully documented, JSON-schema-validated trade proposals. Every stage boundary enforces strict inter-stage JSON contracts. Every handoff is validated. Every output is logged, append-only, queryable by contract, date, decision, and stage.

The pipeline is deliberately adversarial against low-quality decisions:

- **Stage A (Sufficiency Gate)** validates the incoming market packet for completeness, field-level staleness (5-min max; 3-min for CL), session hours, challenge state, and Tier-1 event lockout before forming a single opinion. Missing data returns `NEED_INPUT` or `INSUFFICIENT_DATA` — never an estimate.
- **Stage B (Market Read)** produces a structured analysis with a 1–10 `evidence_score` and a confidence band. A `NO_TRADE` at this stage hard-terminates the pipeline — Stages C and D don't run.
- **Stage C (Setup Construction)** enforces iron-clad R:R minimums — 1.5:1 for HIGH confidence, 2.0:1 for MEDIUM. LOW confidence is automatic `NO_TRADE`. Conflicting signals mechanically cap `evidence_score`: two conflicts cap at 6, three cap at 4. Targets must anchor to identified key levels — no stretching for R:R.
- **Stage D (Risk Authorization)** runs 13 mandatory checks: per-trade max ($1,450), daily loss stop ($10,000), aggregate open risk cap ($40,000), per-contract position limits, 60 trades/day total, 3/day per contract, 30-min cooldown after stop-out, overnight flat enforcement, event proximity re-check. It validates only. It never re-reads the market.
- **Stage E (Logging)** appends a complete audit record for every run regardless of outcome — approved, rejected, no-trade, or lockout.

The system is calibrated to return NO_TRADE on 60–80% of evaluations. That isn't a limitation — it's the design.

***

## Six Contracts, Six Analytical Frameworks

This isn't one prompt copy-pasted six times. Each contract has its own prompt, its own required data extensions, and its own causal logic baked into the Stage B read:

- **ES** — value migration, breadth divergence, index cash tone, opening type initiative
- **NQ** — relative strength vs. ES, megacap leadership concentration, tech-sector beta amplification
- **CL** — volatility regime (compressed vs. expanded), EIA timing and reaction windows, DOM sweep dynamics, strictest sufficiency gate on the board
- **ZN** — macro-primary framing, yield context as the primary causal driver, auction schedule proximity as a hard confidence limiter
- **6E** — Asia → London → NY session sequence analysis, DXY correlation, hard block without session segmentation, thin liquidity flag after 11:00 ET
- **MGC** — DXY and yield dual-dependency, fear catalyst overlay, deterministic sizing math critical given up to 12 contracts

***

## The New Layer: Pre-Market Condition Framework

Here's where NinjaTradeBuilder crosses from decision engine into **operator development tool.**

The analytical intelligence that drives Stage B doesn't appear until the operator queries with live data. Before this layer, that meant operators were querying blind — no structural context, no awareness of what the system was actually going to evaluate, no sense of when a query was timely versus premature.

The Pre-Market Condition Framework changes that. Before RTH, the system consumes prior-day packet data and generates a per-contract structural briefing — not speculative scenarios, but explicitly stated conditions derived from named schema fields at actual values.

It sounds like this — and only like this:

> **ES — Pre-Market Brief**
> `prior_day_high` = 5,604. `previous_session_vah` = 5,598. `overnight_high` = 5,601. Price is coiling inside a 6-point resistance cluster at the top of prior value. `prior_day_close` = 5,581 relative to `previous_session_poc` = 5,589 — sellers had control into the close, price is below value. The Stage B long thesis activates only on acceptance above 5,604: two or more 5-minute bars closing above that level with `cumulative_delta` positive and `breadth` above 55% advancing. The Stage B short thesis activates on a rejection at 5,598–5,604 with `cumulative_delta` turning negative and `index_cash_tone` diverging from futures. Neither thesis is live at open — price has to declare first.
>
> **Query trigger:** Price touches 5,598 or 5,604 AND one 5-minute bar closes at or beyond that level with `cumulative_delta` directional. That's when you send the updated packet.

Every sentence points at a field. Every level has a source. The trigger condition is a direct function of schema inputs — not a guess about what might happen.

That language sounds different for ZN:

> `cash_10y_yield` prior close = 4.42. `treasury_auction_schedule` shows a 10-year auction in 2 days — `evidence_score` is capped at 6 until that auction clears, per Stage A rules. The ZN read today is macro-primary: if yield moves more than 3 basis points from 4.42 on a Tier-1 release, update `macro_release_context` with the actual print and direction vs. expectation, then query. Without that context populated, Stage A returns `NEED_INPUT`.

And different for CL:

> `eia_timing` = today. Event lockout activates 15 minutes before the release timestamp and clears 5 minutes after. Even after the lockout clears, `evidence_score` is capped at 5 for 15 minutes post-release while the post-EIA reaction settles. `realized_volatility_context` = compressed vs. `avg_20d_session_range`. A range expansion with `current_volume_vs_average` > 1.2 is the structural condition that makes a CL read worth querying for today — absent that, the compressed volatility regime will produce NO_TRADE.

The analytical frameworks *are* genuinely different — megacap leadership versus macro yield context versus volatility regime versus session sequence. That intelligence is now audible in the language before the first query, not buried in JSON output after the fact.

***

## What This Does for the Operator

The pre-market brief builds structural awareness so the operator isn't querying blind, isn't querying early, and isn't querying at random. They read the brief, they know exactly what the system is watching for on each contract, and they know the precise observable condition — a level touched, a delta threshold crossed, a session sequence completed, an event window cleared — that means: **send the updated packet now.**

The narrative earns its place only because every sentence points at something verifiable on the operator's own platform in real time. It isn't decoration. It's the system articulating its own analytical thesis in plain language — one layer upstream of the pipeline decision, in service of making that decision better when it arrives.

***

## Risk Architecture That Bites

Fail-closed at every layer: data gap → `NEED_INPUT`, unclear market → `NO_TRADE`, marginal setup → `NO_TRADE`, any of 13 risk checks fail → `REJECTED`, event proximity → `EVENT_LOCKOUT`. The risk controls are layered across data quality, event risk, session risk, evidence quality, setup quality, per-trade risk, daily risk, aggregate risk, position limits, trade frequency, cooldown, and overnight exposure. No single gate carries the load alone.

***

## Engineering Foundation

Installable Python package. Thin operator CLI. Full GitHub Actions CI suite on every push — install, test suite, deterministic smoke checks with no live Gemini dependency. Per-run JSONL audit logs. Schema layer enforces null discipline, provenance tagging, and `contract` field propagation on every stage boundary to prevent cross-contamination. The 6-stage specification was red-teamed and audited at Stages 2A, 3A, and 4A — zero unresolved contradictions at final spec.

***

**NinjaTradeBuilder gives the serious funded-challenge operator a disciplined, documented, auditable decision process across six asset classes — and now, before the open, a contract-specific structural briefing that teaches the operator to see the market the same way the system does. You still pull the trigger manually. The system makes sure you know exactly why, and exactly when.**
