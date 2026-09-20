/* Free Time Scoreboard
 *
 * Mirrors scripts/lib_windows.py exactly. If you change one, change the other.
 *
 * Timezone handling: every instant is normalised to UTC before any arithmetic.
 * This is not cosmetic -- JS Date subtraction is already UTC-based, but the
 * wall-clock <-> UTC conversions below must iterate because the America/
 * Los_Angeles offset changes twice a year.
 */
(function () {
  "use strict";

  const TZ = "America/Los_Angeles";
  const DATA = window.SCHEDULE_DATA;

  // Verified averages, in minutes. Must match DEFAULT_DURATIONS in lib_windows.py.
  const DURATIONS = DATA._meta.durations_minutes;

  // Conservative envelope for a dated game with no announced start time.
  // Must match TBD_ENVELOPE_PT in lib_windows.py.
  const TBD_ENVELOPE = { MLB: ["15:00", "23:59"], NFL: ["09:00", "23:59"], NCAAF: ["11:00", "23:59"], MLS: ["16:00", "23:59"] };

  const LEAGUE_NAMES = { MLB: "MLB", NFL: "NFL", NCAAF: "College Football", MLS: "MLS" };
  const HIGH_PRIORITY_TEAMS = ["San Francisco 49ers", "San Jose Earthquakes", "Stanford", "California", "San Francisco Giants", "Athletics"];

  const MLB_TBD_SENTINEL = "07:33:00";

  // ---------------------------------------------------------------------
  // Timezone helpers
  // ---------------------------------------------------------------------

  /** UTC offset of America/Los_Angeles at a given instant, in minutes. */
  function ptOffsetMinutes(tsMs) {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: TZ, hour12: false,
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    }).formatToParts(new Date(tsMs));
    const m = {};
    parts.forEach((p) => { m[p.type] = p.value; });
    const asUTC = Date.parse(`${m.year}-${m.month}-${m.day}T${m.hour}:${m.minute}:${m.second}Z`);
    return Math.round((asUTC - tsMs) / 60000);
  }

  /** UTC epoch-ms for a wall-clock time in the user's timezone. Iterates to converge across DST. */
  function ptWallToUtc(dateStr, hhmm) {
    const base = Date.parse(`${dateStr}T${hhmm}:00Z`);
    let ts = base;
    for (let i = 0; i < 3; i++) ts = base - ptOffsetMinutes(ts) * 60000;
    return ts;
  }

  function addDaysStr(dateStr, n) {
    const d = new Date(dateStr + "T12:00:00Z");
    d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
  }

  /** [startUtc, endUtc, minutes] for a local calendar day. A DST day is 23 or 25h. */
  function localDay(dateStr) {
    const start = ptWallToUtc(dateStr, "00:00");
    const end = ptWallToUtc(addDaysStr(dateStr, 1), "00:00");
    return { start: start, end: end, minutes: (end - start) / 60000 };
  }

  function fmtTime(tsMs) {
    return new Intl.DateTimeFormat("en-US", {
      timeZone: TZ, hour: "numeric", minute: "2-digit", timeZoneName: "short",
    }).format(new Date(tsMs));
  }

  function fmtTZ(tsMs) {
    const parts = new Intl.DateTimeFormat("en-US", { timeZone: TZ, timeZoneName: "short" }).formatToParts(new Date(tsMs));
    return (parts.find((p) => p.type === "timeZoneName") || {}).value || "PT";
  }

  function fmtLongDate(dateStr) {
    return new Intl.DateTimeFormat("en-US", {
      timeZone: TZ, weekday: "long", year: "numeric", month: "long", day: "numeric",
    }).format(new Date(dateStr + "T20:00:00Z"));
  }

  function hhmmToMinutes(hhmm) {
    const [h, m] = hhmm.split(":").map(Number);
    return h * 60 + m;
  }

  // ---------------------------------------------------------------------
  // Interval engine (mirror of lib_windows.py)
  // ---------------------------------------------------------------------

  function timeIsUnconfirmed(game) {
    if (game.time_status === "TBD_official_date" || game.time_status === "TBD_envelope") return true;
    return !!game.start_utc && game.league === "MLB" && game.start_utc.slice(11, 19) === MLB_TBD_SENTINEL;
  }

  function gameToInterval(game) {
    if (!game.start_utc) return null;
    const minutes = game.duration || DURATIONS[game.league];

    if (timeIsUnconfirmed(game)) {
      const [s, e] = TBD_ENVELOPE[game.league];
      return {
        start: ptWallToUtc(game.date_local, s),
        end: ptWallToUtc(game.date_local, e),
        label: game.label + " (time not announced)",
        priority: game.priority || "normal",
        league: game.league,
        source: game.source || "",
        timeConfirmed: false,
      };
    }

    let start = Date.parse(game.start_utc);
    const end = start + (minutes * 60000);
    // Conservative widening: block from the radio air time if it precedes kickoff.
    if (game.radio_air_utc) {
      const air = Date.parse(game.radio_air_utc);
      if (air < start) start = air;
    }
    return {
      start: start, end: end,
      label: game.label, priority: game.priority || "normal",
      league: game.league, source: game.source || "", timeConfirmed: true,
    };
  }

  function clip(iv, s, e) {
    if (iv.start >= e || iv.end <= s) return null;
    return {
      start: Math.max(iv.start, s), end: Math.min(iv.end, e),
      label: iv.label, priority: iv.priority, league: iv.league,
      source: iv.source, timeConfirmed: iv.timeConfirmed,
    };
  }

  function merge(list) {
    if (!list.length) return [];
    const sorted = list.slice().sort((a, b) => a.start - b.start || a.end - b.end);
    const out = [];
    sorted.forEach((cur) => {
      const last = out[out.length - 1];
      if (last && cur.start <= last.end) {
        last.end = Math.max(last.end, cur.end);
        if (cur.priority === "high") last.priority = "high";
        if (!cur.timeConfirmed) last.timeConfirmed = false;
        if (last.label && cur.label && last.label.indexOf(cur.label) === -1) last.label += " + " + cur.label;
      } else {
        out.push(Object.assign({}, cur));
      }
    });
    return out;
  }

  function freeWindows(dayStart, dayEnd, busy) {
    const merged = merge(busy.map((iv) => clip(iv, dayStart, dayEnd)).filter(Boolean));
    const wins = [];
    let cursor = dayStart;
    merged.forEach((iv) => {
      if (iv.start > cursor) wins.push({ start: cursor, end: iv.start });
      cursor = Math.max(cursor, iv.end);
    });
    if (cursor < dayEnd) wins.push({ start: cursor, end: dayEnd });
    return wins;
  }

  // ---------------------------------------------------------------------
  // Day report
  // ---------------------------------------------------------------------

  function dayReport(dateStr, extraGames) {
    const day = localDay(dateStr);
    const all = DATA.games.concat(extraGames || []);
    const busy = [];
    const unplaced = [];

    all.forEach((game) => {
      const iv = gameToInterval(game);
      if (!iv) { if (game.date_local === dateStr) unplaced.push(game); return; }
      const c = clip(iv, day.start, day.end);
      if (c) busy.push(c);
    });

    const merged = merge(busy);
    const wins = freeWindows(day.start, day.end, busy);
    const busyMs = merged.reduce((a, iv) => a + (iv.end - iv.start), 0);
    const busyMin = busyMs / 60000;
    const unconfirmed = merged.filter((iv) => !iv.timeConfirmed);
    const longest = wins.reduce((a, w) => (!a || w.end - w.start > a.end - a.start ? w : a), null);

    return {
      date: dateStr,
      dayMinutes: day.minutes,
      busyMinutes: Math.round(busyMin * 10) / 10,
      freeMinutes: Math.round((day.minutes - busyMin) * 10) / 10,
      isFreeDay: merged.length === 0,
      hasHighPriority: merged.some((iv) => iv.priority === "high"),
      hasUnconfirmed: unconfirmed.length > 0,
      unconfirmedMinutes: Math.round(unconfirmed.reduce((a, iv) => a + (iv.end - iv.start), 0) / 60000 * 10) / 10,
      longest: longest,
      freeWindows: wins,
      busy: merged,
      unplaced: unplaced,
      dayStart: day.start, dayEnd: day.end,
    };
  }

  // ---------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------

  const $ = (id) => document.getElementById(id);
  let currentDate = addDaysStr(new Date().toISOString().slice(0, 10), 0);
  let liveMlb = null;   // { dateStr, games: [] }
  // The offline/live disclosure is state, not per-render output: renderDay() runs on
  // every navigation and must not silently erase it. Without this, clicking "next
  // day" wiped the warning that you are looking at bundled rather than live data.
  let mlbFeedState = { mode: "pending", message: "" };

  function renderMlbNote(dateStr) {
    const note = $("mlbNote");
    const extras = (liveMlb && liveMlb.dateStr === dateStr) ? liveMlb.games : [];
    if (extras.length) {
      note.className = "note info";
      note.innerHTML = `Showing <strong>${extras.length} MLB games fetched live</strong> from statsapi.mlb.com for ${esc(dateStr)}. ` +
        "This is the authoritative source; it supersedes the bundled snapshot for this date.";
    } else if (mlbFeedState.mode === "offline") {
      note.className = "note warn";
      note.innerHTML = `<strong>Live MLB fetch failed</strong> (${esc(mlbFeedState.message)}). Showing the bundled verified snapshot instead. ` +
        "The app works offline by design; open it over http(s) with network access for the live feed.";
    } else if (mlbFeedState.mode === "empty") {
      note.className = "note info";
      note.innerHTML = `No MLB games on <strong>${esc(dateStr)}</strong> per the live statsapi.mlb.com feed. ` +
        (extras.length ? "" : "This date is genuinely clear of MLB.");
    } else {
      note.className = "note hidden";
      note.innerHTML = "";
    }
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  function pctOf(ts, dayStart, dayEnd) {
    return ((ts - dayStart) / (dayEnd - dayStart)) * 100;
  }

  function renderTimeline(rep) {
    const el = $("timeline");
    el.innerHTML = "";
    rep.busy.forEach((iv) => {
      const d = document.createElement("div");
      d.className = "blk" + (iv.priority === "high" ? " high" : "");
      d.style.left = pctOf(iv.start, rep.dayStart, rep.dayEnd) + "%";
      d.style.width = Math.max(pctOf(iv.end, rep.dayStart, rep.dayEnd) - pctOf(iv.start, rep.dayStart, rep.dayEnd), 0.35) + "%";
      d.title = `${fmtTime(iv.start)} - ${fmtTime(iv.end)}  ${iv.label}`;
      if (!iv.timeConfirmed) d.style.opacity = "0.45";
      el.appendChild(d);
    });

    const axis = $("axis");
    axis.innerHTML = "";
    for (let h = 0; h <= 24; h += 4) {
      const span = document.createElement("span");
      span.textContent = h === 24 ? "12a" : (h === 12 ? "12p" : ((h % 12) || 12) + (h < 12 ? "a" : "p"));
      axis.appendChild(span);
    }
  }

  function renderFree(rep) {
    const box = $("freeList");
    box.innerHTML = "";
    if (!rep.freeWindows.length) {
      box.innerHTML = '<div class="empty">No free time today &mdash; the day is fully covered.</div>';
      return;
    }
    rep.freeWindows.forEach((w) => {
      const mins = Math.round((w.end - w.start) / 60000);
      const div = document.createElement("div");
      div.className = "freewin" + (rep.longest && w === rep.longest ? " best" : "");
      div.innerHTML =
        `<div class="t">${esc(fmtTime(w.start))} &ndash; ${esc(fmtTime(w.end))}</div>` +
        `<div class="d">${mins >= 60 ? Math.floor(mins / 60) + "h " + (mins % 60 ? mins % 60 + "m" : "") : mins + "m"} free</div>`;
      box.appendChild(div);
    });
  }

  function renderScoreboard(rep, games) {
    const box = $("scoreboard");
    box.innerHTML = "";
    const todays = games
      .map((g) => ({ g: g, iv: gameToInterval(g) }))
      .filter((x) => x.iv && x.iv.start < rep.dayEnd && x.iv.end > rep.dayStart)
      .sort((a, b) => a.iv.start - b.iv.start);

    if (!todays.length) {
      box.innerHTML = '<div class="empty">No games scheduled in the covered sources for this date.</div>';
      return;
    }

    const byLeague = {};
    todays.forEach((x) => { (byLeague[x.g.league] = byLeague[x.g.league] || []).push(x); });

    Object.keys(byLeague).sort().forEach((league) => {
      const group = document.createElement("div");
      group.className = "leaguegroup";
      group.innerHTML =
        `<div class="leaguehead"><span class="dot ${league}"></span>${esc(LEAGUE_NAMES[league] || league)}` +
        `<span class="cnt">${byLeague[league].length} game${byLeague[league].length > 1 ? "s" : ""}</span></div>`;

      byLeague[league].forEach((x) => {
        const row = document.createElement("div");
        row.className = "game" + (x.g.priority === "high" ? " high" : "");
        const timeTxt = x.iv.timeConfirmed ? esc(fmtTime(x.iv.start)) : "TBD";
        const tzTxt = x.iv.timeConfirmed ? esc(fmtTZ(x.iv.start)) : "no time set";
        const endTxt = x.iv.timeConfirmed ? esc(fmtTime(x.iv.end)) : "";
        const srcLink = x.g.source ? `<a href="${esc(x.g.source)}" target="_blank" rel="noopener">verify</a>` : "";
        row.innerHTML =
          `<div class="time">${timeTxt}<span class="tz">${tzTxt}</span></div>` +
          `<div class="who">${esc(x.g.label)}` +
            `<span class="det">${esc(x.g.detail || "")}${endTxt ? " &middot; ends ~" + endTxt : ""}</span>` +
            (x.g.network ? `<span class="net">${esc(x.g.network)}</span>` : "") +
          `</div>` +
          `<div class="meta">` +
            (x.g.priority === "high" ? '<span class="pill high">High priority</span> ' : "") +
            (!x.iv.timeConfirmed ? '<span class="pill tbd">Time TBD</span> ' : "") +
            srcLink +
          `</div>`;
        group.appendChild(row);
      });
      box.appendChild(group);
    });
  }

  function renderDay(dateStr) {
    currentDate = dateStr;
    $("dateInput").value = dateStr;

    const extras = (liveMlb && liveMlb.dateStr === dateStr) ? liveMlb.games : [];
    const rep = dayReport(dateStr, extras);
    const games = DATA.games.concat(extras);

    $("dayHeading").textContent = fmtLongDate(dateStr) +
      (rep.dayMinutes !== 1440 ? `  (${Math.round(rep.dayMinutes / 60)}h day, DST)` : "");

    const v = $("verdict");
    v.className = "verdict " + (rep.isFreeDay ? "free" : "busy");
    if (rep.isFreeDay) {
      v.innerHTML = "FULLY FREE &mdash; no scheduled game in any covered source" +
        `<span class="sub">All ${Math.round(rep.dayMinutes / 60)} hours are open.</span>`;
    } else {
      const parts = [];
      parts.push(`Free time: <strong>${Math.round(rep.freeMinutes / 60 * 10) / 10}h</strong> of ${Math.round(rep.dayMinutes / 60 * 10) / 10}h`);
      if (rep.hasHighPriority) parts.push("includes a <strong>high-priority</strong> Bay Area team");
      if (rep.hasUnconfirmed) parts.push("<strong>some start times are not yet announced</strong> &mdash; the shaded block is a conservative estimate, not a confirmed window");
      v.innerHTML = "BUSY &mdash; games are scheduled" + `<span class="sub">${parts.join(" &middot; ")}</span>`;
    }

    $("freeSummary").textContent = `${Math.round(rep.freeMinutes / 60 * 10) / 10}h free / ${Math.round(rep.dayMinutes / 60 * 10) / 10}h`;
    renderTimeline(rep);
    renderFree(rep);
    renderScoreboard(rep, games);

    renderMlbNote(dateStr);
  }

  // ---------------------------------------------------------------------
  // Vacation tab
  // ---------------------------------------------------------------------

  function renderVacation() {
    const interp = document.querySelector('input[name="interp"]:checked').value;
    const rows = DATA.vacation.filter((r) => r.interpretation === interp);
    const body = $("vacationBody");
    body.innerHTML = "";
    let bestYear = null;
    let bestDays = -1;
    rows.forEach((r) => {
      if (r.year > 2026 && r.best && r.best.days > bestDays) { bestDays = r.best.days; bestYear = r.year; }
    });

    rows.forEach((r) => {
      const verified = r.year === 2026;
      const tr = document.createElement("tr");
      if (r.year === bestYear) tr.className = "best";
      tr.innerHTML =
        `<td class="num"><strong>${r.year}</strong>${r.year === bestYear ? " &#9733;" : ""}</td>` +
        `<td class="num">${r.best ? r.best.days + " days" : "none"}</td>` +
        `<td class="num">${r.best ? esc(r.best.start) + " &rarr; " + esc(r.best.end) : "&mdash;"}</td>` +
        `<td class="num">${r.best ? r.best.weeks : 0}</td>` +
        `<td class="num">${r.free_day_count}</td>` +
        `<td class="${verified ? "statusV" : "statusE"}">${verified ? "VERIFIED" : "ESTIMATED"}</td>`;
      body.appendChild(tr);
    });

    const detail = $("vacationDetail");
    detail.innerHTML = rows.map((r) => {
      const p = r.provenance;
      return `<div class="reviewgroup"><h3>${r.year} &mdash; how this was derived</h3>` +
        `<div class="reviewitem">Previous NFL season closes on <strong>${esc(p.nfl_previous_season_end.date)}</strong> &mdash; ${esc(p.nfl_previous_season_end.status)}: ${esc(p.nfl_previous_season_end.note)}` +
        `<span class="r">Source: NFL / league announcement</span></div>` +
        `<div class="reviewitem">MLB blocks <strong>${esc(p.mlb_block.start)} &rarr; ${esc(p.mlb_block.end)}</strong> &mdash; ${esc(p.mlb_block.status)}${p.mlb_block.includes_spring_training ? " (includes Spring Training)" : " (Spring Training excluded)"}` +
        `<span class="r">Source: statsapi.mlb.com/api/v1/seasons</span></div>` +
        `<div class="reviewitem">Current NFL season opens <strong>${esc(p.nfl_current_season_start.date)}</strong> &mdash; ${esc(p.nfl_current_season_start.status)}: ${esc(p.nfl_current_season_start.note)}` +
        `<span class="r">Source: ESPN league calendar / NFL</span></div>` +
        `<div class="reviewitem">All clean runs found: ` +
        r.gaps.map((g) => `${esc(g.start)} &rarr; ${esc(g.end)} (${g.days}d)`).join("; ") +
        `</div></div>`;
    }).join("");
  }

  // ---------------------------------------------------------------------
  // Review + sources tabs
  // ---------------------------------------------------------------------

  function renderReview() {
    const box = $("reviewList");
    const byLeague = {};
    DATA.unresolved.forEach((u) => { (byLeague[u.league] = byLeague[u.league] || []).push(u); });
    $("reviewCount").textContent = DATA.unresolved.length;

    box.innerHTML = Object.keys(byLeague).sort().map((league) => {
      const items = byLeague[league].map((u) =>
        `<div class="reviewitem"><strong>${esc(u.label)}</strong>${u.date_local ? " &middot; " + esc(u.date_local) : ""}` +
        `<span class="r">${esc(u.reason)}</span>` +
        (u.source ? `<span class="r"><a href="${esc(u.source)}" target="_blank" rel="noopener">${esc(u.source)}</a></span>` : "") +
        `</div>`).join("");
      return `<div class="reviewgroup"><h3>${esc(LEAGUE_NAMES[league] || league)} &mdash; ${byLeague[league].length} item(s)</h3>${items}</div>`;
    }).join("");
  }

  function renderSources() {
    const seen = {};
    const rows = [];
    DATA.games.forEach((g) => {
      if (g.source && !seen[g.source]) {
        seen[g.source] = true;
        rows.push({ label: `${g.league} &middot; ${g.label}`, url: g.source });
      }
    });
    const fixed = [
      { label: "MLB Stats API &mdash; season frames 2026-2029", url: "https://statsapi.mlb.com/api/v1/seasons?sportId=1&startSeason=2026&endSeason=2029" },
      { label: "MLB Stats API &mdash; schedule (live, used by this page)", url: "https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=2026-09-20&endDate=2026-09-20&gameType=R" },
      { label: "MLB Stats API &mdash; 2026 postseason bracket (placeholder teams + 07:33Z sentinel times)", url: "https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=2026-09-28&endDate=2026-10-31&gameType=E,S,D,L,F,W" },
      { label: "Westwood One Sports &mdash; official NFL schedule", url: "https://www.westwoodonesports.com/nfl-schedule/" },
      { label: "Westwood One Sports &mdash; station finder", url: "https://www.westwoodonesports.com/station-finder" },
      { label: "ESPN NFL league calendar (week boundaries, preseason, playoffs)", url: "http://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=20260920" },
      { label: "San Francisco 49ers &mdash; official schedule", url: "https://www.49ers.com/schedule/" },
      { label: "49ers / KNBR flagship partnership through 2030 (Cumulus)", url: "https://www.cumulusmedia.com/2026-04-15/san-francisco-49ers-announce-multi-year-partnership-extension-with-cumulus-medias-knbr/" },
      { label: "Stanford Cardinal &mdash; 2026 season opener", url: "https://gostanford.com/news/2026-08-24/2026-season-begins-with-week-0-matchup-against-hawaii-at-stanford-stadium" },
      { label: "Stanford Cardinal &mdash; announced kickoff times", url: "https://gostanford.com/news/2026-05-27/game-times-tv-networks-announced-for-select-games" },
      { label: "California Golden Bears &mdash; ACC Friday Football / 2026 schedule", url: "https://calbears.com/news/2026/5/15/acc-releases-full-2026-friday-football-schedule.aspx" },
      { label: "San Jose Earthquakes &mdash; 2026 MLS schedule", url: "https://www.sjearthquakes.com/news/news-earthquakes-announce-2026-major-league-soccer-schedule" },
      { label: "MLB.com &mdash; playoff picture and clinched teams", url: "https://www.mlb.com/news/mlb-playoff-picture-and-bracket-2026" },
      { label: "NFL &mdash; Super Bowl LXIII awarded to Las Vegas (2029)", url: "https://www.nfl.com/news/las-vegas-to-host-super-bowl-lxiii-in-2029" },
      { label: "NFL &mdash; Super Bowl LXII at Mercedes-Benz Stadium (2028)", url: "https://www.nfl.com/news/mercedes-benz-stadium-in-atlanta-to-host-super-bowl-lxii-in-2028" },
    ];
    $("sourcesList").innerHTML =
      '<div class="srcgrid">' + fixed.concat(rows).map((r) =>
        `<div class="srccard"><h4>${r.label}</h4><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.url)}</a>` +
        `<span class="when">Retrieved 2026-09-20</span></div>`).join("") + "</div>";
  }

  // ---------------------------------------------------------------------
  // Live MLB refresh
  // ---------------------------------------------------------------------

  function fetchMlbFor(dateStr) {
    const url = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=" + dateStr +
      "&endDate=" + dateStr +
      "&gameType=R,E,S,D,L,F,W,A" +
      "&fields=dates,date,games,gamePk,gameDate,teams,away,home,team,id,name";
    return fetch(url)
      .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then((payload) => {
        const out = [];
        ((payload.dates || [])[0] || { games: [] }).games.forEach((g) => {
          const away = g.teams.away.team, home = g.teams.home.team;
          const isHigh = HIGH_PRIORITY_TEAMS.some((t) => (home.name || "").indexOf(t) === 0 || (away.name || "").indexOf(t) === 0);
          out.push({
            league: "MLB",
            label: `${away.name || away.id} at ${home.name || home.id}`,
            detail: "live from statsapi.mlb.com",
            network: isHigh ? "KNBR 680 AM / 104.5 FM" : "",
            priority: isHigh ? "high" : "normal",
            source: "https://www.mlb.com/schedule",
            date_local: dateStr,
            start_utc: g.gameDate.replace("Z", "Z"),
            duration: DURATIONS.MLB,
            time_status: g.gameDate.slice(11, 19) === MLB_TBD_SENTINEL ? "TBD_official_date" : "official",
          });
        });
        return out;
      });
  }

  function refreshMlb(dateStr) {
    fetchMlbFor(dateStr)
      .then((games) => {
        liveMlb = { dateStr: dateStr, games: games };
        mlbFeedState = { mode: games.length ? "live" : "empty", message: "" };
        renderMlbNote(currentDate);
        renderDay(currentDate);
      })
      .catch((err) => {
        mlbFeedState = { mode: "offline", message: String(err && err.message ? err.message : err) };
        renderMlbNote(currentDate);
      });
  }

  // ---------------------------------------------------------------------
  // Wiring
  // ---------------------------------------------------------------------

  let initialised = false;

  function init() {
    // Idempotent on purpose: DOMContentLoaded can fire more than once (and app.js
    // can be evaluated twice), and a second run would double-bind every control --
    // one click on "next day" would then advance two days.
    if (initialised) return;
    initialised = true;

    $("genStamp").textContent = "Bundle generated " + DATA._meta.generated_utc +
      " &middot; " + DATA._meta.counts.games + " games, " + DATA._meta.counts.unresolved + " flagged for review";

    document.querySelectorAll(".tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        $("tab-" + btn.dataset.tab).classList.add("active");
      });
    });

    $("prevDay").addEventListener("click", () => { renderDay(addDaysStr(currentDate, -1)); refreshMlb(currentDate); });
    $("nextDay").addEventListener("click", () => { renderDay(addDaysStr(currentDate, 1)); refreshMlb(currentDate); });
    $("todayBtn").addEventListener("click", () => { renderDay(new Date().toISOString().slice(0, 10)); refreshMlb(currentDate); });
    $("dateInput").addEventListener("change", (e) => { if (e.target.value) { renderDay(e.target.value); refreshMlb(currentDate); } });
    $("refreshMlb").addEventListener("click", () => refreshMlb(currentDate));
    document.querySelectorAll('input[name="interp"]').forEach((r) => r.addEventListener("change", renderVacation));

    renderVacation();
    renderReview();
    renderSources();
    renderDay(currentDate);
    refreshMlb(currentDate);
  }

  // If this file is ever reached after the document has finished parsing (deferred
  // script, late injection), DOMContentLoaded will never fire again and the page
  // would sit dead. Handle both cases.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Exposed for tests/test_parity_js.py -- lets Node run the same engine the browser runs.
  window.FreeTimeEngine = {
    localDay: localDay, ptWallToUtc: ptWallToUtc, ptOffsetMinutes: ptOffsetMinutes,
    gameToInterval: gameToInterval, clip: clip, merge: merge,
    freeWindows: freeWindows, dayReport: dayReport, timeIsUnconfirmed: timeIsUnconfirmed,
    DURATIONS: DURATIONS, TBD_ENVELOPE: TBD_ENVELOPE, TZ: TZ,
  };
})();
