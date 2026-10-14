---
type: Gotcha
title: NHL live feed edits itself
description: Live play-by-play behaviours seen in a recorded game that the schema doesn't reveal, and how the detector copes.
resource: custom_components/nhl_companion/event_detector.py
tags: [nhl-api, events]
sources:
  - {resource: tests/fixtures/replay/stl_ott_2026020096.json.gz, title: "STL @ OTT, 2026-10-13, recorded live"}
generated: {by: claude/opus-5.5, at: 2026-10-14T05:41:07Z}
---
**Symptom**: naive diffing of play-by-play announces wrong assists, phantom penalties, misses goals, or ends games late.

**Cause / fix** (all observed in the STL @ OTT recording):
- **Assists arrive late**: scorer/assists filled in or changed 20–60 s after most goals → fire the goal immediately, then `goal_updated` with `changed`. Changes to `shot_type`/`time_in_period` do *not* fire `goal_updated`.
- **Plays turn into goals**: a play first posted as a missed shot later became a goal (twice in one game) → detector re-checks known plays, not just new `eventId`s.
- **Placeholder penalties**: posted as `minor`/`major`/`penalty`, later replaced (`holding`, `fighting`) or deleted → held up to `MAX_PENALTY_HOLD_POLLS` (6) polls before firing.
- **`OVER` state**: the final horn shows `OVER` ~20 s before `FINAL` → game end fires on `OVER`.
- **Power play**: taken from the feed's `situation` block, which can be wrong for ~40 s (e.g. during fights) or drop out for one update; fallback is the last play's skater counts, which lag until the next faceoff.
- **`drawn_by`** on penalties may be missing/wrong and corrected later; there is no `penalty_updated` event.

**Avoid**: when changing detection, capture a new game with `scripts/record_live.py` (it logs every `AMEND`/`REMOVED` play) rather than trusting synthetic fixtures. OT, shootouts, empty-net goals and real reversals are still unseen live.
