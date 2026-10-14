# NHL Companion for Home Assistant

A custom integration that follows your NHL team and turns games into Home Assistant events: goal horns, light shows, penalty alerts, game-day reminders, plus schedule, standings and live scoreboard cards for any dashboard.

It talks directly to the public NHL web API (`api-web.nhle.com/v1`, community docs: [dword4/nhlapi](https://gitlab.com/dword4/nhlapi/-/blob/master/new-api.md), [Zmalski/NHL-API-Reference](https://github.com/Zmalski/NHL-API-Reference)). No API key, server or database needed.

## Features

- **Events for automations:** team/opponent goals with scorer, assists, strength (EV/PP/SH/EN) and score; corrected goal details (assists the NHL adds after the fact); goal videos; overturned goals; penalties with player and infraction; period start/end; intermissions; game day; game starts soon; game start; win/loss/OT loss.
- **Goal videos on your TV:** the `nhl_companion.play_highlight` action plays the NHL's clip of a goal on any media player that takes a video URL (Chromecast, Apple TV, Fire TV, Kodi, most smart TVs), and a blueprint does it automatically when the clip is posted.
- **Game stats:** shots, hits, blocks, faceoff %, penalty minutes, power play goals, a scoring summary and the three stars, for dashboards and small displays.
- **Game alerts switch:** one toggle per team. Off means no events fire (no horn at 11pm), while scores keep updating.
- **Broadcast delay:** hold events 0-180 s so the horn goes off when the goal shows on *your* TV or stream, not 30 s early.
- **Entities:** game status (with stats), score, opponent score, shots on goal, next game, last game, standings points, game today, game live, power play (with time left).
- **Dashboard cards:** scoreboard, league schedule, standings. Registered automatically, no resource setup.
- **Blueprints:** goal horn (with volume restore), goal lights (flash team colors, then restore), goal announcement, goal videos on a TV, penalty alert, game reminder, win celebration.
- **Test without a game:** the `nhl_companion.simulate_event` action fires any event on demand.
- Follow several teams: add the integration once per team.

## Install

### Option A: HACS (custom repository)

1. HACS > three-dot menu > **Custom repositories**.
2. Repository: `https://github.com/BrandonMiller18/homeassistant-nhl-plugin`, type: **Integration**.
3. Find **NHL Companion** in HACS, download, then restart Home Assistant.

New releases then show up under **Settings > Updates** with their release notes. To try pre-releases, open NHL Companion in HACS, three-dot menu > **Redownload**, and turn on **Show beta versions**.

### Option B: manual copy

1. Copy `custom_components/nhl_companion` into your HA config so you have `/config/custom_components/nhl_companion/manifest.json`. Samba, SSH or the File editor add-on all work.
2. Restart Home Assistant.

### Add your team

**Settings > Devices & services > Add integration > NHL Companion**, then pick a team. Repeat for each team you follow.

Then open the integration's **Configure** to tune it:

| Option | Default | What it does |
|---|---|---|
| Live polling interval | 10 s | Longest gap between play-by-play checks during a game (min 5 s). The NHL rebuilds the feed every 20 s behind a 19 s CDN cache, so the integration also polls about 1.5 s after each cached copy expires instead of up to 10 s later (2 requests per 20 s at the default, as before). When the CDN bypasses its cache (`max-age=0`, seen in 1-2 minute bursts) it just uses this interval. Unchanged responses come back as an empty `304`. |
| Alert delay | 0 s | Holds every event so it lines up with your broadcast. Start around 20-40 s for streaming. |
| "Game starts soon" lead time | 30 min | When `game_soon` fires. |
| Game day alert hour | 9 | Local hour `game_day` fires on game days. |
| Fire opponent events | on | Turn off to skip `opponent_goal` / `opponent_penalty`. |
| NHL API base URL | NHL | Only for testing against the mock server below. |

## Entities

Shown for a team named "Boston Bruins". Entity IDs follow your team name.

| Entity | State | Useful attributes |
|---|---|---|
| `sensor.boston_bruins_game_status` | `no_game`, `scheduled`, `pre_game`, `live`, `intermission`, `final`, `postponed` | opponent, is_home, start_time, venue, period_label, clock, team_score, opponent_score, SOG, strength, power_play_time_remaining, `team_stats` / `opponent_stats`, `goals` (scoring summary), `three_stars`, last_goal, last_goal_video |
| `sensor.boston_bruins_score` / `_opponent_score` | goals in the current game | |
| `sensor.boston_bruins_shots_on_goal` / `_opponent_shots_on_goal` | shots on goal in the current game | |
| `sensor.boston_bruins_next_game` | puck drop (timestamp) | opponent, matchup (`vs TOR` / `@ TOR`), venue |
| `sensor.boston_bruins_last_game` | e.g. `W 4-2`, `OTL 2-3 (OT)` | opponent, start_time |
| `sensor.boston_bruins_standings_points` | points | record, ranks (league/conference/division/wildcard), streak, last 10 |
| `binary_sensor.boston_bruins_game_today` / `_game_live` / `_power_play` | on/off | power play: `strength` (`ev`/`pp`/`sh`), `time_remaining` |
| `switch.boston_bruins_game_alerts` | master on/off for events | |
| `event.boston_bruins_goal` / `_penalty` / `_period` / `_game` | time of last event | `event_type` plus the full payload of the last event |

## Events

Every event is fired two ways with the same data:

1. **Event entities** (`event.<team>_goal` and friends). Pick them in the automation editor (*When: Entity > event.boston_bruins_goal*), and show the last payload on dashboards.
2. **Bus event** `nhl_companion_event`, with `type` set to one of:

`team_goal`, `opponent_goal`, `goal_updated`, `goal_highlight`, `goal_reversed`, `team_penalty`, `opponent_penalty`, `period_start`, `period_end`, `intermission_start`, `intermission_end`, `game_day`, `game_soon`, `game_start`, `game_end_win`, `game_end_loss`, `game_end_otl`

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
highlight_url: null                # usually posted ~9 min later; see goal_highlight
```

`goal_updated` repeats the goal payload with the corrected players, plus `side` (`team`/`opponent`) and `changed` (e.g. `[primary_assist]`). It fires when the NHL fills in or changes the scorer or an assist after the goal was announced. In live data that happened on most goals, 20-60 s after the goal.

`goal_highlight` repeats the goal payload plus `side`, `clip_type` and `clip_id`, once per clip: `short` (a ~10 s goal clip, about 5 minutes after the goal) and `full` (a ~45 s highlight, about 7-9 minutes after). Pass `clip_id` to `nhl_companion.play_highlight`.

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

- Goals fire as soon as they appear in the feed, so the horn is not held back. A play the NHL first posts as a missed shot and turns into a goal (seen twice in one game) still fires the goal.
- A penalty posted with only a placeholder infraction (`minor`, `major`) waits up to 6 polls for the real call. In live data these became `holding`, `fighting` (5-minute majors) or were deleted outright, so waiting avoids announcing penalties that never happened.
- `intermission_end` fires when the intermission clock runs out, about 2 minutes before the next puck drop; `period_start` is the puck drop.
- The game ends on the NHL's `OVER` state at the final horn, about 20 s before it switches to `FINAL`.
- The first look at a game is a baseline. Setting up mid-game, or restarting HA, never replays old goals. Seen plays are saved per game, so a restart during a game picks up where it left off.
- The game alerts switch gates everything. Goals scored while it is off are not replayed when it turns back on.
- Play-by-play polling starts 15 minutes before puck drop and stops after the final. Otherwise the integration checks the schedule hourly (every 5 minutes on game days). After a final it checks for the three stars every 2 minutes until they are posted (about 2 minutes after the final in live data).

## Blueprints

The blueprints ship with the integration. On every start it copies them into `/config/blueprints/automation/nhl_companion/`, so they appear under **Settings > Automations > Blueprints** after the first restart and update along with the integration.

Those files are managed: edits made to them in Home Assistant are overwritten on the next start. To customize one, duplicate it under another folder first, or use **Take control** on an automation built from it.

| Blueprint | Does |
|---|---|
| `goal_horn.yaml` | Snapshot speaker volume, set horn volume, play your horn file/URL, optional extra actions, restore volume. |
| `goal_lights.yaml` | Snapshot lights, flash two team colors N times, restore. |
| `goal_announcement.yaml` | Your own actions on a team goal (scorer data in templates). Optionally runs again on `goal_updated`, since assists often arrive 20-40 s after the goal. |
| `goal_video.yaml` | Plays each goal's NHL video on your TV when it is posted (short clip ~5 min or full highlight ~9 min after the goal), optionally only while the TV is on. |
| `penalty_alert.yaml` | Your own actions on any penalty. |
| `game_reminder.yaml` | Your own actions on `game_day` and `game_soon`. |
| `win_celebration.yaml` | Your own actions on a win. |

Tip: put your team's horn mp3 in `/media` and use `media-source://media_source/local/horn.mp3` as the horn audio.

## Dashboard cards

The cards load automatically. Add them through **Edit dashboard > Add card** (search "NHL") or in YAML:

```yaml
type: custom:nhl-scoreboard-card
entity: sensor.boston_bruins_game_status
show_stats: true                    # shots, hits, blocks, faceoff %, PIM, PP goals (default on)
show_goals: false                   # scoring summary
media_player: media_player.living_room_tv   # optional: adds a "Watch goal" button
```

The scoreboard shows the power play team and time left, the last goal with corrected assists, and the three stars after the final.

### Goal videos

```yaml
action: nhl_companion.play_highlight
data:
  entity_id: media_player.living_room_tv   # leave out to only get the URL back
  clip_id: "{{ trigger.event.data.clip_id }}"   # leave out for the latest goal video
  format: mp4                                # or hls
```

The action returns `url`, `title`, `duration_s` and `goal` as a response, so you can also send the link in a notification. Videos are NHL clips hosted on Brightcove; the stream URLs are signed and looked up each time the action runs.

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

  Then set **Configure > NHL API base URL** to `http://<that-machine>:8765/v1`. Every 20 s the game advances through pre-game, puck drop, goals, a delayed penalty and power play, an assist added after the goal, intermission, an overturned goal and a win. Clear the field to go back to the real NHL API.

## Development

```bash
python -m venv venv && . venv/bin/activate
pip install -r requirements_test.txt
pytest            # parser, detector, stats, API client, replay of a real game, config flow, entities, services, blueprints
ruff check . && ruff format --check .
```

The test suite needs Linux or macOS (Home Assistant does not install on Windows); on Windows use WSL or rely on CI.

### Making a change

1. Branch off `main`, commit, push, open a pull request. CI (tests, ruff, hassfest, HACS validation) must pass before merging.
2. To try the change on a real Home Assistant before releasing, publish a pre-release (below) with a `b` version and install it through HACS with beta versions on.

### Releasing

1. On a branch, bump the version in `manifest.json` and `const.py` together:

   ```bash
   python scripts/bump_version.py 0.3.0      # 0.3.0b1 for a pre-release
   ```

2. Merge the pull request, then tag the merge commit on `main` and push the tag:

   ```bash
   git switch main && git pull
   git tag v0.3.0 && git push origin v0.3.0
   ```

3. The **Release** workflow checks that the tag matches `manifest.json` and is on `main`, runs the tests, and publishes a GitHub release with generated notes (a pre-release for `a`/`b`/`rc` versions). HACS offers it in Home Assistant within a few hours, or straight away after **HACS > three-dot menu > Update information** on the repository.

Blueprint changes ride along: they live in `custom_components/nhl_companion/blueprints/` and are reinstalled on the next start after an update.

Tests combine synthetic payloads from `scripts/fake_nhl.py` (shaped after a recorded live game) with real responses from STL @ OTT on 2026-10-13 (game 2026020096) in `tests/fixtures/real/`, and a replay of that game in `tests/fixtures/replay/`.

To record another game and turn it into a replay test:

```bash
pip install aiohttp
python scripts/record_live.py --team STL --out /tmp/live_stl --interval 10   # runs until 10 min after the final
python scripts/trim_recording.py /tmp/live_stl --team STL --out tests/fixtures/replay/<name>.json.gz
```

`record_live.py` logs every play the NHL edits (`AMEND`) or deletes (`REMOVED`) and the events the integration would fire. It imports the integration package, so run it in the test venv.

Layout:

```
custom_components/nhl_companion/
  api.py              NHL API client (shared per base URL, ETag/304, CDN-aware polling, Brightcove clips)
  parser.py           raw JSON -> models; all knowledge of the NHL schema lives here
  event_detector.py   pure snapshot diff -> events (no HA imports)
  stats.py            team stats and scoring summary from play-by-play
  coordinator.py      league + team coordinators, adaptive polling, event dispatch
  sensor.py, binary_sensor.py, switch.py, event.py
  config_flow.py, websocket_api.py, frontend.py, diagnostics.py
  blueprints.py       copies blueprints/ into /config/blueprints on startup
  blueprints/automation/*.yaml
  www/nhl-companion-cards.js
scripts/  bump_version.py, fake_nhl.py, mock_nhl_server.py, record_fixtures.py, record_live.py, trim_recording.py
```

## Known gaps / next steps

Verified against one real game so far (STL 7-2 @ OTT, 2026-10-13, regulation). Not yet seen live:

- **Overtime, shootouts and OT losses.** `period_label`, `game_end_otl` and `last_period_type` follow the documented `OT`/`SO` period types but have only run on synthetic data.
- **An overturned goal.** No goal was challenged in the recorded game. `goal_reversed` fires when a goal disappears from the feed, stops being a goal, or the score drops, but the real shape of a reversal is unconfirmed.
- **Empty-net goals.** Strength `en` comes from a goalie count of 0 in `situationCode`; no empty-net goal was scored in the recorded game.
- **Playing a goal video on a real TV.** The clip lookup was tested against the live Brightcove API and `play_media` is called with a 720p MP4, but no physical Chromecast/Apple TV was used. The policy key comes from the NHL's public player config and could change without notice; the client refetches it once when Brightcove rejects it. How long the signed stream URLs stay valid is unknown, which is why they are looked up at play time.

Known behaviour from the live data:

- **Power play state follows the feed's own `situation` block,** which the NHL sometimes gets wrong for a moment: during a fight with placeholder penalties it showed the wrong team on a power play for ~40 s, and it occasionally drops out for one update. Without the block the integration falls back to the last play's skater counts, which lag a penalty until the next faceoff.
- **`drawn_by` on penalties can be missing or wrong at first** and corrected 20-40 s later; there is no `penalty_updated` event.
- **`shot_type` and `time_in_period` on goals can be corrected later** (e.g. wrist to backhand, 18:24 to 18:25) without a `goal_updated` event; only scorer and assist changes trigger one.
- **Stats are counted from play-by-play** and matched the NHL boxscore except for one hit and one giveaway at the time of comparison.
- **Videos arrive minutes after the goal** (short clip ~4-6 min, full highlight ~7-9 min, sometimes together), so they suit replays, not the goal horn.
- **Broadcast delay is still manual.** How far the feed runs ahead of (or behind) a given TV or stream was not measured.

Other:

- Cards are plain JS without visual editors (YAML config only). A Lit/TypeScript rewrite with editors is planned.
- No brand icon yet (needs a PR to `home-assistant/brands`).

See `docs/IMPLEMENTATION_PLAN.md` for the full design.
