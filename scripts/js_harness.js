// Node harness: runs the SAME site/app.js the browser runs and dumps day reports
// so tests/test_parity_js.py can diff them against the Python engine.
//
// Usage: node scripts/js_harness.js [--scope 1|2|3|all] [--frames 0|1] [--variants all:0,all:1,1:1] 2026-09-20 ...
//
//   --scope   report only games belonging to that coverage section (default: all)
//   --frames  1 = apply the MLB season-frame fallback (mirrors day_report(mlb_frames=...)),
//             0 = no fallback (mirrors the Python default). Default 0.
//   --variants batch several scope/frame pairs in one Node process. Each pair is
//              written as scope:frames and the JSON output is keyed by that pair.
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const bundlePath = path.join(root, "site", "data", "schedule-data.js");

const argv = process.argv.slice(2);
const opts = { scope: "all", frames: false, variants: null };
const dates = [];
for (let i = 0; i < argv.length; i++) {
  if (argv[i] === "--scope") { opts.scope = argv[++i]; }
  else if (argv[i] === "--frames") { opts.frames = argv[++i] === "1"; }
  else if (argv[i] === "--variants") {
    opts.variants = argv[++i].split(",").map((raw) => {
      const bits = raw.split(":");
      if (bits.length !== 2 || !bits[0] || !/^[01]$/.test(bits[1])) {
        throw new Error("bad --variants entry: " + raw + " (expected scope:0 or scope:1)");
      }
      return { key: raw, scope: bits[0], frames: bits[1] === "1" };
    });
  } else dates.push(argv[i]);
}

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

function serialise(rep) {
  return {
    date: rep.date,
    scope: rep.scope,
    day_minutes: rep.dayMinutes,
    busy_minutes: rep.busyMinutes,
    free_minutes: rep.freeMinutes,
    is_free_day: rep.isFreeDay,
    has_high_priority: rep.hasHighPriority,
    has_conditional: !!rep.hasConditional,
    has_unconfirmed_times: rep.hasUnconfirmed,
    unconfirmed_minutes: rep.unconfirmedMinutes,
    mlb_frame_fallback: rep.mlbFrameFallback,
    outside_scope_count: rep.outside.length,
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
}

const variants = opts.variants || [{ key: "default", scope: opts.scope, frames: opts.frames }];
const reports = {};
variants.forEach((variant) => {
  reports[variant.key] = {};
  dates.forEach((d) => {
    reports[variant.key][d] = serialise(engine.dayReport(d, [], variant.scope, variant.frames));
  });
});
// Keep the original flat output for one-variant callers; --variants returns a
// map and lets parity tests pay Node's startup cost only once.
console.log(JSON.stringify(opts.variants ? reports : reports.default));
