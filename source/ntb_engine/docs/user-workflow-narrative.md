# NinjaTradeBuilder User Workflow Narrative

## Purpose

This document explains how a user interacts with NinjaTradeBuilder from the beginning of an evaluation through final termination.

The system is a staged decision-support engine. It is not a charting terminal and it is not an autonomous execution engine. It evaluates a contract under a strict sequence of gates and stops as soon as the correct no-go condition is reached.

## The user goal

The user wants an answer to a specific question:

- Is this market readable right now?
- If so, is there a valid setup?
- If so, is that setup authorized under the challenge rules?

The system answers those questions in order.

## Step 1: The user initiates an evaluation

The user begins by selecting one contract to evaluate:

- ES
- NQ
- CL
- ZN
- 6E
- MGC

The user or upstream system then supplies the runtime inputs required for that contract evaluation:

- evaluation timestamp
- challenge state
- contract metadata
- market packet
- contract-specific extension fields
- chart attachment metadata

At this point, the user experience is simple: choose a contract, supply the current structured market state, and request an evaluation.

## Step 2: Stage A checks whether evaluation is allowed

The system does not immediately produce a market opinion.

Instead, it first asks whether evaluation should proceed at all.

Stage A performs the sufficiency gate. It checks:

- data freshness
- challenge-state completeness
- event lockout proximity
- session hours
- required field presence
- chart attachment sufficiency
- session wind-down status

From the user’s perspective, this stage answers:

"Do I have enough trustworthy information to analyze this contract right now?"

Possible outcomes:

- `READY`
- `NEED_INPUT`
- `INSUFFICIENT_DATA`
- `EVENT_LOCKOUT`

If the result is not `READY`, the workflow stops here.

This is a feature, not a failure. The system is designed to fail closed instead of pretending to know more than it does.

## Step 3: Stage B produces the contract market read

If Stage A returns `READY`, the system proceeds to Stage B.

This is the market-read phase. The system evaluates the contract in contract-specific terms.

Examples:

- ES emphasizes value, opening type, breadth, delta, and cross-market tone
- NQ emphasizes relative strength versus ES, megacap leadership, and faster structural fragility
- CL emphasizes EIA timing, volatility regime, liquidity context, and headline sensitivity
- ZN emphasizes yields, macro release context, auctions, and post-data structure
- 6E emphasizes session sequencing, DXY, and liquidity decay after London participation fades
- MGC emphasizes DXY, yields, macro fear catalysts, and gold-specific contradiction risk

The system returns a structured `contract_analysis`.

From the user’s perspective, this stage answers:

"What kind of market is this right now, and is there enough clarity to keep going?"

Possible outcomes:

- `ANALYSIS_COMPLETE`
- `NO_TRADE`

If the outcome is `NO_TRADE`, the workflow terminates at Stage B.

The user receives a valid no-trade market read, not a forced setup.

## Step 4: Stage C converts the market read into a trade setup

If Stage B produces a usable analysis, the system proceeds to Stage C.

Stage C translates the market read into a candidate trade setup.

It determines:

- direction
- entry price
- stop price
- target 1
- optional target 2
- position size
- risk dollars
- reward-to-risk ratio
- setup class
- rationale
- sizing math

Stage C can still terminate with `NO_TRADE` if the market read cannot be converted into a valid setup under the rules.

From the user’s perspective, this stage answers:

"Given the market read, is there a concrete trade plan worth considering?"

Possible outcomes:

- `SETUP_PROPOSED`
- `NO_TRADE`

If Stage C returns `NO_TRADE`, the workflow ends here.

## Step 5: Stage D authorizes or rejects the setup

If Stage C returns a real proposed setup, the system moves to Stage D.

This is the challenge and risk authorization stage.

The system evaluates the proposed setup against all challenge controls, including:

- daily loss stop
- per-trade risk cap
- aggregate open risk
- position-size limits
- per-contract position limits
- trades-per-day limits
- event lockout re-check
- cooldown after stop-out
- opposite-direction flip restrictions
- session hours
- overnight-hold prohibition
- reward-to-risk minimum

The system returns a structured `risk_authorization` result.

From the user’s perspective, this stage answers:

"Even if the market read and setup are valid, am I actually allowed to take this trade under the rules?"

Possible outcomes:

- `APPROVED`
- `REJECTED`
- `REDUCED`

If `APPROVED`, the setup is authorized as proposed.

If `REDUCED`, the setup remains valid but must be taken at smaller size.

If `REJECTED`, the setup fails the challenge rules and must not be taken.

## Step 6: Final user-visible result

At the end of the workflow, the user receives one final termination state and one final decision.

Examples:

- terminated at Stage A because the market packet was stale
- terminated at Stage B with `NO_TRADE` because the market read was conflict-heavy
- terminated at Stage C with `NO_TRADE` because no valid setup could be formed
- terminated at Stage D with `TRADE_APPROVED`
- terminated at Stage D with `TRADE_REDUCED`
- terminated at Stage D with `TRADE_REJECTED`

This means the system is not just answering with isolated stage outputs. It is answering with a fully staged evaluation outcome.

## Why the workflow is structured this way

The order is deliberate.

The system is designed to stop as soon as a later stage is no longer justified.

That creates three benefits:

1. The user does not receive fabricated certainty when the data is weak.
2. Risk controls are applied only after a real setup exists.
3. The final output is audit-friendly because every termination point has a structured reason.

## In plain English

The workflow looks like this:

1. The user asks the system to evaluate one contract.
2. The system checks whether the data and timing are sufficient.
3. If they are, the system produces a contract-specific market read.
4. If the market read is usable, the system builds a candidate trade setup.
5. If a setup exists, the system checks whether that setup is authorized under the challenge rules.
6. The system stops immediately at the first valid no-go point or returns an authorized final decision.

## What the user should expect in practice

In normal operation, the user should expect many evaluations to end in `NO_TRADE`, `NEED_INPUT`, or `INSUFFICIENT_DATA`.

That is the intended behavior.

The system is designed to be selective, not permissive.

A run that stops early is often evidence that the workflow is behaving correctly.

## Operational summary

The user experience is best understood as a staged funnel:

- Can I evaluate this?
- Can I read this market?
- Can I form a valid setup?
- Can I authorize that setup?

Only if all four answers are favorable does the system return an executable-grade decision support output.
