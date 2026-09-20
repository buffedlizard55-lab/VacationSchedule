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
  $("dateInput").value = "2026-11-03";
  $("dateInput").dispatchEvent(new window.Event("change", { bubbles: true }));
  check("2026-11-03 (in-coverage, no games) IS free", /FULLY FREE/.test(text("verdict")), text("verdict"));

  // ---- dates outside coverage must read NO DATA, never FREE ----
  $("dateInput").value = "2027-06-15";
  $("dateInput").dispatchEvent(new window.Event("change", { bubbles: true }));
  const nd = text("verdict");
  check("out-of-coverage date says NO DATA", /NO DATA/.test(nd), nd);
  check("out-of-coverage date does not say FREE", !/FULLY FREE/.test(nd), nd);

  // ---- navigation moves the date and clamps to coverage ----
  $("dateInput").value = "2026-11-03";
  $("dateInput").dispatchEvent(new window.Event("change", { bubbles: true }));
  const before = $("dateInput").value;
  $("nextDay").dispatchEvent(new window.Event("click", { bubbles: true }));
  check("next-day button advances the date", $("dateInput").value === "2026-11-04", `${before} -> ${$("dateInput").value}`);
  $("prevDay").dispatchEvent(new window.Event("click", { bubbles: true }));
  check("prev-day button rewinds the date", $("dateInput").value === "2026-11-03", $("dateInput").value);
  // Walking off either edge of the dataset must surface NO DATA, not FREE.
  const sorted = window.SCHEDULE_DATA.games.map(g => g.date_local).filter(Boolean).sort();
  const first = sorted[0], last = sorted[sorted.length - 1];
  $("dateInput").value = first;
  $("dateInput").dispatchEvent(new window.Event("change", { bubbles: true }));
  $("prevDay").dispatchEvent(new window.Event("click", { bubbles: true }));
  check("prev past the coverage start shows NO DATA", /NO DATA/.test(text("verdict")), $("dateInput").value + " :: " + text("verdict"));
  $("dateInput").value = last;
  $("dateInput").dispatchEvent(new window.Event("change", { bubbles: true }));
  $("nextDay").dispatchEvent(new window.Event("click", { bubbles: true }));
  check("next past the coverage end shows NO DATA", /NO DATA/.test(text("verdict")), $("dateInput").value + " :: " + text("verdict"));

  // ---- vacation tab ----
  tab("vacation").dispatchEvent(new window.Event("click", { bubbles: true }));
  check("vacation tab activates", $("tab-vacation").classList.contains("active"));
  const rows = window.document.querySelectorAll("#vacationBody tr");
  check("vacation table has 4 year rows", rows.length === 4, `found ${rows.length}`);
  check("2026 row marked VERIFIED", /VERIFIED/.test($("vacationBody").textContent));
  check("2027-29 rows marked ESTIMATED",
    ($("vacationBody").textContent.match(/ESTIMATED/g) || []).length === 3);

  // ---- interpretation toggle recomputes ----
  const strictText = $("vacationBody").textContent;
  const regular = window.document.querySelector('input[name="interp"][value="regular"]');
  regular.checked = true;
  regular.dispatchEvent(new window.Event("change", { bubbles: true }));
  check("interpretation toggle changes the table", $("vacationBody").textContent !== strictText);
  check("regular interpretation shows 44 days for 2026", /44 days/.test($("vacationBody").textContent));

  // ---- review + sources tabs ----
  tab("review").dispatchEvent(new window.Event("click", { bubbles: true }));
  check("review count matches the bundle", text("reviewCount") === String(window.SCHEDULE_DATA.unresolved.length), text("reviewCount"));
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
