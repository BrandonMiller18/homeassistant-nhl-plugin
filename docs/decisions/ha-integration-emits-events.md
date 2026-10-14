---
type: Decision
title: HA custom integration that emits events; blueprints do the actions
description: Why v2 is a HACS custom integration with typed events, bundled blueprints and cards, one config entry per team.
status: stable
generated: {by: claude/opus-5.5, at: 2026-10-14T05:41:07Z}
---
**Context**: v1 ran a DB, a hosted API and a separate web frontend; its audio/webhook flags were never implemented. The existing HACS option, `vasqued2/ha-teamtracker` (ESPN), only allows a goal horn via score-change state triggers — no scorer, assists, strength or reversal events.

**Decision** (confirmed with the user):
- Packaging: custom integration via HACS, not a Supervisor add-on. HA is runtime, automation engine and display.
- The integration only emits rich, typed events; shipped blueprints perform the actions (audio, lights, TTS, video).
- Cards and blueprints are bundled and auto-registered/installed, so users install one HACS repo with no manual resource or blueprint import step.
- One config entry per team; following more teams means adding the integration again.

**Why**: users get automation-editor triggers with scorer/assist data, a broadcast-delay offset and a master alerts switch — things ha-teamtracker can't offer — without hosting anything.

**Deferred**: cards are vanilla JS custom elements (no build step) rather than the planned Lit + TypeScript with visual editors; HACS default-store submission waits on real-game soak testing.
