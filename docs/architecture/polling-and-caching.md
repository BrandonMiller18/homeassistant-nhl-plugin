---
type: Flow
title: Polling and caching
description: How the integration keeps NHL API traffic to one poller per HA instance and times live polls to the CDN refresh.
resource: custom_components/nhl_companion/api.py
tags: [polling, api]
generated: {by: claude/opus-5.5, at: 2026-10-14T05:41:07Z}
---
v1's frontend polled every 3 s per viewer; v2 polls once per HA instance regardless of dashboards.

- **Shared per base URL**: one `NhlApiClient` and one `LeagueCoordinator` (schedule + standings) per API base URL, ref-counted across team entries in `__init__.py`. Two teams in the same game share play-by-play via the client's short per-URL response cache and per-URL lock (concurrent callers wait for one fetch). Keying by base URL lets one entry point at the mock server without disturbing the others.
- **Adaptive team interval**: idle hourly → game day every 5 min → pre-game (play-by-play starts 15 min before puck drop) → live at the configured interval. After a final it polls every 2 min until the three stars post.
- **CDN alignment**: live play-by-play is rebuilt every ~20 s behind Cloudflare `max-age=19`. The client reads `max-age` and schedules the next poll ~1.5 s (`CDN_REFRESH_SLACK`) after the cached copy expires, capped by the configured interval. `max-age=0` (BYPASS bursts of 1–2 min) is not treated as a hint.
- **Conditional requests**: the client keeps ETag + body per URL and sends `If-None-Match`; unchanged data comes back as an empty `304`.
- Card data (schedule/standings websocket commands) reads the league coordinator cache — no extra API calls per card.

Endpoint details: [NHL web API](/integrations/nhl-web-api.md).
