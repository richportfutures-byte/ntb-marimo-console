# ntb-marimo-console

Marimo operator console for the frozen Phase 1 integration slice.

This repo is the only place new UI, adapter, state, artifact-ingestion, launch, and bootstrap code should be written.
Preserved engine logic remains in `../../source/ntb_engine`.
Reference-only product-shell ideas remain in `../../reference/ntb_v3_idea`.

## Operator Quickstart

1. Bootstrap the target environment:

   Windows PowerShell:

   ```powershell
   powershell.exe -ExecutionPolicy Bypass -File .\scripts\bootstrap_target_env.ps1
   ```

   If Python 3.11+ is not on `PATH`, point the bootstrap script at it explicitly:

   ```powershell
   powershell.exe -ExecutionPolicy Bypass -File .\scripts\bootstrap_target_env.ps1 -PythonExe C:\path\to\python.exe
   ```

   POSIX shells:

   ```bash
   ./scripts/bootstrap_target_env.sh
   ```

2. List supported runtime profiles:

   Windows PowerShell:

   ```powershell
   $env:PYTHONPATH='src'; .\.venv\Scripts\python.exe scripts\list_runtime_profiles.py
   ```

   POSIX shells:

   ```bash
   PYTHONPATH=src .venv/bin/python scripts/list_runtime_profiles.py
   ```

3. Run the single Windows acceptance command:

   Windows PowerShell:

   ```powershell
   $env:PYTHONPATH='src'; .\.venv\Scripts\python.exe scripts\run_windows_acceptance.py
   ```

   A passing result means the current bounded Windows console scope is usable on this machine:

   - bootstrap/import assumptions are usable
   - supported profiles can be listed and all pass strict preflight
   - blocked contracts remain fail-closed and are reported truthfully
   - the validator-driven Watchman gate regression slice passes
   - JSONL-backed Run History / Audit Replay regression slices pass
   - the retained-evidence regression slice passes
   - the documented direct launch path reaches bounded startup with the target-owned Marimo runtime path

   This acceptance command does not do browser automation or in-app clicking. It proves bounded startup/readiness plus the named target regression slices.

   A failing result means at least one acceptance gate failed. Read the named section and failed check summary first.

4. Audit preserved-contract eligibility:

   Windows PowerShell:

   ```powershell
   $env:PYTHONPATH='src'; .\.venv\Scripts\python.exe scripts\audit_preserved_contract_eligibility.py
   ```

   POSIX shells:

   ```bash
   PYTHONPATH=src .venv/bin/python scripts/audit_preserved_contract_eligibility.py
   ```

5. Start the console with one supported profile:

   Fixture/demo:

   Windows PowerShell:

   ```powershell
   $env:NTB_CONSOLE_PROFILE='fixture_es_demo'; $env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m marimo run src\ntb_marimo_console\operator_console_app.py
   ```

   POSIX shells:

   ```bash
   NTB_CONSOLE_PROFILE=fixture_es_demo \
   PYTHONPATH=src .venv/bin/python -m marimo run src/ntb_marimo_console/operator_console_app.py
   ```

   Supported preserved profiles for the five final target contracts (`ES`, `NQ`, `CL`, `6E`, `MGC`):

   POSIX shells:

   ```bash
   NTB_CONSOLE_PROFILE=preserved_es_phase1 \
   PYTHONPATH=src .venv/bin/python -m marimo run src/ntb_marimo_console/operator_console_app.py
   ```

   ```bash
   NTB_CONSOLE_PROFILE=preserved_nq_phase1 \
   PYTHONPATH=src .venv/bin/python -m marimo run src/ntb_marimo_console/operator_console_app.py
   ```

   ```bash
   NTB_CONSOLE_PROFILE=preserved_cl_phase1 \
   PYTHONPATH=src .venv/bin/python -m marimo run src/ntb_marimo_console/operator_console_app.py
   ```

   ```bash
   NTB_CONSOLE_PROFILE=preserved_6e_phase1 \
   PYTHONPATH=src .venv/bin/python -m marimo run src/ntb_marimo_console/operator_console_app.py
   ```

   ```bash
   NTB_CONSOLE_PROFILE=preserved_mgc_phase1 \
   PYTHONPATH=src .venv/bin/python -m marimo run src/ntb_marimo_console/operator_console_app.py
   ```

   Windows PowerShell:

   ```powershell
   $env:NTB_CONSOLE_PROFILE='preserved_es_phase1'; $env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m marimo run src\ntb_marimo_console\operator_console_app.py
   ```

   ```powershell
   $env:NTB_CONSOLE_PROFILE='preserved_nq_phase1'; $env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m marimo run src\ntb_marimo_console\operator_console_app.py
   ```

   ```powershell
   $env:NTB_CONSOLE_PROFILE='preserved_cl_phase1'; $env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m marimo run src\ntb_marimo_console\operator_console_app.py
   ```

   ```powershell
   $env:NTB_CONSOLE_PROFILE='preserved_6e_phase1'; $env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m marimo run src\ntb_marimo_console\operator_console_app.py
   ```

   ```powershell
   $env:NTB_CONSOLE_PROFILE='preserved_mgc_phase1'; $env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m marimo run src\ntb_marimo_console\operator_console_app.py
   ```

   `preserved_zn_phase1` is not a target app runtime profile; direct launch attempts fail closed.

6. Read the app’s `Startup Status` section before using the operator surfaces:

   - `Preflight Status: PASS`
   - `Readiness State: OPERATOR_SURFACES_READY`
   - `Operator Ready: True`

7. If startup is blocked, read the `Blocking Diagnostics` and `Next Action` lines in the app, fix the issue, and restart.

8. After startup passes, use the app’s `Session Lifecycle`, `Session Workflow`, and `Live Query` sections:

   - `Five-Contract Readiness Summary` shows one fixture-safe, non-live row each for `ES`, `NQ`, `CL`, `6E`, and `MGC`.
   - The summary reports profile id, startup readiness, default market-data availability, trigger/query gate state, blocked reasons, evidence/replay status, and the manual-only/preserved-engine boundary.
   - `Market data unavailable` is expected in default launch because live Schwab access is explicitly opt-in.
   - The summary is an operator visibility surface only. It does not prove real Schwab readiness and cannot authorize trades.
   - `Live Query Status: ELIGIBLE` means the loaded snapshot satisfies the current query gate.
   - `Query Action Status: AVAILABLE` means the in-app bounded query button can be used.
   - `Decision Review Ready: True` appears only after the bounded query action completes successfully.
   - `Audit / Replay Ready: True` appears only after the bounded query action completes and the bounded replay surface is loaded.
   - `Reset Session` clears the current bounded query cycle while keeping the selected profile loaded.
   - `Reload Current Profile` reruns preflight and reloads the selected profile from its declared artifact source.

## Multi-Profile Operation

Once the app is running, the operator can work across the currently supported profiles without restarting Marimo:

- `Supported Profile Operations` shows every supported profile, whether it is `Demo` or `Preserved`, and which candidate contracts remain blocked.
- `Profile Selector` only offers currently supported profiles.
- `Switch To Selected Profile` reruns preflight and rebuilds the session from the newly selected profile's declared artifacts.
- A completed profile switch clears bounded query, Decision Review, Audit / Replay, and other session-specific state from the prior profile before the new profile becomes active.
- If a requested profile switch does not complete, the prior active profile remains loaded and the app reports the blocked or failed switch in `Session Lifecycle`.

## Bootstrap

Windows PowerShell:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\bootstrap_target_env.ps1
```

If Python 3.11+ is not on `PATH`:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\bootstrap_target_env.ps1 -PythonExe C:\path\to\python.exe
```

POSIX shells:

```bash
./scripts/bootstrap_target_env.sh
```

Bootstrap behavior:

- Recreates `.venv` for this workspace using Python 3.11+.
- Installs the preserved engine package from `../../source/ntb_engine`.
- Installs the target package plus dev and preserved-engine support dependencies from `target/ntb_marimo_console`.
- Injects `target/ntb_marimo_console/src` and `../../source/ntb_engine/src` into the target virtualenv via a workspace `.pth` file.
- Refreshes all supported preserved runtime-profile artifacts with `scripts/refresh_runtime_profile_artifacts.py`.
- Verifies imports for `marimo`, `ntb_marimo_console`, `ninjatradebuilder`, and `pydantic`.

## Windows Acceptance

Windows PowerShell:

```powershell
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe scripts\run_windows_acceptance.py
```

What it verifies:

- environment/bootstrap imports and target-owned Marimo runtime path preparation
- supported profile listing for `fixture_es_demo`, `preserved_es_phase1`, `preserved_nq_phase1`, `preserved_6e_phase1`, `preserved_mgc_phase1`, and `preserved_cl_phase1`
- strict preflight for every supported profile
- no remaining blocked final-target onboarding candidate reporting
- validator-driven Watchman gate regression coverage
- JSONL-backed Run History / Audit Replay regression coverage
- retained-evidence regression coverage via the target pytest slice
- bounded direct startup for the documented preserved-profile launch path

What it does not verify:

- browser automation
- in-app clicking or profile switching
- live market behavior beyond the frozen bounded startup path

What a passing result means:

- the current supported Windows console scope is ready for bounded operator/developer use on this machine

What a failing result means:

- at least one named readiness gate failed; read the failed section and check summary first

## Release-Candidate Sign-Off

Use the bounded operator sign-off runbook when the build is believed complete:

- [docs/release_candidate_signoff.md](docs/release_candidate_signoff.md)

It covers:

- the clean-workspace precondition
- the single Windows acceptance command
- the four manual verification items from the acceptance matrix

## List Supported Profiles

Windows PowerShell:

```powershell
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe scripts\list_runtime_profiles.py
```

POSIX shells:

```bash
PYTHONPATH=src .venv/bin/python scripts/list_runtime_profiles.py
```

Current supported profiles:

Final target preserved profiles (`ES`, `NQ`, `CL`, `6E`, `MGC`):

- `preserved_es_phase1`: preserved-engine-backed ES profile using the target-owned preserved fixture adapter by default
- `preserved_nq_phase1`: preserved-engine-backed NQ profile using the target-owned preserved fixture adapter by default
- `preserved_cl_phase1`: preserved-engine-backed CL profile using the target-owned preserved fixture adapter by default
- `preserved_6e_phase1`: preserved-engine-backed 6E profile using the target-owned preserved fixture adapter by default
- `preserved_mgc_phase1`: preserved-engine-backed MGC (Micro Gold) profile using the target-owned preserved fixture adapter by default

Fixture/demo profile:

- `fixture_es_demo`: fixture-backed ES regression/demo profile

`MGC` is the Micro Gold contract for this application. `MGC` is not `GC`; `GC` is excluded and must not be used as a synonym, alias, or substitute for `MGC`.

## Five-Contract Readiness Summary

The operator console includes a fixture-backed five-contract readiness summary in non-live mode. It is built without Schwab credentials and appears in the app shell alongside the existing single-profile surfaces.

The summary includes exactly the five final target contracts:

- `ES`
- `NQ`
- `CL`
- `6E`
- `MGC`

`ZN` and `GC` do not appear as final-target readiness rows. The summary reports default live market data as unavailable unless an explicit fixture/non-live input is provided, and it keeps query readiness blocked when the existing gate conditions are not met.

This surface does not replace real Schwab proof. Real five-contract live readiness still requires explicit live opt-in and a sanitized reviewed proof artifact.

## Audit Preserved Contract Eligibility

Windows PowerShell:

```powershell
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe scripts\audit_preserved_contract_eligibility.py
```

POSIX shells:

```bash
PYTHONPATH=src .venv/bin/python scripts/audit_preserved_contract_eligibility.py
```

Interpretation:

- `Supported Now` means the profile is already committed under the current target-owned registry and passes strict preflight.
- `Viable To Onboard Now` means the candidate survives target-template materialization, preserved artifact generation, strict preflight, and bounded app assembly without special-case relaxation.
- `Blocked` means the candidate is not supportable yet; the report prints the exact reason category.

Current blocked candidates:

- none

How this appears in the app:

- `Supported Profile Operations` shows the same supported-versus-blocked split in readable operator language.
- Blocked candidates remain awareness-only if the audit reports any in a future roadmap step; they do not become selectable in `Profile Selector`.

Current onboarding rule:

- A new preserved profile is added only when the audit produces exactly one `Viable To Onboard Now` candidate.
- Once committed, that contract moves into `Supported Now` and is launched through `NTB_CONSOLE_PROFILE=<profile_id>`.

## Run Preflight

Fixture/demo profile:

Windows PowerShell:

```powershell
$env:NTB_CONSOLE_PROFILE='fixture_es_demo'; $env:PYTHONPATH='src'; .\.venv\Scripts\python.exe scripts\run_runtime_preflight.py
```

POSIX shells:

```bash
NTB_CONSOLE_PROFILE=fixture_es_demo \
PYTHONPATH=src .venv/bin/python scripts/run_runtime_preflight.py
```

Supported preserved profiles:

Windows PowerShell:

```powershell
$env:NTB_CONSOLE_PROFILE='preserved_cl_phase1'; $env:PYTHONPATH='src'; .\.venv\Scripts\python.exe scripts\run_runtime_preflight.py
```

```powershell
$env:NTB_CONSOLE_PROFILE='preserved_es_phase1'; $env:PYTHONPATH='src'; .\.venv\Scripts\python.exe scripts\run_runtime_preflight.py
```

POSIX shells:

```bash
NTB_CONSOLE_PROFILE=preserved_cl_phase1 \
PYTHONPATH=src .venv/bin/python scripts/run_runtime_preflight.py
```

```bash
NTB_CONSOLE_PROFILE=preserved_es_phase1 \
PYTHONPATH=src .venv/bin/python scripts/run_runtime_preflight.py
```

Interpretation:

- `Runtime Preflight: PASS` means the selected profile, dependencies, artifacts, and adapter binding are all consistent with the current strict runtime contract.
- `Runtime Preflight: FAIL` means launch should be treated as blocked until the reported category is fixed.
- Preflight never mutates artifacts and never relaxes validation to make a bad profile pass.
- The app now surfaces the same readiness concept in `Startup Status`; blocked preflight remains fail-closed inside the UI.

## Launch The Fixture/Demo Profile

Windows PowerShell:

```powershell
$env:NTB_CONSOLE_PROFILE='fixture_es_demo'; $env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m marimo run src\ntb_marimo_console\operator_console_app.py
```

POSIX shells:

```bash
NTB_CONSOLE_PROFILE=fixture_es_demo \
PYTHONPATH=src .venv/bin/python -m marimo run src/ntb_marimo_console/operator_console_app.py
```

## Launch The Supported Preserved Profiles

Final target preserved profiles for `ES`, `NQ`, `CL`, `6E`, and `MGC`.

POSIX shells:

```bash
NTB_CONSOLE_PROFILE=preserved_es_phase1 \
PYTHONPATH=src .venv/bin/python -m marimo run src/ntb_marimo_console/operator_console_app.py
```

```bash
NTB_CONSOLE_PROFILE=preserved_nq_phase1 \
PYTHONPATH=src .venv/bin/python -m marimo run src/ntb_marimo_console/operator_console_app.py
```

```bash
NTB_CONSOLE_PROFILE=preserved_cl_phase1 \
PYTHONPATH=src .venv/bin/python -m marimo run src/ntb_marimo_console/operator_console_app.py
```

```bash
NTB_CONSOLE_PROFILE=preserved_6e_phase1 \
PYTHONPATH=src .venv/bin/python -m marimo run src/ntb_marimo_console/operator_console_app.py
```

```bash
NTB_CONSOLE_PROFILE=preserved_mgc_phase1 \
PYTHONPATH=src .venv/bin/python -m marimo run src/ntb_marimo_console/operator_console_app.py
```

Windows PowerShell:

```powershell
$env:NTB_CONSOLE_PROFILE='preserved_es_phase1'; $env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m marimo run src\ntb_marimo_console\operator_console_app.py
```

```powershell
$env:NTB_CONSOLE_PROFILE='preserved_nq_phase1'; $env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m marimo run src\ntb_marimo_console\operator_console_app.py
```

```powershell
$env:NTB_CONSOLE_PROFILE='preserved_cl_phase1'; $env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m marimo run src\ntb_marimo_console\operator_console_app.py
```

```powershell
$env:NTB_CONSOLE_PROFILE='preserved_6e_phase1'; $env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m marimo run src\ntb_marimo_console\operator_console_app.py
```

```powershell
$env:NTB_CONSOLE_PROFILE='preserved_mgc_phase1'; $env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m marimo run src\ntb_marimo_console\operator_console_app.py
```

These use profile-bound default adapter references:

- `ntb_marimo_console.preserved_fixture_adapter:adapter` (ES)
- `ntb_marimo_console.preserved_fixture_adapter:adapter_nq`
- `ntb_marimo_console.preserved_fixture_adapter:adapter_cl`
- `ntb_marimo_console.preserved_fixture_adapter:adapter_6e`
- `ntb_marimo_console.preserved_fixture_adapter:adapter_mgc`

`preserved_zn_phase1` is intentionally omitted from the launch set above and fails closed if requested directly.

## Override The Preserved Adapter

Windows PowerShell:

```powershell
$env:NTB_CONSOLE_PROFILE='preserved_es_phase1'; $env:NTB_MODEL_ADAPTER_REF='your_package.your_module:your_adapter'; $env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m marimo run src\ntb_marimo_console\operator_console_app.py
```

POSIX shells:

```bash
NTB_CONSOLE_PROFILE=preserved_es_phase1 \
NTB_MODEL_ADAPTER_REF=your_package.your_module:your_adapter \
PYTHONPATH=src .venv/bin/python -m marimo run src/ntb_marimo_console/operator_console_app.py
```

## Runtime Selection Notes

- `NTB_CONSOLE_PROFILE` is the primary operator-facing selector.
- `NTB_CONSOLE_PROFILE` chooses the initial profile when the app launches.
- After launch, `Profile Selector` can switch between the currently supported profiles without restarting the app.
- The active profile is reflected in `Startup Status`, `Supported Profile Operations`, `Runtime Identity`, and `Session Lifecycle`.
- Direct `PYTHONPATH=src ... -m marimo run ...` launches pin Marimo config, cache, and state to the target-owned path under `target/ntb_marimo_console/.state/marimo`; the console does not rely on `C:\Users\<user>\.config\marimo` or `C:\Users\<user>\.marimo`.
- The selected profile is reflected in the app’s `Startup Status` section along with the full supported-profile list.
- `NTB_CONSOLE_MODE` is optional compatibility plumbing. If you set it explicitly, it must match the selected profile’s required runtime mode.
- `NTB_FIXTURES_ROOT=/path/to/artifact-root` optionally points the console at a different artifact tree root.
- `NTB_FIXTURE_LOCKOUT=true` forces the fixture runtime into a locked-out readiness path for testing.
- `scripts/audit_preserved_contract_eligibility.py` prints the current supported/blocked preserved-contract audit with explicit reason categories.
- `scripts/refresh_runtime_profile_artifacts.py` refreshes all supported preserved profiles.
- `scripts/run_runtime_preflight.py` prints a readable fail-closed report for the selected profile without launching Marimo.
- `scripts/refresh_preserved_es_artifacts.py` remains as a narrow compatibility shim for the current ES preserved profile.

## In-Session Workflow

After startup passes, the operator workflow is explicit:

- `Session Lifecycle` shows whether the session is carrying the current loaded context, has been reset, or has been reloaded.
- `Session Lifecycle` also shows whether a reload reran preflight and whether the declared source artifacts changed.
- `Session Workflow` shows the current in-session state and history.
- `Live Query` shows whether the current loaded snapshot is blocked or eligible.
- The in-app query button runs a bounded Phase 1 pipeline query only against the currently loaded snapshot.
- The query action does not place orders, simulate fills, or imply execution success.
- `Decision Review` remains not ready until the bounded query action completes.
- `Audit / Replay` remains not ready until the bounded query action completes and the bounded replay payload is loaded.

High-level query eligibility:

- Watchman readiness must not be blocked by hard lockout flags.
- At least one declared boolean query trigger must be true on explicit observable fields.
- No manual override path exists in Phase 1.

If the live query is blocked, the app tells the operator why in plain language and keeps the action fail-closed.

## Session Lifecycle Controls

The Phase 1 console is still bounded to manual operator use, but it now supports repeatable session cycles:

- `Switch To Selected Profile` reruns preflight against the selected supported profile, rebuilds the session from that profile's declared artifacts, and clears cross-profile session state on success.
- `Clear Retained Evidence` removes only the durable retained evidence file under the target-owned `.state` path. It does not fabricate a new lifecycle event and does not alter the preserved engine.
- `Run bounded query for loaded snapshot` executes the bounded pipeline only against the currently loaded runtime context.
- `Reset Session` clears bounded query progress, Decision Review, and Audit / Replay while leaving the current profile selection and loaded runtime context intact.
- `Reload Current Profile` reruns preflight and rebuilds the current profile from its declared artifact source.

What reload can and cannot do:

- Reload is manual. It does not create a live refresh loop.
- Reload can report that source artifacts were unchanged. That means the console revalidated and reloaded the same declared inputs.
- Reload fails closed if artifacts, adapter bindings, or dependencies become invalid.
- Profile switch fails closed if the requested target is blocked, unsupported, or does not pass validation/runtime assembly.
- A completed profile switch clears bounded query, Decision Review, Audit / Replay, and other session-specific state from the previous contract before the new profile becomes active.
- After either reset or reload, `Decision Review` and `Audit / Replay` return to not-ready until a new bounded query completes.

How to tell whether the session is fresh:

- `Session Lifecycle` shows the last lifecycle action.
- `Profile Switch Result: SWITCH_COMPLETED` means the active profile changed and the session was rebuilt from the newly selected profile.
- `Profile Switch Result: SWITCH_BLOCKED` means the requested profile never became active; the prior active profile remained loaded.
- `Reload Result: RELOADED_CHANGED` means new source artifacts were loaded.
- `Reload Result: RELOADED_UNCHANGED` means the source files were revalidated and reloaded, but they did not change.
- `Session Lifecycle State: SESSION_RESET_COMPLETED` means the session was cleared back to the current loaded profile context.

## Recent Session Evidence

The Phase 1 console now keeps a bounded recent-session evidence ledger in a target-owned repo-local file and restores it on startup.

- Persistence location: `target/ntb_marimo_console/.state/recent_session_evidence.v1.json`
- Evidence uses ordered event markers plus real UTC record timestamps; it does not fabricate wall-clock data.
- Every record stays attached to the profile that was actually active when that lifecycle outcome occurred.
- `Recent Session Evidence` shows the persistence path, restore status, persistence health, last persistence status, active profile now, current-session versus restored-prior-run counts, the recently used supported profiles, the last known outcome by supported profile, and the most recent activity entries.
- `Last Known Outcome By Supported Profile` means the newest retained evidence entry for that profile in the bounded persisted ledger.
- `Current Session` versus `Restored Prior Run` labels make it explicit whether an outcome came from this running app session or was restored from an earlier one.
- A supported profile with no retained evidence remains explicit as `NO_RECENT_SESSION_EVIDENCE`.

What profile separation means:

- If ES is queried and then the operator switches to another final-target profile such as NQ, ES keeps its own last known query/decision/audit outcome.
- NQ becomes active with a fresh session context and its own new evidence entry.
- A blocked or failed profile switch remains attributed to the currently active originating profile plus the requested target; it does not create fake success evidence for the blocked target.
- After the app is closed and relaunched, restored ES and NQ evidence still remain attached to ES and NQ until a newer event for one of those profiles is recorded.

What reset and reload mean in evidence:

- `Reset Session` records that the active profile stayed the same while bounded query, Decision Review, and Audit / Replay were cleared.
- `Reload Current Profile` records whether the active profile reloaded successfully, reloaded unchanged, or failed closed.
- Failed, blocked, available, completed, and ready/not-ready states remain distinct; the evidence layer does not collapse them into a single success/failure badge.

Restore behavior:

- Missing persistence file is acceptable and starts a fresh bounded ledger.
- Corrupt or incompatible persistence data is ignored fail-closed and reported in the `Restore Status` / `Restore Summary` lines.
- `Persistence Health` and `Last Persistence Status` report only grounded write or clear outcomes for the target-owned retained evidence file.
- `Clear Retained Evidence` intentionally clears only durable retained evidence. Current-session evidence remains visible until restart or subsequent actions.
- The console rewrites the bounded ledger atomically after each recorded evidence event.

## Fail-Closed Startup Errors

The console fails closed on startup when any of these are materially wrong:

- unsupported `NTB_CONSOLE_PROFILE`
- malformed or incomplete runtime-profile definitions
- mismatched explicit `NTB_CONSOLE_MODE`
- missing required artifact files
- artifacts that do not satisfy the required engine-facing contract
- missing runtime dependencies or broken bootstrap
- invalid or missing adapter references for preserved profiles

No implicit fallback occurs from preserved profiles to fixture profiles.

When startup is blocked in the app:

- `Startup Status` shows the selected profile, running mode, preflight result, readiness state, and next action.
- `Supported Profile Operations` still shows which supported profiles remain selectable and which candidate contracts are blocked.
- `Blocking Diagnostics` gives the failure category plus the high-level remedy.
- The primary operator surfaces remain blocked until startup is valid. Raw shell JSON remains available only in `Debug (Secondary)`.

## Fail-Closed Session States

Inside a running session, the console still fails closed when:

- live query conditions are not eligible
- a query action is requested against an ineligible snapshot
- the bounded query action itself fails
- decision review is not actually ready
- audit/replay is not actually ready

Blocked states look blocked. Completed states appear only after the bounded workflow reaches them.

## Scope Boundaries

Functional in this slice:

- session header and operator runtime metadata
- pre-market brief rendering from frozen artifacts
- readiness matrix rendering from fixture-backed or preserved-engine-backed watchman context
- live observables, trigger evaluation, query gating, and decision review
- fixture-backed run history and bounded audit/replay surfaces

Still bounded/frozen:

- no manual override path
- no live-backed Stage E ingestion
- no speculative non-registered profiles
- no UI-side market logic beyond rendering and explicit trigger evaluation
