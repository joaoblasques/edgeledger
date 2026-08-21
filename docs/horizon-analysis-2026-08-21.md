# Resolution-horizon analysis — 2026-08-21

**Question:** will the twelve-month clock produce a scoreable sample, or will most tracked
markets resolve after it ends?

**Method:** every distinct `venue_market_id` in the forecast log (412) looked up via Gamma's
`condition_ids` filter; 403 returned. Bucketed by `endDate` against the clock's end
(2027-08-03, twelve months from the first logged forecast). Markets with no `endDate` were
classified by the year named in the question — all 123 are 2026 midterm races, which settle
2026-11-03, inside the clock.

## What the book actually holds

| Theme | Contracts | Share | Resolves |
|---|---|---|---|
| 2026 midterms / races | 239 | 59% | 2026-11-03 — inside |
| 2028 presidential | 147 | 37% | 2028-11-07 — **after the clock** |
| Other | 16 | 4% | mixed |
| 2027 events | 1 | 0.2% | inside |

- **Inside the clock: 256 / 403 (64%)**
- **After the clock: 147 / 403 (36%)** — almost entirely 2028 presidential contracts, which
  cannot be scored before the project ends no matter what happens.

## The real constraint is not the count — it is clustering

The 239 midterm contracts map to only **161 distinct contests**. 61 of those carry both a
Democrat and a Republican contract, which are near-perfectly anticorrelated: the pair is one
independent outcome, not two. One event (the 2026 Brazilian presidential race) alone accounts
for 16 contracts.

Counting honestly, the twelve months yield roughly:

```
161 distinct midterm contests
+ 17 non-midterm markets resolving inside the clock
= ~178 effectively independent resolutions
```

And 59% of them land on **a single day, 2026-11-03**. That is ~74 days from this analysis.

## Why this matters

Brier confidence intervals narrow with the square root of the sample. At n ≈ 178 independent
outcomes — most of them the same kind of event, resolving simultaneously, under one shared
national swing — the standard error on `brier_delta` is wide relative to any edge a baseline
model would plausibly show. A single correlated shock (one unexpected national result) moves a
large fraction of the book at once, so the effective sample is smaller still.

The measurement layer is not the limitation. The **book composition** is.

## Options (human-owned decision — see CLAUDE.md, "which markets to track")

1. **Do nothing.** ~178 resolutions by Nov 2026, honest but statistically thin, and a third of
   the ingest effort is spent on 2028 contracts that can never be scored in time.
2. **Bias ingestion toward shorter-horizon markets.** Sports, weekly/monthly economic prints,
   and recurring events resolve continuously rather than in one November spike, and they
   accumulate independent outcomes across the whole twelve months.
3. **Keep the long-dated markets for CLV only.** CLV needs no resolution — it is measurable as
   soon as a price moves. The 2028 book is useless for Brier but perfectly good for
   closing-line value, provided that is reported separately and labelled as such.

**Recommended: 2 + 3.** Add a shorter-horizon slice so Brier has a continuously growing
independent sample, and explicitly report the long-dated book under CLV only. Option 3 costs
nothing — it is a reporting distinction, not an ingestion change.

Whatever is chosen, it should be stated in `docs/methodology.md` **before** the numbers exist,
not after — the entire credibility of the project rests on metrics being committed to in
advance rather than selected once they flatter.
