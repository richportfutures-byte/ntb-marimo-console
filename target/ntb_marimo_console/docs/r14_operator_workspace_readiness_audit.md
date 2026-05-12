# R14 Operator Workspace Readiness Audit

This audit classifies whether the repository is ready to begin R14 Operator Workspace Redesign after checkpoint `3489acb Audit R12 R13 trigger gate readiness`.

## Verdict

R14 Operator Workspace Redesign is justified now, with strict scope boundaries.

The repository has fixture-safe foundations for the operator workspace model, Marimo renderer, session lifecycle, decision review, audit/replay, trigger transition log, and R12/R13 pipeline query gate wiring. R14 should proceed as a UI/workspace integration and organization step only. It should not add live behavior, trading behavior, broker integration, new decision authority, or alternate query enablement.

During this audit, one narrow readiness gap was found and fixed: R14-facing workspace and renderer surfaces could mirror a raw mapping that claimed gate enablement without independently requiring real `QUERY_READY` provenance. The underlying R13 gate already enforced provenance after `3489acb`; the R14 surface guard now also refuses to display manual query as allowed unless the mapped gate has `QUERY_READY` and `trigger_state_from_real_producer=True`.

## Verified Checkpoint

- Repo path: `/Users/stu/Projects/ntb-marimo-console`
- Branch: `main`
- Starting checkpoint: `3489acb Audit R12 R13 trigger gate readiness`
- Worktree at audit start: clean

Relevant recent commits:

- `3489acb Audit R12 R13 trigger gate readiness`
- `c969e29 Audit post-R04 cleanup roadmap readiness`
- `8090fd2 Update lifecycle runtime fixture fields for observable v2`

## Surfaces Inspected

- `src/ntb_marimo_console/operator_workspace.py`
- `src/ntb_marimo_console/ui/marimo_phase1_renderer.py`
- `src/ntb_marimo_console/readiness_summary.py`
- `src/ntb_marimo_console/app.py`
- `src/ntb_marimo_console/session_lifecycle.py`
- `src/ntb_marimo_console/pipeline_query_gate.py`
- `src/ntb_marimo_console/trigger_transition_evidence.py`
- `src/ntb_marimo_console/trigger_transition_replay_source.py`
- Decision review and audit/replay tests and renderer helpers

## Current UI Capability

The current fixture-safe surfaces can expose the data R14 needs:

- current profile,
- contract,
- stream/provider/live observable status,
- quote freshness or fixture-safe equivalent,
- trigger state,
- `QUERY_READY` provenance,
- blocking reasons,
- last pipeline result or an explicit not-queried placeholder,
- audit/replay evidence status,
- trigger transition log status and schema guards,
- lifecycle/session-state propagation into runtime, workflow, lifecycle, and query-action panels.

The app shell still uses the frozen Phase 1 renderer surfaces rather than making the standalone operator workspace model the primary user experience. That is the main R14 implementation opportunity.

## Safety Model Preserved

- Query enablement remains driven by `PipelineQueryGateResult.enabled` in the app workflow.
- Display rows, shell state, `TriggerEvaluation`, and `TriggerStatusVM` do not enable the pipeline query gate.
- R14-facing workspace and renderer surfaces now fail closed when a raw mapping claims enablement without real trigger-state provenance.
- `QUERY_READY` remains query readiness only; it is not trade authorization.
- The preserved engine remains the decision authority.
- Manual execution remains the only execution path.
- No broker, order, execution, account, fill, or P&L behavior is added.

## Readiness Gaps And R14 Scope

R14 is not blocked by R12/R13 wiring after the surface-provenance guard.

R14 should focus on reorganizing and integrating existing operator information into a clearer primary workspace. It should not:

- change the trigger-state engine,
- change pipeline query gate conditions,
- infer missing live fields,
- convert fixture evidence into live proof,
- add live Schwab rehearsal behavior,
- add execution or broker behavior,
- make default launch live.

Production/live readiness remains unproven. R14 can improve operator ergonomics, but it cannot claim real Schwab session validation, real CHART_FUTURES delivery, entitlement/rollover proof, DXY/yield proxy proof, or full RTH stability proof.

## Verification

Targeted R14/UI/operator workspace and relevant gate/lifecycle tests:

```bash
PYTHONPATH=/Users/stu/Projects/ntb-marimo-console/source/ntb_engine/src:/Users/stu/Projects/ntb-marimo-console/target/ntb_marimo_console/src uv run pytest -q tests/test_operator_workspace.py tests/test_marimo_phase1_renderer.py tests/test_session_lifecycle.py tests/test_pipeline_query_gate.py tests/test_phase1_pipeline_query_gate_wiring.py tests/test_decision_review_audit.py tests/test_decision_review_replay.py tests/test_trigger_transition_replay_source.py
```

Result after the audit fix: 193 passed in 16.83s.

## Migration Decision

No migration is required before the next roadmap step. The commit counter is reset by this audit commit, and the next R14 implementation can begin from the resulting checkpoint with the R12/R13 safety model preserved.

## Hard Boundaries

- Default launch remains non-live.
- Default tests remain fixture-safe and require no Schwab credentials.
- Live behavior remains explicitly opt-in.
- No fixture fallback after live failure remains preserved.
- The 15-second minimum refresh floor remains preserved.
- Fail-closed behavior remains preserved.
- Final target universe remains ES, NQ, CL, 6E, and MGC.
- ZN and GC remain excluded final target contracts.
- MGC remains Micro Gold and is not GC.
- MGC is not mapped to GC, and GC is not mapped to MGC.
- R04 required-field enforcement remains intact.
- `source/ntb_engine` is not modified.
