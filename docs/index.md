---
okf_version: "0.2"
---
# NHL Companion docs

- [Overview](/overview.md) — what it is, how to run, test and release

## Architecture
- [Event pipeline](/architecture/event-pipeline.md) — snapshot → detector → deduped, gated, delayed events
- [Polling and caching](/architecture/polling-and-caching.md) — one poller per instance, CDN-aligned live polls, ETag/304

## Decisions
- [HA integration that emits events](/decisions/ha-integration-emits-events.md) — why HACS integration + blueprints, one entry per team

## Gotchas
- [NHL feed quirks](/gotchas/nhl-feed-quirks.md) — late assists, placeholder penalties, OVER state, flaky power play
- [Managed blueprints](/gotchas/managed-blueprints.md) — overwritten on start; restart and polling traps

## Integrations
- [NHL web API and Brightcove](/integrations/nhl-web-api.md) — undocumented API, defensive parsing, signed clip URLs

## History
- [Implementation plan](/IMPLEMENTATION_PLAN.md) — original v2 design; partly outdated, concepts above win
