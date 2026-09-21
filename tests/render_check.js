// Real DOM render check: loads site/index.html into jsdom, executes the real
// site/app.js against the real bundle, and asserts the page actually renders.
//
// This is the only test that proves the site works as a page rather than as a
// library. Run with: node tests/render_check.js
const fs = require("fs");
const path = require("path");
const { JSDOM } = require(path.join(__dirname, "..", "node_modules", "jsdom"));

const ROOT = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(ROOT, "site", "index.html"), "utf8");

const failures = [];
const ok = [];

function check(label, cond, detail) {
  if (cond) ok.push(label);
  else failures.push(`${label}${detail ? " :: " + detail : ""}`);
}

// Offline: block all subresource loading. app.js must still render from the bundle.
const dom = new JSDOM(html, {
  url: "http://localhost:8080/",
  runScripts: "outside-only",
  resources: undefined,
  pretendToBeVisual: true,
});
const { window } = dom;

// Stub fetch: the live statsapi.mlb.com call is rejected (that is the offline case
// the page has to survive), while same-origin files - the generated bundle and the
// committed per-season fixture files - are served from disk. This exercises the
// real loading path instead of a stub.
window.fetch = function (url) {
  const target = String(url);
  if (/^https?:\/\//.test(target) && !target.startsWith("http://localhost:8080/")) {
    return Promise.reject(new Error("offline in test"));
  }
  const rel = target.replace(/^http:\/\/localhost:8080\//, "").replace(/^\.\//, "");
  const file = path.join(ROOT, "site", rel);
  return new Promise((resolve, reject) => {
    fs.readFile(file, "utf8", (err, body) => {
      if (err) { reject(new Error("HTTP 404 for " + rel)); return; }
      resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(body)) });
    });
  });
};

// Wait for an async render (the season file load) without hand-rolling sleeps.
function waitFor(predicate, timeoutMs) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      let value = false;
      try { value = predicate(); } catch (e) { value = false; }
      if (value) { resolve(value); return; }
      if (Date.now() - started > timeoutMs) { reject(new Error("timed out")); return; }
      setTimeout(tick, 20);
    };
    tick();
  });
}

const errors = [];
window.addEventListener("error", (e) => errors.push(String(e.message || e.error)));

// Execute the real bundle and the real app, in the order index.html declares them.
window.eval(fs.readFileSync(path.join(ROOT, "site", "data", "schedule-data.js"), "utf8"));
window.eval(fs.readFileSync(path.join(ROOT, "site", "app.js"), "utf8"));

// Fire DOMContentLoaded, which is what wires up the UI.
window.document.dispatchEvent(new window.Event("DOMContentLoaded", { bubbles: true }));

const $ = (id) => window.document.getElementById(id);
const tab = (name) => window.document.querySelector(`.tab[data-tab="${name}"]`);
const text = (id) => ($(id) ? $(id).textContent : "<missing>").replace(/\s+/g, " ").trim();

setTimeout(() => {
  // ---- the page rendered at all ----
  check("day heading rendered", /\d{4}/.test(text("dayHeading")), text("dayHeading"));
  check("verdict banner rendered", /CONFLICT|BUSY/.test(text("verdict")), text("verdict"));
  check("generation stamp rendered", /Bundle generated/.test(text("genStamp")), text("genStamp"));
  check("no uncaught JS errors", errors.length === 0, errors.join(" | "));

  $("dateInput").value = "2026-09-20";
  $("dateInput").dispatchEvent(new window.Event("change", { bubbles: true }));

  // ---- scoreboard actually populated ----
  const games = window.document.querySelectorAll("#scoreboard .game");
  check("scoreboard has game rows", games.length > 0, `found ${games.length}`);
  check("scoreboard has league groups", window.document.querySelectorAll("#scoreboard .leaguegroup").length > 0);

  // ---- the complete NFL slate is visible without pretending every game is radio ----
  $("dateInput").value = "2026-09-13";
  $("dateInput").dispatchEvent(new window.Event("change", { bubbles: true }));
  check("NFL reference panel shows the actual Week 1 slate",
    window.document.querySelectorAll("#nflReference .nflrefrow").length === 13,
    `found ${window.document.querySelectorAll("#nflReference .nflrefrow").length}`);
  check("NFL reference names an actual Week 1 matchup", /Chicago Bears at Carolina Panthers/.test(text("nflReference")));
  check("old generic NFL radio-window label is absent", !/national radio window TBA/.test(window.document.body.textContent));
  tab("nfl").dispatchEvent(new window.Event("click", { bubbles: true }));
  check("NFL slate tab activates", $("tab-nfl").classList.contains("active"));
  check("NFL slate tab exposes all 272 games", /272 of 272 games/.test(text("nflSlateMeta")), text("nflSlateMeta"));
  check("NFL slate tab has 18 week groups", window.document.querySelectorAll("#nflSlate .nflweek").length === 18);
  tab("day").dispatchEvent(new window.Event("click", { bubbles: true }));

  // ---- free windows rendered ----
  const wins = window.document.querySelectorAll("#freeList .freewin");
  check("free windows rendered", wins.length > 0 || /No free window/.test(text("freeList")));

  // ---- timeline blocks rendered ----
  check("timeline blocks rendered", window.document.querySelectorAll("#timeline .blk").length > 0);

  // ---- the regression the user reported: 2026-09-29 must NOT read as free ----
  $("dateInput").value = "2026-09-29";
  $("dateInput").dispatchEvent(new window.Event("change", { bubbles: true }));
  const v = text("verdict");
  check("2026-09-29 (Wild Card day) is NOT free", /BUSY/.test(v), v);
  check("2026-09-29 flags unconfirmed time", /not yet announced/.test(v), v);
  check("2026-09-29 shows a Time TBD chip",
    window.document.querySelectorAll("#scoreboard .pill.tbd").length > 0);

  // ---- a genuinely free day still reads free ----
  // 2026-10-02 is the MLB postseason travel day between the Wild Card Series and
  // the Division Series: no game under any scenario, and no NFL/MLS/college game.
  $("dateInput").value = "2026-10-02";
  $("dateInput").dispatchEvent(new window.Event("change", { bubbles: true }));
  check("2026-10-02 discloses no known conflict, not guaranteed free", /NO KNOWN CONFLICT/.test(text("verdict")), text("verdict"));
  check("2026-10-02 shows no game rows",
    window.document.querySelectorAll("#scoreboard .game").length === 0);

  // ---- navigation buttons move the date ----
  const before = $("dateInput").value;
  $("nextDay").dispatchEvent(new window.Event("click", { bubbles: true }));
  check("next-day button advances the date", $("dateInput").value === "2026-10-03", `${before} -> ${$("dateInput").value}`);
  check("2026-10-03 (Division Series) is NOT free", /BUSY/.test(text("verdict")), text("verdict"));
  $("prevDay").dispatchEvent(new window.Event("click", { bubbles: true }));
  check("prev-day button rewinds the date", $("dateInput").value === "2026-10-02", $("dateInput").value);

  // ---- the section switcher ----
  const scopeBtns = () => window.document.querySelectorAll("#scopePicker .scopebtn");
  check("section picker rendered with 4 options", scopeBtns().length === 4, `found ${scopeBtns().length}`);
  check("section 3 is the default", scopeBtns()[2].classList.contains("active"));
  check("scope note exposes the Warriors/Sharks limitation", /Warriors/.test(text("scopeNote")) && /Sharks/.test(text("scopeNote")));

  // 2026-08-29: Stanford opens its season and the Earthquakes play. Section 1 does
  // not count either; section 3 counts both.
  $("dateInput").value = "2026-08-29";
  $("dateInput").dispatchEvent(new window.Event("change", { bubbles: true }));
  const scope3Rows = window.document.querySelectorAll("#scoreboard .game").length;
  scopeBtns()[0].dispatchEvent(new window.Event("click", { bubbles: true }));
  check("clicking a section activates it", scopeBtns()[0].classList.contains("active"));
  check("section 1 verdict names the section", /section:\s*1\./.test(text("verdict").replace(/\s+/g, " ")), text("verdict"));
  const scope1Rows = window.document.querySelectorAll("#scoreboard .game").length;
  check("section 1 shows fewer games than section 3 on 2026-08-29", scope1Rows < scope3Rows, `${scope1Rows} vs ${scope3Rows}`);
  check("outside-section games are disclosed, not hidden",
    window.document.querySelectorAll("#outsideScope .game").length > 0, text("outsideScope"));
  check("outside-section note names the section", /not counted in 1\./.test(text("outsideScope")), text("outsideScope"));

  // The MLB season frame still blocks: MLB is in season and no per-game data is bundled.
  check("offline MLB season frame blocks conservatively", /MLB is in season/.test(text("verdict")), text("verdict"));

  // Back to section 3 for the vacation-tab assertions below.
  scopeBtns()[2].dispatchEvent(new window.Event("click", { bubbles: true }));

  // ---- vacation tab ----
  tab("vacation").dispatchEvent(new window.Event("click", { bubbles: true }));
  check("vacation tab activates", $("tab-vacation").classList.contains("active"));
  const rows = window.document.querySelectorAll("#vacationBody tr");
  check("vacation table has 4 year rows", rows.length === 4, `found ${rows.length}`);
  check("2026 row describes modeled gaps", /Official inputs · modeled gaps/.test(rows[0].textContent));
  check("2027 row marked MLB VERIFIED (partial)", /MLB VERIFIED/.test($("vacationBody").textContent));
  check("2028-29 rows marked ESTIMATED",
    ($("vacationBody").textContent.match(/ESTIMATED/g) || []).length === 2);

  // ---- vacation table reports the 1/2/3-week requirements ----
  check("vacation table reports 1-week / 2-week / 3-week columns",
    /1 week/.test($("tab-vacation").textContent) && /2 weeks/.test($("tab-vacation").textContent) && /3 weeks/.test($("tab-vacation").textContent));
  check("strict section 3 cannot reach two weeks", /no/.test($("vacationBody").textContent));

  // ---- audit table states WHICH blocking mode produced the answer ----
  check("audit table reports exact fixture dates, not a frame",
    /official fixture dates/.test(text("decisionWhy")), text("decisionWhy").slice(0, 200));
  check("audit table names the committed snapshot as the source",
    /mlb_schedule_2026\.csv/.test(text("decisionWhy")), text("decisionWhy").slice(0, 300));

  // ---- interpretation toggle recomputes ----
  const strictText = $("vacationBody").textContent;
  const regular = window.document.querySelector('input[name="interp"][value="regular"]');
  regular.checked = true;
  regular.dispatchEvent(new window.Event("change", { bubbles: true }));
  check("interpretation toggle changes the table", $("vacationBody").textContent !== strictText);

  // Section 1 under the regular-season reading is the 44-day 2026 window; section 3
  // is the 12-day one. Both must be reachable from the UI without a reload.
  scopeBtns()[0].dispatchEvent(new window.Event("click", { bubbles: true }));
  check("section 1 regular reading shows the 44-day window", /44 d/.test($("vacationBody").textContent), $("vacationBody").textContent.slice(0, 120));
  scopeBtns()[2].dispatchEvent(new window.Event("click", { bubbles: true }));
  check("section 3 regular reading shows the 12-day window", /12 d/.test($("vacationBody").textContent), $("vacationBody").textContent.slice(0, 120));

  // ---- Spring Training included vs excluded, both visible at once ----
  const stRows = window.document.querySelectorAll("#stCompareBody tr");
  check("spring training comparison has 4 year rows", stRows.length === 4, `found ${stRows.length}`);
  check("spring training comparison headers present",
    /With Spring Training \(strict\)/.test(window.document.querySelector("#tab-vacation").textContent) &&
    /Without Spring Training \(regular\)/.test(window.document.querySelector("#tab-vacation").textContent));
  // Section 3, 2026: strict 11 days (Feb 9-19) vs regular 12 days (Feb 9-20) -> +1
  check("spring training comparison quantifies the strict cost (2026, section 3)",
    /\+1 free day/.test(stRows[0].textContent), stRows[0].textContent);
  // 2027-2029 section 3: both readings collapse to the same 5-day run
  check("spring training comparison shows no difference where readings agree (2027)",
    /no difference/.test(stRows[1].textContent), stRows[1].textContent);

  // ---- compare + radio tabs ----
  tab("compare").dispatchEvent(new window.Event("click", { bubbles: true }));
  check("compare tab activates", $("tab-compare").classList.contains("active"));
  check("compare table has a row per year",
    window.document.querySelectorAll("#compareTable2 tbody tr").length === 4,
    `found ${window.document.querySelectorAll("#compareTable2 tbody tr").length}`);
  check("compare table marks the selected section",
    window.document.querySelectorAll("#compareTable2 .cmpcell.current").length === 4);
  check("compare notes explain the MLS delta", /Earthquakes/.test(text("compareSummary")), text("compareSummary").slice(0, 160));

  tab("radio").dispatchEvent(new window.Event("click", { bubbles: true }));
  check("radio tab lists stations", window.document.querySelectorAll("#radioList .station").length >= 6,
    `found ${window.document.querySelectorAll("#radioList .station").length}`);
  check("radio tab names KNBR", /KNBR/.test(text("radioList")));
  check("radio tab discloses the Westwood One affiliates", /Westwood One/.test(text("radioList")));

  // ---- review + sources tabs ----
  tab("review").dispatchEvent(new window.Event("click", { bubbles: true }));
  const reviewCount = parseInt(text("reviewCount"), 10);
  check("review count is 50+", reviewCount >= 50, text("reviewCount"));
  check("review list populated", window.document.querySelectorAll("#reviewList .reviewitem").length > 0);
  tab("sources").dispatchEvent(new window.Event("click", { bubbles: true }));
  check("sources populated", window.document.querySelectorAll("#sourcesList .srccard").length > 15);

  // ---- offline MLB note is labelled, not silently missing ----

  // ---- answer matrix: every section x every year, both Spring Training readings ----
  check("answer matrix renders two readings", window.document.querySelectorAll("#answerMatrix table").length === 2,
    `found ${window.document.querySelectorAll("#answerMatrix table").length}`);
  check("answer matrix has a row per year in each reading",
    window.document.querySelectorAll("#answerMatrix tbody tr").length === 8,
    `found ${window.document.querySelectorAll("#answerMatrix tbody tr").length}`);
  check("answer matrix names all three sections",
    /1\. MLB \+ NFL/.test(text("answerMatrix")) && /Stanford/.test(text("answerMatrix")) && /Earthquakes/.test(text("answerMatrix")),
    text("answerMatrix").slice(0, 200));
  check("answer matrix states which trip lengths fit", /fits /.test(text("answerMatrix")) || /no full week/.test(text("answerMatrix")));
  check("answer matrix flags historical windows",
    /past/.test(text("answerMatrix")), text("answerMatrix").slice(0, 200));

  // ---- postseason tracker: dates resolved, times measured ----
  tab("postseason").dispatchEvent(new window.Event("click", { bubbles: true }));
  check("postseason tab activates", $("tab-postseason").classList.contains("active"));
  check("postseason summary separates dates from times",
    /DATES RESOLVED/.test(text("postseasonSummary")) && /FIRST-PITCH TIMES NOT PUBLISHED/.test(text("postseasonSummary")),
    text("postseasonSummary").slice(0, 200));
  check("postseason clinch cards rendered",
    window.document.querySelectorAll("#postseasonClinched .srccard").length === 3,
    `found ${window.document.querySelectorAll("#postseasonClinched .srccard").length}`);
  check("postseason round table has all four rounds",
    window.document.querySelectorAll("#postseasonRounds tr").length === 4,
    `found ${window.document.querySelectorAll("#postseasonRounds tr").length}`);
  check("postseason round table admits times are unpublished", /Not published/.test(text("postseasonRounds")));
  check("postseason lists reserved dates", /dates are reserved for a game/.test(text("postseasonDates")), text("postseasonDates").slice(0, 120));
  check("postseason names the travel days", /No game is possible on/.test(text("postseasonDates")));
  check("postseason says what would resolve the TBDs", /What would resolve it/.test(text("postseasonUnresolved")));

  // ---- MLB season explorer: real committed fixture files, async load ----
  tab("mlb").dispatchEvent(new window.Event("click", { bubbles: true }));
  check("mlb tab activates", $("tab-mlb").classList.contains("active"));
  const bundledSeasons = (window.SCHEDULE_DATA.mlb_seasons) || {};
  const available = Object.keys(bundledSeasons).filter((y) => bundledSeasons[y].available);
  if (!available.length) {
    check("mlb explorer admits no season file is bundled", /not bundled|No complete season fixture file/.test(text("mlbRows") + text("mlbSeasonMeta")),
      text("mlbSeasonMeta").slice(0, 160));
    return finish();
  }
  waitFor(() => window.document.querySelectorAll("#mlbRows tr").length > 0, 4000)
    .then(() => {
      check("mlb explorer renders fixture rows", true);
      check("mlb explorer reports the fixture count", /matching fixtures/.test(text("mlbCount")), text("mlbCount"));
      check("mlb explorer offers all 30 clubs", window.document.querySelectorAll("#mlbClub option").length === 31,
        `found ${window.document.querySelectorAll("#mlbClub option").length}`);
      check("mlb explorer explains provenance", /official fixtures/.test(text("mlbSeasonMeta")), text("mlbSeasonMeta").slice(0, 160));
      check("mlb explorer names the regular-season quiet dates", /no game at all on/.test(text("mlbSeasonMeta")),
        text("mlbSeasonMeta").slice(0, 200));
      check("mlb explorer rows carry the league game id", /\d{6}/.test(text("mlbRows")), text("mlbRows").slice(0, 120));
      // The Giants/A's filter must still work against the real file.
      $("mlbHighOnly").checked = true;
      $("mlbHighOnly").dispatchEvent(new window.Event("change", { bubbles: true }));
      return waitFor(() => /matching fixtures/.test(text("mlbCount")) && !/loading/.test(text("mlbCount")), 2000);
    })
    .then(() => {
      check("mlb explorer filters to the two high-priority clubs", /of \d+ matching fixtures/.test(text("mlbCount")), text("mlbCount"));
      check("high-priority filter keeps only Giants/A's rows", !/Dodgers at Padres/.test(text("mlbRows")), text("mlbRows").slice(0, 120));
    })
    .catch((err) => check("mlb explorer loaded its season file", false, String(err)))
    // The day note is rewritten asynchronously after each date change, so assert it
    // once the current fetch has settled instead of racing it.
    .then(() => waitFor(() => /Live MLB fetch (failed|unavailable)|works offline/.test(text("mlbNote")), 3000)
      .catch(() => null))
    .then(() => {
      check("offline MLB fetch is disclosed",
        /Live MLB fetch (failed|unavailable)|works offline/.test(text("mlbNote")), text("mlbNote"));
      check("a blocked live feed falls back to the committed season snapshot",
        /Live MLB fetch unavailable/.test(text("mlbNote"))
          ? /committed official season snapshot/.test(text("mlbNote"))
          : true, text("mlbNote"));
    })
    .then(() => finish());
}, 300);

function finish() {
  if (finish.done) return;
  finish.done = true;
  console.log(ok.map((s) => "  PASS " + s).join("\n"));
  if (failures.length) {
    console.log(failures.map((s) => "  FAIL " + s).join("\n"));
    console.log(`\n${ok.length} passed, ${failures.length} FAILED`);
    process.exit(1);
  }
  console.log(`\n${ok.length} passed, 0 failed`);
}
