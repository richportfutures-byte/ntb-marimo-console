# Active Workstream: Operator Testing Module V0

This document is the current execution target for NTB Marimo Console.

It supersedes older audit-heavy prompt queues where they conflict with operator-first execution.

## Current target

Ship Operator Testing Module V0.

The app is not done merely because backend live data works. The app is ready for operator testing only when the top notebook surface lets the operator understand the live workflow within 10 seconds.

## Required app work now

1. Build the top-level Operator Testing Module V0 surface.
2. Make ES, NQ, CL, 6E, and MGC rows the operational center.
3. Remove fixture/demo profile names from primary live-screen identity.
4. Move verbose explanatory/debug/lifecycle prose below the operational surface.
5. Add one clear top-level blocker and one next safe action.
6. Add rendered-surface tests for the actual operator-facing text.
7. Add a one-command live operator launch wrapper if the current launch path remains too error-prone.
8. Add a focused operator-module acceptance command if needed.

## Definition of done for V0

The operator can launch the cockpit and immediately see:

- live runtime status,
- provider status,
- quote status,
- chart status,
- query gate state,
- one top blocker,
- one next safe action,
- ES, NQ, CL, 6E, MGC only,
- manual query disabled unless preserved-engine QUERY_READY provenance exists.

## Backlog, not blockers

These do not block V0 unless they mislead the operator:

- cosmetic layout polish,
- old internal profile names shown only as secondary/debug text,
- historical roadmap cleanup,
- broad release-candidate hardening,
- performance review expansion,
- long-form documentation.

## Next-step rule

If the live cockpit screen is coherent and manual query remains fail-closed without QUERY_READY provenance, the next step is operator testing.

If the screen is incoherent, fix the observed screen blocker.

If operator testing reveals a real workflow blocker, fix that blocker.

Do not return to protocol review unless the protocol itself is the concrete blocker.
