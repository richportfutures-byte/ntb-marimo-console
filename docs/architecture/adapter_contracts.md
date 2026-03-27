# Adapter Contracts — NinjaTradeBuilder v2 / v3 / marimo

> Generated 2026-03-25. Read-only audit output.
> Do not begin marimo shell work until operator review is complete.

---

## Section A: v2-main Public Contract (the "Brain")

### Public API Surface (`execution_facade.py`)

| Function | Signature | Returns |
|---|---|---|
| `sweep_watchman` | `(packet_bundle: dict, readiness_trigger: dict\|ReadinessTrigger) -> dict[str, WatchmanReadinessContext]` | Per-contract deterministic pre-flight |
| `sweep_watchman_and_log` | `(...) -> tuple[dict[str, WatchmanReadinessContext], list[RunHistoryRecord]]` | Sweep + JSONL logging |
| `run_pipeline` | `(packet: dict, contract: str, *, model_adapter: StructuredModelAdapter, ...) -> PipelineExecutionResult` | Full A-B-C-D trace |
| `run_pipeline_and_log` | `(...) -> tuple[PipelineExecutionResult, RunHistoryRecord]` | Pipeline + JSONL logging |
| `run_readiness_for_contract` | `(...) -> PromptExecutionResult` | LLM-evaluated readiness |
| `summarize_pipeline_result` | `(result: PipelineExecutionResult) -> dict[str, Any]` | Flat summary dict |

### Core State Shapes

**`WatchmanReadinessContext`** (Pydantic `StrictModel`, `extra="forbid"`):
- `contract: ContractSymbol` (Literal `"ES","NQ","CL","ZN","6E","MGC"`)
- `session_state, staleness_state, value_location, vwap_posture` — all `str`
- `delta_posture, level_proximity, event_risk_state, macro_state` — all `str`
- `trigger_proximity: TriggerProximity` (sub-model with `state, nearest_trigger, distance_description`)
- `hard_lockout_flags: list[str]`
- `awareness_flags: list[str]`
- `missing_inputs: list[str]`
- `rationales: dict[str, str]`

**`PipelineExecutionResult`** (frozen `@dataclass`):
- `contract: str`
- `termination_stage: TerminationStage` = `"sufficiency_gate" | "contract_market_read" | "setup_construction" | "risk_authorization"`
- `final_decision: FinalDecision` = `"TRADE_APPROVED" | "TRADE_REJECTED" | "TRADE_REDUCED" | "NO_TRADE" | "INSUFFICIENT_DATA" | "EVENT_LOCKOUT" | "NEED_INPUT" | "ERROR"`
- `sufficiency_gate_output: SufficiencyGateOutput | None`
- `contract_analysis: ContractAnalysis | None`
- `proposed_setup: ProposedSetup | None`
- `risk_authorization: RiskAuthorization | None`

**`SufficiencyGateOutput`** (StrictModel):
- `status: "READY" | "NEED_INPUT" | "INSUFFICIENT_DATA" | "EVENT_LOCKOUT"`
- `staleness_check: StalenessCheck` (sub-model: `packet_age_seconds`, `stale`, `threshold_seconds`)
- `event_lockout_detail: EventLockoutDetail | None` (sub-model: `event_name`, `event_time`, `minutes_until`, `lockout_type`)
- `challenge_state_valid: bool`
- `missing_inputs: list[str]`
- `disqualifiers: list[str]`

**`ContractAnalysis`** (StrictModel):
- `outcome: "ANALYSIS_COMPLETE" | "NO_TRADE"`
- `market_regime: Literal["trending_up","trending_down","range_bound","breakout","breakdown","choppy","unclear"]`
- `directional_bias: Literal["bullish","bearish","neutral","unclear"]`
- `evidence_score: int` (1-10)
- `confidence_band: Literal["LOW","MEDIUM","HIGH"]` — LOW=1-3, MEDIUM=4-6, HIGH=7-10
- `key_levels: KeyLevelsOutput` (sub-model: `resistance_levels`, `support_levels`, `pivot_level`)
- `value_context: ValueContext` (sub-model: 4 relative-to fields)
- `structural_notes: str`
- `conflicting_signals: list[str]`
- `assumptions: list[str]`

**`ProposedSetup`** (StrictModel):
- `outcome: "SETUP_PROPOSED" | "NO_TRADE"`
- `direction: "LONG" | "SHORT" | None`
- `entry_price, stop_price, target_1, target_2: float | None`
- `position_size: int | None`
- `risk_dollars: float | None`
- `reward_risk_ratio: float | None`
- `setup_class: str | None`
- `hold_time_estimate_minutes: int | None`
- `sizing_math: SizingMath | None` (sub-model: `stop_distance_ticks`, `risk_per_tick`, `raw_risk_dollars`, `slippage_cost_dollars`, `adjusted_risk_dollars`, `blended_target_distance_ticks`, `blended_reward_dollars`)
- `rationale: str | None`
- `no_trade_reason: str | None`
- `disqualifiers: list[str]`

**`RiskAuthorization`** (StrictModel):
- `decision: "APPROVED" | "REJECTED" | "REDUCED"`
- `checks: list[RiskCheck]` (13 items, each: `check_id`, `check_name`, `passed`, `detail`)
- `rejection_reasons: list[str]`
- `adjusted_position_size: int | None`
- `adjusted_risk_dollars: float | None`
- `remaining_daily_risk_budget: float | None`
- `remaining_aggregate_risk_budget: float | None`

### Input Schemas

**`MarketPacket`** (StrictModel):
- `contract: ContractSymbol`
- `timestamp: AwareDatetime` (Python `datetime` with tz)
- `current_price: float`
- 30+ fields including value area, VWAP, cumulative delta, event calendar
- Nested sub-models: `KeyLevels`, `SessionInfo`, `EventCalendarEntry`

**`ChallengeState`** (StrictModel):
- 18+ fields: `current_balance`, `daily_realized_pnl`, `open_positions: list[OpenPosition]`, `max_position_size_by_contract: PerContractIntMap`, etc.

**`HistoricalPacket`** — Composed validation envelope wrapping all sub-schemas with cross-contract alignment.

### Adapter Protocol

```python
class StructuredModelAdapter(Protocol):
    def generate_structured(self, request: StructuredGenerationRequest) -> Mapping[str, Any]: ...
```

Implementations: `GeminiResponsesAdapter`, `OpenAIResponsesAdapter`, `InProcessStructuredAdapter` (testing).

### Renderer Outputs (`view_models.py`)

| Dataclass | Fields | Source |
|---|---|---|
| `ReadinessCard` | contract, status, session_state, vwap_posture, value_location, level_proximity, trigger_state, trigger_proximity_summary, macro_state, event_risk, hard_lockouts, awareness_items, missing_context | From `WatchmanReadinessContext` |
| `PipelineResultView` | contract, decision, decision_badge, termination_stage, stages_reached, elapsed, has_setup | From `PipelineExecutionResult` |
| `StageProgressionRow` | stage_name, reached, outcome | From `PipelineExecutionResult` |
| `LogHistoryRow` | run_id, logged_at, contract, run_type, watchman_status, trigger_family, vwap_posture, value_location, level_proximity, event_risk, final_decision, notes | From `RunHistoryRecord` |
| `WatchmanDiff` | contract, field, before, after, changed | Diff of two `WatchmanReadinessContext` |

---

## Section B: v3 Public Contract (the "Spine")

### Pipeline Entry Points

| Function | Signature | Returns |
|---|---|---|
| `run_pipeline` | `(contract: str, bundle: PacketBundle) -> PipelineRunRecord` | Full A-B-C-D trace |
| `run_stage_ab` | `(contract, packet, ext, challenge) -> tuple[SufficiencyOutput, ContractAnalysis\|None]` | Gate + analysis |
| `run_stage_c` | `(contract, packet, analysis) -> ProposedSetup` | Setup construction |
| `run_stage_d` | `(contract, setup, challenge, packet) -> RiskAuthorization` | Risk authorization |
| `generate_premarket_brief` | `(contract, packet, ext, session_date, watchman_state?, model?) -> PreMarketBrief` | Pre-RTH brief (v3-only) |
| `generate_all_premarket_briefs` | `(bundle, watchman_states?, contracts?, model?) -> dict[str, PreMarketBrief\|Exception]` | Multi-contract briefs |
| `sweep_contract` | `(contract, packet, ext) -> WatchmanState` | Single-contract watchman |
| `sweep_all` | `(bundle: PacketBundle) -> dict[str, WatchmanState]` | Multi-contract watchman |

### Core State Shapes

**`WatchmanState`** (plain `@dataclass`, NOT Pydantic):
- `contract: str`
- `is_stale: bool`
- `packet_age_seconds: float | None`
- `vwap_posture: str` ("above_vwap" | "below_vwap" | "at_vwap" | "unknown")
- `value_location: str`
- `level_proximity: str`
- `delta_posture: str`
- `event_risk: str`
- `macro_state: str | None`
- `nearest_level_name: str | None`
- `nearest_level_value: float | None`
- `hard_lockout_flags: list[str]`
- `awareness_flags: list[str]`
- `overall_status: str` ("ready" | "caution" | "blocked")

**`PipelineRunRecord`** (Pydantic `BaseModel`, NOT StrictModel):
- `run_id: str`
- `contract: str`
- `session_date: str`
- `run_type: str`
- `started_at: str`
- `completed_at: str | None`
- `termination_stage: str | None` — `"PRE_STAGE_A" | "STAGE_A" | "STAGE_B" | "STAGE_C" | "STAGE_D"`
- `final_decision: str | None` — `"APPROVED" | "REJECTED" | "REDUCED" | "NO_TRADE" | "INSUFFICIENT_DATA" | "EVENT_LOCKOUT" | "NEED_INPUT" | "ERROR" | sufficiency status`
- `sufficiency: SufficiencyOutput | None`
- `analysis: ContractAnalysis | None`
- `setup: ProposedSetup | None`
- `authorization: RiskAuthorization | None`
- `error: str | None`

**`SufficiencyOutput`** (BaseModel):
- `contract: str`
- `status: str` — same values as v2 but no sub-models (no `StalenessCheck`, no `EventLockoutDetail`)
- `missing_fields: list[str]` (v2 uses `missing_inputs`)
- `disqualifiers: list[str]`
- `packet_age_seconds: float | None` (flat field, not nested in StalenessCheck)
- `event_lockout_detail: str | None` (flat string, not structured sub-model)
- `challenge_state_valid: bool`
- `notes: str | None`

**`ContractAnalysis`** (BaseModel):
- `outcome: "ANALYSIS_COMPLETE" | "NO_TRADE"`
- `market_regime: Literal["TREND_UP","TREND_DOWN","RANGE_BOUND","BREAKOUT_PENDING","POST_BREAKOUT","REVERSAL_SETUP","UNDEFINED"]`
- `directional_bias: Literal["LONG","SHORT","NEUTRAL","CONFLICTED"]`
- `evidence_score: int | None` (1-10)
- `confidence_band: Literal["LOW","MEDIUM","HIGH"] | None` — LOW=1-4, MEDIUM=5-7, HIGH=8-10
- `key_levels: list[KeyLevelAnalysis]` (flat list, not sub-model with resistance/support/pivot)
- `value_context: str | None` (flat string, not structured sub-model)
- `structural_notes: str | None`
- `conflicting_signals: list[str]`
- `no_trade_reason: str | None`

**`ProposedSetup`** (BaseModel):
- `outcome: "TRADE_PROPOSED" | "NO_TRADE"` (v2: `"SETUP_PROPOSED"`)
- `direction: "LONG" | "SHORT" | None`
- `entry_price, stop_price, target_1, target_2: float | None`
- `reward_risk_ratio: float | None`
- `setup_class: str | None`
- `hold_time_estimate_minutes: int | None`
- `sizing_math: SizingMath | None` (sub-model: `stop_distance_ticks`, `risk_per_tick_dollars`, `raw_risk_dollars`, `slippage_cost_dollars`, `adjusted_risk_dollars`, `position_size`)
- `rationale: str | None`
- `no_trade_reason: str | None`
- `disqualifiers: list[str]`

**`RiskAuthorization`** (BaseModel):
- `decision: "APPROVED" | "REJECTED" | "REDUCED"`
- `checks: list[RiskCheck]` (13 items, each: `check_id`, `name`, `passed`, `detail`)
- `rejection_reasons: list[str]`
- `adjusted_position_size: int | None`
- `adjusted_risk_dollars: float | None`
- `notes: str | None`

### Input Schemas

**`MarketPacket`** (BaseModel):
- `contract: str` (not `ContractSymbol` Literal)
- `timestamp_et: str` (string, not `AwareDatetime`)
- `current_price: float`
- `levels: KeyLevels` (sub-model with vwap, prior_day_high/low, session_vah/val/poc, etc.)
- `cumulative_delta: float | None`
- `volume_today: int | None`
- `event_calendar: list[EventCalendarEntry]`
- `packet_age_seconds: float | None`

**`ChallengeState`** (BaseModel):
- `account_balance: float` (v2: `current_balance`)
- `daily_pnl: float` (v2: `daily_realized_pnl`)
- `open_risk_dollars: float`
- `open_positions: dict[str, int]` (v2: `list[OpenPosition]`)
- `daily_trade_count: int`
- `trade_count_by_contract: dict[str, int]`
- `last_stop_out_time: str | None`
- `last_trade_direction: dict[str, str]`

**`PacketBundle`** (BaseModel):
- `session_date: str`
- `packets: dict[str, MarketPacket]`
- `extensions: dict[str, dict]`
- `challenge_state: ChallengeState`

### v3-Only Features

**`PreMarketBrief`** (BaseModel):
- `contract, session_date, analytical_framework: str`
- `key_structural_levels: list[KeyLevelAnalysis]`
- `long_thesis, short_thesis: str | None`
- `current_structure_summary: str`
- `query_triggers: list[QueryTrigger]`
- `watch_for: list[str]`
- `schema_fields_referenced: list[str]`
- `generated_at: str`

**`QueryTrigger`** (BaseModel):
- `condition: str`
- `schema_fields: list[str]`
- `level_or_value: str | None`

### Fail-Closed Contract

Pipeline stages execute A -> B -> C -> D. Early termination at each gate:
- Stage A: `status != "READY"` -> terminate with sufficiency status as `final_decision`
- Stage B: `analysis is None or analysis.outcome == "NO_TRADE"` -> terminate `"NO_TRADE"`
- Stage C: `setup.outcome == "NO_TRADE"` -> terminate `"NO_TRADE"`
- Stage D: `authorization.decision` becomes `final_decision`
- Any exception: terminate with `"ERROR"` at that stage

No adapter protocol — calls Gemini directly via `google.genai.Client`. Default model: `gemini-2.5-flash`.

---

## Section C: Impedance Mismatches

### C.1 — Enum Literal Divergence

| Domain | v2 Values | v3 Values |
|---|---|---|
| `market_regime` | `trending_up, trending_down, range_bound, breakout, breakdown, choppy, unclear` | `TREND_UP, TREND_DOWN, RANGE_BOUND, BREAKOUT_PENDING, POST_BREAKOUT, REVERSAL_SETUP, UNDEFINED` |
| `directional_bias` | `bullish, bearish, neutral, unclear` | `LONG, SHORT, NEUTRAL, CONFLICTED` |
| `setup outcome` | `SETUP_PROPOSED` | `TRADE_PROPOSED` |
| `final_decision` | `TRADE_APPROVED, TRADE_REJECTED, TRADE_REDUCED` | `APPROVED, REJECTED, REDUCED` |
| `termination_stage` | `sufficiency_gate, contract_market_read, setup_construction, risk_authorization` | `PRE_STAGE_A, STAGE_A, STAGE_B, STAGE_C, STAGE_D` |

### C.2 — Confidence Band Thresholds

| Band | v2 | v3 |
|---|---|---|
| LOW | 1-3 | 1-4 |
| MEDIUM | 4-6 | 5-7 |
| HIGH | 7-10 | 8-10 |

Score of 4 is MEDIUM in v2 but LOW in v3 (no-trade). Score of 7 is HIGH in v2 but MEDIUM in v3 (requires 2.0:1 R:R vs 1.5:1). **This is a behavioral divergence, not just a naming one.**

### C.3 — Structural Shape Divergence

| Concept | v2 Shape | v3 Shape |
|---|---|---|
| Watchman output | `WatchmanReadinessContext` (Pydantic StrictModel, `extra="forbid"`) | `WatchmanState` (plain `@dataclass`) |
| Pipeline result | `PipelineExecutionResult` (frozen `@dataclass`) | `PipelineRunRecord` (Pydantic `BaseModel`) |
| Sufficiency staleness | `StalenessCheck` sub-model (`packet_age_seconds`, `stale`, `threshold_seconds`) | Flat `packet_age_seconds` field on `SufficiencyOutput` |
| Event lockout | `EventLockoutDetail` sub-model (`event_name`, `event_time`, `minutes_until`, `lockout_type`) | Flat `event_lockout_detail: str \| None` |
| Key levels (analysis) | `KeyLevelsOutput` sub-model (`resistance_levels: list[float]`, `support_levels: list[float]`, `pivot_level: float \| None`) | `list[KeyLevelAnalysis]` (flat list of `{level_name, value, significance}`) |
| Value context | `ValueContext` sub-model (4 relative-to fields) | `str \| None` (free-text) |
| Missing fields | `missing_inputs: list[str]` | `missing_fields: list[str]` |
| Challenge state balance | `current_balance` | `account_balance` |
| Challenge state PnL | `daily_realized_pnl` | `daily_pnl` |
| Challenge open positions | `list[OpenPosition]` (Pydantic model) | `dict[str, int]` |
| Risk check name field | `check_name` | `name` |
| Sizing math tick risk | `risk_per_tick` | `risk_per_tick_dollars` |
| Sizing math extras | `blended_target_distance_ticks`, `blended_reward_dollars` | Not present |
| Timestamp | `timestamp: AwareDatetime` | `timestamp_et: str` |
| Contract type | `ContractSymbol` (Literal) | `str` |
| Model validation | `StrictModel` (`extra="forbid"`) everywhere | `BaseModel` (permissive) everywhere |

### C.4 — Missing in v3 (present in v2)

| Feature | v2 Location | Notes |
|---|---|---|
| Trigger system | `schemas/triggers.py` — `ReadinessTrigger`, `RecheckAtTimeTrigger`, `PriceLevelTouchTrigger` | v3 has no trigger abstraction |
| Readiness Engine | `runtime.py` — `run_readiness()`, 6 doctrine gates | v3 has no LLM-evaluated readiness |
| Adapter protocol | `runtime.py` — `StructuredModelAdapter` | v3 calls Gemini directly |
| Boundary model registry | `runtime.py` — `BOUNDARY_MODEL_REGISTRY` | v3 parses JSON manually |
| Prompt asset system | `prompt_assets.py` — `PromptAsset`, `<<placeholder>>` substitution | v3 uses f-string templates |
| Packet compiler | `packet_compiler/` — per-contract raw-to-packet compilation | v3 assumes pre-compiled packets |
| Post-trade review | `schemas/outputs.py` — `PostTradeReviewRecord` (MAE/MFE, slippage) | Not in v3 |
| Audit system | `audit.py`, `audit_report.py` | Not in v3 |
| Logging records | `logging_record.py` — `RunHistoryRecord` (StrictModel), JSONL append/read | v3 has no logging |
| Per-contract discriminated unions | `schemas/contracts.py` — `AllMarketPacket`, `AllContractSpecificExtension` | v3 uses flat dicts |
| Historical packet validation | `validation.py` — `validate_historical_packet()` | Not in v3 |
| Readiness web API | `readiness_web.py` — WSGI `/api/readiness` | Not in v3 |
| Readiness verification CLI | `readiness_verify.py` | Not in v3 |
| View models | `view_models.py` — `ReadinessCard`, `PipelineResultView`, `StageProgressionRow`, `WatchmanDiff`, `LogHistoryRow` | Not in v3 |

### C.5 — Missing in v2 (present in v3)

| Feature | v3 Location | Notes |
|---|---|---|
| Pre-market brief | `premarket.py` — `PreMarketBrief`, `QueryTrigger`, `KeyLevelAnalysis` | v2 has no pre-RTH briefing system |
| Multi-contract bundle pipeline | `stages.py` — `PacketBundle` with shared `challenge_state` | v2 processes one contract at a time |
| Watchman awareness_flags | `watchman.py` — `WatchmanState.awareness_flags` | v2's `WatchmanReadinessContext` also has this; parity here |

---

## Section D: Proposed Canonical Adapter Layer

### D.1 — Design Principles

1. **v2 is the schema authority.** v2's StrictModel types with `extra="forbid"` are the canonical shapes. v3's permissive BaseModels are the integration target, not the source of truth.
2. **v3 is the pipeline authority.** v3's stage execution logic (stages.py, premarket.py) is the canonical pipeline. v2's `runtime.py` prompt execution is superseded.
3. **Adapters translate at the boundary, never inside.** No pipeline-internal code should import from the other version.
4. **Marimo consumes adapters, never raw types from either version.**

### D.2 — Proposed Modules

#### `v2_brain_adapter.py` — Translates v2 types into canonical interchange format

```
v2_watchman_to_canonical(ctx: WatchmanReadinessContext) -> CanonicalWatchmanState
v2_pipeline_result_to_canonical(result: PipelineExecutionResult) -> CanonicalPipelineResult
v2_sufficiency_to_canonical(output: SufficiencyGateOutput) -> CanonicalSufficiency
v2_analysis_to_canonical(output: ContractAnalysis) -> CanonicalAnalysis
v2_setup_to_canonical(output: ProposedSetup) -> CanonicalSetup
v2_risk_auth_to_canonical(output: RiskAuthorization) -> CanonicalRiskAuth
canonical_to_readiness_card(state: CanonicalWatchmanState) -> ReadinessCard  # v2 view_model
```

Responsibilities:
- Map `trending_up` -> `TREND_UP`, `bullish` -> `LONG`, etc.
- Flatten `StalenessCheck` / `EventLockoutDetail` sub-models to canonical flat fields
- Map `SETUP_PROPOSED` -> `TRADE_PROPOSED`, `TRADE_APPROVED` -> `APPROVED`
- Map `sufficiency_gate` -> `STAGE_A`, `contract_market_read` -> `STAGE_B`, etc.
- Map `missing_inputs` -> `missing_fields`
- Map `check_name` -> `name`
- Convert `AwareDatetime` -> ISO string

#### `v3_spine_adapter.py` — Translates v3 types into canonical interchange format

```
v3_watchman_to_canonical(state: WatchmanState) -> CanonicalWatchmanState
v3_pipeline_record_to_canonical(record: PipelineRunRecord) -> CanonicalPipelineResult
v3_sufficiency_to_canonical(output: SufficiencyOutput) -> CanonicalSufficiency
v3_analysis_to_canonical(output: ContractAnalysis) -> CanonicalAnalysis
v3_setup_to_canonical(output: ProposedSetup) -> CanonicalSetup
v3_risk_auth_to_canonical(output: RiskAuthorization) -> CanonicalRiskAuth
v3_premarket_brief_passthrough(brief: PreMarketBrief) -> PreMarketBrief  # no translation needed
```

Responsibilities:
- v3 enum values are already UPPERCASE — minimal mapping needed
- Wrap flat `packet_age_seconds` + `is_stale` into canonical staleness structure
- Wrap flat `event_lockout_detail: str` into canonical lockout structure
- Map `list[KeyLevelAnalysis]` to canonical key levels structure
- Map plain `@dataclass` fields to canonical typed fields

#### `canonical_types.py` — Canonical interchange dataclasses

All canonical types are plain Python `@dataclass(frozen=True)` — no Pydantic dependency, no validation beyond type hints. These are the *only* types marimo components should consume.

```python
@dataclass(frozen=True)
class CanonicalWatchmanState:
    contract: str
    is_stale: bool
    packet_age_seconds: float | None
    vwap_posture: str          # UPPERCASE normalized
    value_location: str
    level_proximity: str
    delta_posture: str
    event_risk: str
    macro_state: str | None
    hard_lockout_flags: tuple[str, ...]
    awareness_flags: tuple[str, ...]
    missing_fields: tuple[str, ...]
    overall_status: str        # "ready" | "caution" | "blocked"

@dataclass(frozen=True)
class CanonicalSufficiency:
    contract: str
    status: str                # READY | NEED_INPUT | INSUFFICIENT_DATA | EVENT_LOCKOUT
    packet_age_seconds: float | None
    is_stale: bool
    stale_threshold_seconds: float | None
    event_lockout_event_name: str | None
    event_lockout_minutes_until: float | None
    challenge_state_valid: bool
    missing_fields: tuple[str, ...]
    disqualifiers: tuple[str, ...]

@dataclass(frozen=True)
class CanonicalKeyLevel:
    level_name: str
    value: float
    significance: str
    role: str                  # "resistance" | "support" | "pivot"

@dataclass(frozen=True)
class CanonicalAnalysis:
    contract: str
    outcome: str               # ANALYSIS_COMPLETE | NO_TRADE
    market_regime: str         # UPPERCASE normalized
    directional_bias: str      # LONG | SHORT | NEUTRAL | CONFLICTED
    evidence_score: int | None
    confidence_band: str | None  # LOW | MEDIUM | HIGH
    key_levels: tuple[CanonicalKeyLevel, ...]
    value_context: str | None  # free-text summary
    structural_notes: str | None
    conflicting_signals: tuple[str, ...]
    no_trade_reason: str | None

@dataclass(frozen=True)
class CanonicalSizingMath:
    stop_distance_ticks: float
    risk_per_tick_dollars: float
    raw_risk_dollars: float
    slippage_cost_dollars: float
    adjusted_risk_dollars: float
    position_size: int

@dataclass(frozen=True)
class CanonicalSetup:
    contract: str
    outcome: str               # TRADE_PROPOSED | NO_TRADE
    direction: str | None      # LONG | SHORT
    entry_price: float | None
    stop_price: float | None
    target_1: float | None
    target_2: float | None
    reward_risk_ratio: float | None
    setup_class: str | None
    hold_time_estimate_minutes: int | None
    sizing_math: CanonicalSizingMath | None
    rationale: str | None
    no_trade_reason: str | None
    disqualifiers: tuple[str, ...]

@dataclass(frozen=True)
class CanonicalRiskCheck:
    check_id: int
    name: str
    passed: bool
    detail: str

@dataclass(frozen=True)
class CanonicalRiskAuth:
    contract: str
    decision: str              # APPROVED | REJECTED | REDUCED
    checks: tuple[CanonicalRiskCheck, ...]  # exactly 13
    rejection_reasons: tuple[str, ...]
    adjusted_position_size: int | None
    adjusted_risk_dollars: float | None

@dataclass(frozen=True)
class CanonicalPipelineResult:
    run_id: str
    contract: str
    session_date: str
    termination_stage: str     # STAGE_A | STAGE_B | STAGE_C | STAGE_D
    final_decision: str        # APPROVED | REJECTED | REDUCED | NO_TRADE | INSUFFICIENT_DATA | EVENT_LOCKOUT | NEED_INPUT | ERROR
    sufficiency: CanonicalSufficiency | None
    analysis: CanonicalAnalysis | None
    setup: CanonicalSetup | None
    risk_auth: CanonicalRiskAuth | None
    error: str | None
    started_at: str
    completed_at: str | None
```

### D.3 — Confidence Band Resolution

The adapter layer must pick one canonical mapping. **Recommendation: adopt v3's thresholds** (LOW=1-4, MEDIUM=5-7, HIGH=8-10) as they are more conservative (higher bar for HIGH confidence, which reduces false approvals). The v2 brain adapter must re-map scores 4 and 7 accordingly when translating v2 outputs.

Alternatively, carry both `confidence_band` (as-evaluated) and `canonical_confidence_band` (re-mapped) on `CanonicalAnalysis` so marimo can display the original while gates enforce the canonical.

### D.4 — Adapter Protocol for LLM Calls

v3 calls Gemini directly. For marimo to support both v2's adapter protocol and v3's direct calls, introduce:

```python
class PipelineBackend(Protocol):
    def run_pipeline(self, contract: str, packet_bundle: dict) -> CanonicalPipelineResult: ...
    def sweep_watchman(self, packet_bundle: dict) -> dict[str, CanonicalWatchmanState]: ...

class V2Backend:
    """Wraps v2 execution_facade + v2_brain_adapter."""
    def __init__(self, model_adapter: StructuredModelAdapter): ...

class V3Backend:
    """Wraps v3 stages.run_pipeline + v3_spine_adapter."""
    def __init__(self, model: str = "gemini-2.5-flash"): ...
```

Marimo consumes `PipelineBackend`, never raw v2/v3 modules.

---

## Section E: marimo/ Boundary Violation Log

### E.1 — File Classification

| File | Verdict | Imports From | Notes |
|---|---|---|---|
| `notebooks/app.py` | **DELEGATES** | `ninjatradebuilder.execution_facade`, `ninjatradebuilder.view_models`, `ninjatradebuilder.config`, `ninjatradebuilder.gemini_adapter`, `ninjatradebuilder.cli`, `ninjatradebuilder.audit`, `ninjatradebuilder.audit_report`, `ninjatradebuilder.logging_record`, `ninjatradebuilder.schemas.triggers`, `ninjatradebuilder.validation`, local `_components.*` | 100% delegation to v2-main |
| `notebooks/readiness_matrix.py` | **DELEGATES** | `ninjatradebuilder.execution_facade.sweep_watchman`, `ninjatradebuilder.view_models.readiness_cards_from_sweep`, `ninjatradebuilder.logging_record` | 100% delegation to v2-main |
| `notebooks/_components/__init__.py` | **OWNS-TRUTH** (trivial) | None | Package marker only |
| `notebooks/_components/formatters.py` | **OWNS-TRUTH** | None | Presentation-only: price/risk formatting, icon mapping, badge variants. Hardcodes enum literals from v2. |
| `notebooks/_components/cards.py` | **DELEGATES** | `_components.formatters` | Reads v2 `PipelineExecutionResult` and `WatchmanReadinessContext` attributes via `getattr` |
| `notebooks/_components/pipeline_flow.py` | **DELEGATES** | `_components.formatters` | Reads v2 `StageProgressionRow` attributes. Hardcodes v2 stage names. |
| `notebooks/_components/stage_renderers.py` | **DELEGATES** | `_components.cards`, `_components.formatters` | Reads v2 output types deeply. Hardcodes v2 enum values. |
| `notebooks/_components/fail_panel.py` | **DELEGATES** | None | Reads v2 `PipelineExecutionResult` attributes via `getattr`. Hardcodes v2 decision values. |

### E.2 — Specific Boundary Violations

**Violation 1: Hardcoded v2 enum literals in `_components/`**

`stage_renderers.py:108-115` maps `market_regime` using v2 lowercase values:
```python
"trending_up": "approved", "trending_down": "rejected", ...
```
These will **silently fall through** to `"no-trade"` default when fed v3's `TREND_UP`, `TREND_DOWN`.

`stage_renderers.py:119-124` maps `directional_bias` using v2's `bullish`/`bearish`:
```python
"bullish": "approved", "bearish": "rejected", ...
```
v3's `LONG`/`SHORT` will fall through.

`stage_renderers.py:226` checks `outcome == "SETUP_PROPOSED"` — v3 uses `"TRADE_PROPOSED"`.

`fail_panel.py:90` checks `final_decision in ("TRADE_APPROVED", "TRADE_REDUCED")` — v3 uses `"APPROVED"`, `"REDUCED"`.

`formatters.py:36-52,56-77,80-98` — `decision_color`, `status_icon`, `badge_variant` all hardcode v2 values. Some v3 values overlap (`APPROVED`, `REJECTED`, `REDUCED`) but `TRADE_APPROVED`, `TRADE_REJECTED`, `TRADE_REDUCED` are v2-only.

**Violation 2: Direct attribute access assuming v2 sub-model structure**

`stage_renderers.py:32-48` accesses `output.staleness_check.packet_age_seconds`, `output.staleness_check.stale`, `output.staleness_check.threshold_seconds`. v3's `SufficiencyOutput` has no `staleness_check` sub-model — these are flat fields.

`stage_renderers.py:61-64` accesses `output.event_lockout_detail.event_name`, `.event_time`, `.minutes_until`, `.lockout_type`. v3's `event_lockout_detail` is a flat `str | None`, not a sub-model.

`stage_renderers.py:134-152` accesses `output.value_context.relative_to_prior_value_area`, etc. v3's `value_context` is a flat `str | None`.

`stage_renderers.py:184-185` accesses `key_levels.resistance_levels`, `key_levels.support_levels`, `key_levels.pivot_level`. v3 uses `list[KeyLevelAnalysis]` with no resistance/support/pivot grouping.

`stage_renderers.py:261` accesses `sizing.risk_per_tick` — v3 uses `risk_per_tick_dollars`.

`stage_renderers.py:265-266` accesses `sizing.blended_target_distance_ticks`, `sizing.blended_reward_dollars` — not present in v3.

`cards.py:48` accesses `result.sufficiency_gate_output` — v3 uses `result.sufficiency`.

**Violation 3: v2 stage naming in pipeline flow**

`pipeline_flow.py:10-22` hardcodes `STAGE_LABELS` and `STAGE_ORDER` using v2 internal names (`sufficiency_gate`, `contract_market_read`, `setup_construction`, `risk_authorization`). v3 uses `STAGE_A`-`STAGE_D`.

`cards.py:24-29` maps the same v2 internal stage names.

**Violation 4: No v3 support path exists**

None of the `_components/` modules have any conditional logic or fallback for v3 types. If v3 outputs are passed in, `getattr` calls will return `None` or defaults, producing silently incorrect displays — no errors raised, just wrong data shown to the operator.

### E.3 — Duplication

`marimo/notebooks/readiness_matrix.py` duplicates the table-rendering logic that `notebooks/app.py` also performs for the readiness matrix tab. Both import `sweep_watchman` and `readiness_cards_from_sweep` from v2-main and render identical card-to-table-row mappings. The standalone `readiness_matrix.py` notebook is a subset of `app.py`'s readiness tab.

---

*End of adapter contracts. Awaiting operator review before any marimo shell work begins.*
