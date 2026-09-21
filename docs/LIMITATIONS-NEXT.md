# Next session: outstanding requirements and limitations

The site and three comparisons are implemented. **The exhaustive verified
Bay Area AM/FM inventory requested is not complete.** Do not describe this
project as a fully audited schedule of every broadcast or guarantee a quiet trip.

Session 2026-09-21: GitHub Pages planner remains the published artifact (`site/`).
Compare-table week pills were de-duplicated. MLB Stats API still fails TLS from
this sandbox (`SSL_ERROR_SYSCALL`); do not invent fixture rows. Merge to `main`
is required for Pages deploy. Remaining work is data completeness, not UI shell.

## Highest priority

1. **Verify the published full MLB refresh.** The sandbox cannot directly retrieve
   the complete API response (TLS connection failure). The Pages workflow attempts
   it automatically and exposes status. Check the resulting all-club artifact and
   record source hashes/response timestamps. The checked-in snapshot is partial.
2. **Local carriage per game.** Join Westwood One national listings to dated
   KNBR/KTCT/other local station grids. Affiliation alone is insufficient; blackouts
   and Giants/49ers scheduling conflicts can displace feeds. Store separate
   `national_feed`, `local_station`, `carriage_status`, and evidence timestamp.
3. **Complete Stanford/Cal and Earthquakes fixtures.** Refresh kickoff TBDs, full
   MLS fixtures and conditional postseason/bowl slots. Cup and friendly fixtures
   are not comprehensively covered. Never infer a full quiet day from a missing row.
4. **Other local sports, high priority.** Research Warriors and college basketball,
   and determine whether any Sharks coverage is actually over analog AM/FM rather
   than streaming only. Westwood One NCAA basketball, golf, soccer and other sports
   also need local carriage evidence. Keep Sections 1–3 unchanged; add these to a
   clearly named wider radio profile when verified. Current `all` is not exhaustive.
5. **NFL full archive and reconciliation.** The reference has 272 regular-season
   rows, not every team's preseason game. Re-fetch the official release, reconcile
   every matchup/date/time against the inherited CSV, add preseason and per-game
   postseason fixtures, and track flex changes and any Pro Bowl radio assignment.
6. **MLB postseason.** Boston's clinched berth was added from the reviewed playoff
   picture. Matchups/times stay TBD until the official fixture feed sets them.
   Clinching does not establish an opponent, home field or start time. Retire
   obsolete conditional games once series end; preserve rainout/resumption history.

## Planning precision

- Replace continuous season envelopes with complete per-day fixture coverage when
  available. The current model can miss real weeks off; “none found” is not “impossible.”
- Refresh future MLB/NFL releases and MLS's 2027 transition fixtures. MLB 2028/2029
  individual season API queries returned empty in this review. Treat candidate
  endpoints as estimates, not exact bookable boundaries.
- Reconfirm the **exact** Super Bowl LXIII date separately. The reviewed NFL
  announcement verifies Las Vegas/2029 only. February 11 is a model assumption.
- Research official measured duration distributions rather than single secondary
  averages. Add automatic broadcast pre/postgame allowances and uncertainty bands;
  overnight overtime can spill beyond a TBD date's midnight hold.
- Reception is site/equipment dependent; signal contours do not establish indoor
  reception in the Outer Sunset. Do not count HD-only or internet-only feeds as
  ordinary analog AM/FM coverage.

## Engineering and operations

- Add automated source adapters with captured responses, hashes, timestamps and
  schema validation for all leagues and station grids, not just MLB.
- Add end-to-end Chrome/mobile/accessibility tests in CI. Real browser installation
  failed in this sandbox; current checks are jsdom, interval/parity tests and HTTP.
- Pages refresh failure currently publishes the available checked-in fallback, not
  the previous deployment's live snapshot. Consider durable last-good snapshots
  outside Git, with maximum staleness policies.
- Add a first-class unknown-coverage interval type per league; currently uncertainty
  is disclosed globally and TBD dates are reserved, but absent non-MLB data does
  not have a comprehensive per-minute coverage map.
- Extend the trip finder across December/January boundaries and support filtered
  future-only results without hiding historical comparison rows.

No manual game entry is required by the current UI. These are development/data
verification tasks, not requests for the user to reconstruct the schedule.
