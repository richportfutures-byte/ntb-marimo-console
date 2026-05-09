# Release-Candidate Sign-Off

This runbook is the bounded sign-off path for the amended current phase.

Use it only after development work is believed complete.

## Clean Workspace Precondition

The final release-candidate acceptance run must start from a clean workspace.

From the repository root:

```powershell
cd C:\Users\stuar\ntb-marimo-console
git status --short
```

Passing condition:

- no output

If any output appears, stop. Resolve the workspace state before claiming release-candidate acceptance.

## Windows Acceptance Command

From `target/ntb_marimo_console`:

```powershell
cd C:\Users\stuar\ntb-marimo-console\target\ntb_marimo_console
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe scripts\run_windows_acceptance.py
```

Passing condition:

- `Overall Result: PASS`

If the command fails, stop and read the first failed section in the report.

## Manual Verification Checklist

Launch one supported preserved profile:

```powershell
cd C:\Users\stuar\ntb-marimo-console\target\ntb_marimo_console
$env:NTB_CONSOLE_PROFILE='preserved_es_phase1'; $env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m marimo run src\ntb_marimo_console\operator_console_app.py
```

Use in-app profile switching among final-target profiles such as `preserved_nq_phase1`, `preserved_cl_phase1`, `preserved_6e_phase1`, and `preserved_mgc_phase1`. Do not use blocked contracts.

### MV-1 Brief Language Is Actionable

For `preserved_es_phase1`, `preserved_nq_phase1`, and `preserved_cl_phase1`:

- read the rendered pre-market brief in the primary surface
- confirm the brief is understandable and actionable against the operator's own platform workflow
- reject sign-off if the brief reads like a placeholder, debug dump, or generic filler

### MV-2 Contract Language Remains Distinct

- compare the rendered ES and NQ pre-market briefs
- confirm ES and NQ do not collapse into the same causal vocabulary
- switch to CL and confirm the rendered CL brief keeps EIA-specific wording

### MV-3 Evidence And Run History Are Understandable Without Debug

Recommended sequence:

1. on ES, run `Run bounded query for loaded snapshot`
2. review `Run History`, `Decision Review`, and `Audit / Replay`
3. switch to NQ and repeat one bounded query
4. close the app
5. relaunch with any supported preserved profile
6. review `Recent Session Evidence` and confirm:
   - current-session versus restored-prior-run labels are understandable
   - ES and NQ attribution stays separate
   - the operator can understand the surfaces without opening `Debug (Secondary)`

Reject sign-off if run history, audit replay, or evidence require raw JSON interpretation to understand the primary result.

### MV-4 Trade Execution Remains Manual Only

Confirm all of the following:

- the app exposes bounded query and review surfaces only
- no order submission, broker routing, ATM control, or live trade automation control appears
- no profile or query action implies that a trade was placed automatically

Reject sign-off if any operator-facing surface suggests automated execution.

## Release-Candidate Sign-Off Decision

The phase is ready for sign-off only when:

- the workspace is clean
- the Windows acceptance command passes
- MV-1 through MV-4 are all confirmed by the operator

If any one of those fails, the phase is not signed off.
