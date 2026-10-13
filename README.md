# NHL Companion for Home Assistant

A custom integration that follows your NHL team and turns games into Home Assistant events: goal horns, light shows, penalty alerts, game-day reminders, plus schedule, standings and live scoreboard cards for any dashboard.

It talks directly to the public NHL web API (`api-web.nhle.com/v1`, community docs: [dword4/nhlapi](https://gitlab.com/dword4/nhlapi/-/blob/master/new-api.md), [Zmalski/NHL-API-Reference](https://github.com/Zmalski/NHL-API-Reference)). No API key, server or database needed.

## Features

- **Events for automations:** team/opponent goals with scorer, assists, strength (EV/PP/SH/EN) and score; overturned goals; penalties with player and infraction; period start/end; intermissions; game day; game starts soon; game start; win/loss/OT loss.
- **Game alerts switch:** one toggle per team. Off means no events fire (no horn at 11pm), while scores keep updating.
- **Broadcast delay:** hold events 0-180 s so the horn goes off when the goal shows on *your* TV or stream, not 30 s early.
- **Entities:** game status, score, opponent score, next game, last game, standings points, game today, game live, power play.
- **Dashboard cards:** scoreboard, league schedule, standings. Registered automatically, no resource setup.
- **Blueprints:** goal horn (with volume restore), goal lights (flash team colors, then restore), goal announcement, penalty alert, game reminder, win celebration.
- **Test without a game:** the `nhl_companion.simulate_event` action fires any event on demand.
- Follow several teams: add the integration once per team.

## Install

The repository is private, so HACS needs to be signed in to a GitHub account with access to it.

### Option A: HACS (custom repository)

1. HACS > three-dot menu > **Custom repositories**.
2. Repository: `https://github.com/BrandonMiller18/homeassistant-nhl-plugin`, type: **Integration**.
3. Find **NHL Companion** in HACS, download, then restart Home Assistant.

### Option B: manual copy

1. Copy `custom_components/nhl_companion` into your HA config so you have `/config/custom_components/nhl_companion/manifest.json`. Samba, SSH or the File editor add-on all work.
2. Restart Home Assistant.

### Add your team

**Settings > Devices & services > Add integration > NHL Companion**, then pick a team. Repeat for each team you follow.

Then open the integration's **Configure** to tune it:

| Option | Default | What it does |
|---|---|---|
| Live polling interval | 10 s | How often play-by-play is checked during a game (min 5 s). |
| Alert delay | 0 s | Holds every event so it lines up with your broadcast. Start around 20-40 s for streaming. |
| "Game starts soon" lead time | 30 min | When `game_soon` fires. |
| Game day alert hour | 9 | Local hour `game_day` fires on game days. |
| Fire opponent events | on | Turn off to skip `opponent_goal` / `opponent_penalty`. |
| NHL API base URL | NHL | Only for testing against the mock server below. |

## Entities

Shown for a team named "Boston Bruins". Entity IDs follow your team name.

| Entity | State | Useful attributes |
|---|---|---|
| `sensor.boston_bruins_game_status` | `no_game`, `scheduled`, `pre_game`, `live`, `intermission`, `final`, `postponed` | opponent, is_home, start_time, venue, period_label, clock, team_score, opponent_score, SOG, strength, last_goal |
| `sensor.boston_bruins_score` / `_opponent_score` | goals in the current game | |
| `sensor.boston_bruins_next_game` | puck drop (timestamp) | opponent, matchup (`vs TOR` / `@ TOR`), venue |
| `sensor.boston_bruins_last_game` | e.g. `W 4-2`, `OTL 2-3 (OT)` | opponent, start_time |
| `sensor.boston_bruins_standings_points` | points | record, ranks (league/conference/division/wildcard), streak, last 10 |
| `binary_sensor.boston_bruins_game_today` / `_game_live` / `_power_play` | on/off | |
| `switch.boston_bruins_game_alerts` | master on/off for events | |
| `event.boston_bruins_goal` / `_penalty` / `_period` / `_game` | time of last event | `event_type` plus the full payload of the last event |

## Events

Every event is fired two ways with the same data:

1. **Event entities** (`event.<team>_goal` and friends). Pick them in the automation editor (*When: Entity > event.boston_bruins_goal*), and show the last payload on dashboards.
2. **Bus event** `nhl_companion_event`, with `type` set to one of:

`team_goal`, `opponent_goal`, `goal_reversed`, `team_penalty`, `opponent_penalty`, `period_start`, `period_end`, `intermission_start`, `intermission_end`, `game_day`, `game_soon`, `game_start`, `game_end_win`, `game_end_loss`, `game_end_otl`

Goal payload:

```yaml
type: team_goal
config_entry_id: 01J...            # which followed team
game_id: 2025020123
team_abbrev: BOS
team_name: Boston Bruins
opponent_abbrev: TOR
opponent_name: Toronto Maple Leafs
is_home: true
period: 2
period_type: REG                   # REG, OT, SO
period_label: 2nd                  # 1st, 2nd, 3rd, OT, 2OT, SO
time_in_period: "12:41"
time_remaining: "07:19"
score: {team: 3, opponent: 1}
strength: pp                       # ev, pp, sh, en
empty_net: false
shot_type: wrist
scorer: {id, name, first_name, last_name, number, position, headshot, season_total}
primary_assist: {...} or null
secondary_assist: {...} or null
highlight_url: https://...
```

Penalties add `committed_by`, `drawn_by`, `served_by`, `infraction` (e.g. `Hooking`), `penalty_type` (`MIN`, `MAJ`...) and `duration_min`. `goal_reversed` adds `side` (`team`/`opponent`), the original `scorer`, and `original_period_label` / `original_time_in_period`. `game_day` / `game_soon` add `start_time`, `start_time_local` (e.g. `7:00 PM`), `venue` and `minutes_until_start`.

Example: show the scorer on a screen.

```yaml
triggers:
  - trigger: event
    event_type: nhl_companion_event
    event_data:
      type: team_goal
actions:
  - action: notify.living_room_tv
    data:
      title: "GOAL {{ trigger.event.data.team_abbrev }}!"
      message: >
        {{ trigger.event.data.scorer.name }} ({{ trigger.event.data.scorer.season_total }})
        {% if trigger.event.data.primary_assist %}from {{ trigger.event.data.primary_assist.name }}
        {%- if trigger.event.data.secondary_assist %} and {{ trigger.event.data.secondary_assist.name }}{% endif %}
        {% else %}unassisted{% endif %} at {{ trigger.event.data.time_in_period }} of the {{ trigger.event.data.period_label }}
```

### When things fire

- The first look at a game is a baseline. Setting up mid-game, or restarting HA, never replays old goals. Seen plays are saved per game, so a restart during a game picks up where it left off.
- The game alerts switch gates everything. Goals scored while it is off are not replayed when it turns back on.
- Play-by-play polling starts 15 minutes before puck drop and stops after the final. Otherwise the integration checks the schedule hourly (every 5 minutes on game days).

## Blueprints

Copy `blueprints/automation/nhl_companion/` into `/config/blueprints/automation/nhl_companion/` (or, once the repo is public, use **Settings > Automations > Blueprints > Import** with the file's GitHub URL), then **Reload automations**.

| Blueprint | Does |
|---|---|
| `goal_horn.yaml` | Snapshot speaker volume, set horn volume, play your horn file/URL, optional extra actions, restore volume. |
| `goal_lights.yaml` | Snapshot lights, flash two team colors N times, restore. |
| `goal_announcement.yaml` | Your own actions on a team goal (scorer data in templates). |
| `penalty_alert.yaml` | Your own actions on any penalty. |
| `game_reminder.yaml` | Your own actions on `game_day` and `game_soon`. |
| `win_celebration.yaml` | Your own actions on a win. |

Tip: put your team's horn mp3 in `/media` and use `media-source://media_source/local/horn.mp3` as the horn audio.

## Dashboard cards

The cards load automatically. Add them through **Edit dashboard > Add card** (search "NHL") or in YAML:

```yaml
type: custom:nhl-scoreboard-card
entity: sensor.boston_bruins_game_status
```

```yaml
type: custom:nhl-schedule-card
title: NHL schedule
days: 3            # 1 = today only (default), up to 7
team: BOS          # optional: only this team's games
```

```yaml
type: custom:nhl-standings-card
title: Standings
view: division     # division, conference or league
team: BOS          # optional: which division/conference (defaults to your first followed team)
show_all: false    # true = every division/conference
compact: false     # true = hide DIFF and STRK columns
```

Followed teams are highlighted in the schedule and standings.

## Testing without a live game

- **Single events:** Developer tools > Actions > `NHL Companion: Simulate event`. Pick `team_goal` and watch your horn automation run. Respects the game alerts switch.
- **A whole scripted game:** run the mock NHL API on any machine your HA can reach:

  ```bash
  pip install aiohttp
  python scripts/mock_nhl_server.py --team BOS --opponent TOR --step 20
  ```

  Then set **Configure > NHL API base URL** to `http://<that-machine>:8765/v1`. Every 20 s the game advances through pre-game, puck drop, goals, a power play, intermission, an overturned goal and a win. Clear the field to go back to the real NHL API.

## Development

```bash
python -m venv venv && . venv/bin/activate
pip install -r requirements_test.txt
pytest            # 29 tests: parser, event detector, config flow, entities, services, websocket
ruff check . && ruff format --check .
```

Tests use synthetic payloads from `scripts/fake_nhl.py`, shaped after the community API docs. To add real captures (recommended), run `python scripts/record_fixtures.py --team BOS --game <game id>` from a machine with internet access. Files land in `tests/fixtures/real/` and are parsed by `tests/test_parser.py` automatically.

Layout:

```
custom_components/nhl_companion/
  api.py              NHL API client (shared per base URL, short response cache)
  parser.py           raw JSON -> models; all knowledge of the NHL schema lives here
  event_detector.py   pure snapshot diff -> events (no HA imports)
  coordinator.py      league + team coordinators, adaptive polling, event dispatch
  sensor.py, binary_sensor.py, switch.py, event.py
  config_flow.py, websocket_api.py, frontend.py, diagnostics.py
  www/nhl-companion-cards.js
blueprints/automation/nhl_companion/
scripts/  fake_nhl.py, mock_nhl_server.py, record_fixtures.py
```

## Known gaps / next steps

- Tested against Home Assistant 2026.2 with synthetic data and the mock server. It has **not yet seen a real NHL game**. The sandbox it was built in could not reach `api-web.nhle.com`. Field names follow the community docs, and the parser tolerates missing fields, but expect small fixes after the first real game. Diagnostics (*Download diagnostics* on the integration) capture what is needed to debug.
- Strength (`pp`/`sh`) comes from the NHL `situationCode` skater counts. Delayed penalties and coincidental minors can look like a power play for a moment.
- Cards are plain JS without visual editors (YAML config only). A Lit/TypeScript rewrite with editors is planned.
- No brand icon yet (needs a PR to `home-assistant/brands`).
- The last goal shown on the scoreboard card is kept in memory, so it is blank after an HA restart until the next goal. The event entities keep their last payload across restarts.

See `docs/IMPLEMENTATION_PLAN.md` for the full design.
