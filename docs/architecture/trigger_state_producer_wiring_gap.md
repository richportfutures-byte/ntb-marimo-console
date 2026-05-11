# Trigger State Producer Boundary

Status: producer boundary added; lifecycle observation deferred
Date: 2026-05-11
Roadmap: R15

## Audit Conclusion

`SessionLifecycle` owns the explicit replay observation seam:
`SessionLifecycle.observe_trigger_state_result(...)`.

The production app payload now has a narrow pre-display producer boundary:
`build_trigger_state_results(...)` in
`target/ntb_marimo_console/src/ntb_marimo_console/trigger_state_result_producer.py`.
`build_phase1_payload(...)` calls it before the legacy
`TriggerEvaluation` to `TriggerStatusVM` display conversion.

## R15 Re-Audit

The current trigger display row producer remains:

1. `trigger_specs_from_brief(premarket.brief)`
2. `dependencies.trigger_evaluator.evaluate(trigger_specs, inputs.live_snapshot)`
3. `trigger_status_vm_from_eval(...)`
4. `AppShellPayload(trigger_rows=trigger_vms)`

That path produces `TriggerEvaluation` and `TriggerStatusVM` values, not
`TriggerStateResult` values. It is valid for current UI gating, but it is not a
trigger-transition evidence source.

Real `TriggerStateResult` values are now produced in the app payload from
real artifacts already available before display conversion:

- loaded premarket brief
- current live observable snapshot
- selected contract
- pipeline evaluation timestamp as `last_updated`

Quote freshness, bar state, event lockout, session lockout, and invalidator
state are passed only when the runtime already has them. Missing inputs fail
closed through the trigger-state engine instead of fabricating readiness.

The remaining integration gap is not production of a single real result. The
remaining gap is a lifecycle-owned handoff for chronological observations:
`build_phase1_payload(...)` returns typed `TriggerStateResult` values, but the
refresh/reload/query app shell path still does not pass those results to
`SessionLifecycle.observe_trigger_state_result(...)`. Until that handoff exists,
the app cannot establish a real prior/current sequence for the same
contract/setup_id/trigger_id.

## Boundary

Do not derive replay evidence from these display or summary shapes:

- `TriggerEvaluation`
- `TriggerStatusVM`
- trigger table rows
- renderer tables
- pipeline query gate results
- narrative or audit replay payloads
- final shell state or refresh snapshots

`TriggerTransitionReplaySource` may receive observations only through the
session-owned seam and only from real sequential `TriggerStateResult` values.

## Remaining Boundary

The missing boundary is now a production runtime/lifecycle handoff that passes
the typed `Phase1BuildArtifacts.trigger_state_results` sequence to
`SessionLifecycle.observe_trigger_state_result(...)` without reading shell
state, display rows, renderer tables, pipeline summaries, or replay payloads.

Until that boundary exists, lifecycle observation remains deferred and
`trigger_transition_log` must stay unavailable unless tests or future runtime
code explicitly feed real sequential `TriggerStateResult` values into the
session seam.
