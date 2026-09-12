# Horizon change: twelve months → two years, and a 2 hrs/week study cadence

Date: 2026-09-12
Status: decided by Jonas; docs not yet rewritten across the repo

## What changed

Two decisions, taken together:

1. **The hiring horizon moves from ~1 year to ~2 years.** EdgeLedger is no longer a
   twelve-month clock aimed at being hireable in 2027; it is a two-year system aimed
   at 2028.
2. **Study cadence is fixed at 2 hrs/week**, down from the `docs/learning/README.md`
   plan of ~6 hrs/week across two parallel tracks.

## Why the longer horizon is the better call anyway

This is not just a preference change — the repo's own methodology already argued for
it, and the twelve-month framing was the weaker claim.

`docs/methodology.md` § "Expected sample size, stated in advance" states that the
in-clock universe yields **~178 independent resolutions, roughly 59% of them landing
on a single day (2026-11-03)**, and concludes:

> That is thin... At that sample size the confidence interval on `brier_delta` is wide
> relative to any edge a baseline model would plausibly show, and one correlated
> national surprise moves much of the book at once. **A null result is the expected
> outcome, and will be reported as one.**

A twelve-month clock was therefore scheduled to end in a wide-interval null dominated
by a single election day. That is an honest result, and the project was right to
pre-register it — but it is a weak hiring artifact, because it demonstrates rigour
without demonstrating a measured edge.

**Two years fixes the structural problem, not just the timeline.** It spans the 2026
midterms *and* the 2028 primary season, so the sample is no longer concentrated on one
correlated day. More independent resolutions across uncorrelated event clusters is
exactly what widens a thin interval.

## What this invalidates, and what it does not

**Unchanged — do not touch:**
- The append-only, hash-chained `forecast_log` and all six invariants. The immutability
  guarantee is the project's actual differentiator and is horizon-independent.
- Every forecast already logged. Extending the clock adds rows; it never revises old
  ones. Corrections remain new rows, never overwrites.
- Pregame-only, hold-to-resolution scope.

**Needs rewriting (not yet done):**
- `README.md` — tagline, "twelve-month" framing, the hiring claim, § Status.
- `CLAUDE.md` — lines 3–7 carry the twelve-month purpose statement.
- `docs/methodology.md` — the sample-size section should now state the *two-year*
  expected sample and explain why spanning two election cycles is the point.
- `src/edgeledger/scoring/score.py`, `src/edgeledger/forecast/runner.py`,
  `dags/forecast_baseline.py`, `tests/test_scheduled_run.py`, `docs/setup-scheduling.md`,
  `docs/adr/0003-scheduling-and-storage.md` — all carry twelve-month references.
- `docs/learning/README.md` — the ~6 hrs/week plan and its reference to a
  "12-month roadmap" that does not exist as a file.

**Open question for the rewrite:** whether "in-clock" (the horizon filter added
2026-08-21) should be redefined against the new two-year window, or left as-is with
a second universe added. Leaving it alone is the safer default — the filter's whole
purpose was to stop retroactive redefinition of what counts.

## The study plan: 2 hrs/week, from the ground up

### What Jonas asked for

> core concepts, no jargon, no technical terms, I want to learn via very simple
> language, maybe not eli5 and with analogies as it may be too slow but from first
> principles, from the ground up and with simple language, only at the end of the
> teachings may you introduce some technical terms

Read carefully, that is a specific pedagogy, not just "go slower":
- **First principles, ground up** — derive, don't assert.
- **Simple language throughout** — not simplified *content*, simplified *vocabulary*.
- **Analogies allowed but not the engine** — full ELI5 pacing is too slow.
- **Jargon deferred to the end** — name the thing only once it is already understood.

### What already exists, and what it implies

`docs/learning/track-a/a0-what-a-probability-is.md` is **already written in exactly
this style**: marbles in a bag, "no formulas, no market vocabulary, one idea at a
time", the concept built before it is named. A0 is the template. The style question is
settled; it does not need inventing.

The problem is structural, not stylistic:
- Only three notes exist (A0, A1, B1).
- A1 and B1 assume more than A0 delivers — A0 is explicitly "the on-ramp to A1", so the
  ladder has one rung and then a gap.
- Two parallel tracks at 2 hrs/week means each track advances an hour a week, which is
  too slow to hold continuity between sessions.

### Recommended shape (not yet implemented)

**Collapse the two parallel tracks into one ordered spine.** At 6 hrs/week, running
Track A and Track B in parallel was reasonable. At 2 hrs/week it is not: two threads
each get an hour, and a week's gap between one-hour sessions loses more context than
it builds. One sequence, one rung per session, is the cadence that survives a weekly
schedule.

The existing A/B split is a useful *taxonomy* ("is my edge real?" vs "where does a
probability come from?") and should survive as tags on notes, not as two clocks.

**Two hours a week for ~100 weeks is ~200 hours of study** — that is a substantial
curriculum, and the reason the horizon change and the cadence change belong in one
decision rather than two.

## Next actions (none taken yet)

1. Rewrite the twelve-month references listed above. Mechanical but touches ~10 files.
2. Restructure `docs/learning/` into a single ordered spine; keep A0 as the template
   and the first rung.
3. Write the roadmap file `docs/learning/README.md` already links to but which has
   never existed.
4. **Unrelated but urgent:** `.github/workflows/forecast.yml` has
   `timeout-minutes: 20` while successful runs take 15–19 minutes; 13 of the last 30
   runs were cancelled. A two-year horizon doubles the exposure to this. Fix before
   the next scheduled run — see `2026-09-12-project-automation-audit.md` in the AIOS
   vault.
