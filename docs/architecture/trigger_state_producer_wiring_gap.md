# Trigger State Producer Boundary

Status: producer boundary added; lifecycle observation wired
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

`SessionLifecycle` now observes these typed results at the lifecycle app-build
boundary. Startup, bounded-query, reload, and profile-switch builds pass
`Phase1BuildArtifacts.trigger_state_results` to
`SessionLifecycle.observe_trigger_state_result(...)` through the narrow
`observe_phase1_trigger_state_results(...)` helper. The helper accepts only real
`TriggerStateResult` values and does not read shell state, display rows,
renderer tables, pipeline summaries, or replay payloads.

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

## Runtime Boundary

`trigger_transition_log` remains unavailable until at least two real sequential
observations for the same contract/setup_id/trigger_id produce a material
transition. First observations and identical-state refreshes do not create
evidence replay.
