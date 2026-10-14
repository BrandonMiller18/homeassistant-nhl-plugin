/*
 * NHL Companion Lovelace cards. No build step: plain custom elements.
 *   custom:nhl-scoreboard-card  - live score, stats, goals, three stars and goal videos
 *   custom:nhl-schedule-card    - league schedule (today or the week)
 *   custom:nhl-standings-card   - division / conference / league standings
 */
const NHL_VERSION = "0.1.0";
const LOGO = (abbrev) => `https://assets.nhle.com/logos/nhl/svg/${abbrev}_light.svg`;
const LIVE = new Set(["LIVE", "CRIT"]);
const DONE = new Set(["FINAL", "OFF"]);

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const timeOf = (iso) =>
  iso ? new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "";

const dayLabel = (date) => {
  const d = new Date(`${date}T12:00:00`);
  const today = new Date();
  if (d.toDateString() === today.toDateString()) return "Today";
  const tomorrow = new Date(today.getTime() + 86400000);
  if (d.toDateString() === tomorrow.toDateString()) return "Tomorrow";
  return d.toLocaleDateString([], { weekday: "long", month: "short", day: "numeric" });
};

const periodLabel = (n, type) => {
  if (!n) return "";
  if (type === "SO") return "SO";
  if (type === "OT" || n > 3) return n - 3 <= 1 ? "OT" : `${n - 3}OT`;
  return ["", "1st", "2nd", "3rd"][n] || `${n}th`;
};

const BASE_STYLE = `
  :host { display: block; }
  ha-card { padding: 12px 16px 16px; }
  .title { font-size: 1.15em; font-weight: 500; padding: 4px 0 8px; color: var(--primary-text-color); }
  .muted { color: var(--secondary-text-color); }
  .live { color: var(--error-color, #db4437); font-weight: 600; }
  img.logo { width: 28px; height: 28px; object-fit: contain; flex: none; }
  .empty { padding: 12px 0; color: var(--secondary-text-color); }
  .err { color: var(--error-color, #db4437); padding: 8px 0; }
`;

class NhlBaseCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = {};
  }
  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._onFirstHass();
    this._render();
  }
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }
  getCardSize() {
    return 3;
  }
  _onFirstHass() {}
  disconnectedCallback() {
    clearInterval(this._timer);
    this._timer = null;
  }
  connectedCallback() {
    if (this._hass && !this._timer && this._poll) this._startPolling();
  }
  _startPolling(seconds = 60) {
    clearInterval(this._timer);
    this._poll();
    this._timer = setInterval(() => this._poll(), seconds * 1000);
  }
  async _ws(type, extra = {}) {
    return this._hass.callWS({ type: `nhl_companion/${type}`, ...extra });
  }
  _shell(body) {
    const title = this._config.title ? `<div class="title">${esc(this._config.title)}</div>` : "";
    this.shadowRoot.innerHTML = `<style>${BASE_STYLE}${this._style || ""}</style><ha-card>${title}${body}</ha-card>`;
  }
}

/* ------------------------------------------------------------ scoreboard */

class NhlScoreboardCard extends NhlBaseCard {
  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (id) => id.startsWith("sensor.") && id.endsWith("_game_status") && hass.states[id].attributes.team_abbrev,
    );
    return { entity: entity || "sensor.my_team_game_status" };
  }
  setConfig(config) {
    if (!config.entity) throw new Error("Set entity to a team's game status sensor");
    super.setConfig(config);
  }
  get _style() {
    return `
      .row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
      .team { display: flex; flex-direction: column; align-items: center; width: 33%; text-align: center; }
      .team img { width: 64px; height: 64px; object-fit: contain; }
      .abbrev { font-weight: 600; margin-top: 4px; }
      .sog { font-size: 0.85em; }
      .score { font-size: 2.6em; font-weight: 700; min-width: 1.4em; text-align: center; }
      .mid { display: flex; flex-direction: column; align-items: center; flex: 1; }
      .scores { display: flex; align-items: center; gap: 12px; }
      .status { margin-top: 6px; font-size: 0.95em; text-align: center; }
      .goal { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--divider-color); font-size: 0.95em; }
      .goal b { color: var(--primary-text-color); }
      .pp { display: inline-block; margin-left: 6px; padding: 0 6px; border-radius: 8px; font-size: 0.8em;
            background: var(--warning-color, #ffa600); color: #000; }
      .section { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--divider-color); font-size: 0.95em; }
      table.stats { width: 100%; border-collapse: collapse; }
      table.stats td { padding: 2px 4px; text-align: center; }
      table.stats td.label { color: var(--secondary-text-color); font-size: 0.85em; }
      .goals div, .stars div { padding: 2px 0; }
      button.watch { margin-top: 8px; padding: 6px 12px; border: 0; border-radius: 6px; cursor: pointer;
                     background: var(--primary-color); color: var(--text-primary-color, #fff); font: inherit; }
    `;
  }
  _render() {
    if (!this._hass || !this._config.entity) return;
    const st = this._hass.states[this._config.entity];
    if (!st) return this._shell(`<div class="err">Entity ${esc(this._config.entity)} not found</div>`);
    const a = st.attributes;
    if (!a.team_abbrev) return this._shell(`<div class="empty">No upcoming game</div>`);

    const home = a.is_home
      ? { abbrev: a.team_abbrev, logo: a.team_logo, score: a.team_score, sog: a.team_sog }
      : { abbrev: a.opponent_abbrev, logo: a.opponent_logo, score: a.opponent_score, sog: a.opponent_sog };
    const away = a.is_home
      ? { abbrev: a.opponent_abbrev, logo: a.opponent_logo, score: a.opponent_score, sog: a.opponent_sog }
      : { abbrev: a.team_abbrev, logo: a.team_logo, score: a.team_score, sog: a.team_sog };
    const started = ["live", "intermission", "final"].includes(st.state);

    let status;
    if (st.state === "live") {
      status = `<span class="live">${esc(a.period_label || "")} ${esc(a.clock || "")}</span>`;
      if (a.strength === "pp" || a.strength === "sh") {
        const who = a.strength === "pp" ? a.team_abbrev : a.opponent_abbrev;
        const left = a.power_play_time_remaining ? ` ${esc(a.power_play_time_remaining)}` : "";
        status += `<span class="pp">${esc(who)} PP${left}</span>`;
      }
    } else if (st.state === "intermission") {
      status = `<span class="live">${esc(a.period_label || "")} intermission</span>`;
    } else if (st.state === "final") {
      const extra = a.period_label === "OT" || a.period_label === "SO" ? `/${a.period_label}` : "";
      status = `Final${esc(extra)}`;
    } else if (st.state === "postponed") {
      status = "Postponed";
    } else {
      const d = a.start_time ? new Date(a.start_time) : null;
      status = d
        ? `${d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" })} · ${timeOf(a.start_time)}`
        : "Scheduled";
    }

    const side = (t) => `
      <div class="team">
        <img src="${esc(t.logo || LOGO(t.abbrev))}" alt="" onerror="this.style.visibility='hidden'">
        <div class="abbrev">${esc(t.abbrev)}</div>
        ${started && t.sog != null ? `<div class="sog muted">SOG ${esc(t.sog)}</div>` : ""}
      </div>`;

    const sideAbbrev = (s) => (s === "team" ? a.team_abbrev : a.opponent_abbrev);
    const strengthTag = (s) => (s && s !== "ev" ? ` (${esc(s.toUpperCase())})` : "");
    // The scoring summary is rebuilt from play-by-play each poll, so it has late assists
    const goals = Array.isArray(a.goals) ? a.goals : [];
    let goal = "";
    const last = goals[goals.length - 1];
    const g = a.last_goal;
    if (last && last.scorer) {
      goal = `<div class="goal"><span class="muted">Last goal · ${esc(sideAbbrev(last.side))}</span><br>
        <b>${esc(last.scorer)}</b>${strengthTag(last.strength)}
        <span class="muted"> · ${last.assists.length ? last.assists.map(esc).join(", ") : "unassisted"}</span>
        <span class="muted"> · ${esc(last.period_label || "")} ${esc(last.time_in_period || "")}</span></div>`;
    } else if (g && g.scorer && g.game_id === a.game_id) {
      const assists = [g.primary_assist, g.secondary_assist].filter(Boolean).map((p) => esc(p.name)).join(", ");
      goal = `<div class="goal"><span class="muted">Last goal · ${esc(g.type === "opponent_goal" ? g.opponent_abbrev : g.team_abbrev)}</span><br>
        <b>${esc(g.scorer.name)}</b>${g.scorer.season_total ? ` (${esc(g.scorer.season_total)})` : ""}${strengthTag(g.strength)}
        <span class="muted"> · ${assists || "unassisted"}</span>
        <span class="muted"> · ${esc(g.period_label || "")} ${esc(g.time_in_period || "")}</span></div>`;
    }
    if (goal && this._config.media_player && a.last_goal_video) {
      goal = goal.replace(/<\/div>$/, `<br><button class="watch">▶ Watch goal</button></div>`);
    }

    let stats = "";
    const ts = a.team_stats;
    const os = a.opponent_stats;
    if (started && ts && os && this._config.show_stats !== false) {
      const awayS = a.is_home ? os : ts;
      const homeS = a.is_home ? ts : os;
      const rows = [
        ["Shots", "shots_on_goal"],
        ["Hits", "hits"],
        ["Blocks", "blocked_shots"],
        ["Faceoff %", "faceoff_pct"],
        ["PIM", "penalty_minutes"],
        ["PP goals", "power_play_goals"],
      ]
        .map(([label, k]) => `<tr><td>${esc(awayS[k] ?? "–")}</td><td class="label">${label}</td><td>${esc(homeS[k] ?? "–")}</td></tr>`)
        .join("");
      stats = `<div class="section"><table class="stats">${rows}</table></div>`;
    }

    let summary = "";
    if (this._config.show_goals && goals.length) {
      summary = `<div class="section goals">${goals
        .map(
          (x) => `<div><span class="muted">${esc(x.period_label)} ${esc(x.time_in_period)}</span>
            <b>${esc(sideAbbrev(x.side))}</b> ${esc(x.scorer)}${strengthTag(x.strength)}
            <span class="muted">${x.assists.length ? `(${x.assists.map(esc).join(", ")})` : "(unassisted)"}</span></div>`,
        )
        .join("")}</div>`;
    }

    let stars = "";
    if (st.state === "final" && Array.isArray(a.three_stars) && a.three_stars.length) {
      stars = `<div class="section stars"><span class="muted">Three stars</span>${a.three_stars
        .map((s) => `<div>${"★".repeat(s.star || 1)} <b>${esc(s.name)}</b> <span class="muted">${esc(s.team_abbrev || "")}</span></div>`)
        .join("")}</div>`;
    }

    this._shell(`
      <div class="row">
        ${side(away)}
        <div class="mid">
          ${started ? `<div class="scores"><span class="score">${esc(away.score ?? 0)}</span><span class="muted">–</span><span class="score">${esc(home.score ?? 0)}</span></div>` : `<div class="muted">@</div>`}
          <div class="status">${status}</div>
          ${!started && a.venue ? `<div class="muted status">${esc(a.venue)}</div>` : ""}
        </div>
        ${side(home)}
      </div>
      ${goal}${stats}${summary}${stars}`);
    const watch = this.shadowRoot.querySelector("button.watch");
    if (watch) {
      watch.addEventListener("click", () =>
        this._hass.callService("nhl_companion", "play_highlight", {
          entity_id: this._config.media_player,
          clip_id: a.last_goal_video.clip_id,
        }),
      );
    }
  }
}

/* -------------------------------------------------------------- schedule */

class NhlScheduleCard extends NhlBaseCard {
  static getStubConfig() {
    return { title: "NHL schedule", days: 1 };
  }
  get _style() {
    return `
      .day { margin-top: 8px; font-weight: 600; color: var(--secondary-text-color); font-size: 0.9em;
             text-transform: uppercase; letter-spacing: 0.04em; }
      .game { display: grid; grid-template-columns: 1fr auto 1fr auto; align-items: center; gap: 8px;
              padding: 6px 0; border-bottom: 1px solid var(--divider-color); }
      .game:last-child { border-bottom: none; }
      .game.mine { background: color-mix(in srgb, var(--primary-color) 10%, transparent); border-radius: 6px; padding: 6px; }
      .t { display: flex; align-items: center; gap: 6px; min-width: 0; }
      .t.home { justify-content: flex-end; }
      .t .s { font-weight: 700; min-width: 1.2em; text-align: center; }
      .at { color: var(--secondary-text-color); font-size: 0.85em; }
      .st { text-align: right; font-size: 0.85em; min-width: 72px; }
    `;
  }
  _onFirstHass() {
    this._startPolling(60);
  }
  async _poll() {
    try {
      const [sched, teams] = await Promise.all([this._ws("schedule"), this._teams ? null : this._ws("teams")]);
      this._days = sched.days;
      if (teams) this._teams = new Set(teams.teams.map((t) => t.abbrev));
      this._error = null;
    } catch (e) {
      this._error = e.message || String(e);
    }
    this._render();
  }
  _status(g) {
    if (LIVE.has(g.state)) {
      const p = periodLabel(g.period, g.period_type);
      return `<span class="live">${g.in_intermission ? `${p} INT` : `${p} ${esc(g.clock || "")}`}</span>`;
    }
    if (DONE.has(g.state)) {
      const t = g.last_period_type && g.last_period_type !== "REG" ? `/${g.last_period_type}` : "";
      return `<span class="muted">Final${esc(t)}</span>`;
    }
    if (g.schedule_state && g.schedule_state !== "OK") return `<span class="muted">PPD</span>`;
    return `<span class="muted">${timeOf(g.start_utc)}</span>`;
  }
  _render() {
    if (!this._hass) return;
    if (this._error) return this._shell(`<div class="err">${esc(this._error)}</div>`);
    if (!this._days) return this._shell(`<div class="empty">Loading…</div>`);
    const limit = Number(this._config.days || 1);
    const only = this._config.team ? String(this._config.team).toUpperCase() : null;
    const mine = this._teams || new Set();
    const days = this._days.slice(0, limit);
    const body = days
      .map((day) => {
        let games = day.games;
        if (only) games = games.filter((g) => g.home.abbrev === only || g.away.abbrev === only);
        const rows = games
          .map((g) => {
            const started = LIVE.has(g.state) || DONE.has(g.state);
            const isMine = mine.has(g.home.abbrev) || mine.has(g.away.abbrev);
            const team = (t, home) => `
              <div class="t ${home ? "home" : ""}">
                ${home && started ? `<span class="s">${esc(t.score ?? 0)}</span>` : ""}
                ${home ? `<span>${esc(t.abbrev)}</span>` : ""}
                <img class="logo" src="${esc(t.logo || LOGO(t.abbrev))}" alt="" onerror="this.style.visibility='hidden'">
                ${!home ? `<span>${esc(t.abbrev)}</span>` : ""}
                ${!home && started ? `<span class="s">${esc(t.score ?? 0)}</span>` : ""}
              </div>`;
            return `<div class="game ${isMine ? "mine" : ""}">${team(g.away, false)}<span class="at">@</span>${team(g.home, true)}<div class="st">${this._status(g)}</div></div>`;
          })
          .join("");
        const heading = limit > 1 ? `<div class="day">${esc(dayLabel(day.date))}</div>` : "";
        return heading + (rows || `<div class="empty">No games</div>`);
      })
      .join("");
    this._shell(body || `<div class="empty">No games</div>`);
  }
  getCardSize() {
    return 2 + Number(this._config.days || 1) * 3;
  }
}

/* ------------------------------------------------------------- standings */

class NhlStandingsCard extends NhlBaseCard {
  static getStubConfig() {
    return { title: "Standings", view: "division" };
  }
  get _style() {
    return `
      table { width: 100%; border-collapse: collapse; font-size: 0.92em; }
      th { text-align: right; font-weight: 500; color: var(--secondary-text-color); padding: 4px 4px; }
      th:nth-child(1), th:nth-child(2) { text-align: left; }
      td { padding: 4px; text-align: right; border-bottom: 1px solid var(--divider-color); }
      td.rank { text-align: left; color: var(--secondary-text-color); width: 1.5em; }
      td.team { text-align: left; }
      td.team div { display: flex; align-items: center; gap: 6px; }
      td.team img { width: 22px; height: 22px; }
      tr.mine td { font-weight: 700; background: color-mix(in srgb, var(--primary-color) 12%, transparent); }
      td.pts { font-weight: 600; }
      .group { margin-top: 10px; font-weight: 600; color: var(--secondary-text-color); font-size: 0.9em;
               text-transform: uppercase; letter-spacing: 0.04em; }
    `;
  }
  _onFirstHass() {
    this._startPolling(600);
  }
  async _poll() {
    try {
      const [st, teams] = await Promise.all([this._ws("standings"), this._ws("teams")]);
      this._rows = st.standings;
      this._teams = teams.teams.map((t) => t.abbrev);
      this._error = null;
    } catch (e) {
      this._error = e.message || String(e);
    }
    this._render();
  }
  _table(rows, rankKey) {
    const mine = new Set(this._teams || []);
    const body = rows
      .map(
        (r) => `<tr class="${mine.has(r.abbrev) ? "mine" : ""}">
          <td class="rank">${esc(r[rankKey] ?? "")}</td>
          <td class="team"><div><img src="${esc(r.logo || LOGO(r.abbrev))}" alt="" onerror="this.style.visibility='hidden'">${esc(r.abbrev)}</div></td>
          <td>${esc(r.games_played)}</td><td>${esc(r.wins)}</td><td>${esc(r.losses)}</td><td>${esc(r.ot_losses)}</td>
          <td class="pts">${esc(r.points)}</td>
          ${this._config.compact ? "" : `<td>${esc(r.goal_differential ?? "")}</td><td>${esc(r.streak ?? "")}</td>`}
        </tr>`,
      )
      .join("");
    const extra = this._config.compact ? "" : "<th>DIFF</th><th>STRK</th>";
    return `<table><thead><tr><th></th><th>Team</th><th>GP</th><th>W</th><th>L</th><th>OT</th><th>PTS</th>${extra}</tr></thead><tbody>${body}</tbody></table>`;
  }
  _render() {
    if (!this._hass) return;
    if (this._error) return this._shell(`<div class="err">${esc(this._error)}</div>`);
    if (!this._rows) return this._shell(`<div class="empty">Loading…</div>`);
    if (!this._rows.length) return this._shell(`<div class="empty">No standings available</div>`);
    const view = this._config.view || "division";
    const focus = (this._config.team || (this._teams || [])[0] || "").toUpperCase();
    const focusRow = this._rows.find((r) => r.abbrev === focus);
    const byRank = (key) => (a, b) => (a[key] ?? 99) - (b[key] ?? 99);

    if (view === "league") {
      return this._shell(this._table([...this._rows].sort(byRank("league_rank")), "league_rank"));
    }
    const key = view === "conference" ? "conference" : "division";
    const rankKey = view === "conference" ? "conference_rank" : "division_rank";
    let groups = [...new Set(this._rows.map((r) => r[key]).filter(Boolean))].sort();
    if (focusRow && this._config.show_all !== true) groups = [focusRow[key]];
    const html = groups
      .map((group) => {
        const rows = this._rows.filter((r) => r[key] === group).sort(byRank(rankKey));
        return `<div class="group">${esc(group)}</div>${this._table(rows, rankKey)}`;
      })
      .join("");
    this._shell(html);
  }
  getCardSize() {
    return 6;
  }
}

const define = (name, cls) => {
  if (!customElements.get(name)) customElements.define(name, cls);
};
define("nhl-scoreboard-card", NhlScoreboardCard);
define("nhl-schedule-card", NhlScheduleCard);
define("nhl-standings-card", NhlStandingsCard);

window.customCards = window.customCards || [];
for (const [type, name, description] of [
  ["nhl-scoreboard-card", "NHL Scoreboard", "Live score, clock and last goal for a followed team."],
  ["nhl-schedule-card", "NHL Schedule", "League schedule for today or the week with live scores."],
  ["nhl-standings-card", "NHL Standings", "Division, conference or league standings."],
]) {
  if (!window.customCards.some((c) => c.type === type)) {
    window.customCards.push({ type, name, description, preview: true });
  }
}
console.info(`%c NHL-COMPANION-CARDS %c ${NHL_VERSION} `, "background:#000;color:#fff", "background:#fc4c02;color:#000");
