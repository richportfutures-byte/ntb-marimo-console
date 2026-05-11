# Trigger State Producer Wiring Gap

Status: integration deferred
Date: 2026-05-11
Roadmap: R15

## Audit Conclusion

`SessionLifecycle` owns the explicit replay observation seam:
`SessionLifecycle.observe_trigger_state_result(...)`.

The current production runtime/app path does not yet have a safe sequential
`TriggerStateResult` producer that can call that seam. The standalone
trigger-state engine in `target/ntb_marimo_console/src/ntb_marimo_console/trigger_state.py`
creates real `TriggerStateResult` values, but `build_phase1_payload(...)` in
`target/ntb_marimo_console/src/ntb_marimo_console/app.py` still evaluates
`TriggerEvaluation` objects through `TriggerEvaluator` and immediately maps
them into `TriggerStatusVM` display rows.

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

## Missing Producer

The missing producer boundary is a production runtime step that evaluates the
loaded premarket brief plus the current live observable snapshot into
`TriggerStateResult` before any display-model conversion. That producer must
own chronological observations and pass each real result to
`SessionLifecycle.observe_trigger_state_result(...)`.

Until that boundary exists, app/runtime wiring remains deferred and
`trigger_transition_log` must stay unavailable unless tests or future runtime
code explicitly feed real sequential `TriggerStateResult` values into the
session seam.
