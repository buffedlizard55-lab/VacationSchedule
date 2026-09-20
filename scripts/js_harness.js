// Node harness: runs the SAME site/app.js the browser runs and dumps day reports
// so tests/test_parity_js.py can diff them against the Python engine.
//
// Usage: node scripts/js_harness.js 2026-09-20 2026-11-01 ...
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const bundlePath = path.join(root, "site", "data", "schedule-data.js");

const sandbox = { window: {}, document: { addEventListener: function () {}, readyState: "loading" }, console: console };
const listeners = [];
sandbox.window.addEventListener = function (evt, fn) { if (evt === "DOMContentLoaded") listeners.push(fn); };

// Load the bundle: it does `window.SCHEDULE_DATA = {...}`
new Function("window", "document", fs.readFileSync(bundlePath, "utf8"))(sandbox.window, sandbox.document);
// Load the app: it defines the engine and attaches it to window.FreeTimeEngine
new Function("window", "document", "console", "fetch", "Intl", "Date", fs.readFileSync(path.join(root, "site", "app.js"), "utf8"))(
  sandbox.window, sandbox.document, console, function () { throw new Error("no network in harness"); }, Intl, Date
);

const engine = sandbox.window.FreeTimeEngine;
if (!engine) { console.error("engine not exposed"); process.exit(1); }

const dates = process.argv.slice(2);
const out = {};
dates.forEach((d) => {
  const rep = engine.dayReport(d);
  out[d] = {
    date: rep.date,
    data_coverage: rep.dataCoverage,
    day_minutes: rep.dayMinutes,
    busy_minutes: rep.busyMinutes,
    free_minutes: rep.freeMinutes,
    is_free_day: rep.isFreeDay,
    has_high_priority: rep.hasHighPriority,
    has_unconfirmed_times: rep.hasUnconfirmed,
    unconfirmed_minutes: rep.unconfirmedMinutes,
    longest_free_minutes: rep.longest ? Math.round(((rep.longest.end - rep.longest.start) / 60000) * 10) / 10 : 0,
    longest_free_start_pt: rep.longest ? new Date(rep.longest.start).toISOString().slice(0, 19) : "",
    free_windows_pt: rep.freeWindows.map((w) => [
      new Date(w.start).toISOString().slice(0, 19),
      new Date(w.end).toISOString().slice(0, 19),
    ]),
    busy_windows_pt: rep.busy.map((b) => [
      new Date(b.start).toISOString().slice(0, 19),
      new Date(b.end).toISOString().slice(0, 19),
    ]),
  };
});
console.log(JSON.stringify(out));
