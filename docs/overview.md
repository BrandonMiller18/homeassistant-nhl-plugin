---
type: Project
title: NHL Companion
description: Home Assistant custom integration (HACS) that follows NHL teams and turns live games into HA events, entities, blueprints and dashboard cards.
resource: custom_components/nhl_companion
generated: {by: claude/opus-5.5, at: 2026-10-14T05:41:07Z}
---
v2 of NHL Companion. v1 was three hosted services (DB-sync CLI + MySQL, FastAPI on Heroku, Next.js on Vercel); v2 replaces all of them with one HA integration that calls the NHL API directly. See [why](/decisions/ha-integration-emits-events.md).

**Does not**: perform actions itself (horns, lights, TTS live in blueprints), store history, or use any API key or server.

User-facing reference (entities, event types, payloads, options, card YAML) lives in `README.md`; don't duplicate it here.

## Run / test
- `pytest` needs Linux/macOS (Home Assistant won't install on Windows). On Windows use WSL or rely on CI.
- No live game? `nhl_companion.simulate_event` fires one event; `scripts/mock_nhl_server.py` plays a whole scripted game — point the hidden "NHL API base URL" option at it.
- New replay test from a real game: `scripts/record_live.py` then `scripts/trim_recording.py` (run in the test venv; it imports the integration).
- Release: `scripts/bump_version.py` (keeps `manifest.json` and `const.py` in sync) → merge → tag `vX.Y.Z` on `main`. The Release workflow refuses tags that don't match the manifest or aren't on `main`. `b`/`rc` versions publish as pre-releases for HACS beta testing.

## Map
- [Event pipeline](/architecture/event-pipeline.md) — feed → detector → gated, delayed events
- [Polling and caching](/architecture/polling-and-caching.md) — adaptive intervals, CDN alignment, shared clients
- [NHL web API](/integrations/nhl-web-api.md) — undocumented API plus Brightcove clips
- [NHL feed quirks](/gotchas/nhl-feed-quirks.md) — what the live feed does that the schema doesn't say
- [Managed blueprints](/gotchas/managed-blueprints.md) — overwritten on start; restart quirks
