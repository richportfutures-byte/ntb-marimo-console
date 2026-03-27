# Project Freeze — Marimo Operator Console

Status: **FROZEN FOR PHASE 1 SCAFFOLDING**  
Date: **2026-03-26**  
Workspace: `ntb-cli-workspace/`

## Authority Stack (Frozen)

| Priority | Authority |
|---|---|
| 1 | `README.workspace.md` |
| 2 | `docs/spec/watchman_premarket_spec.md` |
| 3 | `docs/spec/sales_pitch.md` |
| 4 | `docs/architecture/adapter_contracts.md` |
| 5 | `docs/architecture/operator_workbook.md` |

Any conflict is resolved by this order.

## Non-Negotiable Constraints

- `source/ntb_engine/` is preserved and authoritative for live pipeline behavior.
- `target/ntb_marimo_console/` is the only location for new console code (UI, adapters, state, view-models).
- `reference/ntb_v3_idea/` is reference-only and has no architectural authority.
- Fail-closed semantics are preserved: ambiguity or missing critical data must not escalate to discretionary trade behavior.
- UI must never invent market logic, projections, or synthetic trade theses.
- Pre-market language is schema-anchored and operator-verifiable.
- Query triggers are boolean predicates on explicitly named observable fields.
- Phase 1 has no manual query override path.
- No preserved engine logic modifications in this phase.

## 1) Canonical Architecture for the New Marimo Operator Console

### Layer contract

| Layer | Owner | Location | Freeze decision |
|---|---|---|---|
| Preserved Engine Runtime | Preserved | `source/ntb_engine/src/ninjatradebuilder/` | Remains the only authority for Stage A→D execution and readiness/watch context generation |
| Console Adapters | New | `target/ntb_marimo_console/src/ntb_marimo_console/adapters/` | Wrap preserved engine APIs and pre-market artifact inputs; no strategy logic |
| Console State | New | `target/ntb_marimo_console/src/ntb_marimo_console/state/` | Holds deterministic session state machine only |
| Console View Models | New | `target/ntb_marimo_console/src/ntb_marimo_console/viewmodels/` | Read-only projections for operator rendering |
| Marimo UI Surfaces | New | `target/ntb_marimo_console/src/ntb_marimo_console/ui/` | Operator surfaces for review, trigger monitoring, and explicit query actions |

### Canonical runtime flow

1. Load pre-market artifacts (`PreMarketPacket`, `PreMarketBrief`) for selected contract/date.
2. Render structural setups and query triggers exactly as schema-anchored guidance.
3. Load/refresh preserved `WatchmanReadinessContext` for current packet.
4. Evaluate query-trigger predicates against `live_observable_snapshot_v1` fields.
5. Only when predicate gate is true, allow pipeline query action.
6. Invoke preserved `run_pipeline` via adapter boundary.
7. Render Stage A/B/C/D termination and decision trace without reinterpretation.
8. Preserve Stage E audit/log semantics as engine-owned behavior; do not render Stage E audit history as a live backend in Phase 1.

## 2) Preserved Engine Responsibilities

The following responsibilities remain exclusively in the preserved engine (`source/ntb_engine`).

| Engine responsibility | Preserved authority |
|---|---|
| Stage A sufficiency gate (`READY` / `NEED_INPUT` / `INSUFFICIENT_DATA` / `EVENT_LOCKOUT`) | `pipeline.py`, `schemas/outputs.py` |
| Stage B contract-specific market read and `evidence_score`/`confidence_band` behavior | `pipeline.py`, contract prompts/assets |
| Stage C setup construction and fail-closed `NO_TRADE` behavior | `pipeline.py`, `schemas/outputs.py` |
| Stage D risk authorization (13 checks, `APPROVED`/`REDUCED`/`REJECTED`) | `pipeline.py`, `schemas/outputs.py` |
| Stage E logging/audit append semantics | `execution_facade.py`, `logging_record.py` |
| Strict schema enforcement (`extra="forbid"`, enum discipline, stage-shape invariants) | `schemas/*.py` |

### Phase 1 preserved stage scope (rendering)

| Scope item | Phase 1 freeze |
|---|---|
| Operator-rendered pipeline stages | Stage A/B/C/D only |
| Stage E audit/log semantics | Preserved in engine, not rendered from live preserved audit backend in Phase 1 |

Frozen execution entry points consumed by Phase 1 console adapters:

- `ninjatradebuilder.execution_facade.sweep_watchman`
- `ninjatradebuilder.execution_facade.run_pipeline`
- `ninjatradebuilder.execution_facade.summarize_pipeline_result`

`sweep_watchman_and_log` and `run_pipeline_and_log` remain preserved-engine capabilities but are not consumed in Phase 1 console scaffolding.

## 3) Preserved Readiness/Watch Responsibilities

Readiness/watch semantics are preserved and not re-authored in UI.

| Preserved function/model | UI treatment |
|---|---|
| `WatchmanReadinessContext` | Render-only projection |
| `hard_lockout_flags`, `awareness_flags`, `missing_inputs` | Display and gate query affordances; never rewritten |
| `trigger_context_state` + `trigger_proximity` | Display context; not used to fabricate trade direction |
| Event/session/staleness states | Display and fail-closed gating only |

Console rule: if watchman context is unavailable, invalid, or stale for selected contract, query action is disabled until resolved.

## 4) Engine Models vs UI View Models

| Engine model (preserved) | UI view-model (new in target) | Allowed transformation |
|---|---|---|
| `WatchmanReadinessContext` | `ReadinessCardVM` | Enum/value normalization for display labels only |
| `PipelineExecutionResult` | `PipelineTraceVM` | Stage rows and badges only; no decision edits |
| `RunHistoryRecord` | `RunHistoryRowVM` | Formatting timestamps/text only |
| `PreMarketBrief` (`pmkt_brief_v1`) | `PreMarketBriefVM` | Structural setup grouping + explicit field references |
| `PreMarketPacket` (`pmkt_v1`) | `PreMarketContextVM` | Display references and provenance only |
| Query trigger predicates + live snapshot | `TriggerStatusVM` | Deterministic boolean evaluation only |

View-models must be pure projections. They must not derive new trading conclusions.

## 5) Adapter Boundaries Between Pre-Market/Watch Outputs and Preserved Live Pipeline Inputs

### Frozen adapter interfaces (Phase 1)

| Interface | Location | Contract |
|---|---|---|
| `PipelineBackend` (Protocol) | `target/ntb_marimo_console/src/ntb_marimo_console/adapters/pipeline_backend.py` | `sweep_watchman(...)`, `run_pipeline(...)`, `summarize_pipeline_result(...)` |
| `PreservedEngineBackend` | `target/ntb_marimo_console/src/ntb_marimo_console/adapters/preserved_engine_backend.py` | Thin wrapper over `ninjatradebuilder.execution_facade` |
| `PreMarketArtifactStore` | `target/ntb_marimo_console/src/ntb_marimo_console/adapters/premarket_store.py` | Load `PreMarketPacket`/`PreMarketBrief` by `(contract, session_date)` |
| `TriggerEvaluator` | `target/ntb_marimo_console/src/ntb_marimo_console/adapters/trigger_evaluator.py` | Evaluate `TriggerSpec[]` predicates against `live_observable_snapshot_v1` using declared dependencies only |
| `RunHistoryStore` | `target/ntb_marimo_console/src/ntb_marimo_console/adapters/run_history_store.py` | Fixture-backed/stubbed Phase 1 history source; no preserved Stage E backend integration |

### Trigger spec dependency contract (Phase 1)

| `TriggerSpec` field | Type | Requirement |
|---|---|---|
| `id` | `str` | Required |
| `predicate` | `str` | Required boolean expression |
| `required_live_field_paths` | `list[str]` | Required; non-empty; each path must exist in `live_observable_snapshot_v1` |
| `source_brief_trigger_id` | `str` | Required mapping back to `PreMarketBrief.structural_setups[*].query_triggers[*].id` |

Freeze rules:

- Every trigger spec must declare `required_live_field_paths` explicitly.
- `TriggerEvaluator` resolves dependencies only from `required_live_field_paths`.
- `TriggerEvaluator` does not infer dependency fields from prose (`description`, `summary`, or narrative text).
- Missing/unknown required field path makes the trigger invalid and evaluates the query gate to false.

### Boundary rules

| Boundary | Inbound | Outbound | Freeze rule |
|---|---|---|---|
| A: Pre-market ingest | `PreMarketPacket`, `PreMarketBrief` | `PreMarketBriefVM`, `TriggerSpec[]` | No mutation of thesis content or field references |
| B: Watchman ingest | `WatchmanReadinessContext` | `ReadinessCardVM` | No replacement of lockout/awareness semantics |
| C: Trigger evaluation | `TriggerSpec[]` + `live_observable_snapshot_v1` | `TriggerStatusVM[]` + boolean gate | Boolean-only evaluation with explicit required field paths; no prose dependency inference; no probabilistic weighting |
| D: Pipeline invocation | `HistoricalPacket` + `contract` + `evaluation_timestamp_iso` | `PipelineExecutionResult` | Console cannot bypass Stage A/B/C/D gates |

## What the UI must never do

- Never call the pipeline with fabricated or partially inferred required fields.
- Never translate `NO_TRADE`, `NEED_INPUT`, `INSUFFICIENT_DATA`, or `EVENT_LOCKOUT` into an implicit trade suggestion.
- Never claim a trigger is met from narrative interpretation; only from explicit predicate evaluation.
- Never provide a manual override control that bypasses predicate gating in Phase 1.
- Never infer trigger dependency fields from prose; only from declared `required_live_field_paths`.
- Never alter preserved engine enum values or stage outcome semantics.
- Never hide hard lockout flags.
- Never generate contract-specific market-read logic in UI code.
- Never import architecture from `reference/ntb_v3_idea/` as runtime authority.

## 6) Marimo Session State Machine

State machine identifier: `marimo_operator_session_v1`

| State | Entry condition | Exit condition | Fail-closed behavior |
|---|---|---|---|
| `BOOTSTRAP` | App initialized | Contract/date selected | Query disabled |
| `CONTRACT_SELECTED` | Contract/date set | Pre-market artifacts load success | Query disabled |
| `PREMARKET_LOADED` | Valid brief/packet loaded | Watchman loaded | Query disabled |
| `WATCHMAN_READY` | Watchman context loaded | Live observable snapshot loaded | Query disabled if hard lockout present |
| `MONITORING` | Snapshot available, predicates false | Any predicate true | Query disabled |
| `TRIGGER_ARMED` | Predicate gate true | Operator presses Query | Query enabled |
| `QUERY_IN_FLIGHT` | Query submitted | Pipeline result returned | Single in-flight query only |
| `RESULT_READY` | Pipeline result rendered | New snapshot or new query cycle | Query disabled until next explicit arming |
| `LOCKED_OUT` | Hard lockout/elevated blocking state | Lockout resolved + refresh | Query disabled |
| `ERROR` | Schema/parsing/runtime boundary error | Manual reset/reload | Query disabled |

No `MANUAL_OVERRIDE` state or transition exists in Phase 1.

## 7) Exact Operator Surfaces

| Surface | Location (target) | Inputs | Operator action |
|---|---|---|---|
| Session/Contract Picker | `ui/surfaces/session_header.py` | contract + session date | Select active contract/date |
| Pre-Market Brief Panel | `ui/surfaces/premarket_panel.py` | `PreMarketBriefVM` | Read structural setups and warnings |
| Trigger Predicate Table | `ui/surfaces/trigger_table.py` | `TriggerStatusVM[]` | Inspect each predicate true/false with field source |
| Live Observable Panel | `ui/surfaces/live_observables.py` | `live_observable_snapshot_v1` | Validate current observable values |
| Readiness Panel | `ui/surfaces/readiness_panel.py` | `ReadinessCardVM` | Review lockout/awareness/missing context |
| Query Action Panel | `ui/surfaces/query_action.py` | trigger gate + readiness gate | Trigger explicit pipeline query |
| Pipeline Trace Panel | `ui/surfaces/pipeline_trace.py` | `PipelineTraceVM` | Review stage termination and final decision |
| Run History Panel | `ui/surfaces/run_history.py` | `RunHistoryRowVM[]` from `RunHistoryStore` | Review fixture-backed/stubbed prior runs for workflow verification |

These are the only operator surfaces in Phase 1.

Run History scope freeze: Phase 1 Run History is fixture-backed/stubbed and is not backed by preserved Stage E audit records.

## 8) Exact Live Observable Field Contract for Query Triggers

Schema name: `live_observable_snapshot_v1`

Trigger dependency authority: every `TriggerSpec` must declare required `live_observable_snapshot_v1` field paths in `required_live_field_paths`; evaluator behavior is bound to that declaration.

| Field path | Type | Required | Notes |
|---|---|---|---|
| `contract` | `"ES"|"NQ"|"CL"|"ZN"|"6E"|"MGC"` | Yes | Active contract |
| `timestamp_et` | ISO8601 string | Yes | Snapshot timestamp |
| `market.current_price` | float | Yes | Current traded price |
| `market.cumulative_delta` | float | Yes | Directional delta confirmation |
| `market.bar_5m_close` | float | Conditional | Required when trigger references 5m close acceptance/rejection |
| `market.bar_5m_close_count_at_or_beyond_level` | int | Conditional | Required when trigger uses 2+ bar acceptance |
| `cross_asset.breadth.current_advancers_pct` | float [0,1] | Conditional | ES/NQ breadth triggers |
| `cross_asset.index_cash_tone` | string enum | Conditional | ES/NQ divergence/confirmation |
| `cross_asset.dxy` | float | Conditional | 6E/MGC triggers |
| `cross_asset.cash_10y_yield` | float | Conditional | ZN/MGC triggers |
| `volatility_context.current_volume_vs_average` | float | Conditional | CL volatility gate |
| `session_sequence.asia_complete` | bool | Conditional | 6E sequence triggers |
| `session_sequence.london_complete` | bool | Conditional | 6E sequence triggers |
| `session_sequence.ny_pending` | bool | Conditional | 6E sequence triggers |
| `macro_context.macro_release_context_populated` | bool | Conditional | ZN NEED_INPUT gating |
| `macro_context.tier1_lockout_active` | bool | Yes | Event lockout visibility |
| `macro_context.eia_lockout_active` | bool | Conditional | CL EIA lockout visibility |

Predicate operators allowed: `==`, `!=`, `>`, `>=`, `<`, `<=`, `AND`, `OR`, `NOT`.

Trigger evaluator rules:

1. Every predicate token must resolve to a field path in this table.
2. Every resolved field path must also appear in `TriggerSpec.required_live_field_paths`.
3. Evaluator does not derive dependencies from prose narrative.
4. Unknown or undeclared field path = predicate invalid = query gate false.

## 9) First Vertical Slice Contract

Vertical slice ID: `vs1_es_premarket_to_query_v1`

| Step | Contract |
|---|---|
| Selected contract | `ES` only |
| Pre-market inputs | One valid `PreMarketPacket` + one valid `PreMarketBrief` (`status=READY`) |
| Live observables | Two snapshots: one with predicates false, one with predicates true |
| Readiness input | One `WatchmanReadinessContext` generated via preserved `sweep_watchman` |
| Query path | `PreservedEngineBackend.run_pipeline(...)` with preserved packet |
| Result | Render `PipelineExecutionResult` with stage trace and final decision |
| Run History source | Fixture-backed `RunHistoryStore` |
| Fail case | If predicates invalid/unresolvable, remain in `MONITORING` with query disabled |

Pass condition: operator can see exactly why query is disabled/enabled and can run one preserved-engine query without any UI-authored market logic; no manual override path exists.

## Phase 1 Scaffold Scope

Only scaffolding and deterministic integration wiring; no broad feature expansion.

### In-scope artifacts

| Artifact | Path |
|---|---|
| Adapter protocol + preserved backend wrapper | `target/ntb_marimo_console/src/ntb_marimo_console/adapters/` |
| Pre-market artifact loader (fixture-backed initially) | `target/ntb_marimo_console/src/ntb_marimo_console/adapters/` |
| Trigger evaluator against `live_observable_snapshot_v1` | `target/ntb_marimo_console/src/ntb_marimo_console/adapters/` |
| Run History fixture store (`RunHistoryStore`) | `target/ntb_marimo_console/src/ntb_marimo_console/adapters/` |
| Session state machine model | `target/ntb_marimo_console/src/ntb_marimo_console/state/` |
| View-model dataclasses and mappers | `target/ntb_marimo_console/src/ntb_marimo_console/viewmodels/` |
| Marimo surface shells for 8 frozen surfaces | `target/ntb_marimo_console/src/ntb_marimo_console/ui/` |
| Fixture and contract tests | `target/ntb_marimo_console/tests/` and `fixtures/` |

### Explicitly out of scope in scaffolding pass

- Any source edits under `source/ntb_engine/`
- Any architecture changes in preserved schemas/prompts
- Any auto-trading or order-routing behavior
- Any non-deterministic LLM generation inside console runtime
- Any manual query override, attestation workflow, or override-state path
- Any preserved Stage E audit-record ingestion backend for Run History

## 10) Acceptance Criteria

1. **Boundary discipline**: all new code lives under `target/ntb_marimo_console/`.
2. **Engine preservation**: no file changes under `source/ntb_engine/`.
3. **Fail-closed gating**: invalid/missing trigger fields keep query gate false.
4. **Schema anchoring**: each rendered setup sentence can show corresponding `fields_used` source.
5. **Predicate determinism**: trigger evaluator returns identical results for identical snapshots.
6. **State machine integrity**: illegal transitions are blocked.
7. **Trace fidelity**: Stage A/B/C/D outcomes are rendered without renaming decisions.
8. **Stage scope discipline**: Stage E audit/log semantics remain preserved-engine responsibilities and are not rendered from live preserved audit backend in Phase 1.
9. **Manual override exclusion**: no UI control or state transition bypasses trigger gating.
10. **Trigger dependency authority**: trigger evaluation uses declared `required_live_field_paths` only.
11. **Run History scope discipline**: Run History panel is sourced from fixture-backed `RunHistoryStore` in Phase 1.
12. **Operator verifiability**: UI surfaces expose lockout flags, warnings, missing inputs, and predicate statuses.

## 11) Golden Fixture Plan

Fixture root: `fixtures/golden/phase1/`

| Fixture | Purpose |
|---|---|
| `premarket/ES/2026-03-25/premarket_packet.json` | Canonical pre-market packet input |
| `premarket/ES/2026-03-25/premarket_brief.ready.json` | Canonical schema-anchored brief |
| `watchman/ES/watchman_context.ready.json` | Ready/caution watchman rendering |
| `watchman/ES/watchman_context.locked_out.json` | Lockout rendering + disabled query |
| `observables/ES/trigger_false.json` | Query gate false regression |
| `observables/ES/trigger_true.json` | Query gate true regression |
| `pipeline/ES/historical_packet.query.json` | Preserved engine query payload |
| `pipeline/ES/pipeline_result.no_trade.json` | Canonical no-trade rendering regression |
| `pipeline/ES/pipeline_result.approved.json` | Canonical approved rendering regression |
| `pipeline/ES/pipeline_result.reduced.json` | Canonical reduced rendering regression |
| `history/ES/run_history.fixture.json` | Fixture-backed Run History source for Phase 1 panel rendering |

Golden rules:

- Fixtures are append-only and versioned by explicit path.
- Fixture updates require changelog note and snapshot diff review.
- Predicate-evaluation tests must reference fixture snapshots, not ad-hoc inline objects.

## 12) Codex Execution Plan for Phase 1 Scaffolding

1. Create adapter contracts and backend wrapper modules under `target/ntb_marimo_console/src/ntb_marimo_console/adapters/`.
2. Implement pre-market fixture store and strict parser for `pmkt_v1` and `pmkt_brief_v1` structures.
3. Implement `live_observable_snapshot_v1` dataclass/schema and `TriggerEvaluator` with declared dependency enforcement (`required_live_field_paths`).
4. Implement `marimo_operator_session_v1` state machine in `state/`.
5. Implement view-model projections in `viewmodels/` (`ReadinessCardVM`, `PreMarketBriefVM`, `TriggerStatusVM`, `PipelineTraceVM`, `RunHistoryRowVM`).
6. Implement `RunHistoryStore` as fixture-backed adapter for Phase 1.
7. Implement frozen UI surfaces in `ui/surfaces/` and one assembled app shell (no manual override control).
8. Add deterministic tests for adapters, trigger evaluator, and state-machine transitions.
9. Add golden-fixture tests for ES vertical slice end-to-end.
10. Run test suite inside `target/ntb_marimo_console/` and fix only scaffold-scope failures.

## Deferred / Not In Phase 1

- Multi-contract concurrent workflow in one session (beyond ES vertical slice).
- Automated scheduler for pre-market generation.
- Live API ingestion for macro calendar/breadth/cross-asset feeds.
- Full production persistence and retrieval service for pre-market briefs.
- Manual query override flow, attestation capture, and override audit semantics.
- Preserved Stage E audit record ingestion for Run History panel.
- Prompt-generation or thesis-registry authoring UI.
- Any replacement of preserved watchman/readiness internals.
- Any migration of preserved engine schema authority into UI code.
