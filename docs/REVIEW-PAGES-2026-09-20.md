# Three-pass Pages implementation review

Local review date: **2026-09-20 (America/Los_Angeles)**.

This is an implementation/data-honesty audit, not a claim that every inherited
fixture was independently reverified against its publisher. Source-by-source
boundaries and retrieval failures are in [SOURCES.md](SOURCES.md).

## Pass 1 — implementation

- Reviewed existing app, builder, interval engine, tests, verified inputs and docs.
  All three requested section definitions already existed; retained them rather
  than making duplicate pages.
- Built a cleaner responsive trip-planning UI, compact navigation, expandable
  calculation audit, confidence banner, historical-window labels and source links.
- Added a monthly calendar with previous/next month, day selection, leap dates,
  date bounds, and explicit conflict/unknown markers. All times use Pacific Time.
- Added the source-checked list of all 30 MLB clubs, Giants/Athletics priorities.
- Added GitHub Actions tests and static `site/` Pages deployment, daily atomic
  all-club MLB refresh, and a visible refresh-health record.
- Kept three-way comparison, 7/14/21-day checks, NFL regular-season reference,
  station inventory, review queue, and no-manual-game-entry workflow.

## Pass 2 — bugs and data assumptions

- TBD/null kickoff now reserves a full local date, including 23/25-hour DST days.
  The old 15:00 MLB envelope left mornings and the final minute falsely free.
- Fixed duplicate Python timezone helper and JS midnight-hour normalization.
- Corrected 2027 Opening Night: March 24 is busy, giving a 37-day regular-only
  candidate ending March 23, not the old 38-day result.
- Replaced obsolete MLS future calendar with official summer–spring format and
  explicitly estimated boundary envelopes; conditional CFP no longer ends January 11.
- Downgraded exact 2029 Super Bowl date: reviewed NFL source specifies host/year only.
- Corrected Westwood One Sep 21 air time from 8 PM to 7 PM ET; match official NFL
  kickoffs where available so pregame airtime does not cause premature free time.
  Unresolved kickoff gets a disclosed planning allowance, not an invented kickoff.
- Fixed A's live-fetch radio attribution to KNEW instead of KNBR; source-checked
  Boston clinch added without inventing postseason assignments.
- Replaced misleading “on air” on every fixture with scheduled/unresolved labels.
- Fixed source coverage bug: postseason retrieval date must not mark missing
  September 20–27 regular-season data complete.
- Daily MLB fetch handles neighboring official dates, PT conversion, cancelled
  rows, replacement of aggregate placeholders, timeout, and out-of-order responses.
- Replaced full-day-free guarantees with “no known conflict”; reception is unmeasured.

## Pass 3 — whole-request / reliability review

- Rechecked all section definitions, priorities, source links, calendar controls,
  trip lengths, future estimates, and current source evidence against the request.
- Removed broken source anchors that treated `NOT RELEASED` prose as a URL; escaped
  source card labels. Kept estimate rationale visible without fabricating links.
- Removed blanket “fully verified” and current-season verified-average claims.
- Rewrote README, source register, method, generated window report and next-session
  backlog so published guidance matches the corrected model.
- Added regression tests for new behavior, atomic refresh rejection, all-club
  display, bounded/leap-day calendar, network races and Pages artifact location.
- Verified the preview responds **HTTP 200**, uses relative assets, and binds to
  `0.0.0.0`. Pages workflow publishes the actual site directory rather than the
  repository-root README.

## Final local validation

- `npm run build`: passes.
- `npm test`: **52 rendering checks + 19 publication/regression checks pass**.
- `python3 -m unittest discover -s tests`: **90 tests pass**, including real
  JS/Python parity across bundled dates and sections.
- `git diff --check`: passes.
- Preview HTTP smoke check: passes.

## Deployment permissions

Changing the repository Pages build-source setting through the connected integration
returned HTTP 403 (resource not accessible by integration). Added a root entry page
and `.nojekyll` so the existing legacy `main`/root Pages configuration can still serve
the app at `site/`. The Actions artifact deployment remains configured; its remote
result must be checked separately. No credentials requested.

## Environmental and requirement limits

- Full MLB download failed TLS setup in this sandbox. The Pages job attempts the
  real feed and records its result; no fabricated full-season file was checked in.
- Chromium installation failed because its download host was unreachable. No claim
  of screenshot/pixel-level or real mobile-browser validation; tests used jsdom.
- Exhaustive AM/FM carriage, every NFL preseason fixture, complete MLS/college
  fixtures, additional local sports, and independent line-by-line reconciliation
  of every inherited source row remain incomplete. These are explicit next-session
  tasks, not silently assumed covered.
- Continuous season envelopes can hide real gaps. Negative results are “none found,”
  never proof that a quiet vacation is impossible.

PR, merge and deployment results are reported in the task's final response after
checking GitHub; local tests alone do not prove a successful remote deployment.
