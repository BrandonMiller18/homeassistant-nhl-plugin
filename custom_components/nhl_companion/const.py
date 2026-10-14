"""Constants for the NHL Companion integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "nhl_companion"
VERSION: Final = "0.1.0"

DEFAULT_API_BASE_URL: Final = "https://api-web.nhle.com/v1"
# NHL video clips (play-by-play highlightClip / discreteClip ids) are Brightcove videos
BRIGHTCOVE_ACCOUNT: Final = "6415718365001"
BRIGHTCOVE_PLAYER_CONFIG_URL: Final = (
    f"https://players.brightcove.net/{BRIGHTCOVE_ACCOUNT}/default_default/config.json"
)
BRIGHTCOVE_PLAYBACK_URL: Final = (
    "https://edge.api.brightcove.com/playback/v1/accounts/{account}/videos/{video_id}"
)
LOGO_URL_TEMPLATE: Final = "https://assets.nhle.com/logos/nhl/svg/{abbrev}_light.svg"

# Config entry data
CONF_TEAM_ABBREV: Final = "team_abbrev"
CONF_TEAM_NAME: Final = "team_name"

# Options
CONF_LIVE_INTERVAL: Final = "live_interval"
CONF_ALERT_DELAY: Final = "alert_delay"
CONF_GAME_SOON_MINUTES: Final = "game_soon_minutes"
CONF_GAME_DAY_HOUR: Final = "game_day_hour"
CONF_TRACK_OPPONENT: Final = "track_opponent"
CONF_API_BASE_URL: Final = "api_base_url"

DEFAULT_LIVE_INTERVAL: Final = 10
MIN_LIVE_INTERVAL: Final = 5
# Live play-by-play is cached at the CDN for 19 s and rebuilt every 20 s. A poll lands
# this long after the cached copy expires, so the refreshed copy is already there.
CDN_REFRESH_SLACK: Final = 1.5
MIN_ALIGNED_POLL: Final = 1.0
DEFAULT_ALERT_DELAY: Final = 0
MAX_ALERT_DELAY: Final = 180
DEFAULT_GAME_SOON_MINUTES: Final = 30
DEFAULT_GAME_DAY_HOUR: Final = 9
DEFAULT_TRACK_OPPONENT: Final = True

# Polling intervals (seconds) outside live play
INTERVAL_IDLE: Final = 3600
INTERVAL_GAME_DAY: Final = 300
INTERVAL_PRE_GAME: Final = 60
INTERVAL_LEAGUE_IDLE: Final = 1800
INTERVAL_LEAGUE_LIVE: Final = 120
SCHEDULE_REFRESH_SECONDS: Final = 3600
STANDINGS_REFRESH_SECONDS: Final = 1800
# Start polling play-by-play this many minutes before puck drop
PBP_LEAD_MINUTES: Final = 15

# Bus event fired for every game event
EVENT_NHL: Final = "nhl_companion_event"

# Event types
EVT_TEAM_GOAL: Final = "team_goal"
EVT_OPPONENT_GOAL: Final = "opponent_goal"
EVT_GOAL_REVERSED: Final = "goal_reversed"
EVT_GOAL_UPDATED: Final = "goal_updated"
EVT_GOAL_HIGHLIGHT: Final = "goal_highlight"
EVT_TEAM_PENALTY: Final = "team_penalty"
EVT_OPPONENT_PENALTY: Final = "opponent_penalty"
EVT_PERIOD_START: Final = "period_start"
EVT_PERIOD_END: Final = "period_end"
EVT_INTERMISSION_START: Final = "intermission_start"
EVT_INTERMISSION_END: Final = "intermission_end"
EVT_GAME_DAY: Final = "game_day"
EVT_GAME_SOON: Final = "game_soon"
EVT_GAME_START: Final = "game_start"
EVT_GAME_END_WIN: Final = "game_end_win"
EVT_GAME_END_LOSS: Final = "game_end_loss"
EVT_GAME_END_OTL: Final = "game_end_otl"

GOAL_EVENTS: Final = [
    EVT_TEAM_GOAL,
    EVT_OPPONENT_GOAL,
    EVT_GOAL_UPDATED,
    EVT_GOAL_HIGHLIGHT,
    EVT_GOAL_REVERSED,
]
PENALTY_EVENTS: Final = [EVT_TEAM_PENALTY, EVT_OPPONENT_PENALTY]
PERIOD_EVENTS: Final = [
    EVT_PERIOD_START,
    EVT_PERIOD_END,
    EVT_INTERMISSION_START,
    EVT_INTERMISSION_END,
]
GAME_EVENTS: Final = [
    EVT_GAME_DAY,
    EVT_GAME_SOON,
    EVT_GAME_START,
    EVT_GAME_END_WIN,
    EVT_GAME_END_LOSS,
    EVT_GAME_END_OTL,
]
ALL_EVENTS: Final = GOAL_EVENTS + PENALTY_EVENTS + PERIOD_EVENTS + GAME_EVENTS
OPPONENT_EVENTS: Final = {EVT_OPPONENT_GOAL, EVT_OPPONENT_PENALTY}

# NHL game states
STATE_FUTURE: Final = "FUT"
STATE_PRE: Final = "PRE"
STATE_LIVE: Final = "LIVE"
STATE_CRITICAL: Final = "CRIT"
STATE_FINAL: Final = "FINAL"
STATE_OFF: Final = "OFF"
LIVE_STATES: Final = {STATE_LIVE, STATE_CRITICAL}
FINISHED_STATES: Final = {STATE_FINAL, STATE_OFF}
UPCOMING_STATES: Final = {STATE_FUTURE, STATE_PRE}

# Dispatcher signals
SIGNAL_EVENT: Final = "nhl_companion_event_{entry_id}"

# Fallback team list used when standings cannot be fetched during setup
TEAMS: Final[dict[str, str]] = {
    "ANA": "Anaheim Ducks",
    "BOS": "Boston Bruins",
    "BUF": "Buffalo Sabres",
    "CAR": "Carolina Hurricanes",
    "CBJ": "Columbus Blue Jackets",
    "CGY": "Calgary Flames",
    "CHI": "Chicago Blackhawks",
    "COL": "Colorado Avalanche",
    "DAL": "Dallas Stars",
    "DET": "Detroit Red Wings",
    "EDM": "Edmonton Oilers",
    "FLA": "Florida Panthers",
    "LAK": "Los Angeles Kings",
    "MIN": "Minnesota Wild",
    "MTL": "Montréal Canadiens",
    "NJD": "New Jersey Devils",
    "NSH": "Nashville Predators",
    "NYI": "New York Islanders",
    "NYR": "New York Rangers",
    "OTT": "Ottawa Senators",
    "PHI": "Philadelphia Flyers",
    "PIT": "Pittsburgh Penguins",
    "SEA": "Seattle Kraken",
    "SJS": "San Jose Sharks",
    "STL": "St. Louis Blues",
    "TBL": "Tampa Bay Lightning",
    "TOR": "Toronto Maple Leafs",
    "UTA": "Utah Mammoth",
    "VAN": "Vancouver Canucks",
    "VGK": "Vegas Golden Knights",
    "WPG": "Winnipeg Jets",
    "WSH": "Washington Capitals",
}
