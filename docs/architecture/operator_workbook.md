# LLM Futures Simulation Operator Workbook

## Purpose

This workbook is the operating version of the operator pack. It is designed to be run in sequence. Each stage has:
- objective
- prompt block
- input paste slots
- operator checklist
- accept or reject gate
- artifact storage note

Use this workbook to build a contract-aware, fail-closed, risk-gated LLM workflow for a simulated futures trading challenge.

---

## Global Build Rules

Paste this block at the top of every stage prompt.

```text
GLOBAL BUILD RULES

You are designing a disciplined LLM-driven workflow for a simulated futures trading challenge.

Non-negotiable requirements:
1. Optimize for reliability, testability, and fail-closed behavior.
2. Do not overclaim what screenshots alone can support.
3. Distinguish clearly between:
   - current-trade evidence quality
   - historical statistical validity
4. Do not use fake probabilistic precision.
5. Treat NO_TRADE and INSUFFICIENT_DATA as first-class outcomes.
6. Do not force a trade when evidence is weak, conflicting, or event risk is too near.
7. Separate contract-specific market reading from shared risk authorization.
8. Preserve architecture consistency across steps unless explicitly asked to revise it.
9. Do not rename statuses, schemas, or core terms unless a contradiction requires correction.
10. When data is missing, return the missing inputs explicitly rather than improvising.

Terminology lock:
- READY
- NEED_INPUT
- NO_TRADE
- INSUFFICIENT_DATA
- market_packet
- contract_analysis
- proposed_setup
- risk_authorization
- evidence_score
- confidence_band

Interpretation rules:
- evidence_score is a quality score, not a probability of success
- confidence_band must be LOW, MEDIUM, or HIGH
- statistical validity can only be discussed at the multi-decision evaluation layer
- contract-specific logic must reflect real differences between ES, NQ, CL, ZN, 6E, and MGC

Do not collapse architecture, prompt wording, and evaluation logic into one vague answer.
```

## Challenge Constants

Paste this block at the top of every stage prompt under the global rules.

```text
CHALLENGE CONSTANTS

Starting balance: $50,000

Allowed products and max position sizes:
- ES: max 2
- NQ: max 2
- CL: max 2
- ZN: max 4
- 6E: max 4
- MGC: max 12
```

---

## Workbook Run Order

Run stages in this order:
1. Stage 0: Rule Completion and Hidden Assumptions
2. Stage 1: Contract-by-Contract Data Sufficiency Specification
3. Stage 2: Workflow Architecture Design
4. Stage 2A: Architecture Defect Audit
5. Stage 3: JSON Schemas and Inter-Stage Contracts
6. Stage 3A: Schema Defect Audit
7. Stage 4: Production-Ready Prompt Set
8. Stage 4A: Prompt Red-Team Audit
9. Stage 5: Validation, Logging, and Evaluation Framework
10. Stage 6: Final Consolidation into One System Spec
11. Runtime Operator Packet Template

Do not skip audit stages.

---

# Stage 0: Rule Completion and Hidden Assumptions

## Objective
Define all missing challenge rules and implementation assumptions before architecture begins.

## Prompt

```text
[PASTE GLOBAL BUILD RULES]
[PASTE CHALLENGE CONSTANTS]

Your task is to identify and resolve the missing challenge rules and implementation assumptions that materially affect the design of an LLM-driven simulated futures trading workflow.

Do not design the system yet.
Do not write prompts yet.
Do not write schemas yet.

I want you to produce four sections:

1. Missing challenge rules
List every challenge rule that is still undefined but would materially affect the workflow, including but not limited to:
- per-trade max dollar risk
- daily loss stop
- max open risk across positions
- whether multiple products may be held simultaneously
- whether opposite-direction flips are allowed immediately
- allowed trading hours by contract
- event lockout windows
- whether trades can be held through scheduled events
- slippage assumptions
- commission assumptions
- whether partial exits are allowed
- whether scale-in or scale-out is allowed
- whether the system can choose NO_TRADE all day
- whether the system can re-enter in the same direction after a stop-out
- minimum reward-to-risk requirement
- maximum intended holding time by setup class
- whether overnight holds are prohibited

2. Recommended defaults
For every missing rule above, recommend a default setting suitable for a disciplined simulated challenge participant. Explain briefly why.

3. High-impact assumptions
Identify the assumptions that, if changed, would materially alter:
- prompt architecture
- risk gate behavior
- sizing logic
- evaluation methodology

4. Final operator decision sheet
Produce a clean checklist that I can fill in with final decisions before system design begins.

Output requirements:
- Be concrete
- Do not hide behind “depends”
- Mark each item as REQUIRED_TO_DEFINE or RECOMMENDED_DEFAULT
- Do not design the workflow yet
```

## Input Paste Slot

```text
<STAGE_0_INPUT>
No prior stage inputs required.
</STAGE_0_INPUT>
```

## Operator Checklist

- Missing rules are explicit and actionable
- Recommended defaults are concrete
- High-impact assumptions are separated from lower-impact ones
- A usable final operator decision sheet is included

## Accept / Reject Gate

- Accept if the output gives enough rule clarity to constrain the rest of the build
- Reject if it remains vague, hedged, or incomplete

## Artifact Storage Note

Save approved output as:
`STAGE_0_FINAL_OPERATOR_DECISIONS`

---

# Stage 1: Contract-by-Contract Data Sufficiency Specification

## Objective
Define the exact data requirements needed for defensible contract-specific market reads.

## Prompt

```text
[PASTE GLOBAL BUILD RULES]
[PASTE CHALLENGE CONSTANTS]

Use the final operator decisions below as binding constraints:

<FINAL_OPERATOR_DECISIONS>
[paste completed output from Stage 0 here]
</FINAL_OPERATOR_DECISIONS>

Your task is to design the minimum and preferred market data requirements that an LLM would need to make a defensible next-trade decision for each contract.

Important constraints:
- Do not give trading ideas.
- Do not write prompts yet.
- Do not assume screenshots alone are sufficient unless justified.
- Distinguish between mandatory, preferred, and optional inputs.
- Be explicit about what should be precomputed numerically rather than inferred visually.
- Tailor the requirements to each contract’s actual behavior and drivers.

For each contract separately, specify:
1. Required charts
2. Preferred charts
3. Required structured fields
4. Required session references
5. Required TPO / market profile inputs
6. Required volume profile inputs
7. Required order-flow inputs
8. Required volatility context
9. Required macro / event calendar context
10. Required cross-market context
11. What constitutes READY vs NEED_INPUT vs INSUFFICIENT_DATA

Then produce:
A. A contract-by-contract specification for ES, NQ, CL, ZN, 6E, and MGC
B. One normalized shared market_packet schema that all six contracts can consume
C. A list of contract-specific market_packet extensions where one normalized packet is not enough
D. A section called “What must be computed upstream”
E. A section called “What images are evidentiary only and should not be the sole source of truth”

Output requirements:
- Separate common requirements from contract-specific requirements
- Call out hidden assumptions
- Be exhaustive but operational
- Do not write prompts yet
```

## Input Paste Slot

```text
<FINAL_OPERATOR_DECISIONS>
[paste STAGE_0_FINAL_OPERATOR_DECISIONS here]
</FINAL_OPERATOR_DECISIONS>
```

## Operator Checklist

- ES includes value migration, VWAP, opening type, overnight references
- NQ includes ES relative strength and megacap context
- CL includes event timing, tape urgency, volatility, sweep/liquidity context
- ZN includes macro calendar, yield context, post-data sensitivity
- 6E includes session segmentation and DXY context
- MGC includes dollar, yield, and macro fear context
- Upstream-computed fields are separated from image-only evidence

## Accept / Reject Gate

- Accept if each contract is materially distinct and operationally specified
- Reject if any contract is treated generically

## Artifact Storage Note

Save approved output as:
`STAGE_1_DATA_SUFFICIENCY_SPEC`

---

# Stage 2: Workflow Architecture Design

## Objective
Define the exact staged workflow from market packet to final trade decision.

## Prompt

```text
[PASTE GLOBAL BUILD RULES]
[PASTE CHALLENGE CONSTANTS]

Use the final operator decisions below as binding constraints:

<FINAL_OPERATOR_DECISIONS>
[paste completed output from Stage 0 here]
</FINAL_OPERATOR_DECISIONS>

Use the market-data sufficiency specification below as the source of truth:

<DATA_SUFFICIENCY_SPEC>
[paste output from Stage 1 here]
</DATA_SUFFICIENCY_SPEC>

Your task is to design the best workflow architecture for an LLM-driven simulated futures trading challenge.

Determine whether this should be handled by one monolithic prompt or by a staged workflow.

Be candid. Do not default to “multi-agent” language unless it is functionally justified.

Design the exact sequence of stages needed to go from raw market_packet to final trade decision.

For each stage, specify:
1. Stage name
2. Purpose
3. Inputs
4. Outputs
5. What decisions are allowed at that stage
6. What that stage must never do
7. Failure behavior when data is missing or conflicting
8. Whether that stage is shared across all contracts or contract-specific

Your architecture must explicitly decide where the following belong:
- data sufficiency checking
- contract-specific market read
- setup construction
- risk and challenge authorization
- NO_TRADE decisions
- INSUFFICIENT_DATA decisions
- event lockout decisions
- logging hooks
- post-trade evaluation hooks

Also answer:
- What should be shared across all contracts
- What must differ by contract
- Whether confidence should be numeric, banded, or both
- How to avoid fake probabilistic precision
- Whether the final system should allow multiple candidate trades or only one
- Whether the runtime system should preserve prior-stage outputs verbatim or allow reinterpretation

Output requirements:
- Recommend a final staged workflow
- Justify why it is better than one-pass prompting for this use case
- Include fail-closed behavior
- Include NO_TRADE and INSUFFICIENT_DATA as first-class outcomes
- Do not write the final prompts yet
```

## Input Paste Slots

```text
<FINAL_OPERATOR_DECISIONS>
[paste STAGE_0_FINAL_OPERATOR_DECISIONS here]
</FINAL_OPERATOR_DECISIONS>

<DATA_SUFFICIENCY_SPEC>
[paste STAGE_1_DATA_SUFFICIENCY_SPEC here]
</DATA_SUFFICIENCY_SPEC>
```

## Operator Checklist

- Architecture is staged, not monolithic
- Sufficiency gate occurs before market read
- Setup construction is separate from risk authorization
- Event lockout placement is explicit
- Later stages are prevented from silently rewriting earlier logic
- NO_TRADE and INSUFFICIENT_DATA are preserved cleanly

## Accept / Reject Gate

- Accept if stage boundaries are crisp and fail-closed
- Reject if roles overlap materially or the architecture is vague

## Artifact Storage Note

Save approved output as:
`STAGE_2_WORKFLOW_ARCHITECTURE`

---

# Stage 2A: Architecture Defect Audit

## Objective
Audit the architecture before schema design.

## Prompt

```text
[PASTE GLOBAL BUILD RULES]
[PASTE CHALLENGE CONSTANTS]

You are performing a defect audit of the workflow architecture below.

Your job is not to redesign it casually.
Your job is to identify contradictions, missing controls, ambiguous stage boundaries, or places where the system is likely to hallucinate, drift, or overreach.

Use the following as inputs:

<FINAL_OPERATOR_DECISIONS>
[paste completed output from Stage 0 here]
</FINAL_OPERATOR_DECISIONS>

<DATA_SUFFICIENCY_SPEC>
[paste output from Stage 1 here]
</DATA_SUFFICIENCY_SPEC>

<WORKFLOW_ARCHITECTURE>
[paste output from Stage 2 here]
</WORKFLOW_ARCHITECTURE>

Produce five sections:

1. Critical defects
Only include issues that would materially compromise correctness or reliability.

2. Hidden ambiguities
List fields, decisions, or responsibilities that are underspecified.

3. Failure-path weaknesses
Identify where the system could fail open instead of fail closed.

4. Recommended corrections
For each defect, propose the smallest correction necessary.

5. Architecture approval verdict
Return one of:
- APPROVE_AS_IS
- APPROVE_WITH_CORRECTIONS
- REVISE_BEFORE_CONTINUING

Do not generate schemas yet.
Do not write prompts yet.
Do not replace the architecture wholesale unless it is fundamentally broken.
```

## Input Paste Slots

```text
<FINAL_OPERATOR_DECISIONS>
[paste STAGE_0_FINAL_OPERATOR_DECISIONS here]
</FINAL_OPERATOR_DECISIONS>

<DATA_SUFFICIENCY_SPEC>
[paste STAGE_1_DATA_SUFFICIENCY_SPEC here]
</DATA_SUFFICIENCY_SPEC>

<WORKFLOW_ARCHITECTURE>
[paste STAGE_2_WORKFLOW_ARCHITECTURE here]
</WORKFLOW_ARCHITECTURE>
```

## Operator Checklist

- Critical defects are real, not stylistic noise
- Failure-open risks are identified explicitly
- Corrections are minimal and targeted
- Clear verdict is returned

## Accept / Reject Gate

- If APPROVE_WITH_CORRECTIONS, apply corrections and save cleaned architecture
- If REVISE_BEFORE_CONTINUING, do not proceed to Stage 3

## Artifact Storage Note

Save approved or corrected output as:
`STAGE_2A_APPROVED_WORKFLOW_ARCHITECTURE`

---

# Stage 3: JSON Schemas and Inter-Stage Contracts

## Objective
Lock the interfaces before generating runtime prompts.

## Prompt

```text
[PASTE GLOBAL BUILD RULES]
[PASTE CHALLENGE CONSTANTS]

Use the final operator decisions below as binding constraints:

<FINAL_OPERATOR_DECISIONS>
[paste completed output from Stage 0 here]
</FINAL_OPERATOR_DECISIONS>

Use the approved workflow architecture below as the source of truth:

<APPROVED_WORKFLOW_ARCHITECTURE>
[paste approved or corrected output from Stage 2 / Stage 2A here]
</APPROVED_WORKFLOW_ARCHITECTURE>

Your task is to create the complete JSON contract for every stage of the workflow.

Requirements:
- Every stage must have a strict schema
- Every schema must support fail-closed behavior
- Every schema must support NO_TRADE or INSUFFICIENT_DATA when relevant
- Distinguish clearly between analysis outputs, setup outputs, and final execution outputs
- Do not use fake statistical language
- If you include any score, explain exactly what it means and what it does not mean
- Preserve consistent naming across schemas

At minimum, define schemas for:
1. shared market_packet
2. contract-specific market_packet extensions
3. sufficiency_gate_output
4. contract_analysis
5. proposed_setup
6. risk_authorization
7. logging_record
8. post_trade_review_record

For each schema:
- provide the JSON shape
- explain the meaning of each field
- note which fields are mandatory
- define allowed enum values where appropriate
- define which fields are informational vs decision-critical
- define which fields are allowed to be null and why

Additional requirements:
- Include contract metadata needed for sizing, such as tick size, dollar per tick, point value, and max position size
- Include risk-control fields such as per-trade risk cap, daily stop, event lockout window, and minimum acceptable reward-to-risk
- Include explicit room for missing_inputs, disqualifiers, assumptions, and data_quality_flags
- Include provenance fields so later stages can identify which stage produced the output
- Keep the schemas practical enough to implement in code

Output requirements:
- Produce clean production-usable schemas
- Explain how the schemas map to the architecture stages
- Do not write the actual prompts yet
```

## Input Paste Slots

```text
<FINAL_OPERATOR_DECISIONS>
[paste STAGE_0_FINAL_OPERATOR_DECISIONS here]
</FINAL_OPERATOR_DECISIONS>

<APPROVED_WORKFLOW_ARCHITECTURE>
[paste STAGE_2A_APPROVED_WORKFLOW_ARCHITECTURE here]
</APPROVED_WORKFLOW_ARCHITECTURE>
```

## Operator Checklist

- Schemas are strict and consistent
- Provenance exists
- Mandatory fields are obvious
- Null behavior is controlled
- evidence_score is explicitly non-probabilistic
- contract_analysis, proposed_setup, and risk_authorization are cleanly separated

## Accept / Reject Gate

- Accept if the interfaces are implementation-ready
- Reject if schema boundaries are muddy or fields encourage hallucination

## Artifact Storage Note

Save approved output as:
`STAGE_3_SCHEMA_SET`

---

# Stage 3A: Schema Defect Audit

## Objective
Audit schemas before writing prompts.

## Prompt

```text
[PASTE GLOBAL BUILD RULES]
[PASTE CHALLENGE CONSTANTS]

You are performing a schema integrity audit on the workflow interfaces below.

Your task is to identify:
- contradictions across schemas
- missing mandatory fields
- inconsistent terminology
- ambiguous null handling
- fields that encourage hallucination
- places where later stages could silently reinterpret earlier-stage outputs
- places where sizing or risk logic cannot be computed reliably

Use the following inputs:

<FINAL_OPERATOR_DECISIONS>
[paste completed output from Stage 0 here]
</FINAL_OPERATOR_DECISIONS>

<APPROVED_WORKFLOW_ARCHITECTURE>
[paste approved architecture here]
</APPROVED_WORKFLOW_ARCHITECTURE>

<SCHEMA_SET>
[paste output from Stage 3 here]
</SCHEMA_SET>

Produce four sections:
1. Critical schema defects
2. Recommended fixes
3. Safe-to-proceed verdict:
   - SAFE_TO_PROCEED
   - SAFE_TO_PROCEED_WITH_FIXES
   - DO_NOT_PROCEED
4. Cleaned schema notes

Do not write prompts yet.
```

## Input Paste Slots

```text
<FINAL_OPERATOR_DECISIONS>
[paste STAGE_0_FINAL_OPERATOR_DECISIONS here]
</FINAL_OPERATOR_DECISIONS>

<APPROVED_WORKFLOW_ARCHITECTURE>
[paste STAGE_2A_APPROVED_WORKFLOW_ARCHITECTURE here]
</APPROVED_WORKFLOW_ARCHITECTURE>

<SCHEMA_SET>
[paste STAGE_3_SCHEMA_SET here]
</SCHEMA_SET>
```

## Operator Checklist

- Contradictions are real and specific
- Recommended fixes are minimal and concrete
- Verdict is clear enough to govern progression

## Accept / Reject Gate

- If SAFE_TO_PROCEED_WITH_FIXES, apply fixes and create cleaned schema set
- If DO_NOT_PROCEED, stop before Stage 4

## Artifact Storage Note

Save approved or corrected output as:
`STAGE_3A_APPROVED_SCHEMA_SET`

---

# Stage 4: Production-Ready Prompt Set

## Objective
Generate the final runtime prompts only after architecture and schemas are stable.

## Prompt

```text
[PASTE GLOBAL BUILD RULES]
[PASTE CHALLENGE CONSTANTS]

Use the final operator decisions below as binding constraints:

<FINAL_OPERATOR_DECISIONS>
[paste completed output from Stage 0 here]
</FINAL_OPERATOR_DECISIONS>

Use the approved workflow architecture exactly as provided below.
Do not redesign it unless you identify a contradiction.
If you identify a contradiction, list it first before proposing any change.

<APPROVED_WORKFLOW_ARCHITECTURE>
[paste approved architecture here]
</APPROVED_WORKFLOW_ARCHITECTURE>

Use the approved JSON schemas exactly as provided below.
Do not rename statuses or schema objects unless a contradiction requires correction.

<APPROVED_SCHEMA_SET>
[paste approved or corrected schema set here]
</APPROVED_SCHEMA_SET>

Your task is to write the full production-ready prompt set for the simulated futures trading challenge.

I want:
1. One shared master doctrine prompt
2. One contract-specific intake / sufficiency / market-read prompt for each contract:
   - ES
   - NQ
   - CL
   - ZN
   - 6E
   - MGC
3. One shared setup-construction prompt
4. One shared risk / challenge-authorization prompt

Requirements for every prompt:
- Define role precisely
- Define required inputs
- Define allowed decisions
- Define what it must never do
- Fail closed when critical information is missing
- Treat NO_TRADE as a valid and preferred outcome when evidence is weak
- Do not fabricate order flow, levels, or event context
- Do not claim statistical certainty from a single market snapshot
- Return structured JSON only, consistent with the approved schemas
- Preserve locked terminology

Contract-specific prompts must:
- request the exact charts and fields required for that contract
- produce NEED_INPUT if the packet is incomplete
- produce a contract-specific value read and market regime read if sufficient data is present
- reflect real differences between ES, NQ, CL, ZN, 6E, and MGC

Shared prompts must:
- preserve consistency across contracts
- enforce risk discipline
- enforce challenge limits
- refuse marginal setups
- prevent downstream reinterpretation of prior-stage outputs beyond the role defined in architecture

Output requirements:
- Present each prompt in a separate copy-paste-ready block
- Label each prompt clearly
- Keep wording operational
- Do not redesign the architecture
```

## Input Paste Slots

```text
<FINAL_OPERATOR_DECISIONS>
[paste STAGE_0_FINAL_OPERATOR_DECISIONS here]
</FINAL_OPERATOR_DECISIONS>

<APPROVED_WORKFLOW_ARCHITECTURE>
[paste STAGE_2A_APPROVED_WORKFLOW_ARCHITECTURE here]
</APPROVED_WORKFLOW_ARCHITECTURE>

<APPROVED_SCHEMA_SET>
[paste STAGE_3A_APPROVED_SCHEMA_SET here]
</APPROVED_SCHEMA_SET>
```

## Operator Checklist

- Each contract prompt is genuinely distinct
- Master doctrine is concise and non-generic
- Setup prompt uses sizing metadata correctly
- Risk gate validates rather than re-trades the market
- Outputs map exactly to schemas

## Accept / Reject Gate

- Accept if prompts are production-usable and schema-aligned
- Reject if prompts drift from architecture or duplicate responsibilities

## Artifact Storage Note

Save approved output as:
`STAGE_4_PROMPT_SET`

---

# Stage 4A: Prompt Red-Team Audit

## Objective
Stress-test the prompt set before deployment.

## Prompt

```text
[PASTE GLOBAL BUILD RULES]
[PASTE CHALLENGE CONSTANTS]

You are conducting a red-team audit of the prompt set below.

Your job is to identify failure modes, prompt leakage, schema drift risk, hidden contradictions, and places where the runtime model is likely to hallucinate, overtrade, or ignore NO_TRADE conditions.

Use the following inputs:

<FINAL_OPERATOR_DECISIONS>
[paste completed output from Stage 0 here]
</FINAL_OPERATOR_DECISIONS>

<APPROVED_WORKFLOW_ARCHITECTURE>
[paste approved architecture here]
</APPROVED_WORKFLOW_ARCHITECTURE>

<APPROVED_SCHEMA_SET>
[paste approved schema set here]
</APPROVED_SCHEMA_SET>

<PROMPT_SET>
[paste output from Stage 4 here]
</PROMPT_SET>

Produce six sections:
1. Prompt-level contradictions
2. Missing safeguards
3. Overreach / hallucination risks
4. Overtrading risks
5. Contract-specific weaknesses, especially for CL, ZN, 6E, and NQ
6. Recommended wording fixes

Then return a final verdict:
- DEPLOYABLE
- DEPLOYABLE_WITH_FIXES
- REWRITE_REQUIRED

Do not rewrite the whole prompt set unless the verdict is REWRITE_REQUIRED.
```

## Input Paste Slots

```text
<FINAL_OPERATOR_DECISIONS>
[paste STAGE_0_FINAL_OPERATOR_DECISIONS here]
</FINAL_OPERATOR_DECISIONS>

<APPROVED_WORKFLOW_ARCHITECTURE>
[paste STAGE_2A_APPROVED_WORKFLOW_ARCHITECTURE here]
</APPROVED_WORKFLOW_ARCHITECTURE>

<APPROVED_SCHEMA_SET>
[paste STAGE_3A_APPROVED_SCHEMA_SET here]
</APPROVED_SCHEMA_SET>

<PROMPT_SET>
[paste STAGE_4_PROMPT_SET here]
</PROMPT_SET>
```

## Operator Checklist

- Real runtime failure modes are surfaced
- Overtrading risk is explicitly addressed
- Contract-specific weak points are identified
- Verdict is decisive

## Accept / Reject Gate

- If DEPLOYABLE_WITH_FIXES, apply only required wording corrections
- If REWRITE_REQUIRED, do not move to Stage 5 until corrected

## Artifact Storage Note

Save approved or corrected output as:
`STAGE_4A_APPROVED_PROMPT_SET`

---

# Stage 5: Validation, Logging, and Evaluation Framework

## Objective
Define how the system will be judged, audited, and paused if performance degrades.

## Prompt

```text
[PASTE GLOBAL BUILD RULES]
[PASTE CHALLENGE CONSTANTS]

Use the final operator decisions below as binding constraints:

<FINAL_OPERATOR_DECISIONS>
[paste completed output from Stage 0 here]
</FINAL_OPERATOR_DECISIONS>

Use the approved architecture, schemas, and prompt set below as the source of truth:

<APPROVED_WORKFLOW_ARCHITECTURE>
[paste approved architecture here]
</APPROVED_WORKFLOW_ARCHITECTURE>

<APPROVED_SCHEMA_SET>
[paste approved schema set here]
</APPROVED_SCHEMA_SET>

<APPROVED_PROMPT_SET>
[paste approved prompt set here]
</APPROVED_PROMPT_SET>

Your task is to design the evaluation framework for this simulated futures trading workflow.

Be explicit that prompt quality is not the same as trading edge.

I want:
1. A logging schema for every decision
2. The minimum fields required for historical replay testing
3. The minimum fields required for live-sim review
4. A methodology for measuring:
   - win rate
   - expectancy
   - average reward-to-risk actually achieved
   - MAE
   - MFE
   - hold time
   - setup-family performance
   - regime-specific performance
   - time-of-day performance
   - contract-specific performance
5. A methodology for separating:
   - data sufficiency failures
   - prompt reasoning failures
   - risk-gate failures
   - execution-quality failures
6. The minimum sample size and testing structure needed before making serious claims about reliability
7. A section called “What this system still cannot legitimately claim”
8. An operator review checklist
9. The top failure modes to watch for in CL, ZN, 6E, and NQ
10. A section called “Criteria for pausing deployment and re-auditing the system”

Output requirements:
- Make this operational enough to implement
- Distinguish clearly between one-trade evidence quality and actual statistical validity across many decisions
- Do not overstate confidence
```

## Input Paste Slots

```text
<FINAL_OPERATOR_DECISIONS>
[paste STAGE_0_FINAL_OPERATOR_DECISIONS here]
</FINAL_OPERATOR_DECISIONS>

<APPROVED_WORKFLOW_ARCHITECTURE>
[paste STAGE_2A_APPROVED_WORKFLOW_ARCHITECTURE here]
</APPROVED_WORKFLOW_ARCHITECTURE>

<APPROVED_SCHEMA_SET>
[paste STAGE_3A_APPROVED_SCHEMA_SET here]
</APPROVED_SCHEMA_SET>

<APPROVED_PROMPT_SET>
[paste STAGE_4A_APPROVED_PROMPT_SET here]
</APPROVED_PROMPT_SET>
```

## Operator Checklist

- Evidence quality is separated from statistical validity
- Failure taxonomy exists
- Pause criteria exist
- Contract-specific failure modes are explicit
- Review process is operational, not decorative

## Accept / Reject Gate

- Accept if this could be used as a real review framework
- Reject if it remains conceptual and non-operational

## Artifact Storage Note

Save approved output as:
`STAGE_5_VALIDATION_FRAMEWORK`

---

# Stage 6: Final Consolidation into One System Specification

## Objective
Create one durable reference document from the approved outputs.

## Prompt

```text
[PASTE GLOBAL BUILD RULES]
[PASTE CHALLENGE CONSTANTS]

You are consolidating the approved outputs below into one coherent system specification document.

Use the following as source of truth:

<FINAL_OPERATOR_DECISIONS>
[paste final Stage 0 output here]
</FINAL_OPERATOR_DECISIONS>

<DATA_SUFFICIENCY_SPEC>
[paste final Stage 1 output here]
</DATA_SUFFICIENCY_SPEC>

<APPROVED_WORKFLOW_ARCHITECTURE>
[paste final approved Stage 2 output here]
</APPROVED_WORKFLOW_ARCHITECTURE>

<APPROVED_SCHEMA_SET>
[paste final approved Stage 3 output here]
</APPROVED_SCHEMA_SET>

<APPROVED_PROMPT_SET>
[paste final approved Stage 4 output here]
</APPROVED_PROMPT_SET>

<VALIDATION_FRAMEWORK>
[paste final Stage 5 output here]
</VALIDATION_FRAMEWORK>

Your task:
Produce a single consolidated system specification document that is suitable for implementation review.

Required sections:
1. Objective and non-goals
2. Challenge rules and operator decisions
3. Contract-by-contract market data requirements
4. Workflow architecture
5. Inter-stage JSON contracts
6. Prompt inventory
7. Runtime decision flow
8. Risk controls
9. Logging and evaluation framework
10. Known limitations
11. Open questions
12. Implementation priorities

Output requirements:
- Preserve prior approved decisions
- Do not redesign the system
- Resolve only superficial redundancy
- Flag unresolved contradictions explicitly if any remain
```

## Input Paste Slots

```text
<FINAL_OPERATOR_DECISIONS>
[paste STAGE_0_FINAL_OPERATOR_DECISIONS here]
</FINAL_OPERATOR_DECISIONS>

<DATA_SUFFICIENCY_SPEC>
[paste STAGE_1_DATA_SUFFICIENCY_SPEC here]
</DATA_SUFFICIENCY_SPEC>

<APPROVED_WORKFLOW_ARCHITECTURE>
[paste STAGE_2A_APPROVED_WORKFLOW_ARCHITECTURE here]
</APPROVED_WORKFLOW_ARCHITECTURE>

<APPROVED_SCHEMA_SET>
[paste STAGE_3A_APPROVED_SCHEMA_SET here]
</APPROVED_SCHEMA_SET>

<APPROVED_PROMPT_SET>
[paste STAGE_4A_APPROVED_PROMPT_SET here]
</APPROVED_PROMPT_SET>

<VALIDATION_FRAMEWORK>
[paste STAGE_5_VALIDATION_FRAMEWORK here]
</VALIDATION_FRAMEWORK>
```

## Operator Checklist

- Prior approved decisions are preserved
- Contradictions are flagged, not buried
- The result is implementation-review ready

## Accept / Reject Gate

- Accept if it is cohesive and faithful to approved prior stages
- Reject if it quietly redesigns the system

## Artifact Storage Note

Save approved output as:
`STAGE_6_FINAL_SYSTEM_SPEC`

---

# Runtime Operator Packet Template

## Objective
Provide the runtime input structure for actual market decisions once the build phase is complete.

```text
RUNTIME MARKET PACKET TEMPLATE

challenge_state:
- current_balance:
- daily_realized_pnl:
- max_risk_per_trade_dollars:
- daily_loss_stop_dollars:
- minimum_reward_to_risk:
- event_lockout_minutes:
- whether_multiple_positions_allowed:
- current_open_positions:

contract_metadata:
- contract:
- tick_size:
- dollar_per_tick:
- point_value:
- max_position_size:

market_packet:
- timestamp:
- session_type:
- current_price:
- session_open:
- prior_day_high:
- prior_day_low:
- prior_day_close:
- overnight_high:
- overnight_low:
- current_session_vah:
- current_session_val:
- current_session_poc:
- previous_session_vah:
- previous_session_val:
- previous_session_poc:
- vwap:
- session_range:
- avg_20d_session_range:
- cumulative_delta:
- current_volume_vs_average:
- opening_type:
- major_higher_timeframe_levels:
- key_hvns:
- key_lvns:
- singles_excess_poor_high_low_notes:
- event_calendar_remainder:
- cross_market_context:
- data_quality_flags:

contract_specific_extension:
- ES:
  - breadth:
  - index_cash_tone:
- NQ:
  - relative_strength_vs_es:
  - megacap_leadership_table:
- CL:
  - eia_timing:
  - oil_specific_headlines:
  - liquidity_sweep_summary:
  - dom_liquidity_summary:
  - realized_volatility_context:
- ZN:
  - cash_10y_yield:
  - treasury_auction_schedule:
  - macro_release_context:
  - absorption_summary:
- 6E:
  - asia_high_low:
  - london_high_low:
  - ny_high_low_so_far:
  - dxy_context:
  - europe_initiative_status:
- MGC:
  - dxy_context:
  - yield_context:
  - swing_penetration_volume_summary:
  - macro_fear_catalyst_summary:

attached_visuals:
- daily_chart_attached: true/false
- higher_timeframe_chart_attached: true/false
- tpo_chart_attached: true/false
- volume_profile_attached: true/false
- execution_chart_attached: true/false
- footprint_chart_attached: true/false
- dom_snapshot_attached: true/false if relevant
```

---

# Cross-Stage Acceptance Checklist

## Accept a stage only if all are true

### Data sufficiency stage
- each contract has distinct required inputs
- macro/event context is explicit where necessary
- structured fields are prioritized over screenshot-only inference
- READY / NEED_INPUT / INSUFFICIENT_DATA are well-defined

### Architecture stage
- the system is staged, not monolithic
- role boundaries are explicit
- NO_TRADE and INSUFFICIENT_DATA exist as first-class outcomes
- event lockout is clearly placed
- risk authorization is separate from market read

### Schema stage
- stage outputs are not overlapping
- provenance exists
- mandatory fields are obvious
- null behavior is controlled
- risk inputs are computable

### Prompt stage
- prompts align with schemas exactly
- contract prompts are truly specific
- risk gate is not reinterpretive
- missing-data behavior is explicit
- no prompt can quietly force a trade

### Validation stage
- failure taxonomy exists
- deployment pause criteria exist
- sample-size guidance exists
- one-trade confidence is not confused with statistical reliability

---

# Optional Advanced Passes

## Adversarial Scenario Pack

```text
Use the approved prompt set and create 12 adversarial runtime scenarios that are likely to cause overtrading, hallucination, or false confidence. For each, describe the expected correct system behavior and which stage should block or downgrade the trade.
```

## Determinism Pass

```text
Review the approved prompt set and identify wording that may produce inconsistent outputs across repeated runs. Recommend wording changes that improve determinism without losing necessary nuance.
```

## Minimal Viable Implementation Map

```text
Map this system into an implementation plan with:
1. upstream feature computation layer
2. prompt orchestration layer
3. schema validation layer
4. logging layer
5. replay-testing harness
Do not redesign the trading logic. Focus on implementation sequence and interface discipline.
```

---

# Final Operator Notes

- Do not run Stage 4 before Stage 3 is stable.
- Do not let the model invent challenge rules by omission.
- Do not merge corrections and runtime prompt generation into one pass.
- Preserve approved outputs between stages so later prompts cannot silently mutate them.
- When in doubt, tighten schemas before tightening prose.
- The safest default outcome remains NO_TRADE.

