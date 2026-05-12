"""Test-only helper that stubs the R13 trigger-state producer with real QUERY_READY output.

Production callers obtain TriggerStateResult values exclusively through
`ntb_marimo_console.trigger_state_result_producer.build_trigger_state_results`.
Tests that need to exercise the completed-query, audit-replay, or persisted-evidence
paths must inject a real produced QUERY_READY TriggerStateResult at the producer
boundary, never through display rows, TriggerEvaluation, TriggerStatusVM, narrative
text, replay payloads, pipeline output, shell rows, or after-the-fact snapshots.

This helper returns a single real TriggerStateResult instance keyed to the
request's contract. Callers patch `ntb_marimo_console.app.build_trigger_state_results`
with this function for the duration of the test.
"""

from __future__ import annotations

from ntb_marimo_console.trigger_state import TriggerState, TriggerStateResult


def query_ready_trigger_state_results(request: object) -> tuple[TriggerStateResult, ...]:
    contract = getattr(request, "contract", "ES")
    return (
        TriggerStateResult(
            contract=contract,
            setup_id=f"{contract.lower()}_setup_1",
            trigger_id=f"{contract.lower()}_trigger_query_ready",
            state=TriggerState.QUERY_READY,
            distance_to_trigger_ticks=0.0,
            required_fields=("market.current_price",),
            missing_fields=(),
            invalid_reasons=(),
            blocking_reasons=(),
            last_updated=getattr(request, "last_updated", None) or "2026-03-25T09:35:00-04:00",
        ),
    )
