# R19 Release Candidate Readiness Audit

This audit captures whether the NTB Marimo Console is currently fit to be treated as a personal release candidate. It is deterministic, source-backed, and intentionally conservative. It must not overstate readiness.

R19 is an audit layer only. It does not change runtime behavior, default launch mode, stream manager behavior, or operator UI surfaces.

## Release Candidate Verdict

**Verdict: CONDITIONALLY READY**

The repo is ready to be treated as a fixture-verified personal release candidate, pending operator-run real Schwab live validation across the final target universe. It is not ready to be treated as a production-proven, broker-integrated, live-trading platform, and R19 makes no such claim.

A READY verdict is explicitly withheld because the sanitized D3 five-contract Schwab live rehearsal result is partial: login and subscription plumbing reached `status=ok`, but `market_data_received=no` and `received_contracts_count=0`. A NOT READY verdict is explicitly withheld because every release-blocking item that can be verified deterministically from the repository is verified through fixture-safe tests today.

## Evidence Classification

R19 distinguishes four evidence tiers. Fixture and harness evidence must never be represented as real live Schwab proof.

### Deterministic fixture / non-live evidence (verified)

- The canonical non-live acceptance harness (`scripts/verify_non_live_acceptance.py`) covers the contract universe, exclusions, default non-live launch, profile preflight, stream manager redaction and lifecycle, live observable snapshot v2, CHART_FUTURES bar builder, ES/CL/NQ/6E/MGC live workstation foundations, watchman brief and gate foundations, fail-closed trigger and pipeline query gate behavior, operator workspace, evidence replay, and performance review determinism.
- The R18 fixture/dry-run rehearsal (`scripts/run_manual_live_rehearsal.py --fixture`) exercises the final target universe, LEVELONE_FUTURES and CHART_FUTURES assumptions, one-connection discipline, repeated cache/UI refresh without re-login, fail-closed query readiness, blocked-data scenarios, live-failure no-fixture-fallback, evidence JSONL serializability, and unsupported-contract blocking.
- The R17 harness uses fixture and mocked clients only. It does not require Schwab credentials and does not read any token, secret, customer id, correl id, account id, or streamer url material.

### Manual live rehearsal checklist evidence (operator-run, not in CI)

- The R18 explicit live mode (`scripts/run_manual_live_rehearsal.py --live`) prints the manual operator checklist for a Schwab market-data rehearsal. It exits as manual-required and is not part of default tests or the canonical non-live harness.
- The single-quote Schwab manual live harness documented in `docs/schwab_manual_live_harness_runbook.md` remains the concrete opt-in market-data smoke path. It is operator-run, requires explicit `--live`, and does not run during default verification.
- The R20 five-contract proof-capture foundation (`scripts/capture_five_contract_live_proof.py`) creates a sanitized JSON artifact template for operator review. Fixture mode is the default and cannot satisfy the real-live proof gate. Live artifact creation requires explicit `--live` and explicit operator attestations; it does not run during default verification.

### Real live Schwab evidence (partial, manual-only)

- A sanitized D3 five-contract live rehearsal result is recorded in `docs/live_proof/five_contract_live_rehearsal_result_2026-05-12.md`.
- The recorded result proves Schwab streamer metadata retrieval, runtime start, live login, and a reported five-contract subscription without printed sensitive values.
- The recorded result does not prove live market-data delivery: `market_data_received=no` and `received_contracts_count=0`.
- Real five-contract live market-data proof for `ES`, `NQ`, `CL`, `6E`, and `MGC` is therefore still classified as pending. R19 does not claim that real live market-data proof has passed.
- The current five-contract proof-capture path is documented in `docs/five_contract_live_proof_capture.md`. Until a reviewed live artifact proves market-data delivery, that path remains a manual capture foundation rather than proof completion.

### Deferred or absent evidence (out of scope for this release candidate)

- Broker order routing, order placement, fills, account state, P&L, expectancy validity, and trading edge are deferred and absent by design. R19 does not measure them and does not block on them.
- Production monitoring, multi-symbol soak/reconnect testing, and dedicated live-app launch wiring are deferred future work and are not release-candidate gates for personal use.

## Final Target Universe

- Final target contracts: `ES`, `NQ`, `CL`, `6E`, `MGC`.
- `MGC` is Micro Gold and is the gold contract for this application.
- `MGC` is not `GC`. `GC` is not a synonym, alias, profile name, label, or substitute for `MGC`.
- Excluded contracts: `ZN`, `GC`.
- `ZN` may remain only as source-engine history, fixture data, or excluded-contract guard evidence. It is not target app runtime support and must not be re-promoted.
- `GC` is excluded and is not present as a supported runtime profile or engine schema contract.

## Contract Support Audit

For each final target contract, the audit verifies the same fixture-safe foundations. Real live Schwab market-data proof remains a separate operator-run gate and is pending across all five contracts.

| Contract | Runtime profile | Premarket / watchman fixture coverage | Live workstation read-model foundation | Trigger-state support | Pipeline gate support | Non-live harness coverage | Release-blocking gap |
|---|---|---|---|---|---|---|---|
| ES | `preserved_es_phase1` | Yes | Yes | Yes | Yes | Yes | Market-data delivery proof pending |
| NQ | `preserved_nq_phase1` | Yes | Yes | Yes | Yes | Yes | Market-data delivery proof pending |
| CL | `preserved_cl_phase1` | Yes | Yes | Yes | Yes | Yes | Market-data delivery proof pending |
| 6E | `preserved_6e_phase1` | Yes | Yes | Yes | Yes | Yes | Market-data delivery proof pending |
| MGC | `preserved_mgc_phase1` | Yes | Yes | Yes | Yes | Yes | Market-data delivery proof pending |

`ZN` and `GC` are not final target support. `ZN` is not exposed as a target app runtime profile. `GC` is not present and must not be added.

## Live Data Audit

The following live-data foundations are present and exercised by the non-live harness and the R18 fixture rehearsal. Their behavior is verified through fixture-safe tests; real Schwab traffic remains operator-run only.

- Persistent Schwab stream manager foundation: present (`market_data/stream_manager.py`).
- LEVELONE_FUTURES handling: present and exercised through fixture ingestion.
- CHART_FUTURES bar-builder handling: present (`market_data/bar_builder.py`, `chart_bars.py`).
- Live observable snapshot v2: present (`live_observables/builder.py`, `schema_v2.py`, `quality.py`).
- Quote freshness and fail-closed blocking: enforced; stale, missing, and mismatched data fail closed.
- One-connection discipline by design and test: verified by the R18 fixture rehearsal `one_stream_connection_discipline` check.
- No repeated login per Marimo refresh: verified by the R18 fixture rehearsal `repeated_refresh_does_not_relogin` check.
- No fixture fallback after live failure: verified by the R18 fixture rehearsal `simulated_live_failure_no_fixture_fallback` check; after a simulated live denial there is no fallback to fixture data.
- Live behavior is explicitly opt-in: the manual live rehearsal requires `--live` and exits as manual-required; the Schwab market-data harness requires explicit `--live`; default launch is non-live.
- Five-contract proof capture is explicitly opt-in for real-live artifacts: fixture mode is default, and `scripts/capture_five_contract_live_proof.py --live` requires operator attestations before a live artifact can be written.
- 15-second minimum refresh floor: enforced as `MIN_STREAM_REFRESH_FLOOR_SECONDS = 15.0` in `market_data/stream_manager.py`. The minimum refresh floor seconds is 15.

## Decision-Authority Audit

- Live data only arms, blocks, invalidates, or annotates pipeline state. Live data does not authorize trades.
- The preserved engine remains the sole decision authority. R19 does not introduce a second decision authority outside the preserved engine.
- Replay does not authorize trades. Replay is read-only audit-evidence playback.
- Performance review does not authorize trades. Performance review is read-only summary analysis.
- Manual query only. Pipeline queries are operator-initiated and gated by the fail-closed pipeline query gate.
- Manual execution only. Trade execution is manual-only on the operator's own platform; the app exposes no order submission, broker routing, ATM control, or live trade automation control.
- No broker, order, fill, account, or P&L behavior is present. R19 does not add any such behavior.

## UI / Operator Readiness Audit

- The operator workspace and read-model exists (`operator_workspace.py`, `viewmodels/`, `ui/`).
- Blocked reasons are visible in the operator workspace and live observable snapshot surfaces.
- Debug JSON is not the primary operator workflow. Primary surfaces remain readable per the acceptance matrix UI rules; raw JSON is restricted to clearly secondary debug surfaces.
- No best-trade ranking surface exists. The app does not rank or recommend trades.
- No alert language implies execution. The app exposes bounded query and review surfaces only.
- Default launch remains non-live. The default launch remains non-live. Live behavior is opt-in.

## Evidence / Replay / Performance Audit

- The audit/replay foundation exists (`evidence_replay.py`, `tests/test_evidence_replay.py`).
- The performance review foundation exists (`performance_review.py`, `tests/test_performance_review.py`).
- Replay cannot authorize trades.
- Performance review cannot authorize trades.
- Fixture evidence is not represented as real live evidence. The R18 rehearsal labels its events as fixture, and the canonical non-live harness is documented as not proving live operational readiness.

## Release Blockers and Proof Gaps

Release blockers and proof gaps are reported using exact language and explicit classification.

1. Real five-contract Schwab market-data delivery proof is pending operator-run validation.
   - This is not a deterministic code blocker.
   - This is a real-live proof gap.
   - Manual operator-run login/subscription plumbing reached `status=ok`, but no market data was received during the 15-second bounded receive loop.
   - Until a sanitized operator-run real five-contract Schwab live result proves market-data delivery, R19 will not claim that a real Schwab five-contract live market-data session has passed.

No additional release blockers were identified by deterministic, source-backed inspection of the repository at this checkpoint. Default launch remains non-live. Fixture-safe behavior remains intact. No fixture fallback after live failure remains intact. The 15-second minimum refresh floor remains enforced.

## Release Candidate Conclusion

The NTB Marimo Console is ready to be treated as a fixture-verified personal release candidate, with a partial operator-run real Schwab live rehearsal recorded and live market-data delivery still unproven. It is not yet ready to be treated as a fully production-proven live-trading platform, and this audit does not claim otherwise.

If the next operator-run real five-contract Schwab live session proves market-data delivery and a sanitized artifact is committed, the verdict can be re-evaluated. Until that proof exists in the repository, this audit deliberately holds the verdict at CONDITIONALLY READY rather than READY.

## Non-Goals For R19

R19 does not:

- add live Schwab calls, credentials, or token state inspection,
- modify default launch mode,
- modify stream manager behavior,
- change runtime profiles,
- add UI polish,
- add execution, order, broker, account, fill, or P&L behavior,
- introduce a second decision authority outside the preserved engine,
- promote replay or performance review into a trade-authorizing surface,
- promote fixture evidence into real live evidence,
- re-promote `ZN` into final target support,
- map `MGC` to `GC` or `GC` to `MGC`.
