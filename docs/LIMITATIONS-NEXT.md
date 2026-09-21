# Next session: outstanding requirements and limitations

The site, the three-section comparison, the 2026–2029 vacation analysis, the
daily scoreboard and the wider live-radio scope are implemented and merged to
`main`. **The exhaustive verified Bay Area AM/FM inventory is still not
complete.** Do not describe this project as a fully audited schedule of every
broadcast or guarantee a quiet trip.

Session 2026-09-21 (this document's pass): Westwood One rows re-verified line by
line against the live page; MLB clinch facts corrected (IR-32); Super Bowl LXIII
promoted to VERIFIED everywhere consistently (IR-34); Warriors NBA + Valkyries
WNBA added as high-priority live-radio sports with per-game 95.7 flags; Sharks
verified streaming-only and excluded with sources; MLB/MLB-API year frames
re-checked (IR-33). Merge to `main` publishes the Pages artifact.

Session 2 (2026-09-21, later pass): WWO row-count meta corrected (71 rows, not
70) with a line-by-line re-verification against all four live page chunks; 49ers
per-game radio stations transcribed from 49ers.com (Weeks 2-3 on KSFO 810 AM /
KSAN 107.7 FM; Week 4 onward on KSAN 107.7 FM / KNBR 104.5 FM / 680 AM; none
listed for the Melbourne opener) and propagated through the builder with a
regression test; Athletics home venue confirmed as Sutter Health Park
(Sacramento) via the Stats API, consistent with the KSTE/KNEW note; 2026/2027
MLB frames, the 53-record 2026 postseason API state (still all 07:33Z sentinel,
`startTimeTBD=true` — no times published) and the six-clinch tracker state
re-verified live; a permanent "Spring Training included vs excluded" side-by-side
table added to the All windows tab; five new regression tests. See
REVIEW-2026-09-21.md (Session 2 section) and SOURCES.md (session 2 table).

## Highest priority for the next session

1. **MLB postseason times, from 2026-09-27.** Dates are official and stored;
   first-pitch times do not exist yet. When MLB sets Wild Card times (expected
   after the field locks on the final Sunday), fetch them, replace the TBD
   envelope rows, and re-run the day board for Sept 29–Oct 1. Then repeat round
   by round (DS, LCS, WS). Record source URLs and timestamps. Retire obsolete
   conditional rows as series end (rainout/resumption history preserved).
2. **Valkyries playoffs.** First-round reserved dates (Sept 27 + two windows)
   are in the engine with time/opponent TBD. Update as the WNBA publishes:
   tip times, opponents, whether 95.7 carries each game, and the
   semifinal/final windows (currently one unresolved flag). Reconcile the IR-35
   September date/record discrepancy with a game log source.
3. **Warriors grid reconciliation (IR-37).** The transcribed CBS grid has 6
   preseason + 80 regular-season rows (nominally 82). Find the missing rows
   against an NBA-owned feed when sandbox TLS allows (the Pages workflow's
   runner can fetch statsapi-style endpoints where this sandbox cannot), flip
   `schedule_status` to league-verified, and confirm per-game 95.7 carriage
   against the station's own schedule where possible.
4. **Local carriage per game.** Join Westwood One national listings to dated
   KNBR/KTCT grids; store `national_feed`, `local_station`, `carriage_status`,
   evidence timestamp. Affiliation alone is insufficient: blackouts and
   conflicts displace feeds (the Station Finder says so explicitly).
5. **Complete Stanford/Cal and Earthquakes fixtures.** Refresh kickoff TBDs, the
   2027 MLS transition-season fixtures as they release, and conditional bowl/CFP
   slots. Never infer a free day from a missing row.
6. **Remaining wider-scope gaps** (`data/verified/other_radio_sports.json`
   `unresolved_coverage`): USF men's basketball on KNBR (2026-27 schedule when
   published), Westwood One NCAA basketball event grid + local carriage,
   Stanford/Cal/USF basketball radio evidence. Add each as a clearly tagged
   wider-scope league when verified. Keep Sections 1–3 unchanged.
7. **NFL full archive and reconciliation.** The reference has 272 regular-season
   rows, not every team's preseason. Re-fetch the official release each season,
   track flex changes and any Pro Bowl radio assignment, and keep Week 18's
   date/kickoff fields honest until the league sets them.

## Planning precision

- Replace continuous season envelopes with complete per-day fixture coverage
  where possible. The envelopes (including the new NBA/WNBA ones) deliberately
  over-block rest days; "none found" in the `all` scope is a model statement,
  not proof that no week is gameless. This matters most for the superset row
  (IR-38).
- Reconfirm MLB 2028/2029 and NFL 2027–2029 the moment each league publishes;
  every future row is labelled ESTIMATED until then. The 2027 MLB frame is
  contingent on a new CBA (the old one expires 2026-12-01) — re-check after any
  agreement or lockout (IR-19).
- Research official measured duration distributions rather than single
  secondary averages; add broadcast pre/postgame allowances and uncertainty
  bands. NBA 150 / WNBA 120 are planning numbers like the rest.
- Reception is site/equipment dependent; no field strength at 94122 has been
  measured. Do not count HD-only or internet-only feeds as analog AM/FM.

## Engineering and operations

- Automated source adapters with captured responses, hashes, timestamps and
  schema validation for every league and station grid, not just the MLB refresh.
  The sandbox blocks TLS to statsapi.mlb.com/site.api.espn.com; run retrievals in
  the Pages workflow or another network-capable runner and commit normalized
  snapshots only.
- End-to-end Chrome/mobile/accessibility tests in CI (still jsdom-only here).
- Pages refresh failure currently publishes the checked-in fallback rather than
  the previous deployment's live snapshot; consider durable last-good snapshots
  with staleness limits.
- A first-class unknown-coverage interval type per league (uncertainty is today
  global disclosure + TBD reservation, not a per-minute coverage map).
- Extend the trip finder across December/January boundaries and support
  future-only filtering without hiding historical comparison rows.

No manual game entry is required by the current UI. These are development/data
verification tasks, not requests for the user to reconstruct the schedule.
