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

// Stub fetch so the live MLB call takes its offline path instead of hanging.
window.fetch = function () { return Promise.reject(new Error("offline in test")); };

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
  check("verdict banner rendered", /FREE|BUSY/.test(text("verdict")), text("verdict"));
  check("generation stamp rendered", /Bundle generated/.test(text("genStamp")), text("genStamp"));
  check("no uncaught JS errors", errors.length === 0, errors.join(" | "));

  // ---- scoreboard actually populated ----
  const games = window.document.querySelectorAll("#scoreboard .game");
  check("scoreboard has game rows", games.length > 0, `found ${games.length}`);
  check("scoreboard has league groups", window.document.querySelectorAll("#scoreboard .leaguegroup").length > 0);

  // ---- free windows rendered ----
  const wins = window.document.querySelectorAll("#freeList .freewin");
  check("free windows rendered", wins.length > 0 || /No free time/.test(text("freeList")));

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
  check("2026-10-02 (postseason travel day) IS free", /FULLY FREE/.test(text("verdict")), text("verdict"));
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
  check("2026 row marked VERIFIED", /VERIFIED/.test($("vacationBody").textContent));
  check("2027 row marked MLB VERIFIED (partial)", /MLB VERIFIED/.test($("vacationBody").textContent));
  check("2028-29 rows marked ESTIMATED",
    ($("vacationBody").textContent.match(/ESTIMATED/g) || []).length === 2);

  // ---- vacation table reports the 1/2/3-week requirements ----
  check("vacation table reports 1-week / 2-week / 3-week columns",
    /1 week/.test($("tab-vacation").textContent) && /2 weeks/.test($("tab-vacation").textContent) && /3 weeks/.test($("tab-vacation").textContent));
  check("strict section 3 cannot reach two weeks", /no/.test($("vacationBody").textContent));

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
  check("offline MLB fetch is disclosed", /Live MLB fetch failed|works offline/.test(text("mlbNote")), text("mlbNote"));

  console.log(ok.map((s) => "  PASS " + s).join("\n"));
  if (failures.length) {
    console.log(failures.map((s) => "  FAIL " + s).join("\n"));
    console.log(`\n${ok.length} passed, ${failures.length} FAILED`);
    process.exit(1);
  }
  console.log(`\n${ok.length} passed, 0 failed`);
}, 300);
