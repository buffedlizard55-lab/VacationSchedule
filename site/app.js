/* Free Time Scoreboard
 *
 * Mirrors scripts/lib_windows.py exactly. If you change one, change the other.
 *
 * Timezone handling: every instant is normalised to UTC before any arithmetic.
 * This is not cosmetic -- JS Date subtraction is already UTC-based, but the
 * wall-clock <-> UTC conversions below must iterate because the America/
 * Los_Angeles offset changes twice a year.
 *
 * Sections: the user asked to compare three definitions of "busy" (see
 * data/verified/profiles.json). Every game carries a `sections` list computed at
 * build time, and every report is produced once per section.
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
  const LEAGUE_ORDER = ["MLB", "NFL", "NCAAF", "MLS"];
  const HIGH_PRIORITY_TEAMS = ["San Francisco 49ers", "San Jose Earthquakes", "Stanford", "California", "San Francisco Giants", "Athletics"];

  const MLB_TBD_SENTINEL = "07:33:00";
  // A day report is evaluated for multiple scopes/frame variants by parity tests.
  // Interval construction is independent of the selected scope, so cache it by
  // game object and avoid repeating expensive Intl timezone conversions.
  const INTERVAL_CACHE = new WeakMap();

  const SECTIONS = (DATA.sections && DATA.sections.sections) || [];
  const EXTRA_SCOPE = (DATA.sections && DATA.sections.extra_scope) || { id: "all", short: "Everything tracked" };
  const SCOPES = SECTIONS.map((s) => ({ id: s.id, short: s.short, name: s.name, definition: s.definition, radio: s.radio }))
    .concat([{ id: EXTRA_SCOPE.id, short: EXTRA_SCOPE.short, name: EXTRA_SCOPE.name, definition: EXTRA_SCOPE.definition || [], radio: [] }]);

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

  /** UTC epoch-ms for a wall-clock time in an IANA timezone. */
  function zoneWallToUtc(dateStr, hhmm, zone) {
    const base = Date.parse(`${dateStr}T${hhmm}:00Z`);
    let ts = base;
    for (let i = 0; i < 3; i++) {
      const parts = new Intl.DateTimeFormat("en-US", {
        timeZone: zone, hour12: false,
        year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", second: "2-digit",
      }).formatToParts(new Date(ts));
      const m = {};
      parts.forEach((p) => { m[p.type] = p.value; });
      const asUTC = Date.parse(`${m.year}-${m.month}-${m.day}T${m.hour}:${m.minute}:${m.second}Z`);
      ts = base - Math.round((asUTC - ts) / 60000) * 60000;
    }
    return ts;
  }

  /** UTC epoch-ms for a Pacific wall-clock time. Iterates across DST. */
  function ptWallToUtc(dateStr, hhmm) {
    return zoneWallToUtc(dateStr, hhmm, TZ);
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

  function gameInScope(game, scope) {
    if (!scope || scope === "all") return true;
    return (game.sections || []).indexOf(scope) !== -1;
  }

  function timeIsUnconfirmed(game) {
    if (game.time_status === "TBD_official_date" || game.time_status === "TBD_envelope") return true;
    return !!game.start_utc && game.league === "MLB" && game.start_utc.slice(11, 19) === MLB_TBD_SENTINEL;
  }

  function gameToInterval(game) {
    if (INTERVAL_CACHE.has(game)) return INTERVAL_CACHE.get(game);
    if (!game.start_utc) {
      INTERVAL_CACHE.set(game, null);
      return null;
    }
    const minutes = game.duration || DURATIONS[game.league];
    let result;

    if (timeIsUnconfirmed(game)) {
      const [s, e] = TBD_ENVELOPE[game.league];
      result = {
        start: ptWallToUtc(game.date_local, s),
        end: ptWallToUtc(game.date_local, e),
        label: game.label + " (time not announced)",
        priority: game.priority || "normal",
        league: game.league,
        source: game.source || "",
        timeConfirmed: false,
        provisional: false,
      };
    } else {
      let start = Date.parse(game.start_utc);
      const end = start + (minutes * 60000);
      // Conservative widening: block from the radio air time if it precedes kickoff.
      if (game.radio_air_utc) {
        const air = Date.parse(game.radio_air_utc);
        if (air < start) start = air;
      }
      result = {
        start: start, end: end,
        label: game.label, priority: game.priority || "normal",
        league: game.league, source: game.source || "", timeConfirmed: true,
        provisional: false,
      };
    }
    INTERVAL_CACHE.set(game, result);
    return result;
  }

  function recordIsOnDate(game, dateStr) {
    if (game.date_local === dateStr) return true;
    if (!game.start_utc) return false;
    const ts = Date.parse(game.start_utc);
    if (isNaN(ts)) return false;
    return ptDateOf(ts) === dateStr;
  }

  function ptDateOf(tsMs) {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit",
    }).formatToParts(new Date(tsMs));
    const m = {};
    parts.forEach((p) => { m[p.type] = p.value; });
    return `${m.year}-${m.month}-${m.day}`;
  }

  function mlbFrameFor(dateStr, frames) {
    if (!frames) return null;
    const keys = Object.keys(frames).sort();
    for (let i = 0; i < keys.length; i++) {
      const f = frames[keys[i]];
      if (f && f.start && f.end && f.start <= dateStr && dateStr <= f.end) return f;
    }
    return null;
  }

  function mlbFrameIsCovered(dateStr, frame) {
    const ranges = (frame && frame.complete_ranges) || [];
    for (let i = 0; i < ranges.length; i++) {
      if (ranges[i][0] <= dateStr && dateStr <= ranges[i][1]) return true;
    }
    return false;
  }

  function mlbCoveredOnDate(games, dateStr) {
    return games.some((g) => g.league === "MLB" && recordIsOnDate(g, dateStr));
  }

  function framePlaceholderInterval(dateStr, frame) {
    const [s, e] = TBD_ENVELOPE.MLB;
    return {
      start: ptWallToUtc(dateStr, s),
      end: ptWallToUtc(dateStr, e),
      label: (frame.label || "MLB") + " - per-game time not in the bundled snapshot",
      priority: "normal", league: "MLB", source: frame.source || "",
      timeConfirmed: false, provisional: true,
    };
  }

  function clip(iv, s, e) {
    if (iv.start >= e || iv.end <= s) return null;
    return {
      start: Math.max(iv.start, s), end: Math.min(iv.end, e),
      label: iv.label, priority: iv.priority, league: iv.league,
      source: iv.source, timeConfirmed: iv.timeConfirmed, provisional: iv.provisional,
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

  function dayReport(dateStr, extraGames, scope, useFrames) {
    const day = localDay(dateStr);
    const games = DATA.games.concat(extraGames || []);
    const all = games.filter((g) => gameInScope(g, scope));
    const busy = [];
    const unplaced = [];

    all.forEach((game) => {
      const iv = gameToInterval(game);
      if (!iv) { if (game.date_local === dateStr) unplaced.push(game); return; }
      const c = clip(iv, day.start, day.end);
      if (c) busy.push(c);
    });

    const frames = useFrames === false ? null : DATA.mlb_frames;
    const frame = mlbFrameFor(dateStr, frames);
    const frameUsed = !!(frame && !mlbCoveredOnDate(all, dateStr) && !mlbFrameIsCovered(dateStr, frame));
    if (frameUsed) {
      const c = clip(framePlaceholderInterval(dateStr, frame), day.start, day.end);
      if (c) busy.push(c);
    }

    const merged = merge(busy);
    const wins = freeWindows(day.start, day.end, busy);
    const busyMs = merged.reduce((a, iv) => a + (iv.end - iv.start), 0);
    const busyMin = busyMs / 60000;
    const unconfirmed = merged.filter((iv) => !iv.timeConfirmed);
    const longest = wins.reduce((a, w) => (!a || w.end - w.start > a.end - a.start ? w : a), null);

    // Games the project tracks that this section does NOT count. Shown, never hidden.
    const outside = games.filter((g) => !gameInScope(g, scope))
      .map((g) => ({ g: g, iv: gameToInterval(g) }))
      .filter((x) => x.iv && x.iv.start < day.end && x.iv.end > day.start)
      .sort((a, b) => a.iv.start - b.iv.start);

    return {
      date: dateStr,
      scope: scope || "all",
      dayMinutes: day.minutes,
      busyMinutes: Math.round(busyMin * 10) / 10,
      freeMinutes: Math.round((day.minutes - busyMin) * 10) / 10,
      isFreeDay: merged.length === 0,
      hasHighPriority: merged.some((iv) => iv.priority === "high"),
      hasUnconfirmed: unconfirmed.length > 0,
      unconfirmedMinutes: Math.round(unconfirmed.reduce((a, iv) => a + (iv.end - iv.start), 0) / 60000 * 10) / 10,
      mlbFrameFallback: frameUsed,
      mlbFrame: frame,
      longest: longest,
      freeWindows: wins,
      busy: merged,
      outside: outside,
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
  let scope = "3";      // the site's original definition; switchable in the header
  let tripLength = 14;  // decision engine: consecutive free days the trip needs

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  function scopeLabel(id) {
    const s = SCOPES.filter((x) => x.id === id)[0];
    return s ? s.name : id;
  }

  function scopeShort(id) {
    const s = SCOPES.filter((x) => x.id === id)[0];
    return s ? s.short : id;
  }

  function fmtDuration(mins) {
    const m = Math.round(mins);
    return m >= 60 ? Math.floor(m / 60) + "h " + (m % 60 ? (m % 60) + "m" : "") : m + "m";
  }

  function renderScopePicker() {
    const box = $("scopePicker");
    if (!box) return;
    box.innerHTML = SCOPES.map((s) =>
      `<button type="button" class="scopebtn${s.id === scope ? " active" : ""}" data-scope="${esc(s.id)}" ` +
      `title="${esc(s.name)}">${esc(s.short)}</button>`
    ).join("");
    box.querySelectorAll(".scopebtn").forEach((btn) => {
      btn.addEventListener("click", () => setScope(btn.dataset.scope));
    });
  }

  function renderScopeNote() {
    const box = $("scopeNote");
    if (!box) return;
    const s = SCOPES.filter((x) => x.id === scope)[0];
    if (!s) { box.className = "note hidden"; return; }
    box.className = "note info";
    box.innerHTML =
      `<strong>Section ${esc(s.id === "all" ? "" : s.id)}${esc(s.id === "all" ? " (superset)" : "")} &mdash; ${esc(s.name)}</strong>` +
      `<ul class="def">${s.definition.map((d) => `<li>${esc(d)}</li>`).join("")}</ul>` +
      (s.radio && s.radio.length ? `<span class="r">On the radio: ${s.radio.map(esc).join(" &middot; ")}</span>` : "") +
      `<span class="r"><strong>Scope limit:</strong> Warriors (KGMZ 95.7) and Sharks broadcasts are not included in Sections 1&ndash;3; a displayed free window is not an all-sports-radio guarantee.</span>`;
  }

  function renderMlbNote(dateStr) {
    const note = $("mlbNote");
    const extras = (liveMlb && liveMlb.dateStr === dateStr) ? liveMlb.games : [];
    const frame = DATA.mlb_frames && Object.keys(DATA.mlb_frames)
      .map((k) => DATA.mlb_frames[k])
      .filter((f) => f.start <= dateStr && dateStr <= f.end)
      .sort((a, b) => (a.start < b.start ? -1 : 1))[0];
    if (extras.length) {
      note.className = "note info";
      note.innerHTML = `Showing <strong>${extras.length} MLB games fetched live</strong> from statsapi.mlb.com for ${esc(dateStr)}. ` +
        "This is the authoritative source; it supersedes the bundled snapshot for this date.";
    } else if (mlbFeedState.mode === "offline") {
      note.className = "note warn";
      note.innerHTML = `<strong>Live MLB fetch failed</strong> (${esc(mlbFeedState.message)}). Showing the bundled verified snapshot instead. ` +
        (frame ? `Because ${esc(frame.label)} is in progress and no per-game times are bundled for this date, the day is blocked conservatively from ${esc(TBD_ENVELOPE.MLB[0])} to ${esc(TBD_ENVELOPE.MLB[1])} PT rather than being called free.` : "");
    } else if (mlbFeedState.mode === "empty") {
      note.className = "note info";
      note.innerHTML = `No MLB games on <strong>${esc(dateStr)}</strong> per the live statsapi.mlb.com feed.`;
    } else {
      note.className = "note hidden";
      note.innerHTML = "";
    }
  }

  function pctOf(ts, dayStart, dayEnd) {
    return ((ts - dayStart) / (dayEnd - dayStart)) * 100;
  }

  function renderTimeline(rep) {
    const el = $("timeline");
    el.innerHTML = "";
    rep.busy.forEach((iv) => {
      const d = document.createElement("div");
      d.className = "blk" + (iv.priority === "high" ? " high" : "") + (iv.provisional ? " provisional" : "");
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
        `<div class="d">${fmtDuration(mins)} free</div>`;
      box.appendChild(div);
    });
  }

  function gameRow(x) {
    const g = x.g, iv = x.iv;
    const timeTxt = iv.timeConfirmed ? esc(fmtTime(iv.start)) : "TBD";
    const tzTxt = iv.timeConfirmed ? esc(fmtTZ(iv.start)) : "no time set";
    const endTxt = iv.timeConfirmed ? esc(fmtTime(iv.end)) : "";
    const srcLink = g.source ? `<a href="${esc(g.source)}" target="_blank" rel="noopener">verify</a>` : "";
    return `<div class="game${g.priority === "high" ? " high" : ""}${iv.timeConfirmed ? "" : " tbdgame"}">` +
      `<div class="time">${timeTxt}<span class="tz">${tzTxt}</span></div>` +
      `<div class="who"><span class="onair">&#9679; on air</span> ${esc(g.label)}` +
        `<span class="det">${esc(g.detail || "")}${endTxt ? " &middot; ends ~" + endTxt : ""}</span>` +
        (g.network ? `<span class="net">${esc(g.network)}</span>` : "") +
        (g.status ? `<span class="r">${esc(g.status)}</span>` : "") +
      `</div>` +
      `<div class="meta">` +
        (g.priority === "high" ? '<span class="pill high">High priority</span> ' : "") +
        (!iv.timeConfirmed ? '<span class="pill tbd">Time TBD</span> ' : "") +
        (iv.provisional ? '<span class="pill tbd">season frame</span> ' : "") +
        srcLink +
      `</div></div>`;
  }

  function nflScheduleRowsForDate(dateStr) {
    const payload = DATA.nfl_schedule_2026 || {};
    return (payload.games || []).filter((g) =>
      g.date_local === dateStr || (!g.date_local && (g.date_window || []).indexOf(dateStr) !== -1)
    );
  }

  function nflScheduleTime(g, dateForTbd) {
    if (!g.date_local || !g.kickoff_et) return "TBD";
    const ts = zoneWallToUtc(g.date_local, g.kickoff_et, "America/New_York");
    return fmtTime(ts) + " PT";
  }

  function nflScheduleDate(g) {
    if (g.date_local) return g.date_local;
    const window = g.date_window || [];
    return `TBD (official Week ${g.week} window: ${window.join(" – ")})`;
  }

  function nflIsHigh(g) {
    return g.away === "San Francisco 49ers" || g.home === "San Francisco 49ers";
  }

  function renderNflReference(dateStr) {
    const box = $("nflReference");
    if (!box) return;
    const rows = nflScheduleRowsForDate(dateStr);
    if (!rows.length) {
      box.innerHTML = "";
      return;
    }
    const week = rows[0].week;
    const hasTbd = rows.some((g) => !g.date_local);
    box.innerHTML =
      `<h3 class="sect">NFL 2026 full-slate reference &mdash; Week ${week}</h3>` +
      `<div class="note info"><strong>${rows.length} official league game${rows.length === 1 ? "" : "s"} shown.</strong> ` +
      (hasTbd
        ? `Some Week ${week} flexible assignments are official matchups, but their date/time is not published.`
        : "Kickoffs are converted from the official Eastern-time schedule to Pacific Time.") +
      " This reference does not add every NFL game to the Bay Area radio busy interval; the radio selection is listed above when published." +
      ` <a href="${esc((DATA.nfl_schedule_2026 || {}).source || "")}" target="_blank" rel="noopener">Verify the official release</a></div>` +
      `<div class="nflrefgrid">` + rows.map((g) =>
        `<div class="nflrefrow${nflIsHigh(g) ? " high" : ""}">` +
          `<div class="nflreftime">${esc(nflScheduleTime(g, dateStr))}<span>${esc(nflScheduleDate(g))}</span></div>` +
          `<div><strong>${esc(g.label)}</strong><span class="det">${!g.date_local ? "official matchup; date/time TBD" : "official regular-season game"}</span></div>` +
          `<div class="meta">${nflIsHigh(g) ? '<span class="pill high">49ers</span>' : ""}</div>` +
        `</div>`
      ).join("") + `</div>`;
  }

  function renderNflSlate() {
    const payload = DATA.nfl_schedule_2026 || {};
    const games = payload.games || [];
    const meta = $("nflSlateMeta");
    const box = $("nflSlate");
    if (!meta || !box) return;
    meta.innerHTML = `${games.length} of ${esc(payload.expected_games || 272)} games in the verified matchup snapshot. ` +
      `Flexible Week 16/17 assignments and Week 18 date/time fields are intentionally unresolved. ` +
      `<a href="${esc(payload.source || "")}" target="_blank" rel="noopener">Official source</a>`;
    const byWeek = {};
    games.forEach((g) => { (byWeek[g.week] = byWeek[g.week] || []).push(g); });
    box.innerHTML = Object.keys(byWeek).sort((a, b) => Number(a) - Number(b)).map((week) =>
      `<details class="nflweek"${week === "1" ? " open" : ""}><summary>Week ${week} <span>${byWeek[week].length} games</span></summary>` +
      `<table><thead><tr><th>Date</th><th>Kickoff PT</th><th>Matchup</th><th>Status</th></tr></thead><tbody>` +
      byWeek[week].map((g) => `<tr${nflIsHigh(g) ? ' class="nflhigh"' : ""}>` +
        `<td>${esc(nflScheduleDate(g))}</td>` +
        `<td>${esc(nflScheduleTime(g))}</td>` +
        `<td>${esc(g.label)}${nflIsHigh(g) ? ' <span class="pill high">49ers</span>' : ""}</td>` +
        `<td>${g.date_local ? "Official date/time" : "Official matchup; date/time TBD"}</td>` +
      `</tr>`).join("") + `</tbody></table></details>`
    ).join("");
  }

  function renderScoreboard(rep, games) {
    const box = $("scoreboard");
    box.innerHTML = "";
    const inScope = games
      .map((g) => ({ g: g, iv: gameToInterval(g) }))
      .filter((x) => x.iv && x.iv.start < rep.dayEnd && x.iv.end > rep.dayStart && gameInScope(x.g, scope))
      .sort((a, b) => a.iv.start - b.iv.start);

    if (!inScope.length) {
      box.innerHTML = `<div class="empty">No game in <strong>${esc(scopeShort(scope))}</strong> on this date.</div>`;
    } else {
      LEAGUE_ORDER.forEach((league) => {
        const mine = inScope.filter((x) => x.g.league === league);
        if (!mine.length) return;
        const group = document.createElement("div");
        group.className = "leaguegroup";
        group.innerHTML =
          `<div class="leaguehead"><span class="dot ${league}"></span>${esc(LEAGUE_NAMES[league] || league)}` +
          `<span class="cnt">${mine.length} game${mine.length > 1 ? "s" : ""}</span></div>` +
          mine.map(gameRow).join("");
        box.appendChild(group);
      });
    }

    const out = $("outsideScope");
    if (rep.outside.length) {
      const groups = {};
      rep.outside.forEach((x) => { (groups[x.g.league] = groups[x.g.league] || []).push(x); });
      out.className = "note info";
      out.innerHTML = `<strong>Tracked, but not counted in ${esc(scopeShort(scope))}.</strong> ` +
        "These games are live on Bay Area radio and are included in a wider section, so this date is not free there:" +
        Object.keys(groups).sort().map((lg) =>
          `<div class="leaguegroup"><div class="leaguehead"><span class="dot ${lg}"></span>${esc(LEAGUE_NAMES[lg] || lg)}` +
          `<span class="cnt">${groups[lg].length}</span></div>` + groups[lg].map(gameRow).join("") + "</div>"
        ).join("");
    } else {
      out.className = "note hidden";
      out.innerHTML = "";
    }
  }

  function renderDay(dateStr) {
    currentDate = dateStr;
    $("dateInput").value = dateStr;

    const extras = (liveMlb && liveMlb.dateStr === dateStr) ? liveMlb.games : [];
    const rep = dayReport(dateStr, extras, scope, extras.length ? false : undefined);
    const games = DATA.games.concat(extras);

    $("dayHeading").textContent = fmtLongDate(dateStr) +
      (rep.dayMinutes !== 1440 ? `  (${Math.round(rep.dayMinutes / 60)}h day, DST)` : "");

    const v = $("verdict");
    v.className = "verdict " + (rep.isFreeDay ? "free" : "busy");
    if (rep.isFreeDay) {
      v.innerHTML = "FULLY FREE for " + esc(scopeShort(scope)) +
        `<span class="sub">No scheduled game in this section &mdash; all ${Math.round(rep.dayMinutes / 60)} hours are open.</span>`;
    } else {
      const parts = [];
      parts.push(`Free time: <strong>${Math.round(rep.freeMinutes / 60 * 10) / 10}h</strong> of ${Math.round(rep.dayMinutes / 60 * 10) / 10}h`);
      if (rep.hasHighPriority) parts.push("includes a <strong>high-priority</strong> Bay Area team");
      if (rep.hasUnconfirmed) parts.push("<strong>some start times are not yet announced</strong> &mdash; the shaded block is a conservative envelope, not a confirmed window");
      if (rep.mlbFrameFallback) parts.push("MLB is in season but its per-game times are not in the offline snapshot, so the MLB window is blocked conservatively");
      parts.push("section: <strong>" + esc(scopeShort(scope)) + "</strong>");
      v.innerHTML = "BUSY &mdash; games are scheduled" + `<span class="sub">${parts.join(" &middot; ")}</span>`;
    }

    $("freeSummary").textContent = `${Math.round(rep.freeMinutes / 60 * 10) / 10}h free / ${Math.round(rep.dayMinutes / 60 * 10) / 10}h`;
    renderTimeline(rep);
    renderFree(rep);
    renderScoreboard(rep, games);
    renderNflReference(dateStr);
    renderMlbNote(dateStr);
  }

  // ---------------------------------------------------------------------
  // Vacation tab
  // ---------------------------------------------------------------------

  function interp() {
    const el = document.querySelector('input[name="interp"]:checked');
    return el ? el.value : "strict";
  }

  function rq(ok) { return ok ? '<span class="yes">yes</span>' : '<span class="no">no</span>'; }

  function renderVacation() {
    const which = interp();
    const rows = DATA.vacation.filter((r) => r.interpretation === which && r.section === scope);
    const body = $("vacationBody");
    body.innerHTML = "";

    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="7">No analysis rows for section ${esc(scope)}.</td></tr>`;
      return;
    }

    rows.forEach((r) => {
      const mlb = (DATA.seasons && DATA.seasons.mlb && DATA.seasons.mlb[String(r.year)]) || {};
      const mlbVerified = mlb.status === "VERIFIED";
      const fullVerified = r.year === 2026;
      const tr = document.createElement("tr");
      const b = r.best_3_weeks || r.best_2_weeks || r.best_1_week || r.best;
      tr.innerHTML =
        `<td class="num"><strong>${r.year}</strong></td>` +
        `<td class="num">${b ? b.days + " d" : "none"}</td>` +
        `<td class="num">${b ? esc(b.start) + " &rarr; " + esc(b.end) : "&mdash;"}</td>` +
        `<td class="num">${rq(r.requirements.week_1)}</td>` +
        `<td class="num">${rq(r.requirements.weeks_2)}</td>` +
        `<td class="num">${rq(r.requirements.weeks_3)}</td>` +
        `<td class="num">${r.free_day_count}</td>` +
        `<td class="${fullVerified ? "statusV" : (mlbVerified ? "statusP" : "statusE")}">` +
        `${fullVerified ? "VERIFIED" : (mlbVerified ? "MLB VERIFIED, rest EST" : "ESTIMATED")}</td>`;
      body.appendChild(tr);
    });

    const detail = $("vacationDetail");
    detail.innerHTML = rows.map((r) => {
      const p = r.provenance;
      const pb = p.nfl_previous_season_end.pro_bowl_games;
      const reqs = r.requirements;
      return `<div class="reviewgroup"><h3>${r.year} &mdash; ${esc(r.section_name)}</h3>` +
        `<div class="reviewitem"><strong>1 week (7 d): ${reqs.week_1 ? "yes" : "no"} &middot; 2 weeks (14 d): ${reqs.weeks_2 ? "yes" : "no"} &middot; 3 weeks (21 d): ${reqs.weeks_3 ? "yes" : "no"}</strong>` +
        `<span class="r">Longest run: ${r.best ? r.best.days + " days (" + esc(r.best.start) + " &rarr; " + esc(r.best.end) + ")" : "none"}` +
        `${r.best_3_weeks ? " &middot; best 3-week: " + esc(r.best_3_weeks.start) + " &rarr; " + esc(r.best_3_weeks.end) : ""}` +
        `${!r.best_3_weeks && r.best_2_weeks ? " &middot; best 2-week: " + esc(r.best_2_weeks.start) + " &rarr; " + esc(r.best_2_weeks.end) : ""}` +
        `${!r.best_2_weeks && r.best_1_week ? " &middot; best 1-week: " + esc(r.best_1_week.start) + " &rarr; " + esc(r.best_1_week.end) : ""}</span></div>` +
        `<div class="reviewitem">Previous NFL season: Super Bowl on <strong>${esc(p.nfl_previous_season_end.super_bowl)}</strong> &mdash; ${esc(p.nfl_previous_season_end.status)}: ${esc(p.nfl_previous_season_end.note)}` +
        `<span class="r">Playoff dates blocked this year: ${esc((p.nfl_previous_season_end.playoff_dates_in_year || []).join(", "))}</span></div>` +
        `<div class="reviewitem">Pro Bowl Games (NFL all-star): <strong>${esc(pb.date)}</strong> &mdash; ${esc(pb.status)}: ${esc(pb.note)}</div>` +
        (p.mlb_block ? `<div class="reviewitem">MLB blocks <strong>${esc(p.mlb_block.start)} &rarr; ${esc(p.mlb_block.end)}</strong> &mdash; ${esc(p.mlb_block.status)}${p.mlb_block.includes_spring_training ? " (includes Spring Training)" : " (Spring Training excluded)"}` +
          `<span class="r">Source: statsapi.mlb.com/api/v1/seasons</span></div>` : "") +
        `<div class="reviewitem">Current NFL season opens <strong>${esc(p.nfl_current_season_start.date)}</strong> &mdash; ${esc(p.nfl_current_season_start.status)}: ${esc(p.nfl_current_season_start.note)}</div>` +
        (p.ncaaf_blocks || []).map((s) => `<div class="reviewitem">College football: <strong>${esc(s.start)} &rarr; ${esc(s.end)}</strong> (${esc(s.label)}) &mdash; ${esc(s.status)}${s.conditional ? " &middot; conditional" : ""}<span class="r">${esc(s.source)}</span></div>`).join("") +
        (p.mls_blocks || []).map((s) => `<div class="reviewitem">MLS: <strong>${esc(s.start)} &rarr; ${esc(s.end)}</strong> (${esc(s.label)}) &mdash; ${esc(s.status)}${s.conditional ? " &middot; conditional" : ""}<span class="r">${esc(s.source)}</span></div>`).join("") +
        `<div class="reviewitem">All clean runs found: ${r.gaps.slice(0, 12).map((g) => `${esc(g.start)} &rarr; ${esc(g.end)} (${g.days}d)`).join("; ")}${r.gaps.length > 12 ? " &hellip; " + (r.gaps.length - 12) + " more" : ""}</div>` +
        `</div>`;
    }).join("");
    renderAllGaps();
  }

  // ---------------------------------------------------------------------
  // Compare tab
  // ---------------------------------------------------------------------

  function renderCompare() {
    const which = interp();
    const cmp = (DATA.vacation_compare && DATA.vacation_compare[which]) || {};
    const ids = SCOPES.map((s) => s.id);
    let html = "<thead><tr><th>Year</th>" + ids.map((id) => `<th>${esc(scopeShort(id))}</th>`).join("") + "</tr></thead><tbody>";
    Object.keys(cmp).sort().forEach((year) => {
      html += `<tr><td class="num"><strong>${esc(year)}</strong></td>`;
      ids.forEach((id) => {
        const row = cmp[year][id];
        if (!row) { html += "<td>&mdash;</td>"; return; }
        const labels = [];
        if (row.requirements.weeks_3) labels.push('<span class="pill ok">3 weeks</span>');
        else if (row.requirements.weeks_2) labels.push('<span class="pill ok">2 weeks</span>');
        else if (row.requirements.week_1) labels.push('<span class="pill warn">1 week</span>');
        else labels.push('<span class="pill bad">none</span>');
   if (row.requirements.weeks_2) labels.push('<span class="pill ok">2 weeks</span>');
        else if (row.requirements.week_1) labels.push('<span class="pill warn">1 week</span>');
        else labels.push('<span class="pill bad">none</span>');
        html += `<td class="cmpcell${id === scope ? " current" : ""}">` +
          `<div class="big">${row.longest_days} d</div>` +
          `<div class="small">${row.longest_start ? esc(row.longest_start) + " &rarr; " + esc(row.longest_end) : "&mdash;"}</div>` +
          `<div>${labels.join("")}</div>` +
          `<div class="small">${row.free_days} free days in the year</div></td>`;
      });
      html += "</tr>";
    });
    html += "</tbody>";
    ["compareTable", "compareTable2"].forEach((id) => {
      const t = $(id);
      if (t) t.innerHTML = html;
    });

    const summary = $("compareSummary");
    if (summary) summary.innerHTML = (DATA.vacation_compare_notes || []).map((n) => `<li>${esc(n.text || n)}</li>`).join("");
  }

  // ---------------------------------------------------------------------
  // Decision engine (1-2-3 Decide tab + line-by-line tables)
  //
  // Every number here is read from the generated bundle (DATA.vacation),
  // which is produced by scripts/analyze_vacation.py. Nothing is estimated
  // in the browser: friendly dates are derived from the ISO dates, and the
  // status of each year mirrors renderVacation exactly.
  // ---------------------------------------------------------------------

  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function fmtDateISO(iso) {
    const p = String(iso).split("-");
    return MONTHS[parseInt(p[1], 10) - 1] + " " + parseInt(p[2], 10) + ", " + p[0];
  }

  function fmtRangeFriendly(start, end) {
    const a = String(start).split("-"), b = String(end).split("-");
    if (a[0] === b[0] && a[1] === b[1]) return MONTHS[+a[1] - 1] + " " + (+a[2]) + " \u2013 " + (+b[2]) + ", " + a[0];
    if (a[0] === b[0]) return MONTHS[+a[1] - 1] + " " + (+a[2]) + " \u2013 " + MONTHS[+b[1] - 1] + " " + (+b[2]) + ", " + a[0];
    return fmtDateISO(start) + " \u2013 " + fmtDateISO(end);
  }

  function statusForYear(year) {
    const mlb = (DATA.seasons && DATA.seasons.mlb && DATA.seasons.mlb[String(year)]) || {};
    if (year === 2026) return { label: "VERIFIED", cls: "statusV" };
    if (mlb.status === "VERIFIED") return { label: "MLB VERIFIED, rest EST", cls: "statusP" };
    return { label: "ESTIMATED", cls: "statusE" };
  }

  function vacationRows() {
    const which = interp();
    return DATA.vacation
      .filter((r) => r.interpretation === which && r.section === scope)
      .sort((a, b) => a.year - b.year);
  }

  function bestMeeting(row, minDays) {
    const gaps = row.gaps || [];
    for (let i = 0; i < gaps.length; i++) {
      if (gaps[i].days >= minDays) return gaps[i];
    }
    return null;
  }

  function setScope(s) {
    scope = s;
    renderScopePicker();
    renderScopeNote();
    renderDay(currentDate);
    renderVacation();
    renderCompare();
    renderDecScopeCards();
    renderDecision();
  }

  function setInterp(v) {
    document.querySelectorAll('input[name="interp"]').forEach((r) => { r.checked = (r.value === v); });
    const dec = document.querySelectorAll('input[name="interpDecide"]');
    if (dec.length) dec.forEach((r) => { r.checked = (r.value === v); });
    renderVacation();
    renderCompare();
    renderDecScopeCards();
    renderDecision();
  }

  function renderDecScopeCards() {
    const box = $("decScopeCards");
    if (!box) return;
    const which = interp();
    box.innerHTML = "";
    SECTIONS.forEach((s) => {
      const cmp = (DATA.vacation_compare && DATA.vacation_compare[which]) || {};
      let best = 0, bestYear = null, bestStart = null, bestEnd = null;
      Object.keys(cmp).sort().forEach((y) => {
        const r = cmp[y][s.id];
        if (r && r.longest_days > best) { best = r.longest_days; bestYear = y; bestStart = r.longest_start; bestEnd = r.longest_end; }
      });
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "sitecard" + (s.id === scope ? " active" : "");
      let html = '<span class="sitename">' + esc(s.short) + "</span>" +
        "<ul>" + s.definition.map((d) => "<li>" + esc(d) + "</li>").join("") + "</ul>";
      if (best) {
        html += '<div class="preview">Longest run (' + (which === "strict" ? "strict" : "regular only") + '): <strong>' + best + " days</strong> &mdash; " + esc(fmtRangeFriendly(bestStart, bestEnd)) + " (" + esc(bestYear) + ")</div>";
      }
      btn.innerHTML = html;
      btn.setAttribute("aria-pressed", s.id === scope ? "true" : "false");
      const id = s.id;
      btn.addEventListener("click", () => setScope(id));
      box.appendChild(btn);
    });
  }

  function renderDecision() {
    const summary = $("decisionSummary"), body = $("decisionBody"),
      opts = $("decisionOptionsBody"), why = $("decisionWhy");
    if (!summary || !body || !opts) return;
    const rows = vacationRows();
    const reading = interp() === "strict"
      ? "Strict (Spring Training counts)"
      : "Regular season only (Spring Training ignored)";

    const ok = rows.filter((r) => !!bestMeeting(r, tripLength));
    let overall = null;
    rows.forEach((r) => {
      (r.gaps || []).forEach((g) => {
        if (!overall || g.days > overall.days) overall = { days: g.days, start: g.start, end: g.end, year: r.year };
      });
    });

    if (ok.length) {
      summary.className = "verdict free";
      summary.innerHTML = "YES &mdash; a " + tripLength + "-day trip fits in " + ok.length + " of " + rows.length + " years" +
        `<span class="sub">${esc(scopeShort(scope))} &middot; ${esc(reading)}` +
        ` &middot; years that work: <strong>${ok.map((r) => r.year).join(", ")}</strong>` +
        (overall ? ` &middot; longest exact window overall: <strong>${overall.days} days</strong> (${esc(fmtRangeFriendly(overall.start, overall.end))})` : "") + "</span>";
    } else {
      summary.className = "verdict busy";
      summary.innerHTML = "NO &mdash; no unbroken " + tripLength + "-day window in any year under these answers" +
        `<span class="sub">${esc(scopeShort(scope))} &middot; ${esc(reading)}` +
        (overall ? ` &middot; the longest exact run anywhere is <strong>${overall.days} days</strong> (${esc(fmtRangeFriendly(overall.start, overall.end))}, ${overall.year})` : "") +
        " &middot; try a shorter trip, the other Spring Training rule, or a narrower situation</span>";
    }

    body.innerHTML = "";
    rows.forEach((r) => {
      const st = statusForYear(r.year);
      const fit = bestMeeting(r, tripLength);
      const show = fit || r.best;
      const tr = document.createElement("tr");
      const verdictCell = fit ? '<span class="pill ok">Yes</span>' : '<span class="pill bad">No</span>';
      const datesCell = show
        ? esc(fmtRangeFriendly(show.start, show.end)) + `<div class="small">${esc(show.start)} &rarr; ${esc(show.end)}</div>` +
          (fit ? "" : '<div class="small">longest available &mdash; too short for this trip</div>')
        : "&mdash;";
      tr.innerHTML =
        `<td class="num"><strong>${r.year}</strong></td>` +
        `<td>${verdictCell}</td>` +
        `<td>${datesCell}</td>` +
        `<td class="num">${show ? show.days + " d" : "&mdash;"}</td>` +
        `<td class="num">${r.free_day_count}</td>` +
        `<td class="${st.cls}">${st.label}</td>`;
      body.appendChild(tr);
    });

    const lines = [];
    rows.forEach((r) => {
      (r.gaps || []).forEach((g) => {
        if (g.days >= tripLength) lines.push({ year: r.year, g: g });
      });
    });
    lines.sort((a, b) => a.year - b.year || b.g.days - a.g.days);
    opts.innerHTML = "";
    if (!lines.length) {
      const tr0 = document.createElement("tr");
      tr0.innerHTML = `<td colspan="8" class="empty">No unbroken run of ${tripLength} days exists in 2026&ndash;2029 under these answers. Every gap is shorter &mdash; see the &ldquo;Every clean run, line by line&rdquo; table on the Vacation Windows tab for the full list.</td>`;
      opts.appendChild(tr0);
    } else {
      lines.forEach((ln) => {
        const st = statusForYear(ln.year);
        const tr = document.createElement("tr");
        tr.innerHTML =
          `<td class="num"><strong>${ln.year}</strong></td>` +
          `<td>${esc(fmtDateISO(ln.g.start))}<div class="small">${esc(ln.g.start)}</div></td>` +
          `<td>${esc(fmtDateISO(ln.g.end))}<div class="small">${esc(ln.g.end)}</div></td>` +
          `<td class="num">${ln.g.days} d</td>` +
          `<td>${rq(ln.g.days >= 7)}</td>` +
          `<td>${rq(ln.g.days >= 14)}</td>` +
          `<td>${rq(ln.g.days >= 21)}</td>` +
          `<td class="${st.cls}">${st.label}</td>`;
        opts.appendChild(tr);
      });
    }

    if (why) {
      why.innerHTML = rows.map((r) => {
        const st = statusForYear(r.year);
        const p = r.provenance || {};
        const prev = p.nfl_previous_season_end || {};
        const pb = prev.pro_bowl_games || {};
        const mlb = p.mlb_block || {};
        const cur = p.nfl_current_season_start || {};
        let out = `<div class="whyyear"><h4>${r.year} &mdash; <span class="${st.cls}">${st.label}</span></h4>`;
        out += "<table><tbody>";
        const line = (k, v) => { out += `<tr><td>${esc(k)}</td><td>${v}</td></tr>`; };
        if (prev.super_bowl) line("Super Bowl", `<strong>${esc(prev.super_bowl)}</strong> &mdash; ${esc(prev.status || "")}: ${esc(prev.note || "")}`);
        if ((prev.playoff_dates_in_year || []).length) line("Playoff dates blocked", esc(prev.playoff_dates_in_year.join(", ")));
        if (pb.date) line("Pro Bowl Games", `<strong>${esc(pb.date)}</strong> &mdash; ${esc(pb.status || "")}: ${esc(pb.note || "")}`);
        if (mlb.start) line("MLB blocks", `<strong>${esc(mlb.start)} &rarr; ${esc(mlb.end)}</strong> &mdash; ${esc(mlb.status || "")}${mlb.includes_spring_training ? " (includes Spring Training)" : " (Spring Training excluded)"}`);
        if (cur.date) line("NFL season starts", `<strong>${esc(cur.date)}</strong> &mdash; ${esc(cur.status || "")}: ${esc(cur.note || "")}`);
        (p.ncaaf_blocks || []).forEach((s) => {
          line("College football", `<strong>${esc(s.start)} &rarr; ${esc(s.end)}</strong> (${esc(s.label || "")}) &mdash; ${esc(s.status || "")}${s.conditional ? " &middot; conditional" : ""}`);
        });
        (p.mls_blocks || []).forEach((s) => {
          line("MLS", `<strong>${esc(s.start)} &rarr; ${esc(s.end)}</strong> (${esc(s.label || "")}) &mdash; ${esc(s.status || "")}${s.conditional ? " &middot; conditional" : ""}`);
        });
        line("Result", r.free_day_count + " free days; longest run " + (r.best ? `<strong>${r.best.days} days</strong> (${esc(r.best.start)} &rarr; ${esc(r.best.end)})` : "none"));
        out += "</tbody></table></div>";
        return out;
      }).join("");
    }
  }

  function renderAllGaps() {
    const body = $("allGapsBody");
    if (!body) return;
    body.innerHTML = "";
    vacationRows().forEach((r) => {
      const st = statusForYear(r.year);
      (r.gaps || []).forEach((g) => {
        const tr = document.createElement("tr");
        tr.innerHTML =
          `<td class="num"><strong>${r.year}</strong></td>` +
          `<td>${esc(fmtDateISO(g.start))}<div class="small">${esc(g.start)}</div></td>` +
          `<td>${esc(fmtDateISO(g.end))}<div class="small">${esc(g.end)}</div></td>` +
          `<td class="num">${g.days} d</td>` +
          `<td>${rq(g.days >= 7)}</td>` +
          `<td>${rq(g.days >= 14)}</td>` +
          `<td>${rq(g.days >= 21)}</td>` +
          `<td class="${st.cls}">${st.label}</td>`;
        body.appendChild(tr);
      });
    });
  }

  // ---------------------------------------------------------------------
  // Review + sources + radio tabs
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

  function renderRadio() {
    const box = $("radioList");
    if (!box) return;
    const radio = DATA.radio || { stations: [] };
    box.innerHTML = (radio.stations || []).map((s) => {
      const rec = s.reception_94122 || "";
      const cls = /STRONG/.test(rec) ? "ok" : (/MEDIUM/.test(rec) ? "warn" : "bad");
      return `<div class="srccard station">` +
        `<h4>${esc(s.call_letters)} &mdash; ${esc(s.dial)}</h4>` +
        `<div class="small">${esc(s.city_of_license)} &middot; ${esc(s.operator || "")}</div>` +
        `<div class="pill ${cls}">94122 reception: ${esc(rec)}</div>` +
        `<span class="r">${esc(s.reception_basis || "")}</span>` +
        `<ul class="def">${(s.carries || []).map((c) => `<li>${esc(c)}</li>`).join("")}</ul>` +
        `<span class="r">${(s.sources || []).map((u) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(u)}</a>`).join("<br>")}</span>` +
        `</div>`;
    }).join("") +
      (radio.westwood_one_affiliates_in_market
        ? `<div class="srccard station"><h4>Westwood One Sports &mdash; San Francisco market affiliates</h4>` +
          `<ul class="def">${radio.westwood_one_affiliates_in_market.stations.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>` +
          `<span class="r">${esc(radio.westwood_one_affiliates_in_market.note)}</span>` +
          `<span class="r"><a href="${esc(radio.westwood_one_affiliates_in_market.source)}" target="_blank" rel="noopener">${esc(radio.westwood_one_affiliates_in_market.source)}</a></span></div>`
        : "") +
      ((radio.affiliates_outside_sections || []).map((a) =>
        `<div class="srccard station"><h4>${esc(a.call_letters)} &mdash; ${esc(a.dial)}</h4>` +
        `<ul class="def">${(a.carries || []).map((c) => `<li>${esc(c)}</li>`).join("")}</ul>` +
        `<span class="r">${esc(a.note || "")}</span></div>`).join(""));
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
      { label: "MLB Stats API &mdash; 2026 postseason dates (verified per date; times are the 07:33Z sentinel)", url: "https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=2026-09-28&endDate=2026-10-31&gameType=E,S,D,L,F,W" },
      { label: "MLB.com &mdash; current playoff picture and clinch status", url: "https://www.mlb.com/news/mlb-playoff-picture-and-bracket-2026" },
      { label: "MLB.com &mdash; 2027 schedule released 2026-07-16", url: "https://www.mlb.com/news/mlb-2027-schedule-released" },
      { label: "NFL &mdash; official 2026 schedule release (272 games)", url: "https://www.nfl.com/nfl-schedule-release/" },
      { label: "NFL &mdash; official 2026 by-week schedule PDF", url: "https://media.nfl.com/content/dam/communications/football-communications/2026/news/05%2014%2026%20-%202026%20NFL%20Schedule%20-%20By%20Week.pdf" },
      { label: "Westwood One Sports &mdash; official NFL radio schedule", url: "https://www.westwoodonesports.com/nfl-schedule/" },
      { label: "Westwood One Sports &mdash; station finder (San Francisco market affiliates)", url: "https://www.westwoodonesports.com/station-finder/" },
      { label: "NFL key dates 2026-27 (Wild Card, Divisional, Championships, Super Bowl LXI)", url: "https://www.seahawks.com/news/nfl-announces-important-dates-for-2026-2027" },
      { label: "NFL Operations &mdash; 2026 Pro Bowl Games moved to Super Bowl week", url: "https://operations.nfl.com/updates/the-game/2026-pro-bowl-games-presented-by-verizon-moved-to-tuesday-of-super-bowl-lx-week-in-bay-area/" },
      { label: "Super Bowl LXIII awarded to Las Vegas, 2029-02-11", url: "https://www.nfl.com/news/las-vegas-to-host-super-bowl-lxiii-in-2029" },
      { label: "49ers / Cumulus &mdash; KNBR flagship extension, 2026-04-15", url: "https://www.cumulusmedia.com/2026/04/15/san-francisco-49ers-announce-multi-year-partnership-extension-with-cumulus-medias-knbr/" },
      { label: "California Golden Bears &mdash; 2026 football schedule (radio: KSFO 810 AM)", url: "https://calbears.com/sports/football/schedule" },
      { label: "Stanford Cardinal &mdash; 2026 football schedule", url: "https://gostanford.com/sports/football/schedule" },
      { label: "Athletics &mdash; radio affiliates (KSTE 650 AM, KNEW 960 AM)", url: "https://www.mlb.com/athletics/schedule/watch" },
      { label: "San Jose Earthquakes &mdash; 2026 MLS schedule", url: "https://www.sjearthquakes.com/news/news-earthquakes-announce-2026-major-league-soccer-schedule" },
      { label: "Cumulus Media surrenders 560 AM; KSFO is now 810 AM (50 kW)", url: "https://www.radioworld.com/news-and-business/cumulus-media-surrenders-license-of-san-franciscos-560-am" },
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
            start_utc: g.gameDate,
            duration: DURATIONS.MLB,
            sections: ["1", "2", "3"],
            time_status: g.gameDate.slice(11, 19) === MLB_TBD_SENTINEL ? "TBD_official_date" : "official",
          });
        });
        return out;
      });
  }

  function refreshMlb(dateStr) {
    return fetchMlbFor(dateStr)
      .then((games) => {
        liveMlb = { dateStr: dateStr, games: games };
        mlbFeedState = { mode: games.length ? "live" : "empty", message: "" };
        renderMlbNote(currentDate);
        renderDay(currentDate);
      })
      .catch((err) => {
        mlbFeedState = { mode: "offline", message: String(err && err.message ? err.message : err) };
        renderMlbNote(currentDate);
        renderDay(currentDate);
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
      " · " + DATA._meta.counts.games + " games, " + DATA._meta.counts.unresolved + " flagged for review";

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
    document.querySelectorAll('input[name="interp"]').forEach((r) => r.addEventListener("change", () => setInterp(r.value)));
    document.querySelectorAll('input[name="interpDecide"]').forEach((r) => r.addEventListener("change", () => setInterp(r.value)));
    document.querySelectorAll('input[name="trip"]').forEach((r) => r.addEventListener("change", () => { tripLength = parseInt(r.value, 10); renderDecision(); }));

    renderScopePicker();
    renderScopeNote();
    renderNflSlate();
    renderVacation();
    renderCompare();
    renderDecScopeCards();
    renderDecision();
    renderReview();
    renderRadio();
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
    gameInScope: gameInScope, recordIsOnDate: recordIsOnDate, ftDateOf: ptDateOf,
    DURATIONS: DURATIONS, TBD_ENVELOPE: TBD_ENVELOPE, TZ: TZ, SCOPES: SCOPES,
    getScope: function () { return scope; }, setScope: function (s) { scope = s; },
  };
})();
