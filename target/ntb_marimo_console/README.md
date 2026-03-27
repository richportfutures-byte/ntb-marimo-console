# ntb-marimo-console

Marimo operator console for the frozen Phase 1 integration slice.

This repo is the only place new UI, adapter, state, artifact-ingestion, launch, and bootstrap code should be written.
Preserved engine logic remains in `../../source/ntb_engine`.
Reference-only product-shell ideas remain in `../../reference/ntb_v3_idea`.

## Operator Quickstart

1. Bootstrap the target environment:

   ```bash
   ./scripts/bootstrap_target_env.sh
   ```

2. List supported runtime profiles:

   ```bash
   PYTHONPATH=src .venv/bin/python scripts/list_runtime_profiles.py
   ```

3. Start the console with one supported profile:

   Fixture/demo:

   ```bash
   NTB_CONSOLE_PROFILE=fixture_es_demo \
   PYTHONPATH=src .venv/bin/python -m marimo run src/ntb_marimo_console/operator_console_app.py
   ```

   Supported preserved profiles:

   ```bash
   NTB_CONSOLE_PROFILE=preserved_es_phase1 \
   PYTHONPATH=src .venv/bin/python -m marimo run src/ntb_marimo_console/operator_console_app.py
   ```

   ```bash
   NTB_CONSOLE_PROFILE=preserved_zn_phase1 \
   PYTHONPATH=src .venv/bin/python -m marimo run src/ntb_marimo_console/operator_console_app.py
   ```

4. Read the app’s `Startup Status` section before using the operator surfaces:

   - `Preflight Status: PASS`
   - `Readiness State: OPERATOR_SURFACES_READY`
   - `Operator Ready: True`

5. If startup is blocked, read the `Blocking Diagnostics` and `Next Action` lines in the app, fix the issue, and restart.

6. After startup passes, use the app’s `Session Lifecycle`, `Session Workflow`, and `Live Query` sections:

   - `Live Query Status: ELIGIBLE` means the loaded snapshot satisfies the current query gate.
   - `Query Action Status: AVAILABLE` means the in-app bounded query button can be used.
   - `Decision Review Ready: True` appears only after the bounded query action completes successfully.
   - `Audit / Replay Ready: True` appears only after the bounded query action completes and the bounded replay surface is loaded.
   - `Reset Session` clears the current bounded query cycle while keeping the selected profile loaded.
   - `Reload Current Profile` reruns preflight and reloads the selected profile from its declared artifact source.

## Bootstrap

```bash
./scripts/bootstrap_target_env.sh
```

Bootstrap behavior:

- Recreates `.venv` with `--system-site-packages` for this workspace.
- Injects `target/ntb_marimo_console/src` and `../../source/ntb_engine/src` into the target virtualenv via a workspace `.pth` file.
- Refreshes all supported preserved runtime-profile artifacts with `scripts/refresh_runtime_profile_artifacts.py`.
- Verifies imports for `marimo`, `ntb_marimo_console`, `ninjatradebuilder`, and `pydantic`.

## List Supported Profiles

```bash
PYTHONPATH=src .venv/bin/python scripts/list_runtime_profiles.py
```

Current supported profiles:

- `fixture_es_demo`: fixture-backed ES regression/demo profile
- `preserved_es_phase1`: preserved-engine-backed ES profile using the target-owned preserved fixture adapter by default
- `preserved_zn_phase1`: preserved-engine-backed ZN profile using the target-owned preserved fixture adapter by default

## Run Preflight

Fixture/demo profile:

```bash
NTB_CONSOLE_PROFILE=fixture_es_demo \
PYTHONPATH=src .venv/bin/python scripts/run_runtime_preflight.py
```

Supported preserved profiles:

```bash
NTB_CONSOLE_PROFILE=preserved_es_phase1 \
PYTHONPATH=src .venv/bin/python scripts/run_runtime_preflight.py
```

```bash
NTB_CONSOLE_PROFILE=preserved_zn_phase1 \
PYTHONPATH=src .venv/bin/python scripts/run_runtime_preflight.py
```

Interpretation:

- `Runtime Preflight: PASS` means the selected profile, dependencies, artifacts, and adapter binding are all consistent with the current strict runtime contract.
- `Runtime Preflight: FAIL` means launch should be treated as blocked until the reported category is fixed.
- Preflight never mutates artifacts and never relaxes validation to make a bad profile pass.
- The app now surfaces the same readiness concept in `Startup Status`; blocked preflight remains fail-closed inside the UI.

## Launch The Fixture/Demo Profile

```bash
NTB_CONSOLE_PROFILE=fixture_es_demo \
PYTHONPATH=src .venv/bin/python -m marimo run src/ntb_marimo_console/operator_console_app.py
```

## Launch The Supported Preserved Profiles

```bash
NTB_CONSOLE_PROFILE=preserved_es_phase1 \
PYTHONPATH=src .venv/bin/python -m marimo run src/ntb_marimo_console/operator_console_app.py
```

```bash
NTB_CONSOLE_PROFILE=preserved_zn_phase1 \
PYTHONPATH=src .venv/bin/python -m marimo run src/ntb_marimo_console/operator_console_app.py
```

These use profile-bound default adapter references:

- `ntb_marimo_console.preserved_fixture_adapter:adapter`
- `ntb_marimo_console.preserved_fixture_adapter:adapter_zn`

## Override The Preserved Adapter

```bash
NTB_CONSOLE_PROFILE=preserved_es_phase1 \
NTB_MODEL_ADAPTER_REF=your_package.your_module:your_adapter \
PYTHONPATH=src .venv/bin/python -m marimo run src/ntb_marimo_console/operator_console_app.py
```

```bash
NTB_CONSOLE_PROFILE=preserved_zn_phase1 \
NTB_MODEL_ADAPTER_REF=your_package.your_module:your_adapter \
PYTHONPATH=src .venv/bin/python -m marimo run src/ntb_marimo_console/operator_console_app.py
```

## Runtime Selection Notes

- `NTB_CONSOLE_PROFILE` is the primary operator-facing selector.
- The selected profile is reflected in the app’s `Startup Status` section along with the full supported-profile list.
- `NTB_CONSOLE_MODE` is optional compatibility plumbing. If you set it explicitly, it must match the selected profile’s required runtime mode.
- `NTB_FIXTURES_ROOT=/path/to/artifact-root` optionally points the console at a different artifact tree root.
- `NTB_FIXTURE_LOCKOUT=true` forces the fixture runtime into a locked-out readiness path for testing.
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

- `Run bounded query for loaded snapshot` executes the bounded pipeline only against the currently loaded runtime context.
- `Reset Session` clears bounded query progress, Decision Review, and Audit / Replay while leaving the current profile selection and loaded runtime context intact.
- `Reload Current Profile` reruns preflight and rebuilds the current profile from its declared artifact source.

What reload can and cannot do:

- Reload is manual. It does not create a live refresh loop.
- Reload can report that source artifacts were unchanged. That means the console revalidated and reloaded the same declared inputs.
- Reload fails closed if artifacts, adapter bindings, or dependencies become invalid.
- After either reset or reload, `Decision Review` and `Audit / Replay` return to not-ready until a new bounded query completes.

How to tell whether the session is fresh:

- `Session Lifecycle` shows the last lifecycle action.
- `Reload Result: RELOADED_CHANGED` means new source artifacts were loaded.
- `Reload Result: RELOADED_UNCHANGED` means the source files were revalidated and reloaded, but they did not change.
- `Session Lifecycle State: SESSION_RESET_COMPLETED` means the session was cleared back to the current loaded profile context.

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
