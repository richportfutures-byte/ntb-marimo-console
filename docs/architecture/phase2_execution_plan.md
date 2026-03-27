# Phase 2 Execution Plan — ES Console Runtime Wiring

Status: **PROPOSED FOR IMPLEMENTATION**  
Date: **2026-03-26**  
Workspace: `ntb-cli-workspace/`

## 1) Phase 2 Direction (Chosen)

**Chosen direction:** **ES-only with preserved-engine-backed adapters first**.

### Why this is the smallest correct next step

1. It moves the accepted console beyond pure fixture-demo behavior by exercising preserved engine execution paths (`sweep_watchman`, `run_pipeline`, `summarize_pipeline_result`) for the same ES vertical slice.
2. It preserves current surface area (no new operator panels, no workflow expansion) and therefore minimizes boundary-discipline risk.
3. It isolates one variable at a time: runtime backend source (fixture -> preserved engine) before contract-space growth (ES -> multi-contract).
4. It keeps trigger contracts, state machine behavior, and UI projection rules unchanged while validating real adapter boundaries.

**Not chosen for Phase 2:** multi-contract expansion first, because it couples scope growth (contract matrix + fixtures + test permutations) with backend migration and increases the chance of boundary regressions.

## 2) Exact Phase 2 Objective

Upgrade the accepted `vs1_es_premarket_to_query_v1` path from **fixture-backed backend simulation** to **preserved-engine-backed runtime invocation** for ES, while keeping all Phase 1 freeze constraints intact:

- ES-only scope remains.
- Same 8 frozen surfaces remain.
- No manual override path.
- No UI-authored market logic.
- Run History remains fixture-backed.
- Live-backed Stage E behavior remains deferred.

## 3) In Scope / Out of Scope

### In Scope (Phase 2)

- Add a single local ES launch path that wires `PreservedEngineBackend` into the existing app assembly.
- Keep pre-market packet/brief input source fixture-backed for this phase.
- Keep run history source fixture-backed (`RunHistoryStore`) for this phase.
- Add a bounded backend-selection seam so both modes exist:
  - `fixture_demo` (existing deterministic demo)
  - `preserved_engine_es` (new Phase 2 path)
- Require explicit mode selection for preserved mode; no implicit fallback from `preserved_engine_es` to `fixture_demo`.
- Add runtime guardrails for missing engine dependencies/model adapter configuration that fail closed and preserve query-disable behavior.
- Add tests proving Phase 2 path still obeys trigger gating, lockout handling, Stage A/B/C/D rendering discipline, and ES-only contract guard.

### Out of Scope (Phase 2)

- Any multi-contract support beyond ES.
- Any new UI surfaces, tabs, or workflows.
- Any manual override control/state transition.
- Any market logic in UI/view-model layers.
- Any edits under `source/ntb_engine/`.
- Any live-backed Stage E run-history/audit ingestion.
- Any scheduler, persistence service, or live feed ingestion work.

## 4) Adapter Changes Required

Phase 2 changes are constrained to `target/ntb_marimo_console/`.

1. **Backend construction seam**
   - Introduce a small builder/factory in console code that returns `PipelineBackend` by mode.
   - Modes:
     - fixture mode -> `FixturePipelineBackend` (existing)
     - preserved mode -> `PreservedEngineBackend`
   - `preserved_engine_es` initialization failure must be terminal for that run (no automatic mode downgrade).

2. **Model adapter injection boundary**
   - Add explicit configuration contract for `PreservedEngineBackend(model_adapter=...)` creation.
   - The injected object must satisfy preserved structured-generation adapter behavior (`generate_structured(...)`) required by `execution_facade.run_pipeline`.
   - Console code does not construct provider SDK clients directly; model adapter object is injected at launch boundary.
   - If model adapter is unavailable/invalid, fail closed before query execution path.

3. **No contract-interface broadening**
   - Keep current `PipelineBackend` protocol unchanged for Phase 2.
   - Keep `PreMarketArtifactStore` and `RunHistoryStore` contracts unchanged.

4. **Launch module separation**
   - Keep `demo_fixture_app.py` as deterministic reference path.
   - Add `src/ntb_marimo_console/preserved_engine_es_app.py` as the only preserved-engine ES launch module (explicit non-demo labeling).

## 5) Preserved-Engine Touch Points

Phase 2 is allowed to consume (already frozen in Phase 1 architecture):

- `ninjatradebuilder.execution_facade.sweep_watchman`
- `ninjatradebuilder.execution_facade.run_pipeline`
- `ninjatradebuilder.execution_facade.summarize_pipeline_result`

Touch-point rules:

- Console app/UI modules do not call `execution_facade` directly; calls are routed through `PreservedEngineBackend` only.
- Explicitly forbidden in Phase 2: `sweep_watchman_and_log`, `run_pipeline_and_log`, `run_readiness_for_contract`.

**No preserved-engine source edits are allowed.**

## 6) Stage E Decision for Phase 2

**Stage E live-backed behavior remains deferred in Phase 2.**

Rationale:
- Smallest bounded step is backend invocation for watchman + pipeline trace while keeping run history fixture-backed.
- Introducing live Stage E ingestion would add persistence/backfill, schema and operational coupling beyond the minimum required transition from demo mode.

## 7) Risks to Boundary Discipline

1. **UI logic creep risk**
   - Risk: backend differences tempt UI-side normalization/business logic.
   - Control: all normalization remains in adapters/mappers; UI remains projection-only.

2. **Hidden fallback risk**
   - Risk: silent fallback from preserved backend to fixture behavior can mask integration failures.
   - Control: explicit mode selection + startup validation + clear error state on invalid preserved backend wiring.

3. **Scope creep to multi-contract risk**
   - Risk: touching preserved backend may invite adding NQ/CL/ZN/6E/MGC prematurely.
   - Control: enforce ES-only guard at app context and tests.

4. **Stage E bleed-through risk**
   - Risk: preserved logging APIs (`*_and_log`) get pulled in opportunistically.
   - Control: Phase 2 forbids `sweep_watchman_and_log` / `run_pipeline_and_log` usage.

## 8) Acceptance Criteria (Phase 2)

1. Console retains the same 8 frozen surfaces; no new operator surfaces.
2. ES-only contract guard remains enforced in runtime path.
3. Preserved-engine routing is test-verified: `PreservedEngineBackend` delegates only to `sweep_watchman`, `run_pipeline`, and `summarize_pipeline_result`.
4. No implicit fallback exists: if `preserved_engine_es` cannot initialize, app startup fails closed for that mode and does not switch to `fixture_demo`.
5. Trigger gating remains fail-closed with declared dependency authority unchanged.
6. Lockout behavior still disables query action without manual override path.
7. Stage A/B/C/D trace rendering remains faithful to preserved summary; no renamed decisions.
8. Run History panel remains fixture-backed `RunHistoryStore` (not live Stage E backend).
9. Stage E live-backed ingestion is absent from runtime and docs for Phase 2, and `_and_log` entry points are not consumed.
10. No manual override control/state transition exists.
11. All new/changed code remains under `target/ntb_marimo_console/`.
12. No files under `source/ntb_engine/` are modified.

## 9) Test Plan (Phase 2)

### Unit / Contract Tests

- Backend factory tests:
  - returns fixture backend for demo mode
  - returns preserved backend for preserved mode
  - fails closed on missing/invalid model adapter config
- No-fallback test: `preserved_engine_es` init failure does not auto-downgrade to fixture mode.
- Facade-routing tests (spy/monkeypatch):
  - allowed calls: `sweep_watchman`, `run_pipeline`, `summarize_pipeline_result`
  - forbidden calls absent: `sweep_watchman_and_log`, `run_pipeline_and_log`, `run_readiness_for_contract`
- ES-only guard tests remain and pass.
- Trigger evaluator dependency-authority tests remain and pass unchanged.

### Integration Tests

- Preserved-engine-backed app assembly smoke test (ES only) with deterministic model adapter stub and valid ES packet bundle fixture.
- Lockout integration test on preserved path: query disabled when hard lockout flags present.
- Query-armed integration test on preserved path: trigger true + no lockout yields query path invocation and one `run_pipeline` call.
- Startup-failure integration test: preserved mode with missing adapter config fails closed and does not execute query path.
- Stage scope regression: rendered trace remains A/B/C/D only.
- Run history source regression: preserved mode still renders fixture-backed run history source only.

### Launch / Docs Verification

- Documented preserved-engine launch command is executable from `target/ntb_marimo_console/`.
- Existing fixture demo launch command remains valid.

## 10) Migration Sequence from Current Fixture-Backed Path

1. **Freeze baseline**
   - Keep current fixture demo path and tests unchanged as control.

2. **Harden preserved-input fixtures for ES runtime path**
   - Add/validate one ES fixture `packet_bundle` shape acceptable to preserved `sweep_watchman`.
   - Reuse existing ES `query_packet` fixture for preserved `run_pipeline` invocation.
   - Do not change brief/run-history fixture responsibilities.

3. **Introduce backend selection seam**
   - Add explicit runtime mode wiring (`fixture_demo` vs `preserved_engine_es`) without changing UI surfaces.
   - Enforce no-implicit-fallback semantics.

4. **Add preserved-engine ES launch path**
   - Add `src/ntb_marimo_console/preserved_engine_es_app.py`.
   - Wire `PreservedEngineBackend` with explicit model adapter dependency.
   - Add startup validation for dependency/config presence.

5. **Add preserved-path tests**
   - Add routing/no-fallback/smoke/gating/stage-scope/run-history-source tests for preserved mode.
   - Keep fixture tests to prevent regressions in deterministic demo mode.

6. **Update README (minimal)**
   - Keep fixture demo as deterministic path.
   - Add one clearly labeled preserved-engine ES launch path.
   - Re-state that Stage E live-backed behavior remains deferred.

7. **Acceptance audit**
   - Re-run Phase 1 + Phase 2 criteria subset to confirm no boundary regressions.

## 11) Implementation Readiness Decision

**Phase 2 is implementation-ready** under this document because:

- Direction is singular and bounded (ES-only backend wiring first).
- Surface area is unchanged.
- Boundary controls are explicit.
- Acceptance and test gates are concrete and auditable.
