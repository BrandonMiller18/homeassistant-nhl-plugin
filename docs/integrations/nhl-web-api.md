---
type: Integration
title: NHL web API and Brightcove clips
description: The undocumented public NHL API the integration polls, and the Brightcove lookup behind goal videos.
resource: custom_components/nhl_companion/api.py
tags: [nhl-api, external]
sources:
  - {resource: "https://github.com/Zmalski/NHL-API-Reference", title: NHL-API-Reference}
  - {resource: "https://gitlab.com/dword4/nhlapi/-/blob/master/new-api.md", title: dword4 new-api.md}
generated: {by: claude/opus-5.5, at: 2026-10-14T05:41:07Z}
---
**NHL web API** (`api-web.nhle.com/v1`): unauthenticated, undocumented, community-referenced only. No key, no published quota. Endpoints used: league schedule, standings (also the source of the team list and logos — there is no teams endpoint), club season schedule, gamecenter play-by-play / landing / boxscore.
- Schema can change without notice, so `parser.py` reads every field defensively (`.get()` + defaults): a surprise degrades one field instead of breaking the entry.
- Any HTTP ≥400 or network error raises; the coordinator surfaces it as `UpdateFailed` and simply retries on its next interval (no exponential backoff, despite the original plan). Traffic shaping: [Polling and caching](/architecture/polling-and-caching.md).
- Base URL is a hidden option (`api_base_url`) used only to point at `scripts/mock_nhl_server.py`.
- Some sandboxed/cloud environments block the host; tests run fully offline on fixtures for that reason.

**Brightcove** (goal videos, `nhl_companion.play_highlight`): the Playback API needs a policy key, which the client reads from the NHL's public player config. It can change without notice; the client refetches it once when Brightcove rejects it. Stream URLs are signed with unknown lifetime, so they're looked up at play time, never cached in events. Clips post minutes after the goal (short ~5 min, full ~7–9 min) — fine for replays, too late for the horn.
