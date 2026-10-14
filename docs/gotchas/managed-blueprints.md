---
type: Gotcha
title: Bundled blueprints are managed files
description: Blueprints are copied into the HA config on every start, so edits made in HA are lost and moving them has restart quirks.
resource: custom_components/nhl_companion/blueprints.py
tags: [blueprints, deploy]
generated: {by: claude/opus-5.5, at: 2026-10-14T05:41:07Z}
---
**Symptom**: a blueprint edited in Home Assistant reverts after a restart or update.

**Cause**: on every start the integration copies `custom_components/nhl_companion/blueprints/` into `/config/blueprints/automation/nhl_companion/`, overwriting what's there. This is how blueprint changes ship with releases.

**Fix / avoid**:
- Change blueprints in the repo and release; never hand-edit them in HA. Users who want a custom one duplicate it to another folder or use **Take control** on the automation.
- Repointing an automation to a byte-identical blueprint at a new path does not refresh HA's blueprint-usage index on `automation.reload`; a full restart is needed before the old blueprint can be deleted.
- When waiting for HA to come back after a restart, poll `/manifest.json`, not `/api/` — unauthenticated `/api/` hits are logged as failed logins and can trigger `ip_ban`.
