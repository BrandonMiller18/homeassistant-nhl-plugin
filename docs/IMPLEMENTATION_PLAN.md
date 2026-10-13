# NHL Companion for Home Assistant: Implementation Plan

## Status (MVP built)

Done: phases 0-6 below, using vanilla JS cards (no Lit build yet). Verified with 29 pytest tests and an end-to-end run on Home Assistant 2026.2.3. The run covered the real config/options flow, a scripted game served by `scripts/mock_nhl_server.py` (all 18 live events in order), the blueprints running against demo speakers and lights, and the cards rendered in Chromium at desktop and phone widths. Not yet verified: a real NHL game, because the build sandbox could not reach api-web.nhle.com.

## MVP build pass

The user asked for as much as possible, autonomously, ending in something they can install on their local HA and test. Blockers found during research:
- This sandbox blocks `api-web.nhle.com`, `web.archive.org`, and WebFetch's resolver for the NHL host. PyPI and npm work.
- dword4's `new-api.md` has no play-by-play sample, and `Zmalski/NHL-API-Reference` only lists endpoints.

Workarounds:
- Fixtures are hand-built from the documented schema and live in `tests/fixtures/`, each marked synthetic. `scripts/record_fixtures.py` lets the user replace them with real captures.
- `parser.py` reads every field defensively with `.get()` and defaults, so a schema surprise degrades a field instead of crashing.
- A hidden `api_base_url` option (default `https://api-web.nhle.com/v1`) plus `scripts/mock_nhl_server.py` let a real HA instance run end-to-end in the sandbox against a scripted game: pre-game, then a goal, a penalty, a period end, a reversal, and the final.

Build order and MVP cuts:
1. Scaffold: `hacs.json`, `manifest.json`, `pyproject.toml` (ruff + pytest config), `requirements_test.txt`, `.gitignore`, and CI workflows (hassfest, HACS validate, pytest).
2. `const.py`, `models.py`, `parser.py`, `api.py`, `event_detector.py`, plus synthetic fixtures and unit tests.
3. `coordinator.py` (league and team), `config_flow.py` (team picker plus options), `entity.py`, `sensor.py`, `binary_sensor.py`, `switch.py`, `event.py`, bus event, alert delay, `Store` dedupe, `services.yaml` (`simulate_event`, `refresh`), `diagnostics.py`, `websocket_api.py`, `frontend.py`, strings and translations.
4. Cards: the MVP uses **vanilla custom elements in one plain JS file** (`www/nhl-companion-cards.js`) with no build step. Lit and TypeScript move to a later pass. Cards: schedule, standings, scoreboard, each with a simple stub config. The integration auto-registers the file through `async_register_static_paths` and `frontend.add_extra_js_url`.
5. Blueprints: goal horn, goal lights, game reminder, penalty alert, win celebration.
6. Tests: `pytest-homeassistant-custom-component` covering the parser, detector, config flow, entity setup, toggle gating, and simulate service.
7. E2E smoke test: install `homeassistant` in a venv, run `hass -c` with the mock server, and confirm the integration loads, entities appear, and events fire. Done through the HA REST/websocket API with a long-lived token created in the onboarding flow, or via `hass --script check_config` if onboarding automation proves too fiddly.
8. README with install steps (HACS custom repo, or manually copy `custom_components/nhl_companion`), entity and event reference, blueprint import links, and known gaps. Commit and push to `claude/dreamy-brown-85wb1v`.

Deferred and listed in README "Known gaps": Lit/TS card rewrite with visual editors, a `game_day` time-of-day option beyond the default, real recorded fixtures, HACS default-store submission, and a landing-endpoint three-stars sensor.

## Context

NHL Companion v1 is three hosted services: a DB-sync CLI that pulls `api-web.nhle.com/v1` into MySQL, a FastAPI read API on Heroku (`nhl-companion-api`), and a Next.js frontend on Vercel (`nhl-companion-frontend`). The frontend polls every 3 s and finds new plays by diffing `playIndex` (`app/live/[gameId]/page.tsx`). It flags `goal`, `penalty`, `period-start`, `period-end`, `game-end` as major plays (`lib/utils.ts:isMajorPlay`). Audio and webhook flags exist in `LiveGameConfig`, but the code never implements them.

v2 moves into Home Assistant as a **custom integration** (`custom_components/nhl_companion`) installed through HACS. HA becomes the runtime, the automation engine, and the display layer. There is no DB, no hosted API, and no separate frontend: the integration calls the NHL API directly.

Decisions confirmed with the user:
- Packaging: custom integration via HACS, not a Supervisor add-on.
- Actions (audio, lights, anything else): the integration emits rich events. Shipped blueprints do the actions.
- Dashboards: Lovelace cards (Lit + TypeScript) that the integration bundles and registers itself, so users install one HACS repo.
- Teams: one config entry per team. Users add the integration again for each extra team.

Existing alternative, for reference: `vasqued2/ha-teamtracker` (HACS) already exposes NHL scores from ESPN as sensor attributes. It gives a goal horn only through score-change state triggers and has no structured scorer or assist events. v2 differs with discrete typed events (scorer, assists, strength, goal reversal), a broadcast-delay offset, a master toggle, and schedule and standings cards.

## Architecture

```
api-web.nhle.com/v1 ──aiohttp──> NhlApiClient (api.py)
        │
        ├─ LeagueCoordinator (one per HA instance, hass.data shared)
        │     schedule/now, standings/now   — refresh 15–60 min
        │
        └─ TeamCoordinator (one per config entry)
              club-schedule-season/{abbr}/now  — finds next/today's game
              adaptive interval: idle 1h → game day 5 min → pre-game 1 min → live N s
              gamecenter/{id}/play-by-play while live
                     │
                     ▼
              EventDetector (pure, no HA imports) — diffs snapshots → NhlEvent list
                     │
          ┌──────────┼──────────────────────┐
          ▼          ▼                      ▼
   Event entities  hass.bus "nhl_companion_event"   Sensors / binary_sensors
   (UI triggers,   (blueprints, power users)        (dashboards)
    last-event attrs)
          ▲
   switch.<team>_game_alerts gates all event emission (entities keep updating)
```

## NHL API endpoints

Undocumented public API. Community reference: GitHub `Zmalski/NHL-API-Reference`. Every endpoint below is unauthenticated.
- `/schedule/now` and `/schedule/{YYYY-MM-DD}`: league week schedule.
- `/club-schedule-season/{TEAM}/now`: team season schedule.
- `/gamecenter/{gameId}/play-by-play`: `plays[]` (`eventId`, `sortOrder`, `typeDescKey`, `periodDescriptor`, `timeInPeriod`, `timeRemaining`, `situationCode`, `details{scoringPlayerId, assist1PlayerId, assist2PlayerId, eventOwnerTeamId, committedByPlayerId, descKey, duration, homeScore, awayScore}`), `rosterSpots[]` (names, sweater number, headshot), `gameState`, `clock`, scores.
- `/gamecenter/{gameId}/landing`: three stars and final summary.
- `/standings/now`: league, conference, division, and wildcard standings.
- Team list and logos come from `/standings/now` (`teamAbbrev`, `teamName`, `teamLogo`), so no separate teams endpoint is needed.

**Environment note:** this cloud session's egress proxy blocks `api-web.nhle.com`. Fixtures must be recorded on a machine with access (`scripts/record_fixtures.py`) or the domain allowlisted. All tests run offline against fixtures.

## Repository layout

```
custom_components/nhl_companion/
  __init__.py          setup/unload entry, create shared LeagueCoordinator, register frontend + websocket + services
  manifest.json        domain nhl_companion, iot_class cloud_polling, config_flow true, requirements []
  const.py             DOMAIN, event type names, defaults, option keys
  api.py               NhlApiClient (aiohttp via async_get_clientsession), typed errors, retries/backoff
  models.py            dataclasses: Game, Play, Player, Standing, NhlEvent (+ .as_event_data())
  parser.py            raw JSON → models (isolates NHL schema churn to one file)
  event_detector.py    pure diff logic: (prev_snapshot, new_snapshot, team_id) → list[NhlEvent]
  coordinator.py       LeagueCoordinator, TeamCoordinator (DataUpdateCoordinator subclasses, adaptive interval, pregame timers)
  config_flow.py       user step: pick team (from standings); OptionsFlow for tuning
  entity.py            NhlTeamEntity base (DeviceInfo per team, has_entity_name)
  sensor.py            game status, score, opponent score, next game, period/clock, last goal, standings position
  binary_sensor.py     game_today, game_live, power_play
  switch.py            game_alerts (RestoreEntity) — master on/off
  event.py             EventEntity platform: goal, penalty, period, game
  services.yaml        simulate_event, refresh
  websocket_api.py     nhl_companion/schedule, nhl_companion/standings, nhl_companion/game
  frontend.py          serves www/ via StaticPathConfig + add_extra_js_url
  diagnostics.py       redacted coordinator dump for bug reports
  strings.json, translations/en.json, icons.json
  www/nhl-companion-cards.js   built bundle (committed, generated by frontend/)
frontend/              TypeScript + Lit source, Rollup build → custom_components/.../www/
  src/schedule-card.ts, standings-card.ts, scoreboard-card.ts, editors/, shared/
blueprints/automation/nhl_companion/
  goal_horn.yaml, goal_lights.yaml, game_reminder.yaml, penalty_alert.yaml, win_celebration.yaml
tests/                 pytest-homeassistant-custom-component; fixtures/*.json
scripts/record_fixtures.py, scripts/replay_game.py
hacs.json, README.md, docs/IMPLEMENTATION_PLAN.md
.github/workflows/  hassfest.yml, hacs.yml, tests.yml (pytest + ruff + mypy), frontend.yml (lint + build check)
```

## Events and payloads

The integration exposes two surfaces, and both carry identical data.

1. **Event entities** (HA `EventEntity`, added in 2023.8, developers.home-assistant.io/docs/core/entity/event). Users pick them in the automation UI ("Entity → event.bruins_goal"). The last payload stays as attributes, so a dashboard can show "Last goal: Pastrňák (Marchand, McAvoy) 12:41 P2".
   - `event.<team>_goal`: `team_goal`, `opponent_goal`, `goal_reversed`
   - `event.<team>_penalty`: `team_penalty`, `opponent_penalty`
   - `event.<team>_period`: `period_start`, `period_end`, `intermission_start`, `intermission_end`
   - `event.<team>_game`: `game_day`, `game_soon`, `game_start`, `game_end_win`, `game_end_loss`, `game_end_otl`
2. **Bus event** `nhl_companion_event`, with `data.type` set to one of the types above. Blueprints use it, and it supports templated triggers.

Goal payload (other types use the relevant subset):
```yaml
type: team_goal
team_abbrev: BOS
opponent_abbrev: TOR
game_id: 2025020123
period: 2              # period_type: REG|OT|SO
time_in_period: "12:41"
time_remaining: "07:19"
strength: pp           # ev|pp|sh|en, from situationCode / descKey
scorer: {id, name, number, headshot, season_total}
primary_assist:   {id, name, number, season_total}   # or null
secondary_assist: {id, name, number, season_total}   # or null
score: {team: 3, opponent: 1}
config_entry_id: ...
```
Penalty payload adds `committed_by`, `drawn_by`, `duration_min`, `infraction` (from `descKey`).

Detection rules (`event_detector.py`):
- Dedupe plays by `eventId`. Keep a set of emitted IDs per game and persist it to `Store` so an HA restart mid-game doesn't re-fire every goal.
- First snapshot after startup or toggle-on is a baseline. It never emits historical plays.
- `goal_reversed` fires when a previously emitted goal `eventId` disappears, or when a team's score drops. This covers the coach's-challenge case.
- Win, loss, and OTL come from final scores plus `periodDescriptor.periodType` of the last period.
- `game_day` fires once at a configurable local time on game days. `game_soon` fires N minutes before puck drop. Both use `async_track_point_in_time` rather than polling.

**Broadcast delay option.** Streams and cable feeds run 10–60 s behind the live API. The `alert_delay_seconds` option holds event emission (via `async_call_later`) so the horn plays when the goal appears on screen. Without it, the API reports the goal before the TV shows it. This is the most-requested feature on goal-horn projects.

## Toggle (requirement: turn alerts off)

`switch.<team>_game_alerts` uses `RestoreEntity`, so the state survives restarts. When it is off, the coordinator keeps polling and sensors keep updating, but no events fire. Turning it on re-baselines, so old goals never replay. The switch is also exposed as a normal entity, so users can automate it (on when the TV turns on, off at bedtime). The README documents this.

## Config and options flow

- **User step:** dropdown of 32 teams, built from `/standings/now`. The unique ID is the team abbreviation, which blocks duplicate entries.
- **Options:** live poll interval (default 10 s, min 5 s), alert delay (0–120 s), game-soon lead time (default 30 min), game-day notification time (default 09:00), enabled event categories (multi-select), and whether to track the opponent's events.

## Dashboard cards (bundled)

- `nhl-schedule-card`: today, this week, or the team season. Logos, local start times, live scores. Data comes from websocket `nhl_companion/schedule`, which reads the LeagueCoordinator cache with no extra API calls.
- `nhl-standings-card`: division, conference, wildcard, or league view, with a highlighted followed team. Data comes from websocket `nhl_companion/standings`.
- `nhl-scoreboard-card`: live score, clock, period, SOG, and last goal, read from the team entities. Updates in real time through `hass` state.
- Each card has a visual editor. The integration auto-registers the cards on setup, so no manual resource step is needed.

Any HA-connected display (wall tablet, Fire tablet running Fully Kiosk, Nest Hub via cast) renders these cards. Displays such as ESPHome screens or Awtrix use the sensors and event attributes directly.

## Blueprints (audio, lights, anything)

- `goal_horn`: input is a `media_player` (multi), horn media (`media-source://` or URL), and volume. It sets volume, plays the horn, and restores volume afterward. A condition requires the toggle to be on, as a belt-and-suspenders check.
- `goal_lights`: input is lights or a light group plus team colors. It flashes N times, then restores the scene snapshot (`scene.create`).
- `game_reminder`: on `game_soon`, it sends a notify or TTS announcement.
- `penalty_alert` and `win_celebration`: same pattern.

The README includes a template example for displaying the scorer and assists on a screen with `trigger.event.data.scorer.name`.

## Implementation phases

0. **Scaffold:** commit this plan to `docs/IMPLEMENTATION_PLAN.md`. Add `hacs.json`, `manifest.json`, CI (hassfest, HACS action, pytest, ruff), devcontainer (`ludeeus/integration_blueprint` layout), and README skeleton.
1. **API client + parser + fixtures:** `api.py`, `parser.py`, `models.py`. Record fixtures for a scheduled game, a live game mid-period, a final, an OT game, a shootout, a goal reversal, and standings. Unit-test the parser against every fixture.
2. **Event detector:** pure module with the highest test density. Table-driven tests replay fixture sequences and assert the exact events produced, including restart-baseline and reversal cases.
3. **Coordinators + config flow + core entities:** adaptive intervals, LeagueCoordinator sharing, sensors, binary sensors, game-alerts switch, diagnostics.
4. **Event emission:** event entities, bus event, alert delay, `Store` persistence, toggle gating, and the `simulate_event` service so users can test automations without a live game.
5. **Websocket API + Lovelace cards:** Rollup build into `www/`, then registration.
6. **Blueprints + docs:** README install via HACS custom repo, automation recipes, screenshots.
7. **Release:** tag v0.1.0 as a HACS custom repository. Submit to HACS default after real-game soak testing.

## Polling budget

The previous frontend polled every 3 s per viewer. v2 polls once per HA instance:
- League data: about 96 calls per day.
- Team schedule: about 24 calls per day.
- Live game: 10 s × about 2.5 h ≈ 900 calls per game.

Two followed teams in the same game share the play-by-play fetch through a per-game cache in the client. Handle 429 and 5xx responses with exponential backoff and `UpdateFailed`.

## Verification

- `pytest tests/` (pytest-homeassistant-custom-component) covers the config flow, coordinator interval transitions, entity states, event detection sequences, toggle gating, and restart dedupe. The coverage target is ≥90% on `event_detector.py` and `parser.py`.
- CI runs `hassfest` and the HACS validation action. Both must pass.
- `scripts/replay_game.py` serves a recorded game's play-by-play snapshots in sequence from a local aiohttp server. Point the client at it with a debug option to watch events fire in a real dev HA instance (devcontainer, `hass -c config`).
- Manual check in dev HA: add an entry, confirm entities and device, call `nhl_companion.simulate_event` with `type: team_goal`, and confirm the event entity updates, the goal_horn blueprint plays on a `media_player.demo` entity, and nothing fires with the toggle off.
- Live soak test: follow at least 3 real games, one with OT or shootout if possible, and compare the event log against the NHL gamecenter.
- Frontend: `npm run build && npm run lint`. Load the cards in dev HA, then check light and dark themes and phone width.
