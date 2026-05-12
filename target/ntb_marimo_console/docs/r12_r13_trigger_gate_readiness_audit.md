# R12/R13 Trigger Gate Readiness Audit

This audit classifies the current R12 Trigger State Engine and R13 Pipeline Query Gate state after checkpoint `c969e29 Audit post-R04 cleanup roadmap readiness`.

## Verdict

R12 and R13 are accepted as fixture-safe, repository-verified foundation checkpoints after a narrow provenance hardening fix to the pipeline query gate.

The gap found during this audit was not a broad production wiring gap in the app path. The app path already produces `TriggerStateResult` values before display conversion and passes those results into the pipeline query gate. The narrow gap was at the lower-level gate boundary: a direct caller could supply a synthetic `TriggerState.QUERY_READY` or `"QUERY_READY"` value and otherwise-ready inputs. The gate now requires a real `TriggerStateResult` plus real-producer provenance before `QUERY_READY` can enable the query action.

This is not live-complete, production-proven, or broker-integrated readiness. It does not add broker, order, execution, account, fill, or P&L behavior.

## Verified Checkpoint

- Repo path: `/Users/stu/Projects/ntb-marimo-console`
- Branch: `main`
- Starting checkpoint: `c969e29 Audit post-R04 cleanup roadmap readiness`
- Worktree at audit start: clean
- Relevant implementation files inspected:
  - `src/ntb_marimo_console/trigger_state.py`
  - `src/ntb_marimo_console/trigger_state_result_producer.py`
  - `src/ntb_marimo_console/trigger_transition_evidence.py`
  - `src/ntb_marimo_console/trigger_transition_replay_source.py`
  - `src/ntb_marimo_console/pipeline_query_gate.py`
  - `src/ntb_marimo_console/app.py`
  - `src/ntb_marimo_console/session_lifecycle.py`

## Verification Performed

The exact requested test list could not run unchanged because `tests/test_trigger_transition_evidence.py` is not present in this checkout, and the trigger-state tests are present as `tests/test_trigger_state_engine.py`.

Equivalent present R12/R13 targeted suite:

```bash
PYTHONPATH=/Users/stu/Projects/ntb-marimo-console/source/ntb_engine/src:/Users/stu/Projects/ntb-marimo-console/target/ntb_marimo_console/src uv run pytest -q tests/test_trigger_state_engine.py tests/test_trigger_state_result_producer.py tests/test_trigger_transition_replay_source.py tests/test_pipeline_query_gate.py tests/test_phase1_pipeline_query_gate_wiring.py tests/test_session_lifecycle.py
```

Final result after the audit document and gate hardening change: 129 passed in 15.90s.

## R12 Classification

R12 Trigger State Engine is accepted as a fixture-safe foundation checkpoint.

- State model coverage: stable states cover `UNAVAILABLE`, `DORMANT`, `APPROACHING`, `TOUCHED`, `ARMED`, `QUERY_READY`, `INVALIDATED`, `BLOCKED`, `LOCKOUT`, `STALE`, and `ERROR`.
- Deterministic same-input behavior: same brief, snapshot, and completed bar state produce the same `TriggerStateResult` payload.
- Missing field fail-closed behavior: missing required live fields return `BLOCKED`, not `QUERY_READY`.
- Stale quote behavior: stale quote input returns `STALE`, not `QUERY_READY`.
- Event lockout behavior: event lockout returns `LOCKOUT`, not `QUERY_READY`.
- Invalidated setup behavior: active invalidators return `INVALIDATED`; reset conditions are explicit.
- Real production path: `build_trigger_state_results()` produces `TriggerStateResult` values from premarket brief, live snapshot, and optional bar/lockout/invalidator inputs.
- Replay/evidence boundary: lifecycle observation and replay source accept `TriggerStateResult` values and reject display-only inputs for lifecycle observation.

R12 remains a fixture-safe foundation. It does not prove live market-data completeness, real event lockout feeds, real symbol entitlement, or full-session behavior.

## R13 Classification

R13 Pipeline Query Gate is accepted as a fixture-safe foundation checkpoint after the narrow provenance hardening fix.

The gate requires:

- final target contract,
- runtime profile preflight,
- Watchman validator `READY`,
- fresh live snapshot or explicitly accepted fixture mode,
- fresh quote,
- fresh and available bars,
- required live fields present,
- real produced `TriggerStateResult` with state `QUERY_READY`,
- valid session,
- no event lockout,
- connected stream or explicitly accepted fixture stream.

The gate reports enabled reasons, disabled reasons, blocking reasons, and missing conditions. Query enablement is driven by `PipelineQueryGateResult.enabled` in the app workflow and query-action surface.

## Display-Object Boundary

The app path builds trigger state results before display conversion:

- `build_trigger_state_results()` creates `TriggerStateResult` values.
- `TriggerEvaluator` output is still converted to display rows, but those rows do not enable the pipeline query gate.
- `TriggerEvaluation` and `TriggerStatusVM` are rejected at the trigger-state producer and lifecycle observation boundaries.
- The gate now fails closed if `QUERY_READY` is supplied as a raw display-like string, enum, or unproven result rather than a real produced `TriggerStateResult`.

This preserves the rule that display rows, shell state, `TriggerEvaluation`, and `TriggerStatusVM` cannot enable the query gate.

## Manual Query And Authority Boundary

- `QUERY_READY` means only bounded query readiness.
- Query action remains operator-initiated.
- The preserved engine remains the decision authority.
- Pipeline query gate authorization does not authorize trades.
- No trade, broker, order, account, fill, or P&L authority is introduced.
- Manual execution remains the only execution path.

## Limitations

- No manual live rehearsal was performed.
- No real Schwab live session proof is established by this audit.
- No real CHART_FUTURES delivery proof is established by this audit.
- No real symbol entitlement, rollover, DXY, yield proxy, or full RTH stability proof is established by this audit.
- Fixture-safe R12/R13 readiness is accepted; production readiness remains unproven.

## Hard Boundaries Preserved

- Default launch remains non-live.
- Default tests remain fixture-safe.
- No fixture fallback after live failure remains preserved.
- The 15-second minimum refresh floor remains preserved.
- Fail-closed behavior remains preserved.
- Final target universe remains ES, NQ, CL, 6E, and MGC.
- ZN and GC remain excluded final target contracts.
- MGC remains Micro Gold and is not GC.
- MGC is not mapped to GC, and GC is not mapped to MGC.
- R04 required-field enforcement is not loosened.
- `source/ntb_engine` is not modified.
