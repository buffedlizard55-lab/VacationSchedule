"""Core free-time engine for VacationSchedule.

Everything here is pure, deterministic and dependency-free (stdlib only) so the
same rules can be unit-tested and reused by both the analysis scripts and the
browser app (which mirrors this logic in site/app.js).

Key concepts
------------
blocking interval
    A half-open interval [start, end) of wall-clock time in America/Los_Angeles
    during which a live over-the-air radio broadcast of a game is presumed to be
    running.  A day is "free" only outside the union of all blocking intervals.

game record
    A dict with at least:
        league   : 'MLB' | 'NFL' | 'NCAAF' | 'MLS'
        start_utc: ISO-8601 UTC instant of the scheduled start
                 (kickoff / first pitch).  `None` means the time is not yet
                 officially set -- the caller must pass `placeholder=True`.
        duration : minutes, taken from VERIFIED league averages (see docs/
                   METHODOLOGY.md).  Never invented per game.
        priority : 'high' for the user's flagged Bay Area teams, else 'normal'
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Constants -- single source of truth.  See docs/METHODOLOGY.md for citations.
# ---------------------------------------------------------------------------

USER_TZ = ZoneInfo("America/Los_Angeles")

#: Verified average game durations, in minutes.
#:   MLB   164 = 2:44  (2026 season average, BetMGM/MLB pace-of-play reporting)
#:   NFL   192 = 3:12  (widely reported NFL average, 12-minute halftime)
#:   NCAAF 204 = 3:24  (NCAA FBS average, 20-minute halftime)
#:   MLS   120 = 2:00  (90 min regulation + stoppage + 15 min halftime)
DEFAULT_DURATIONS = {
    "MLB": 164,
    "NFL": 192,
    "NCAAF": 204,
    "MLS": 120,
}

#: MLB Stats API sentinel timestamp used for games whose start time has not been
#: officially announced.  Every un-announced 2026 postseason game is served as
#: 07:33:00Z, which is 03:33 EDT -- an impossible first pitch.  We treat any
#: start at exactly this instant as "time not yet set".
MLB_TBD_SENTINEL_UTC = "07:33:00"

#: Placeholder team ids MLB uses for undecided postseason participants.
#: Ids >= 4000 are MLB's "TBD/placeholder" club ids (real clubs are 108-158).
MLB_PLACEHOLDER_ID_FLOOR = 4000

#: Extra minutes added to the tail of every broadcast window to cover
#: post-game / overtime risk.  Kept explicit rather than baked into durations.
DEFAULT_OVERRUN_BUFFER_MIN = 0


class ValidationError(ValueError):
    """Raised when a game record cannot be turned into a blocking interval."""


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def parse_utc(value: str) -> datetime:
    """Parse an ISO-8601 timestamp into an aware UTC datetime."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValidationError(f"timestamp without timezone: {value!r}")
    return parsed.astimezone(timezone.utc)


def to_user_tz(moment: datetime) -> datetime:
    """Convert an aware datetime to the user's wall-clock timezone."""
    return moment.astimezone(USER_TZ)


def is_tbd_utc(value: str) -> bool:
    """True when a statsapi `gameDate` is the un-announced-time sentinel."""
    return parse_utc(value).strftime("%H:%M:%S") == MLB_TBD_SENTINEL_UTC


def local_wall_clock(date_iso: str, hhmm: str = "00:00") -> datetime:
    """A wall-clock time in the user's timezone as a *UTC-normalized* datetime.

    Every instant the engine works with is stored in UTC on purpose. Python's
    documented rule is that when two aware datetimes share the same `tzinfo`
    object, subtraction AND ordering ignore the UTC offset and fall back to
    naive wall-clock semantics. Two midnights either side of a DST transition
    therefore subtract to exactly 24h even though the real day is 23h or 25h.
    Normalizing to UTC up front makes that class of bug impossible: all
    arithmetic and comparisons then happen on a single fixed offset.
    """
    naive = datetime.strptime(f"{date_iso}T{hhmm}:00", "%Y-%m-%dT%H:%M:%S")
    # fold=0 picks the first occurrence of an ambiguous fallback wall-clock time.
    return naive.replace(tzinfo=USER_TZ, fold=0).astimezone(timezone.utc)


def local_day_bounds(date_iso: str) -> tuple[datetime, datetime]:
    """Return [midnight, next midnight) for a local date, as UTC-normalized.

    A DST day is 23 or 25 hours long; `span_minutes` reports that correctly.
    """
    start = local_wall_clock(date_iso)
    nxt = (start.astimezone(USER_TZ) + timedelta(days=1)).date().isoformat()
    return start, local_wall_clock(nxt)


def span_minutes(start: datetime, end: datetime) -> float:
    """Elapsed minutes between two instants, DST-safe.

    Always routes through UTC so a shared `tzinfo` can never cause the
    wall-clock shortcut described in `local_wall_clock`.
    """
    return (
        end.astimezone(timezone.utc) - start.astimezone(timezone.utc)
    ).total_seconds() / 60.0


# ---------------------------------------------------------------------------
# Intervals
# ---------------------------------------------------------------------------


class Interval:
    """A half-open [start, end) interval of aware datetimes."""

    __slots__ = ("start", "end", "label", "priority", "league", "source", "time_confirmed")

    def __init__(
        self,
        start: datetime,
        end: datetime,
        label: str = "",
        priority: str = "normal",
        league: str = "",
        source: str = "",
    ) -> None:
        # Normalize to UTC immediately: see local_wall_clock() for why.
        self.start = start.astimezone(timezone.utc)
        self.end = end.astimezone(timezone.utc)
        if self.end <= self.start:
            raise ValidationError(f"empty/negative interval for {label!r}")
        self.label = label
        self.priority = priority
        self.league = league
        self.source = source
        #: False when the date is official but no start time has been published,
        #: so the interval is a conservative envelope rather than a real window.
        self.time_confirmed = True

    @property
    def minutes(self) -> float:
        return span_minutes(self.start, self.end)

    def as_dict(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "start_pt": _fmt_pt(self.start),
            "end_pt": _fmt_pt(self.end),
            "label": self.label,
            "priority": self.priority,
            "league": self.league,
            "source": self.source,
            "time_confirmed": self.time_confirmed,
        }

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"Interval({_fmt_pt(self.start)}-{_fmt_pt(self.end)}, {self.label!r})"


def _fmt_pt(moment: datetime) -> str:
    local = moment.astimezone(USER_TZ)
    return local.strftime("%Y-%m-%d %H:%M %Z")


def clip(iv: Interval, day_start: datetime, day_end: datetime) -> Interval | None:
    """Trim an interval to [day_start, day_end), or None if it does not overlap.

    Clipping matters for correctness of the day totals: a game that starts at
    10:00 PM and runs to 12:44 AM contributes 120 minutes to the first date and
    only 44 to the second.  Without clipping, `busy_minutes` double-counts the
    full duration on both dates and `free_minutes` is understated.
    """
    if iv.start >= day_end or iv.end <= day_start:
        return None
    out = Interval(
        max(iv.start, day_start),
        min(iv.end, day_end),
        iv.label,
        iv.priority,
        iv.league,
        iv.source,
    )
    out.time_confirmed = iv.time_confirmed
    return out


def merge(intervals: Sequence[Interval]) -> list[Interval]:
    """Merge overlapping/adjacent intervals.

    Merging loses per-game labels, so callers that need labels should keep the
    un-merged list too.  Priority is preserved by promoting to 'high' when any
    merged member is high priority.
    """
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda iv: (iv.start, iv.end))
    out: list[Interval] = []
    for current in ordered:
        if out and current.start <= out[-1].end:
            last = out[-1]
            last.end = max(last.end, current.end)
            if current.priority == "high":
                last.priority = "high"
            if not current.time_confirmed:
                last.time_confirmed = False
            if last.label and current.label and current.label not in last.label:
                last.label = f"{last.label} + {current.label}"
            elif not last.label:
                last.label = current.label
        else:
            fresh = Interval(
                current.start,
                current.end,
                current.label,
                current.priority,
                current.league,
                current.source,
            )
            fresh.time_confirmed = current.time_confirmed
            out.append(fresh)
    return out


def free_windows(
    day_start: datetime, day_end: datetime, busy: Sequence[Interval]
) -> list[Interval]:
    """Complement of `busy` inside [day_start, day_end).

    Only the portion of each busy interval that actually falls inside the day is
    subtracted, so games that spill past midnight are handled correctly.
    """
    merged = merge(
        [c for c in (clip(iv, day_start, day_end) for iv in busy) if c is not None]
    )
    windows: list[Interval] = []
    cursor = day_start
    for iv in merged:
        if iv.start > cursor:
            windows.append(Interval(cursor, iv.start, "FREE", "free"))
        cursor = max(cursor, iv.end)
    if cursor < day_end:
        windows.append(Interval(cursor, day_end, "FREE", "free"))
    return windows


def longest_free_window(windows: Sequence[Interval]) -> Interval | None:
    if not windows:
        return None
    return max(windows, key=lambda iv: iv.minutes)


# ---------------------------------------------------------------------------
# Game -> Interval
# ---------------------------------------------------------------------------


#: Window blocked for a game whose DATE is verified but whose start time has not
#: been announced.  Conservative on purpose: it is far better to hide a real
#: free window than to advertise one that turns out to have a game on the radio.
TBD_ENVELOPE_PT = {"NCAAF": ("11:00", "23:59"), "MLS": ("16:00", "23:59"), "NFL": ("09:00", "23:59"), "MLB": ("15:00", "23:59")}

#: The All scope: every game the project tracks, regardless of section.
SCOPE_ALL = "all"


# ---------------------------------------------------------------------------
# Coverage sections
# ---------------------------------------------------------------------------
#
# The user asked to compare three definitions of "busy":
#   1  MLB (all 30 clubs) + 49ers (preseason/regular/postseason) + Westwood One national NFL
#   2  Section 1 + Stanford and California college football
#   3  Section 2 + San Jose Earthquakes MLS
#
# Every game record carries a `sections` list, computed at build time from the
# tag vocabulary in data/verified/profiles.json. Filtering by section is then a
# one-line membership test in both engines, which keeps them provably identical.


def game_in_scope(game: dict, scope: str | None = None) -> bool:
    """True when `game` counts as busy under `scope`.

    `None` and `"all"` both mean "no filtering" -- every tracked game counts.
    That is the backwards-compatible default: existing callers keep the old
    behaviour unless they opt in.
    """
    if scope is None or scope == SCOPE_ALL:
        return True
    return scope in (game.get("sections") or [])


def filter_scope(games: Iterable[dict], scope: str | None = None) -> list[dict]:
    return [g for g in games if game_in_scope(g, scope)]


def _envelope_interval(game: dict, date_iso: str, table: dict[str, int]) -> Interval:
    """Build the conservative all-day-ish block for an un-timed but dated game."""
    league = game["league"]
    start_hhmm, end_hhmm = TBD_ENVELOPE_PT[league]
    day = date_iso or parse_utc(game["start_utc"]).astimezone(USER_TZ).date().isoformat()
    return Interval(
        local_wall_clock(day, start_hhmm),
        local_wall_clock(day, end_hhmm),
        f"{game.get('label', league)} (time not announced)",
        game.get("priority", "normal"),
        league,
        game.get("source", ""),
    )


def game_time_is_unconfirmed(game: dict) -> bool:
    """True when the date is known but no official start time has been published."""
    if game.get("time_status") in ("TBD_official_date", "TBD_envelope"):
        return True
    start_raw = game.get("start_utc")
    return bool(start_raw) and game["league"] == "MLB" and is_tbd_utc(start_raw)


def game_to_interval(
    game: dict,
    durations: dict[str, int] | None = None,
    overrun_buffer_min: int = DEFAULT_OVERRUN_BUFFER_MIN,
) -> Interval | None:
    """Build a blocking interval from a game record.

    A game with no known date at all returns None -- there is nothing to place.
    A game with a known date but no announced time returns the conservative
    envelope from `TBD_ENVELOPE_PT`, because reporting that day as free would
    repeat the exact bug this project exists to fix.
    """
    table = durations or DEFAULT_DURATIONS
    league = game["league"]
    start_raw = game.get("start_utc")
    if not start_raw:
        return None

    if game_time_is_unconfirmed(game):
        interval = _envelope_interval(game, game.get("date_local"), table)
        interval.time_confirmed = False
        return interval

    start = parse_utc(start_raw)
    minutes = int(game.get("duration") or table[league])
    end = start + timedelta(minutes=minutes + overrun_buffer_min)

    # Conservative widening: if a radio pre-game air time is known and precedes
    # the official start, block from the earlier of the two.  This matters for
    # Westwood One national NFL feeds (see docs/IRREGULARITIES.md).
    air_raw = game.get("radio_air_utc")
    if air_raw:
        air = parse_utc(air_raw)
        if air < start:
            start = air

    interval = Interval(
        start,
        end,
        game.get("label", ""),
        game.get("priority", "normal"),
        league,
        game.get("source", ""),
    )
    interval.time_confirmed = True
    return interval


def record_is_on_date(game: dict, date_iso: str) -> bool:
    """True when a record's broadcast is *scheduled* on the local date `date_iso`."""
    if game.get("date_local") == date_iso:
        return True
    raw = game.get("start_utc")
    if not raw:
        return False
    try:
        return parse_utc(raw).astimezone(USER_TZ).date().isoformat() == date_iso
    except ValidationError:
        return False


def mlb_frame_for(date_iso: str, frames: dict | None) -> dict | None:
    """The MLB season frame covering `date_iso`, or None.

    `frames` maps a label -> {start, end, status, source, label}. Dates inside a
    frame have MLB games but the bundle does not carry the per-game times; the
    engine therefore blocks the conservative envelope instead of reporting a free
    day. This is deliberately the *safe* failure mode: MLB plays on essentially
    every date inside its season, and the project's founding rule is that a game
    the site covers is never reported as free.
    """
    if not frames:
        return None
    for key in sorted(frames):
        frame = frames[key] or {}
        start, end = frame.get("start"), frame.get("end")
        if start and end and start <= date_iso <= end:
            return dict(frame, key=key)
    return None


def mlb_covered_on_date(games: Iterable[dict], date_iso: str) -> bool:
    """True when the bundle already carries MLB game data for `date_iso`.

    Used to decide whether the season-frame fallback is needed. When the bundle
    has the complete per-date list (the 2026 postseason), a date inside the frame
    with no game is genuinely free and must NOT be envelope-blocked.
    """
    return any(
        g.get("league") == "MLB" and record_is_on_date(g, date_iso) for g in games
    )


def mlb_frame_is_covered(date_iso: str, frame: dict) -> bool:
    """True when `date_iso` sits inside a range whose MLB list is known-complete."""
    for start, end in frame.get("complete_ranges") or []:
        if start <= date_iso <= end:
            return True
    return False


def frame_placeholder_interval(date_iso: str, frame: dict, durations: dict[str, int] | None = None) -> Interval:
    """The conservative block used when only the season frame is known."""
    label = frame.get("label") or "MLB"
    start_hhmm, end_hhmm = TBD_ENVELOPE_PT["MLB"]
    interval = Interval(
        local_wall_clock(date_iso, start_hhmm),
        local_wall_clock(date_iso, end_hhmm),
        f"{label} - per-game time not in the bundled snapshot",
        "normal",
        "MLB",
        frame.get("source", ""),
    )
    interval.time_confirmed = False
    return interval


def intervals_for_day(
    games: Iterable[dict],
    date_iso: str,
    durations: dict[str, int] | None = None,
    overrun_buffer_min: int = DEFAULT_OVERRUN_BUFFER_MIN,
    scope: str | None = None,
    mlb_frames: dict | None = None,
) -> tuple[list[Interval], list[dict]]:
    """All blocking intervals overlapping `date_iso`, plus skipped TBD games.

    `scope` filters to one coverage section (see `game_in_scope`). `mlb_frames`
    turns on the season-frame fallback described in `mlb_frame_for`.
    """
    games = list(games)
    day_start, day_end = local_day_bounds(date_iso)
    busy: list[Interval] = []
    skipped: list[dict] = []
    mlb_covered = False
    for game in games:
        if game.get("league") == "MLB" and record_is_on_date(game, date_iso):
            mlb_covered = True
        if not game_in_scope(game, scope):
            continue
        interval = game_to_interval(game, durations, overrun_buffer_min)
        if interval is None:
            if game.get("date_local") == date_iso:
                skipped.append(game)
            continue
        clipped = clip(interval, day_start, day_end)
        if clipped is not None:
            busy.append(clipped)

    frame = mlb_frame_for(date_iso, mlb_frames)
    if (
        frame is not None
        and not mlb_covered
        and not mlb_frame_is_covered(date_iso, frame)
        and game_in_scope({"sections": ["1", "2", "3"]}, scope)
    ):
        busy.append(clip(frame_placeholder_interval(date_iso, frame, durations), day_start, day_end))
    return [b for b in busy if b is not None], skipped


def day_report(
    games: Iterable[dict],
    date_iso: str,
    durations: dict[str, int] | None = None,
    overrun_buffer_min: int = DEFAULT_OVERRUN_BUFFER_MIN,
    scope: str | None = None,
    mlb_frames: dict | None = None,
) -> dict:
    """Full free/busy report for one local day, in the user's timezone."""
    games = list(games)
    day_start, day_end = local_day_bounds(date_iso)
    busy, skipped = intervals_for_day(games, date_iso, durations, overrun_buffer_min, scope, mlb_frames)
    merged = merge(busy)
    windows = free_windows(day_start, day_end, busy)
    busy_minutes = sum(iv.minutes for iv in merged)
    unconfirmed = [iv for iv in merged if not iv.time_confirmed]
    unconfirmed_minutes = sum(iv.minutes for iv in unconfirmed)
    total_minutes = span_minutes(day_start, day_end)
    longest = longest_free_window(windows)
    frame = mlb_frame_for(date_iso, mlb_frames)
    frame_used = bool(
        frame is not None
        and not mlb_covered_on_date(games, date_iso)
        and not mlb_frame_is_covered(date_iso, frame)
        and game_in_scope({"sections": ["1", "2", "3"]}, scope)
    )

    # A day counts as free only when nothing at all is scheduled on it.  A game
    # whose date is official but whose time is not announced still blocks the
    # day via the conservative envelope -- the earlier version of this project
    # reported such days as free, which is the bug being fixed.
    return {
        "date": date_iso,
        "scope": scope or SCOPE_ALL,
        "day_length_minutes": total_minutes,
        "busy_minutes": round(busy_minutes, 1),
        "free_minutes": round(total_minutes - busy_minutes, 1),
        "is_free_day": not merged,
        "has_high_priority": any(iv.priority == "high" for iv in merged),
        "has_unconfirmed_times": bool(unconfirmed),
        "unconfirmed_minutes": round(unconfirmed_minutes, 1),
        "mlb_frame_fallback": frame_used,
        "mlb_frame": frame,
        "longest_free_window": longest.as_dict() if longest else None,
        "free_windows": [iv.as_dict() for iv in windows],
        "busy_windows": [iv.as_dict() for iv in merged],
        "tbd_unresolved": [
            {
                "league": g["league"],
                "label": g.get("label", ""),
                "date_local": g.get("date_local"),
                "source": g.get("source", ""),
                "reason": "no start time published",
            }
            for g in skipped
        ] + [
            {
                "league": iv.league,
                "label": iv.label,
                "date_local": date_iso,
                "source": iv.source,
                "reason": "date official, first pitch / kickoff not yet announced",
            }
            for iv in unconfirmed
        ],
    }


# ---------------------------------------------------------------------------
# Vacation-window search
# ---------------------------------------------------------------------------


def occupied_dates(
    games: Iterable[dict],
    durations: dict[str, int] | None = None,
    scope: str | None = None,
) -> dict[str, set[str]]:
    """Map each local date to the set of leagues that block it, within `scope`."""
    table = durations or DEFAULT_DURATIONS
    occupied: dict[str, set[str]] = {}
    for game in games:
        if not game_in_scope(game, scope):
            continue
        interval = game_to_interval(game, table)
        if interval is None:
            continue
        day = interval.start.astimezone(USER_TZ).date()
        # A game that runs past midnight also blocks the following date.
        last = (interval.end - timedelta(minutes=1)).astimezone(USER_TZ).date()
        while day <= last:
            occupied.setdefault(day.isoformat(), set()).add(game["league"])
            day = day + timedelta(days=1)
    return occupied


def find_gaps(
    blocked: set[str],
    range_start: str,
    range_end: str,
    min_days: int = 1,
) -> list[dict]:
    """Contiguous runs of unblocked dates within [range_start, range_end].

    `blocked` is a set of ISO dates.  Only dates we have actually verified are
    meaningful -- callers must pass a range they have full coverage for.
    """
    start = datetime.strptime(range_start, "%Y-%m-%d").date()
    end = datetime.strptime(range_end, "%Y-%m-%d").date()
    gaps: list[dict] = []
    run_start = None
    day = start
    while day <= end:
        iso = day.isoformat()
        if iso in blocked:
            if run_start is not None and (day - run_start).days >= min_days:
                gaps.append(_gap(run_start, day - timedelta(days=1)))
            run_start = None
        else:
            if run_start is None:
                run_start = day
        day = day + timedelta(days=1)
    if run_start is not None and (end - run_start).days + 1 >= min_days:
        gaps.append(_gap(run_start, end))
    gaps.sort(key=lambda g: -g["days"])
    return gaps


def _gap(first, last) -> dict:
    return {
        "start": first.isoformat(),
        "end": last.isoformat(),
        "days": (last - first).days + 1,
        "weeks": round(((last - first).days + 1) / 7, 2),
    }
