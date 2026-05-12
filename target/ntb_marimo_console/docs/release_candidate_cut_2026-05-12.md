# NTB Marimo Console Release Candidate Cut - 2026-05-12

This record cuts the NTB Marimo Console as a repository-verifiable, fixture-safe personal workstation release candidate. It is not a production-live Schwab readiness claim.

## Cut Record

- Release candidate: `NTB Marimo Console RC-2026-05-12`
- Clean checkpoint used for the cut: `110f09a Add performance review layer`
- Release-candidate harness: `scripts/verify_release_candidate.py`
- Verification mode: credential-free, fixture-safe, default non-live
- Release verdict: fixture-verified personal workstation candidate with production-live Schwab readiness still unproven

## Contract Boundary

- Supported target contracts: `ES`, `NQ`, `CL`, `6E`, `MGC`
- Excluded contracts: `ZN`, `GC`
- `MGC` is Micro Gold and is not `GC`.
- `GC` is not a synonym, substitute, label, alias, or runtime profile for `MGC`.
- `ZN` remains excluded from final target support and is not re-promoted by this cut.

## Authority Boundary

- Execution is manual-only on the operator's own platform.
- The app does not add broker, order, account, fill, P&L, or automated execution behavior.
- Pipeline decisions remain preserved-engine-derived.
- The preserved engine remains the sole decision authority.
- Replay, cockpit evidence, performance review, readiness summaries, and release records are review-only surfaces.
- Review metrics are descriptive only and do not prove statistical edge.
- No query authorization can be derived from review metrics.
- Stale, missing, unsupported, lockout, invalidated, non-provenance, partial-bar, missing-bar, unavailable dependency, derived-without-source, review-derived, or display-derived states must not produce `QUERY_READY`.

## Runtime Boundary

- Default launch is non-live.
- Live behavior remains explicitly opt-in.
- Fixture-safe default tests require no Schwab credentials.
- No fixture fallback after live failure remains preserved.
- The 15-second minimum refresh floor remains preserved.
- The release-candidate harness does not run a live Schwab rehearsal, read secret or token file contents, log in, subscribe, or connect to Schwab.

## Recorded D3 Live Rehearsal Interpretation

The sanitized D3 five-contract live rehearsal result remains **PARTIAL / FAIL-CLOSED**.

| D3 check | Recorded value |
|---|---|
| live_login_succeeded | yes |
| live_subscribe_succeeded | yes |
| subscribed_contracts_count | 5 |
| market_data_received | no |
| received_contracts_count | 0 |
| repeated_login_on_refresh | no |
| cleanup_status | ok |
| values_printed | no |

This proves only that the explicitly authorized live path reached streamer metadata retrieval, runtime start, login, and a reported five-contract subscription without printed sensitive values.

This does not prove production-live Schwab readiness. It does not prove `LEVELONE_FUTURES` real delivery across `ES`, `NQ`, `CL`, `6E`, and `MGC` in the workstation loop. It does not prove production live `CHART_FUTURES` delivery. Because `market_data_received=no` and `received_contracts_count=0`, the workstation must remain fail-closed from the D3 result.

## Release-Candidate Statement

This release candidate is honest only as a fixture-safe personal workstation candidate. It verifies repository-owned boundaries around supported contracts, fail-closed query gating, manual-only execution, preserved-engine decision authority, evidence/replay attribution, cockpit event evidence, redaction, D2 dry-run safety, the D3 partial/fail-closed record, and descriptive performance review.

Production-live Schwab readiness remains unproven until a future explicitly authorized manual live rehearsal records sanitized live market-data delivery evidence for the final target universe.
