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

  // Planning estimates, in minutes. Must match DEFAULT_DURATIONS in lib_windows.py.
  const DURATIONS = DATA._meta.durations_minutes;

  // Conservative envelope for a dated game with no announced start time.
  // Must match TBD_ENVELOPE_PT in lib_windows.py.
  const TBD_ENVELOPE = DATA._meta.tbd_envelope_pt;

  const LEAGUE_NAMES = { MLB: "MLB", NFL: "NFL", NCAAF: "College Football", MLS: "MLS", NBA: "NBA", WNBA: "WNBA" };
  const LEAGUE_ORDER = ["MLB", "NFL", "NCAAF", "MLS", "NBA", "WNBA"];
  const HIGH_PRIORITY_TEAMS = ["San Francisco 49ers", "San Jose Earthquakes", "Stanford", "California", "San Francisco Giants", "Athletics", "Golden State Warriors", "Golden State Valkyries"];

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
    const asUTC = Date.parse(`${m.year}-${m.month}-${m.day}T${m.hour === "24" ? "00" : m.hour}:${m.minute}:${m.second}Z`);
    return Math.round((asUTC - tsMs) / 60000);
  }

  /** UTC epoch-ms for a wall-clock time in an IANA timezone. */
  function zoneWallToUtc(dateStr, hhmm, zone) {
    if (hhmm === "24:00") { dateStr = addDaysStr(dateStr, 1); hhmm = "00:00"; }
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
      const asUTC = Date.parse(`${m.year}-${m.month}-${m.day}T${m.hour === "24" ? "00" : m.hour}:${m.minute}:${m.second}Z`);
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
    if (game.cancelled) return null;
    if (INTERVAL_CACHE.has(game)) return INTERVAL_CACHE.get(game);
    if (!game.start_utc && !game.date_local) {
      INTERVAL_CACHE.set(game, null);
      return null;
    }
    const minutes = game.duration || DURATIONS[game.league];
    let result;

    if (!game.start_utc || timeIsUnconfirmed(game)) {
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

  /**
   * Does the project know this date's MLB fixture status?
   *   "no-game"  - the official list is complete here and no game is scheduled
   *   "game"     - the official list has at least one game (time may still be TBD)
   *   "unknown"  - no complete fixture list for that season/date
   */
  function mlbFrameCoverage(dateStr, frame) {
    if (frame && (frame.anchor_dates || []).indexOf(dateStr) !== -1) return "game";
    const snapStart = frame && frame.snapshot_start;
    const snapEnd = frame && frame.snapshot_end;
    if (snapStart && snapEnd && snapStart <= dateStr && dateStr <= snapEnd) {
      return (frame.dates_with_games || []).indexOf(dateStr) === -1 ? "no-game" : "game";
    }
    const ranges = (frame && frame.complete_ranges) || [];
    for (let i = 0; i < ranges.length; i++) {
      if (ranges[i][0] <= dateStr && dateStr <= ranges[i][1]) return "no-game";
    }
    return "unknown";
  }

  function mlbFrameIsCovered(dateStr, frame) {
    return mlbFrameCoverage(dateStr, frame) === "no-game";
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
    const games = combinedGames(extraGames);
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
  let currentDate = ptDateOf(Date.now());
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

  function sourceLink(source, label) {
    if (!source) return "";
    if (!/^https?:\/\/[^\s<>]+$/.test(source)) return `<span class="small">${esc(source)}</span>`;
    return `<a href="${esc(source)}" target="_blank" rel="noopener">${esc(label || source)}</a>`;
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
    if (extras.length && mlbFeedState.mode === "snapshot") {
      note.className = "note warn";
      note.innerHTML = `<strong>Live MLB fetch unavailable</strong> (${esc(mlbFeedState.message)}). Showing ` +
        `<strong>${extras.length} MLB game${extras.length === 1 ? "" : "s"} from the committed official season snapshot</strong> ` +
        `(data/verified/mlb_schedule_${esc(dateStr.slice(0, 4))}.csv, league Stats API) for ${esc(dateStr)}. ` +
        "The fixture list is official; only the live score/status refresh is missing.";
    } else if (extras.length) {
      note.className = "note info";
      note.innerHTML = `Showing <strong>${extras.length} MLB games fetched live</strong> from statsapi.mlb.com across neighboring official dates around ${esc(dateStr)}. ` +
        "This is the authoritative source; it supersedes the bundled snapshot for this date.";
    } else if (mlbFeedState.mode === "offline") {
      note.className = "note warn";
      note.innerHTML = `<strong>Live MLB fetch failed</strong> (${esc(mlbFeedState.message)}). Showing the available bundled snapshot instead. ` +
        (frame ? `Within ${esc(frame.label)}, missing fixture coverage reserves the full date. Known bundled dates are used where available.` : "");
    } else if (mlbFeedState.mode === "empty") {
      note.className = "note info";
      note.innerHTML = `No MLB records returned around <strong>${esc(dateStr)}</strong>. An empty future feed is not evidence that no games will be scheduled; conservative holds remain.`;
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
      box.innerHTML = '<div class="empty">No free window identified. Scheduled games or full-date uncertainty holds cover this date.</div>';
      return;
    }
    rep.freeWindows.forEach((w) => {
      const mins = Math.round((w.end - w.start) / 60000);
      const div = document.createElement("div");
      div.className = "freewin" + (rep.longest && w === rep.longest ? " best" : "");
      div.innerHTML =
        `<div class="t">${esc(fmtTime(w.start))} &ndash; ${esc(fmtTime(w.end))}</div>` +
        `<div class="d">${fmtDuration(mins)} estimated free</div>`;
      box.appendChild(div);
    });
  }

  function gameRow(x) {
    const g = x.g, iv = x.iv;
    const timeTxt = iv.timeConfirmed ? esc(fmtTime(iv.start)) : "TBD";
    const tzTxt = iv.timeConfirmed ? esc(fmtTZ(iv.start)) : "no time set";
    const endTxt = iv.timeConfirmed ? esc(fmtTime(iv.end)) : "";
    const srcLink = sourceLink(g.source, "Source");
    return `<div class="game${g.priority === "high" ? " high" : ""}${iv.timeConfirmed ? "" : " tbdgame"}">` +
      `<div class="time">${timeTxt}<span class="tz">${tzTxt}</span></div>` +
      `<div class="who"><span class="onair">${iv.timeConfirmed ? "Scheduled" : "Time unresolved"}</span> ${esc(g.label)}` +
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
      box.innerHTML = `<div class="empty">No bundled game in <strong>${esc(scopeShort(scope))}</strong> on this date.</div>`;
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
        "These tracked events are included in a wider section. Local carriage may still be unconfirmed:" +
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
    const rep = dayReport(dateStr, extras, scope);
    const games = combinedGames(extras);

    $("dayHeading").textContent = fmtLongDate(dateStr) +
      (rep.dayMinutes !== 1440 ? `  (${Math.round(rep.dayMinutes / 60)}h day, DST)` : "");

    const v = $("verdict");
    v.className = "verdict " + (rep.isFreeDay ? "free" : "busy");
    if (rep.isFreeDay) {
      v.innerHTML = "NO KNOWN CONFLICT for " + esc(scopeShort(scope)) +
        `<span class="sub">No bundled conflict in this section. Incomplete or unreleased schedules can still change this result; this is not confirmed free time.</span>`;
    } else {
      const parts = [];
      parts.push(`Free time: <strong>${Math.round(rep.freeMinutes / 60 * 10) / 10}h</strong> of ${Math.round(rep.dayMinutes / 60 * 10) / 10}h`);
      if (rep.hasHighPriority) parts.push("includes a <strong>high-priority</strong> team or national broadcast");
      if (rep.hasUnconfirmed) parts.push("<strong>some start times are not yet announced</strong> &mdash; the shaded block is a conservative envelope, not a confirmed window");
      if (rep.mlbFrameFallback) parts.push("MLB is in season but its per-game times are not in the offline snapshot, so the MLB window is blocked conservatively");
      parts.push("section: <strong>" + esc(scopeShort(scope)) + "</strong>");
      v.innerHTML = "BUSY / RESERVED &mdash; scheduled games or unresolved coverage" + `<span class="sub">${parts.join(" &middot; ")}</span>`;
    }

    $("freeSummary").textContent = `${Math.round(rep.freeMinutes / 60 * 10) / 10}h free / ${Math.round(rep.dayMinutes / 60 * 10) / 10}h`;
    renderTimeline(rep);
    renderFree(rep);
    renderScoreboard(rep, games);
    renderNflReference(dateStr);
    renderMlbNote(dateStr);
    renderCalendar();
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
      const tr = document.createElement("tr");
      const b = r.best_3_weeks || r.best_2_weeks || r.best_1_week || r.best;
      tr.innerHTML =
        `<td class="num"><strong>${r.year}</strong></td>` +
        `<td class="num">${b ? b.days + " d" : "none"}</td>` +
        `<td class="num">${b ? esc(b.start) + " &rarr; " + esc(b.end) + historicalLabel(b.end) : "&mdash;"}</td>` +
        `<td class="num">${rq(r.requirements.week_1)}</td>` +
        `<td class="num">${rq(r.requirements.weeks_2)}</td>` +
        `<td class="num">${rq(r.requirements.weeks_3)}</td>` +
        `<td class="num">${r.free_day_count}</td>` +
        `<td class="${mlbVerified ? "statusP" : "statusE"}">` +
        `${statusForYear(r.year).label}</td>`;
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
        (p.other_radio_blocks || []).map((s) => `<div class="reviewitem">Other live radio (${esc(s.league)}): <strong>${esc(s.start)} &rarr; ${esc(s.end)}</strong> (${esc(s.label)}) &mdash; ${esc(s.status)}${s.conditional ? " &middot; conditional" : ""}<span class="r">${esc(s.source)}</span></div>`).join("") +
        `<div class="reviewitem">All clean runs found: ${r.gaps.slice(0, 12).map((g) => `${esc(g.start)} &rarr; ${esc(g.end)} (${g.days}d)`).join("; ")}${r.gaps.length > 12 ? " &hellip; " + (r.gaps.length - 12) + " more" : ""}</div>` +
          `</div>`;
    }).join("");
    renderAllGaps();
    renderStCompare();
  }

  // ---------------------------------------------------------------------
  // Spring Training comparison (strict vs regular, both shown at once)
  // ---------------------------------------------------------------------

  function stCell(r) {
    if (!r) return "&mdash;";
    return r.best
      ? `<strong>${r.best.days} d</strong> &mdash; ${esc(r.best.start)} &rarr; ${esc(r.best.end)}${historicalLabel(r.best.end)}`
      : "none found";
  }

  function renderStCompare() {
    const body = $("stCompareBody");
    if (!body) return;
    body.innerHTML = "";
    for (let year = 2026; year <= 2029; year++) {
      const strict = DATA.vacation.find((r) => r.year === year && r.section === scope && r.interpretation === "strict");
      const regular = DATA.vacation.find((r) => r.year === year && r.section === scope && r.interpretation === "regular");
      if (!strict || !regular) {
        body.innerHTML = `<tr><td colspan="4">No analysis rows for section ${esc(scope)}.</td></tr>`;
        return;
      }
      const delta = (regular.best ? regular.best.days : 0) - (strict.best ? strict.best.days : 0);
      const tr = document.createElement("tr");
      tr.innerHTML =
        `<td class="num"><strong>${year}</strong></td>` +
        `<td class="num">${stCell(strict)}</td>` +
        `<td class="num">${stCell(regular)}</td>` +
        `<td class="num">${delta > 1 ? `+${delta} free days` : delta === 1 ? "+1 free day" : "no difference"}</td>`;
      body.appendChild(tr);
    }
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
        html += `<td class="cmpcell${id === scope ? " current" : ""}">` +
          `<div class="big">${row.longest_days} d</div>` +
          `<div class="small">${row.longest_start ? esc(row.longest_start) + " &rarr; " + esc(row.longest_end) : "&mdash;"}</div>` +
          `<div>${labels.join("")}</div>` +
          `<div class="small">${row.free_days} modeled free days in the year</div></td>`;
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

  function historicalLabel(end) {
    return end < ptDateOf(Date.now()) ? '<span class="past-label">Past window · comparison only</span>' : "";
  }

  function statusForYear(year) {
    const mlb = (DATA.seasons && DATA.seasons.mlb && DATA.seasons.mlb[String(year)]) || {};
    if (year === 2026) return { label: "Official inputs · modeled gaps", cls: "statusP" };
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
      let best = 0, bestStart = null, bestEnd = null;
      Object.keys(cmp).sort().forEach((y) => {
        const r = cmp[y][s.id];
        if (r && r.longest_days > best) { best = r.longest_days; bestStart = r.longest_start; bestEnd = r.longest_end; }
      });
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "sitecard" + (s.id === scope ? " active" : "");
      let html = '<span class="sitename">' + esc(s.short) + "</span>" +
        "<ul>" + s.definition.map((d) => "<li>" + esc(d) + "</li>").join("") + "</ul>";
      if (best) {
        html += '<div class="preview">Longest run (' + (which === "strict" ? "strict" : "regular only") + '): <strong>' + best + " days</strong> &mdash; " + esc(fmtRangeFriendly(bestStart, bestEnd)) + "</div>";
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
      summary.innerHTML = "CANDIDATE &mdash; a " + tripLength + "-day trip fits in " + ok.length + " of " + rows.length + " years" +
        `<span class="sub">${esc(scopeShort(scope))} &middot; ${esc(reading)}` +
        ` &middot; years that work: <strong>${ok.map((r) => r.year).join(", ")}</strong>` +
        (overall ? ` &middot; longest modeled window overall: <strong>${overall.days} days</strong> (${esc(fmtRangeFriendly(overall.start, overall.end))})` : "") + "</span>";
    } else {
      summary.className = "verdict busy";
      summary.innerHTML = "NO CANDIDATE &mdash; no unbroken " + tripLength + "-day window in any year under these answers" +
        `<span class="sub">${esc(scopeShort(scope))} &middot; ${esc(reading)}` +
        (overall ? ` &middot; the longest modeled run is <strong>${overall.days} days</strong> (${esc(fmtRangeFriendly(overall.start, overall.end))})` : "") +
        " &middot; try a shorter trip, the other Spring Training rule, or a narrower situation</span>";
    }

    body.innerHTML = "";
    rows.forEach((r) => {
      const st = statusForYear(r.year);
      const fit = bestMeeting(r, tripLength);
      const show = fit || r.best;
      const tr = document.createElement("tr");
      const verdictCell = fit ? '<span class="pill ok">Candidate</span>' : '<span class="pill bad">None found</span>';
      const datesCell = show
        ? esc(fmtRangeFriendly(show.start, show.end)) + `<div class="small">${esc(show.start)} &rarr; ${esc(show.end)}</div>${historicalLabel(show.end)}` +
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
        (p.other_radio_blocks || []).forEach((s) => {
          line("Other live radio (" + esc(s.league || "") + ")", `<strong>${esc(s.start)} &rarr; ${esc(s.end)}</strong> (${esc(s.label || "")}) &mdash; ${esc(s.status || "")}${s.conditional ? " &middot; conditional" : ""}`);
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

  // ---------------------------------------------------------------------
  // Complete MLB season explorer (all 30 clubs, every game type)
  // ---------------------------------------------------------------------

  const MLB_TYPE_NAMES = {
    S: "Spring Training", R: "Regular season", E: "Exhibition", A: "All-Star Game",
    F: "Wild Card Series", D: "Division Series", L: "League Championship Series",
    W: "World Series", P: "Postseason", C: "Championship",
  };
  const MLB_HIGH_IDS = ["133", "137"];
  const MLB_ROW_LIMIT = 600;

  const mlbSeasonCache = {};

  function mlbTypeName(code) { return MLB_TYPE_NAMES[code] || code || "&mdash;"; }

  function fmtHM(hhmm) {
    if (!hhmm) return "TBD";
    const [h, m] = hhmm.split(":").map(Number);
    const suffix = h >= 12 ? "PM" : "AM";
    const hour12 = h % 12 === 0 ? 12 : h % 12;
    return hour12 + ":" + String(m).padStart(2, "0") + " " + suffix;
  }

  function fmtDateLong(iso) {
    const [y, m, d] = iso.split("-").map(Number);
    const wd = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
    return `${wd} ${MONTHS[m - 1]} ${d}, ${y}`;
  }

  function mlbSeasonInfo(year) {
    return (DATA.mlb_seasons && DATA.mlb_seasons[year]) || { available: false };
  }

  function mlbYears() {
    const info = DATA.mlb_seasons || {};
    return Object.keys(info).filter((y) => info[y].available).sort();
  }

  /** Load a season fixture file once, then keep it in memory. */
  function loadMlbSeason(year) {
    if (mlbSeasonCache[year]) return Promise.resolve(mlbSeasonCache[year]);
    const info = mlbSeasonInfo(year);
    if (!info.available || !info.site_file) return Promise.resolve(null);
    const url = info.site_file;
    const doFetch = (typeof fetch === "function") ? fetch(url) : Promise.reject(new Error("no fetch"));
    return doFetch
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
      .then((payload) => { mlbSeasonCache[year] = payload; return payload; })
      .catch(() => null);
  }

  function mlbSeasonMetaText(year, info) {
    const summary = info.summary;
    const when = summary && summary._meta ? summary._meta.retrieved_utc : "";
    const source = summary && summary._meta ? summary._meta.source_url : "";
    const validation = summary && summary.validation ? summary.validation : null;
    const quiet = info.dates_without_a_game || [];
    let out = `<strong>${esc(year)} season:</strong> ${info.games} official fixtures across ` +
      `${info.clubs} clubs (${info.first_date} to ${info.last_date}) &middot; ` +
      `${info.with_published_time} with a published first pitch, ` +
      `${info.time_tbd} still without a time (the date is still official).` +
      (info.regular_season_days ? ` The regular season covers ${info.regular_season_days} dates;` : "") +
      (quiet.length
        ? ` inside it the league schedules no game at all on ${quiet.map((d) => esc(d)).join(", ")} (the All-Star break).`
        : (info.regular_season_days ? " every date in it carries at least one game." : "")) +
      (when ? ` Snapshot retrieved <strong>${esc(when)}</strong>.` : "") +
      (source ? ` <a href="${esc(source)}" target="_blank" rel="noopener">Open the league query</a>` : "");
    if (validation) {
      out += `<span class="r">Committed as data/verified/mlb_schedule_${esc(year)}.csv and re-checked on every run: ` +
        `all 30 clubs in the regular season &middot; ${validation.regular_season_games} regular-season games &middot; ` +
        (Object.keys(validation.clubs_with_non_162_regular_season_games || {}).length === 0
          ? "all 30 clubs at exactly 162" : "club game counts need review") +
        ` &middot; unique game ids ${validation.unique_game_pks ? "yes" : "NO"}.</span>`;
    }
    return out;
  }

  function mlbRowMatches(row, club, month, type, highOnly) {
    const [date, , awayId, homeId, , gameType] = row;
    if (month && date.slice(0, 7) !== month) return false;
    if (type && gameType !== type) return false;
    if (highOnly && !(MLB_HIGH_IDS.includes(awayId) || MLB_HIGH_IDS.includes(homeId))) return false;
    if (club && awayId !== club && homeId !== club) return false;
    return true;
  }

  function renderMlbRows() {
    const body = $("mlbRows");
    if (!body) return;
    const year = $("mlbYear").value;
    const payload = mlbSeasonCache[year];
    const info = mlbSeasonInfo(year);
    const countEl = $("mlbCount");
    if (!payload) {
      body.innerHTML = `<tr><td colspan="8" class="empty">Fixture file for ${esc(year)} is not bundled in this build. ` +
        `The day checker still fetches this season live from statsapi.mlb.com.</td></tr>`;
      if (countEl) countEl.textContent = info.available ? "loading…" : "not bundled";
      return;
    }
    const meta = payload._meta || {};
    const clubs = meta.clubs || {};
    const club = $("mlbClub").value;
    const month = $("mlbMonth").value;
    const type = $("mlbType").value;
    const highOnly = $("mlbHighOnly").checked;
    const filtered = payload.games.filter((r) => mlbRowMatches(r, club, month, type, highOnly));
    const shown = filtered.slice(0, MLB_ROW_LIMIT);

    body.innerHTML = shown.map((row) => {
      const [date, time, awayId, homeId, venue, gameType, status, gamePk] = row;
      const highAway = MLB_HIGH_IDS.includes(awayId);
      const highHome = MLB_HIGH_IDS.includes(homeId);
      const cls = (highAway || highHome) ? ' class="hp-row"' : "";
      return `<tr${cls}>` +
        `<td class="num">${esc(fmtDateLong(date))}<div class="small">${esc(date)}</div></td>` +
        `<td class="num">${time ? esc(fmtHM(time)) : '<span class="pill tbd">TBD</span>'}</td>` +
        `<td>${esc(clubs[awayId] || awayId)}${highAway ? ' <span class="pill high">HP</span>' : ""}</td>` +
        `<td>${esc(clubs[homeId] || homeId)}${highHome ? ' <span class="pill high">HP</span>' : ""}</td>` +
        `<td>${esc(venue || "")}</td>` +
        `<td>${esc(mlbTypeName(gameType))}</td>` +
        `<td>${esc(status || "")}</td>` +
        `<td class="num small">${gamePk ? esc(gamePk) : "&mdash;"}</td>` +
        `</tr>`;
    }).join("");
    if (!shown.length) {
      body.innerHTML = '<tr><td colspan="8" class="empty">No fixture matches these filters.</td></tr>';
    }
    if (countEl) {
      countEl.textContent = `${shown.length} of ${filtered.length} matching fixtures (${meta.games} in ${year})`;
    }
    const hint = $("mlbTableHint");
    if (hint) {
      hint.innerHTML = filtered.length > shown.length
        ? `Showing the first ${shown.length} matching fixtures of ${filtered.length}. Narrow the filters (club, month or type) to see the rest.`
        : `All ${filtered.length} matching fixtures are shown. Times are Pacific; a row with <span class="pill tbd">TBD</span> has an official date but no published first pitch yet.`;
    }
  }

  function renderMlbExplorer() {
    const yearSelect = $("mlbYear");
    if (!yearSelect) return;
    const years = mlbYears();
    const previous = yearSelect.value;
    yearSelect.innerHTML = years.length
      ? years.map((y) => `<option value="${esc(y)}">${esc(y)}</option>`).join("")
      : '<option value="">none bundled</option>';
    if (years.includes(previous)) yearSelect.value = previous;

    const meta = $("mlbSeasonMeta");
    const first = years[0];
    if (meta) {
      meta.innerHTML = years.length
        ? years.map((y) => mlbSeasonMetaText(y, mlbSeasonInfo(y))).join("<br>")
        : `No complete season fixture file is bundled in this build. The day checker still fetches ` +
          `statsapi.mlb.com live, and the CI refresh commits the full season files automatically.`;
    }
    if (!years.length) {
      $("mlbRows").innerHTML = '<tr><td colspan="7" class="empty">No bundled season file in this build.</td></tr>';
      return;
    }

    if (!yearSelect.dataset.bound) {
      yearSelect.dataset.bound = "1";
      yearSelect.addEventListener("change", () => {
        loadMlbSeason(yearSelect.value).then(() => { rebuildMlbFilters(); renderMlbRows(); });
      });
      ["mlbClub", "mlbMonth", "mlbType"].forEach((id) => $(id).addEventListener("change", renderMlbRows));
      $("mlbHighOnly").addEventListener("change", renderMlbRows);
    }
    loadMlbSeason(yearSelect.value || first).then(() => { rebuildMlbFilters(); renderMlbRows(); });
  }

  /** Rebuild the club/month/type pickers from whichever season is loaded. */
  function rebuildMlbFilters() {
    const year = $("mlbYear").value;
    const payload = mlbSeasonCache[year];
    if (!payload) return;
    const meta = payload._meta || {};
    const clubSelect = $("mlbClub");
    const monthSelect = $("mlbMonth");
    const typeSelect = $("mlbType");
    const previousClub = clubSelect.value;
    const previousMonth = monthSelect.value;
    const previousType = typeSelect.value;

    const allClubs = meta.clubs || {};
    // Only the league's own 30 clubs belong in the filter; exhibition rows can
    // also mention national teams and college squads, which stay visible in rows.
    const official = (meta.mlb_club_ids && meta.mlb_club_ids.length) ? meta.mlb_club_ids : Object.keys(allClubs);
    const clubs = official.slice().sort((a, b) => ((allClubs[a] || a) > (allClubs[b] || b) ? 1 : -1));
    clubSelect.innerHTML = `<option value="">All ${clubs.length} clubs</option>` + clubs.map((id) =>
      `<option value="${esc(id)}">${esc(allClubs[id] || id)}${MLB_HIGH_IDS.includes(id) ? " (high priority)" : ""}</option>`).join("");
    const months = Array.from(new Set(payload.games.map((r) => r[0].slice(0, 7)))).sort();
    monthSelect.innerHTML = '<option value="">Every month</option>' + months.map((m) =>
      `<option value="${esc(m)}">${esc(fmtDateLong(m + "-01").replace(/^\w+ /, ""))}</option>`).join("");
    const types = Array.from(new Set(payload.games.map((r) => r[5]))).sort();
    typeSelect.innerHTML = '<option value="">Every game type</option>' + types.map((t) =>
      `<option value="${esc(t)}">${esc(mlbTypeName(t))}</option>`).join("");

    clubSelect.value = previousClub;
    monthSelect.value = previousMonth;
    typeSelect.value = previousType;

    const summaryBox = $("mlbSeasonSummary");
    if (summaryBox) {
      const summary = meta.summary;
      summaryBox.innerHTML = summary
        ? `<div class="whyyear"><h4>${esc(year)} &mdash; machine validation</h4><table><tbody>` +
          `<tr><td>Source</td><td><a href="${esc(summary._meta.source_url)}" target="_blank" rel="noopener">${esc(summary._meta.source_url)}</a></td></tr>` +
          `<tr><td>Retrieved (UTC)</td><td>${esc(summary._meta.retrieved_utc)}</td></tr>` +
          `<tr><td>Raw payload SHA-256</td><td><code>${esc(summary._meta.raw_sha256)}</code></td></tr>` +
          `<tr><td>Fixtures</td><td>${summary.counts.total} (${Object.entries(summary.counts.by_game_type).map(([k, v]) => esc(k) + ": " + v).join(" · ")})</td></tr>` +
          `<tr><td>Regular season</td><td>${summary.regular_season.games} games, ${esc(summary.regular_season.first_date)} &rarr; ${esc(summary.regular_season.last_date)}, ${summary.regular_season.days_with_a_game} days with a game</td></tr>` +
          `<tr><td>All 30 clubs present</td><td>${summary.validation.all_30_clubs_present ? "yes" : "NO &mdash; review"}</td></tr>` +
          `<tr><td>Unique game ids</td><td>${summary.validation.unique_game_pks ? "yes" : "NO &mdash; review"}</td></tr>` +
          `</tbody></table>${(summary.validation_notes || []).map((n) => `<span class="r">Note: ${esc(n)}</span>`).join("")}</div>`
        : `<span class="r">No machine summary bundled for ${esc(year)}.</span>`;
    }
  }

  // ---------------------------------------------------------------------
  // Postseason tracker: resolved dates vs unpublished times
  // ---------------------------------------------------------------------

  function renderPostseason() {
    const payload = DATA.postseason;
    const summary = $("postseasonSummary");
    if (!payload || !summary) return;
    const meta = payload._meta || {};
    const clinch = payload.clinch_status || {};
    const dates = payload.dates_with_a_reserved_game || [];
    const offDays = payload.off_days_with_no_possible_game || [];
    const rounds = payload.rounds || [];
    const state = DATA.postseason_state;
    const stateCounts = (state && state.counts) || null;
    const reservedDays = stateCounts ? stateCounts.distinct_dates_with_a_game : dates.length;
    const timesLine = stateCounts
      ? `First-pitch times published: <strong>${stateCounts.with_published_time} of ${stateCounts.game_records}</strong> league game records ` +
        `(measured ${esc(state._meta.retrieved_utc)}).`
      : `First-pitch times published: <strong>none yet</strong> &mdash; the league posts a round's times only once its matchups lock.`;

    summary.className = "verdict busy";
    summary.innerHTML = `DATES RESOLVED &middot; FIRST-PITCH TIMES NOT PUBLISHED` +
      `<span class="sub">${reservedDays} dates carry a reserved postseason game; ${offDays.length} dates ` +
      `(travel days, including ${esc(offDays[0] || "")}) cannot have one. ${timesLine} ` +
      `Berths locked: <strong>${(clinch.clinched_postseason_berth || []).length} of 12</strong>. ` +
      `Sources: <a href="${esc(meta.primary_source || "")}" target="_blank" rel="noopener">MLB Stats API postseason query</a> and the ` +
      `<a href="${esc((clinch.source || "").split(" ")[0])}" target="_blank" rel="noopener">MLB clinch tracker</a>.</span>`;

    const clinchBox = $("postseasonClinched");
    if (clinchBox) {
      clinchBox.innerHTML =
        `<div class="srcgrid"><div class="srccard station"><h4>Clinched a postseason berth (${(clinch.clinched_postseason_berth || []).length})</h4>` +
        `<ul class="def">${(clinch.clinched_postseason_berth || []).map((t) => `<li>${esc(t)}</li>`).join("")}</ul></div>` +
        `<div class="srccard station"><h4>Clinched a division title (${(clinch.clinched_division || []).length})</h4>` +
        `<ul class="def">${(clinch.clinched_division || []).map((t) => `<li>${esc(t)}</li>`).join("")}</ul></div>` +
        `<div class="srccard station"><h4>Resolution progress</h4><ul class="def">` +
        Object.values(clinch.resolution_progress || {}).map((v) => `<li>${esc(v)}</li>`).join("") +
        `</ul></div></div>` +
        (clinch.corrections_2026_09_21 ? `<p class="hint">Correction recorded: ${esc(clinch.corrections_2026_09_21)}</p>` : "");
    }

    const roundsBody = $("postseasonRounds");
    if (roundsBody) {
      roundsBody.innerHTML = rounds.map((r) =>
        `<tr><td><strong>${esc(r.round)}</strong></td><td class="num">${esc(String(r.best_of))}</td>` +
        `<td>${esc(r.dates.join(", "))}<div class="small">${esc(r.first_date)} &rarr; ${esc(r.last_date)}</div></td>` +
        `<td class="num">${esc(String(r.games_per_round_day || "—"))}</td>` +
        `<td><span class="pill tbd">Not published</span><div class="small">Games at 28 dates; ESPN/MLB print “times TBD”</div></td></tr>`).join("");
    }

    const datesBox = $("postseasonDates");
    if (datesBox) {
      const measuredDates = (state && state.dates_with_a_reserved_game) || dates;
      const impossible = (state && state.dates_in_window_with_no_game) || offDays;
      datesBox.innerHTML = `<strong>${measuredDates.length} dates are reserved for a game:</strong> ${esc(measuredDates.join(", "))}.` +
        (impossible.length ? `<br><strong>No game is possible on:</strong> ${esc(impossible.join(", "))} ` +
          `(travel days, measured against the league response). Those dates are free of MLB even in the worst case.` : "") +
        (state ? `<br><span class="r">Measured from ${esc(state._meta.source_url)} on ${esc(state._meta.retrieved_utc)} ` +
          `(payload SHA-256 <code>${esc(state._meta.raw_sha256)}</code>).` +
          (stateCounts && stateCounts.participants_are_placeholders
            ? " Participants are still the league's seed placeholders (e.g. “AL Wild Card #1”), so no matchup is shown." : "") +
          `</span>` : "");
    }
    const offNote = $("postseasonOffDays");
    if (offNote) {
      offNote.innerHTML = `Wild Card Series: ${esc((rounds[0] || {}).dates ? rounds[0].dates.join(", ") : "")} · ` +
        `Division Series from ${esc((rounds[1] || {}).first_date || "")} · ` +
        `LCS from ${esc((rounds[2] || {}).first_date || "")} · ` +
        `World Series Game 1 ${esc((rounds[3] || {}).first_date || "")}, Game 7 ${esc((rounds[3] || {}).last_date || "")}. ` +
        `Any of these dates can still be the day a vacation day turns busy.`;
    }

    const unresolvedBox = $("postseasonUnresolved");
    if (unresolvedBox) {
      const items = [
        ["First-pitch times", meta.time_resolution_status || ""],
        ["Matchups", (clinch.resolution_progress || {}).matchups || ""],
        ["Wild-card slots", (clinch.resolution_progress || {}).wild_card_slots || ""],
        ["Still unresolved", clinch.still_unresolved || ""],
        ["What would resolve it", "The league sets early-round times round by round once matchups lock on 2026-09-27. " +
          "The daily CI refresh re-measures and this tab re-renders; the date-level holds stay conservative until a real instant exists."],
        ["Review note", clinch.review_note || ""],
      ].filter((pair) => pair[1]);
      unresolvedBox.innerHTML = `<div class="whyyear"><h4>Unresolved, in plain language</h4><table><tbody>` +
        items.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join("") +
        `</tbody></table><span class="r">When the league publishes a round's times, the CI refresh replaces the ` +
        `date-level hold with the real instant and this page re-runs. Nothing is estimated into a time.</span></div>`;
    }
  }

  // ---------------------------------------------------------------------
  // Answer matrix: every section x every trip length, both readings
  // ---------------------------------------------------------------------

  function answerCell(row) {
    if (!row || !row.best) return '<td class="num">none</td>';
    const fits = [];
    if (row.requirements.week_1) fits.push("1 wk");
    if (row.requirements.weeks_2) fits.push("2 wk");
    if (row.requirements.weeks_3) fits.push("3 wk");
    const past = row.best.end < ptDateOf(Date.now()) ? '<span class="past-label">past</span>' : "";
    return `<td class="num"><strong>${row.best.days} d</strong>` +
      `<div class="small">${esc(fmtRangeFriendly(row.best.start, row.best.end))}${past}</div>` +
      `<div class="small">${fits.length ? "fits " + fits.join(", ") : "no full week"}</div></td>`;
  }

  function renderAnswerMatrix() {
    const box = $("answerMatrix");
    if (!box) return;
    const years = [2026, 2027, 2028, 2029];
    const table = (interpKey, title, note) => {
      const head = '<tr><th>Year</th>' + SECTIONS.map((s) => `<th>${esc(s.short)}</th>`).join("") + "</tr>";
      const body = years.map((year) => {
        const cells = SECTIONS.map((s) => {
          const row = DATA.vacation.find((r) => r.year === year && r.section === s.id && r.interpretation === interpKey);
          return answerCell(row);
        }).join("");
        const status = statusForYear(year);
        return `<tr><td class="num"><strong>${year}</strong><div class="${status.cls} small">${esc(status.label)}</div></td>${cells}</tr>`;
      }).join("");
      return `<div class="tablewrap"><table class="vtable answer">` +
        `<thead><tr><th class="tabletitle" colspan="${SECTIONS.length + 1}">${title}</th></tr>${head}</thead>` +
        `<tbody>${body}</tbody></table><p class="hint">${note}</p></div>`;
    };
    box.innerHTML =
      table(
        "strict",
        "Spring Training counts as MLB (the literal reading: Giants Spring Training is on KNBR)",
        "Because Spring Training runs almost every day from mid-February, strict runs are short. " +
        "The longest strict run in every section is inside the gap between the Super Bowl and the first Spring Training game."
      ) +
      table(
        "regular",
        "Regular season + postseason only (Spring Training ignored)",
        "This is the reading that produces the long February–March windows. Every cell still accounts for " +
        "the previous NFL season's playoff dates, the Pro Bowl Games and the next NFL season's start."
      );
    box.insertAdjacentHTML("beforeend",
      `<p class="lede">Rule of thumb from the tables above: the quiet stretch every year is the gap between the ` +
      `Super Bowl and Opening Day. Section 1 and Section 2 behave identically there because college football is over; ` +
      `Section 3 loses the corridor to the Earthquakes' MLS calendar.</p>`);
  }

  function renderReview() {
    const box = $("reviewList");
    const byLeague = {};
    DATA.unresolved.forEach((u) => { (byLeague[u.league] = byLeague[u.league] || []).push(u); });
    $("reviewCount").textContent = DATA.unresolved.length;

    box.innerHTML = Object.keys(byLeague).sort().map((league) => {
      const items = byLeague[league].map((u) =>
        `<div class="reviewitem"><strong>${esc(u.label)}</strong>${u.date_local ? " &middot; " + esc(u.date_local) : ""}` +
        `<span class="r">${esc(u.reason)}</span>` +
        (u.source ? `<span class="r">${sourceLink(u.source)}</span>` : "") +
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
        `<div class="pill ${cls}">94122 reception: unmeasured</div>` +
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
      { label: "MLS official calendar change (format confirmed, fixtures unresolved)", url: "https://www.mlssoccer.com/news/mls-to-align-calendar-with-top-leagues-around-world" },
      { label: "MLB official 2025 duration research (historical, not 2026)", url: "https://www.mlb.com/news/mlb-average-game-time-under-three-hours-third-straight-year" },
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
      { label: "NFL &mdash; Super Bowl LXIII host/year confirmed (Las Vegas, 2029)", url: "https://www.nfl.com/news/las-vegas-to-host-super-bowl-lxiii-in-2029" },
      { label: "NFL Annual Meeting 2026-03-30 &mdash; Super Bowl LXIII exact date: February 11, 2029", url: "https://www.forbes.com/sites/alexkirschner/2026/03/30/nfl-super-bowl-2029-date-location-las-vegas-allegiant-stadium/" },
      { label: "CBS Sports &mdash; Warriors 2026-27 schedule grid (ET tips; transcribed)", url: "https://www.cbssports.com/nba/teams/GS/golden-state-warriors/schedule/" },
      { label: "ESPN API &mdash; Warriors opener spot-check (matches transcribed grid)", url: "http://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/9/schedule?dates=2026-2027" },
      { label: "Golden State Valkyries &mdash; 2026 broadcast partners and per-game radio flags", url: "https://www.wnba.com/valkyries/roster" },
      { label: "KGMZ 95.7 The Game &mdash; official Warriors/Valkyries release", url: "https://www.cumulusmedia.com/2025/09/25/golden-state-valkyries-join-95-7-the-game-as-official-flagship-station/" },
      { label: "San Jose Sharks &mdash; Sports Radio 1140 AM listing; app-only broadcasts (verified streaming)", url: "https://www.nhl.com/sharks/fans/how-to-listen-watch-2526" },
      { label: "Forbes sports business &mdash; new NHL local radio coverage (no Bay Area 49ers/Sharks carry)", url: "https://www.forbes.com/sites/paulkaplan/2026/09/04/san-jose-sharks-new-local-radio-coverage/" },
      { label: "49ers / Cumulus &mdash; KNBR flagship extension, 2026-04-15", url: "https://www.cumulusmedia.com/2026/04/15/san-francisco-49ers-announce-multi-year-partnership-extension-with-cumulus-medias-knbr/" },
      { label: "California Golden Bears &mdash; 2026 football schedule (radio: KSFO 810 AM)", url: "https://calbears.com/sports/football/schedule" },
      { label: "Stanford Cardinal &mdash; 2026 football schedule", url: "https://gostanford.com/sports/football/schedule" },
      { label: "Athletics &mdash; radio affiliates (KSTE 650 AM, KNEW 960 AM)", url: "https://www.mlb.com/athletics/schedule/watch" },
      { label: "San Jose Earthquakes &mdash; 2026 MLS schedule", url: "https://www.sjearthquakes.com/news/news-earthquakes-announce-2026-major-league-soccer-schedule" },
      { label: "Cumulus Media surrenders 560 AM; KSFO is now 810 AM (50 kW)", url: "https://www.radioworld.com/news-and-business/cumulus-media-surrenders-license-of-san-franciscos-560-am" },
    ];
    $("sourcesList").innerHTML =
      '<div class="srcgrid">' + fixed.concat(rows).map((r) =>
        `<div class="srccard"><h4>${esc(r.label.replace(/&mdash;/g, "—").replace(/&middot;/g, "·"))}</h4>${sourceLink(r.url)}` +
        `<span class="when">Source register · line-by-line review 2026-09-21 · links can change</span></div>`).join("") + "</div>";
  }

  // ---------------------------------------------------------------------
  // Live MLB refresh
  // ---------------------------------------------------------------------

  function combinedGames(extras) {
    const incoming = extras || [];
    const dates = new Set(incoming.map((g) => g.date_local));
    // A fresh all-club response replaces stale per-date/aggregate MLB rows.
    // Empty/unreleased responses never wipe the conservative offline fallback.
    return DATA.games.filter((g) => !(g.league === "MLB" && dates.has(g.date_local))).concat(incoming);
  }

  function normalizeMlb(payload, source) {
    if (!Array.isArray(payload.dates)) throw new Error("Invalid MLB response");
    return payload.dates.flatMap((d) => (d.games || []).map((g) => {
      const away = g.teams.away.team, home = g.teams.home.team;
      const ids = [away.id, home.id];
      const high = ids.includes(133) || ids.includes(137);
      const raw = g.gameDate;
      const tbd = !raw || raw.slice(11, 19) === MLB_TBD_SENTINEL || (g.status || {}).startTimeTBD;
      const date = tbd ? (g.officialDate || d.date) : ptDateOf(Date.parse(raw));
      const networks = [];
      if (ids.includes(137)) networks.push("Giants affiliate: KNBR 680 AM / 104.5 FM");
      if (ids.includes(133)) networks.push("Athletics affiliate: KNEW 960 AM");
      return {
        id: "mlb-" + g.gamePk, game_pk: g.gamePk, league: "MLB",
        label: `${away.name} at ${home.name}`, game_type: g.gameType,
        detail: "Official MLB feed · " + ((g.status || {}).detailedState || "Scheduled") + " · end time estimated",
        network: networks.join("; ") || "Local AM/FM carriage unconfirmed; counts by all-MLB rule",
        priority: high ? "high" : "normal", source: source,
        date_local: date, start_utc: raw || null, duration: DURATIONS.MLB,
        sections: ["1", "2", "3"],
        cancelled: ["C", "D"].includes((g.status || {}).codedGameState),
        time_status: tbd ? "TBD_official_date" : "official",
      };
    }));
  }

  function fetchMlbFor(dateStr) {
    // Include adjoining official dates: MLB dates are not necessarily PT dates,
    // and yesterday's late game may extend beyond midnight.
    const url = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=" + addDaysStr(dateStr, -1) +
      "&endDate=" + addDaysStr(dateStr, 1) + "&gameType=R,E,S,D,L,F,W,A";
    const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), 12000) : null;
    return fetch(url, controller ? { signal: controller.signal } : {})
      .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then((payload) => normalizeMlb(payload, url))
      .finally(() => { if (timer) clearTimeout(timer); });
  }

  let mlbRequest = 0;
  /** Fixtures for one Pacific date from the committed official season snapshot. */
  function snapshotGamesFor(dateStr) {
    const payload = mlbSeasonCache[dateStr.slice(0, 4)];
    if (!payload) return [];
    const meta = payload._meta || {};
    const clubs = meta.clubs || {};
    return payload.games.filter((row) => row[0] === dateStr).map((row) => {
      const [date, time, awayId, homeId, venue, gameType, status, gamePk] = row;
      const ids = [Number(awayId), Number(homeId)];
      const high = ids.includes(133) || ids.includes(137);
      const networks = [];
      if (ids.includes(137)) networks.push("Giants affiliate: KNBR 680 AM / 104.5 FM");
      if (ids.includes(133)) networks.push("Athletics affiliate: KNEW 960 AM");
      const startUtc = time
        ? new Date(ptWallToUtc(date, time)).toISOString().replace(/\.\d{3}Z$/, "Z")
        : null;
      return {
        id: "mlb-snapshot-" + (gamePk || date + "-" + awayId + "-" + homeId),
        game_pk: gamePk || "",
        league: "MLB",
        game_type: gameType,
        label: `${clubs[awayId] || awayId} at ${clubs[homeId] || homeId}`,
        detail: `${mlbTypeName(gameType)} · official fixture from the committed season snapshot · ${status || ""}`,
        network: networks.join("; ") || "Local AM/FM carriage unconfirmed; counts by all-MLB rule",
        priority: high ? "high" : "normal",
        source: meta.source || "",
        date_local: date,
        start_utc: startUtc,
        duration: DURATIONS.MLB,
        sections: ["1", "2", "3"],
        time_status: startUtc ? "official" : "TBD_official_date",
        snapshot: true,
      };
    });
  }

  function refreshMlb(dateStr) {
    const request = ++mlbRequest;
    return fetchMlbFor(dateStr)
      .then((games) => {
        if (request !== mlbRequest || dateStr !== currentDate) return;
        liveMlb = { dateStr: dateStr, games: games };
        mlbFeedState = { mode: games.length ? "live" : "empty", message: "" };
        renderDay(currentDate);
      })
      .catch((err) => {
        if (request !== mlbRequest || dateStr !== currentDate) return;
        const message = String(err && err.message ? err.message : err);
        // The committed official snapshot is on the same origin as this page, so
        // it usually survives exactly the failure that breaks statsapi.mlb.com.
        return loadMlbSeason(dateStr.slice(0, 4)).then(() => {
          if (request !== mlbRequest || dateStr !== currentDate) return;
          const snap = snapshotGamesFor(dateStr);
          if (snap.length) {
            liveMlb = { dateStr: dateStr, games: snap };
            mlbFeedState = { mode: "snapshot", message: message };
          } else {
            mlbFeedState = { mode: "offline", message: message };
          }
          renderDay(currentDate);
        });
      });
  }

  const MIN_DATE = "2026-01-01", MAX_DATE = "2029-12-31";
  function navigateDay(date) {
    renderDay(date < MIN_DATE ? MIN_DATE : date > MAX_DATE ? MAX_DATE : date);
    refreshMlb(currentDate);
  }

  function renderCalendar() {
    const box = $("monthCalendar");
    if (!box) return;
    const first = currentDate.slice(0, 8) + "01";
    const month = new Date(first + "T12:00:00Z");
    $("monthHeading").textContent = new Intl.DateTimeFormat("en-US", {month:"long", year:"numeric", timeZone:TZ}).format(month);
    box.innerHTML = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => `<span class="weekday">${d}</span>`).join("");
    for (let i = 0; i < month.getUTCDay(); i++) box.appendChild(document.createElement("span"));
    for (let date = first; date.slice(0, 7) === first.slice(0, 7); date = addDaysStr(date, 1)) {
      const rep = dayReport(date, [], scope);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "calendar-day" + (date === currentDate ? " selected" : "");
      button.disabled = date < MIN_DATE || date > MAX_DATE;
      button.setAttribute("aria-pressed", String(date === currentDate));
      button.setAttribute("aria-label", `${date}: ${rep.isFreeDay ? "no bundled conflict; coverage unresolved" : "game or conservative hold"}`);
      button.innerHTML = Number(date.slice(8)) + `<span aria-hidden="true">${rep.isFreeDay ? "○" : "●"}</span>`;
      const selectedDate = date;
      button.addEventListener("click", () => navigateDay(selectedDate));
      box.appendChild(button);
    }
    $("prevDay").disabled = currentDate <= MIN_DATE;
    $("nextDay").disabled = currentDate >= MAX_DATE;
    $("prevMonth").disabled = currentDate.slice(0, 7) <= MIN_DATE.slice(0, 7);
    $("nextMonth").disabled = currentDate.slice(0, 7) >= MAX_DATE.slice(0, 7);
  }

  function moveMonth(n) {
    const d = new Date(currentDate.slice(0,8) + "01T12:00:00Z");
    d.setUTCMonth(d.getUTCMonth() + n);
    navigateDay(d.toISOString().slice(0,10));
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
        document.querySelectorAll(".tab").forEach((b) => { b.classList.remove("active"); b.removeAttribute("aria-current"); });
        document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        btn.setAttribute("aria-current", "page");
        $("tab-" + btn.dataset.tab).classList.add("active");
        // The season fixture files are large, so they are only requested when the
        // tab that needs them is actually opened.
        if (btn.dataset.tab === "mlb") renderMlbExplorer();
      });
    });

    $("prevDay").addEventListener("click", () => { navigateDay(addDaysStr(currentDate, -1)); });
    $("nextDay").addEventListener("click", () => { navigateDay(addDaysStr(currentDate, 1)); });
    $("todayBtn").addEventListener("click", () => { navigateDay(ptDateOf(Date.now())); });
    $("dateInput").addEventListener("change", (e) => { if (e.target.value) { navigateDay(e.target.value); } });
    $("prevMonth").addEventListener("click", () => moveMonth(-1));
    $("nextMonth").addEventListener("click", () => moveMonth(1));
    $("refreshMlb").addEventListener("click", () => refreshMlb(currentDate));
    document.querySelectorAll('input[name="interp"]').forEach((r) => r.addEventListener("change", () => setInterp(r.value)));
    document.querySelectorAll('input[name="interpDecide"]').forEach((r) => r.addEventListener("change", () => setInterp(r.value)));
    document.querySelectorAll('input[name="trip"]').forEach((r) => r.addEventListener("change", () => { tripLength = parseInt(r.value, 10); renderDecision(); }));

    if ($("mlbClubs")) $("mlbClubs").innerHTML = (DATA.mlb_clubs.teams || []).map((team) =>
      `<div class="club-item"><span>${esc(team.name)}</span>${team.priority === "high" ? '<span class="pill high">High priority</span>' : ""}</div>`
    ).join("") + `<a href="${esc(DATA.mlb_clubs.source)}" target="_blank" rel="noopener">Official MLB club list</a>`;
    const coverage = $("coverageStamp");
    if (coverage) {
      const seasons = DATA.mlb_seasons || {};
      const bits = Object.keys(seasons).sort().map((year) => {
        const info = seasons[year] || {};
        return info.available ? `${year}: ${info.games} official fixtures` : `${year}: not bundled`;
      });
      const state = DATA.postseason_state;
      let stamp = bits.length ? "Committed fixture lists — " + bits.join(" · ") + ". " : "";
      if (state && state.counts) {
        stamp += `Postseason ${state._meta && state._meta.year ? state._meta.year : ""}: ` +
          `${state.counts.game_records} game records, ${state.counts.with_published_time} with a published first pitch` +
          (state._meta && state._meta.retrieved_utc ? ` (measured ${state._meta.retrieved_utc})` : "") + ". ";
      }
      stamp += "Other league inputs retrieved 2026-09-20; unpublished times and unreleased seasons remain incomplete.";
      coverage.textContent = stamp;
    }
    fetch("data/refresh-status.json").then((r) => r.ok ? r.json() : null).then((health) => {
      if (health && $("refreshHealth")) $("refreshHealth").textContent =
        "Last automated MLB refresh: " + health.mlb + " · " + health.attempted_utc;
    }).catch(() => {});
    renderScopePicker();
    renderScopeNote();
    renderNflSlate();
    renderVacation();
    renderCompare();
    renderDecScopeCards();
    renderDecision();
    renderAnswerMatrix();
    renderMlbExplorer();
    renderPostseason();
    renderReview();
    renderRadio();
    renderSources();
    navigateDay(currentDate);
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
    normalizeMlb: normalizeMlb, combinedGames: combinedGames, refreshMlb: refreshMlb,
    DURATIONS: DURATIONS, TBD_ENVELOPE: TBD_ENVELOPE, TZ: TZ, SCOPES: SCOPES,
    getScope: function () { return scope; }, setScope: function (s) { scope = s; },
  };
})();
