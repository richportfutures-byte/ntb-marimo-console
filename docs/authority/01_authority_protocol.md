# Authority Document Protocol

**Authority document set:** `docs/authority/`  
**This document:** `authority_protocol.md`  
**Generated:** 2026-03-28  
**Status:** BINDING

## What This Document Is

This is the operating manual for the authority document set. It defines how the authority documents are used in practice, what they replace, how decisions are classified, how stale documents are superseded, how backlog is derived, and how amendments are made.

After this document is accepted, "what do we want?" is no longer the working question. The only valid question is: **does this match the authority set or not?**

## Role of Each Authority Document

| Document | Role | Binding For |
|---|---|---|
| `product_authority_brief.md` | Product identity, operator profile, permanent design principles, long-run architectural north star | Product direction across all phases |
| `current_phase_scope_contract.md` | Phase definition, mandatory capabilities, exclusions, engine boundary, data truth, runtime invariants | All scope decisions for this phase |
| `support_matrix.md` | Contract status, promotion sequence, data sources, pre-market capability, parity policy | Contract-level implementation decisions |
| `acceptance_matrix.md` | Enumerated acceptance tests, manual checks, rejection criteria, failure conditions | Phase closure determination |
| `deferred_work_register.md` | Deferred items with prerequisites, rejected items with reasons, promotion gate | Scope creep prevention |
| `current_state_baseline.md` | Factual snapshot of what exists, what is confirmed not done, docs-vs-code delta | Implementation gap measurement |
| `contradiction_detection_report.md` | Structured contradiction review and testing-gap scan against the interrogation record | Authority hygiene and pre-build review |

## Canonical Source Precedence

When sources disagree, use this order:

1. `authority_protocol.md`
2. The current authority documents in `docs/authority/`
3. `contradiction_detection_report.md` for contradiction resolutions and test-gap notes
4. `ntb_interrogation_answers_review.md`
5. `project_status_report.md` for current-state evidence only
6. Legacy freeze docs, stale phase plans, vision specs, and README wording as non-authoritative background

A lower-precedence source cannot override a higher-precedence source. It can only trigger an amendment proposal.

## Principle 1: The Authority Set Is the Only Binding Source of Truth

Scope, exclusions, acceptance criteria, contract coverage, data-truth rules, runtime invariants, and failure doctrine come from the authority documents. They do not come from older planning docs, spec files, chat memory, or whatever has already been built.

**Enforcement rule:** If any developer, reviewer, or planning document claims something is in scope, out of scope, deferred, rejected, or complete, and that claim contradicts the authority set, the authority set wins. The claim must either be retracted or the authority set must be formally amended.

## Principle 2: Stale Documents Are Superseded

The following classes of documents must receive the supersession header if they contain scope, requirements, or acceptance definitions that predate the authority set:

- phase execution plans
- project freeze documents
- vision/spec documents that describe requirements as a spec
- target-console READMEs that contain scope definitions
- any document that lists "deferred" or "in scope" items without referencing the authority set

### Supersession Header

```markdown
> ⚠️ **SUPERSEDED**
> This document has been superseded by the authority document set in `docs/authority/`.
> It is retained for historical reference only.
> Binding scope, requirements, and acceptance criteria are defined in:
> - `docs/authority/current_phase_scope_contract.md`
> - `docs/authority/acceptance_matrix.md`
> Last valid date: 2026-03-28
```

After supersession, those documents are reference material only. Citing them to justify scope, acceptance, or exclusion decisions is invalid.

## Principle 3: All Work Is Classified Against the Authority Set

Every code task, review comment, feature request, and planning discussion must be classified into exactly one of these four categories:

| Category | Definition | Valid? |
|---|---|---|
| **Implements a THIS PHASE requirement** | The task directly satisfies a capability listed in `current_phase_scope_contract.md` | Yes |
| **Supports an acceptance test** | The task is necessary for a test in `acceptance_matrix.md` to pass | Yes |
| **Documents a deferred or rejected boundary** | The task records, clarifies, or enforces a boundary from `deferred_work_register.md` | Yes |
| **Out of scope** | The task touches an explicit exclusion, implements a REJECTED item, or addresses something not present in any authority document | No |

**If a task cannot be classified:** It is either missing from the authority set and needs amendment, or it is out of scope. Ambiguity is resolved by the authority set, not by developer preference.

## Principle 4: The Acceptance Matrix Is the Hard Finish Line

A build is acceptable only when all four conditions below are true:

1. Every test in `acceptance_matrix.md` passes.
2. Every manual verification item is confirmed by the operator.
3. No rejection criterion in K4 is triggered.
4. No application failure condition from the A5/J1-J5 table is present.

If any one condition fails, the phase does not close.

## Principle 5: The Deferred Register Prevents Scope Creep

Good ideas do not enter the active build because they sound useful.

- If an idea is already DEFERRED, it stays deferred until its stated prerequisite is met.
- If an idea is already REJECTED, it does not reappear under a softer name, as disabled code, or as an exploratory branch.
- If an idea is new, it must be classified through amendment before work begins.

Until classified, it is not worked on.

## Principle 6: The Current State Baseline Measures Delta

The baseline answers four questions:

1. What the code already does
2. What the docs claim, and where those claims differ from code reality
3. What still has to be built
4. What only looks real but is actually a prop, placeholder, or unverified path

Claims about completeness must be tested against the baseline. If the baseline says "requires verification" and the claimant cannot produce evidence, the claim is false.

## Principle 7: Runtime Truthfulness Outranks Smoothness

No operator-facing convenience may override truthfulness. This rule is already embedded in the phase scope and acceptance matrix, but it is restated here because it governs execution choices:

- no fake READY gate
- no partial proposal under uncertainty
- no silent fallback
- no synthetic audit evidence presented as real session history
- no smoothing over engine defects from the app surface

This principle resolves implementation disputes in favor of fail-closed behavior.

## Operational Working Loop

After the authority documents are accepted, work proceeds in this order:

```text
1. Run contradiction review against contradiction_detection_report.md
2. Confirm authority docs still reflect the interrogation state
3. Supersede stale docs
4. Compare authority to code using current_state_baseline.md
5. Produce the gap list from the baseline's confirmed-not-done table
6. Execute only classifiable work
7. Test against acceptance_matrix.md and manual verification
8. Close or fail
```

### Loop Rules

- Steps 1 through 4 are cheap and mandatory.
- Step 5 is the backlog. There is no second backlog.
- Every task entering implementation must already have a Principle 3 classification.
- Steps 7 and 8 are binary. There is no "mostly done."

## Amendment Protocol

The authority set can change under control. Every amendment must:

1. identify the document and exact section being amended
2. state the interrogation answer it traces to, or state that a new interrogation question is being asked
3. run a targeted contradiction check
4. update every affected authority document
5. update `current_state_baseline.md` if required work changes

Amendments that skip any of these steps are invalid.

## What This Protocol Replaces

Before this protocol, scope decisions were made by:

- reading planning docs that contradicted each other
- assuming the current build defined the target
- reopening settled questions in conversation
- interpreting ambiguity in favor of scope expansion

Those mechanisms are superseded. The authority set and this protocol are now the only valid scope, acceptance, and classification authority for this phase.
