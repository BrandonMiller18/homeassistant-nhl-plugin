---
type: Flow
title: Event pipeline
description: How a play-by-play snapshot becomes an HA event, and the invariants that stop duplicate, replayed or unwanted alerts.
resource: custom_components/nhl_companion/coordinator.py
tags: [events, coordinator]
generated: {by: claude/opus-5.5, at: 2026-10-14T05:41:07Z}
---
`TeamCoordinator` (one per config entry = one team) fetches play-by-play, hands the snapshot to `EventDetector`, and dispatches the resulting `NhlEvent`s.

- **Detector is pure** (`event_detector.py`, no HA imports) so it can be table-tested and driven by `scripts/record_live.py` outside HA. All NHL schema knowledge stays in `parser.py`; the detector only sees models.
- **Baseline**: the first snapshot of a game emits nothing. Setting up mid-game or restarting never replays old goals.
- **Dedupe**: each event has a key; emitted keys are persisted per entry with `Store`, so a restart mid-game resumes instead of re-firing.
- **Mark before gate**: a key is recorded as emitted *before* the alerts switch and opponent filter are checked. Suppressed events are therefore never replayed when alerts turn back on — intentional.
- **Alert delay** (broadcast sync) schedules the fire with `async_call_later`; the switch is checked again at fire time, so turning alerts off during the delay drops the event.
- **Two surfaces, same payload**: bus event `nhl_companion_event` (blueprints, templated triggers) and `event.<team>_*` entities (UI triggers, last payload as attributes).
- **Reversals** are inferred (goal disappears, stops being a goal, or score drops) — the real shape of a challenge is still unverified (README "Known gaps").

Feed behaviours that shaped the detector: [NHL feed quirks](/gotchas/nhl-feed-quirks.md).
