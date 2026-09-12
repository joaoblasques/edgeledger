# The learning spine

One ordered sequence, one session per week, two hours a session. Written 2026-09-12,
when the project horizon moved to two years (`../horizon-change-2026-09-12.md`).

This is the file `README.md` has always linked to and which never existed.

## How this is paced, and why it adds up

The unit of work is **one section of one rung**, not one rung.

That comes from measuring what is already written:

| Note | Words | Major sections |
|---|---|---|
| A0 — What a probability is | 1,139 | 3 |
| A1 — Probability foundations | 5,221 | 6 |
| B1 — What a model is | 5,932 | 5 |

A0 is about one session. A1 and B1 are **five to six sessions each**. Treating a rung
as a week would have put A1 and B1 in two weeks and silently skipped 90% of them; that
is how a plan looks finished and teaches nothing.

Fourteen rungs at an average of ~4.5 sections each is **~63 study sessions**. At one
session a week that is ~63 weeks of teaching inside a ~100-week horizon, leaving ~37
weeks of slack — which is correct, not wasteful. Some sections will take two sittings,
some weeks will be lost, and the back half of the sequence should be re-planned rather
than pre-written (see "Where this stops being a plan").

## How each session works

1. **One section. Read it, work it, stop.** Do not read ahead into the next section
   because the current one felt easy; the next one assumes you did the exercises.
2. **Work the exercises on paper before opening any answer.** Every existing note ends
   with a "Check yourself" block for this reason. A section is not finished because it
   was read.
3. **The gate:** you can explain the section's core idea in plain language, without the
   technical term, to someone who does not have it. If you cannot, repeat the section
   next week. Repeating is the normal case, not a failure.
4. **Write the note as you learn it.** Notes are added as they are learned, never
   pre-created. The note *is* the record that the session happened.

## The teaching style (this is a constraint, not a preference)

`track-a/a0-what-a-probability-is.md` is the template. Its opening move — ten marbles
in a bag, the share lives in the pile not the pull — is what every section should do:

- **Build from first principles.** Derive it; do not assert it and move on.
- **Plain language throughout.** Simplify the *vocabulary*, never the *content*. The
  bias-variance decomposition does not become less true when explained without the
  phrase "bias-variance decomposition".
- **Analogies are allowed, but they are not the engine.** Full ELI5 pacing is too slow
  for 63 sessions. One good concrete object per idea, then move.
- **The technical term arrives last.** Name the thing only once the reader already
  understands it. A0 does this: the concept is complete before the word is used.

A section that opens with a definition has failed the style, no matter how correct it
is.

## Sequence

Interleaved so that each rung arrives roughly when the project needs it, and so the
two strands stay in contact. **A/B labels are tags, not tracks** — there is one clock.

### Phase 1 — What a probability is, and what a model is (~weeks 1–13)

| # | Session | From |
|---|---|---|
| 1 | A probability is a share, not a prediction | A0 §1 |
| 2 | One outcome cannot refute a probability | A0 §2 |
| 3 | From a share to a price | A0 §3 |
| 4 | Probability as a price | A1 §1 |
| 5 | Conditional probability | A1 §2 |
| 6 | Bayes' theorem | A1 §3 |
| 7 | Expectation and variance | A1 §4 |
| 8 | Odds ↔ probability ↔ log-odds | A1 §5 |
| 9 | Vig and overround removal | A1 §6 |
| 10 | Features → probability: the mapping | B1 §1 |
| 11 | Generative vs discriminative | B1 §2 |
| 12 | Signal vs noise | B1 §3 |
| 13 | Bias-variance decomposition | B1 §4 |

**Phase gate:** you can explain, without jargon, why a price *is* a probability, and
why a model that fits the past perfectly is usually worse than one that does not.

### Phase 2 — Honesty of probabilities, and the baseline (~weeks 14–26)

Opens by finishing B1 (§5 carries over from Phase 1 — the existing notes supply 14
sessions, and Phase 1 holds 13).

| # | Session | From |
|---|---|---|
| 14 | Why log-odds is the natural space | B1 §5 |
| 15–18 | Distributions: Bernoulli, binomial, Poisson, normal | A2 (new) |
| 19–21 | Scoring: Brier, log loss, reliability diagrams | A2 (new) |
| 22 | Calibration vs discrimination | A2 (new) |
| 23–26 | Baselines that are hard to beat: market price, base rates, Elo, Bradley-Terry | B2 (new) |

**Phase gate:** you can say what it means for a forecast to be *honest* as distinct
from *accurate*, and you have beaten — or failed to beat — a stated baseline.

B2 carries the project's hardest rule: **never build a model without beating a baseline
first.** It lands here deliberately, before any regression.

### Phase 3 — Is the edge real (~weeks 27–39)

A3 (MLE, sampling distributions, confidence intervals, bootstrap, hypothesis testing,
multiple-comparison correction, effective sample size), then B3 (linear → logistic
regression, link functions, coefficients in log-odds, regularisation).

A3 before B3 on purpose: you should be able to tell whether a number is noise before
you build the thing that produces more numbers.

**Phase gate:** given the project's own ~178-resolution sample, you can state the
confidence interval on `brier_delta` and explain why a point estimate alone would be
misleading. This is the rung that makes you able to read your own results.

### Phase 4 — Where the backtest lies (~weeks 40–52)

B6 (time-series cross-validation, walk-forward, look-ahead leakage, survivorship bias,
backtest overfitting), pulled **much earlier than its original month 9–10 slot**.

`track-b/README.md` already flags B6 as "the single highest-value rung for this
project's specific risk — an AI agent will cheerfully hand you a beautiful backtest
built on leakage." Given that, leaving it in month 9 of a two-year plan was the wrong
order: it is the rung that protects every rung after it. It moves up.

**Phase gate:** you can find the leak in a backtest someone else wrote — including one
written for you by a model.

### Where this stops being a plan (~week 53 onward)

Remaining rungs: **A4** (Kelly and sizing), **A5** (microstructure, closing-line
value), **A6** (portfolio and capacity), **B4** (process models), **B5** (Bayesian and
hierarchical), **B7** (ensembling and recalibration).

These are **deliberately not scheduled week by week.** Sequencing them now would be
invention, not planning: by week 53 the log will have roughly a year of forecasts, the
2026 midterms will have resolved, and the results will say which of these matters. If
the baseline is not beaten, B4/B5 (better models) come first. If it is beaten but the
interval is wide, A3's tools and A6's capacity questions matter more. If the edge is
real and stable, A4 (sizing) stops being theory.

**Re-plan this section at week 50, against the actual scoreboard.** A spine that
pretends to know week 80 today is the same failure as a backtest that pretends to know
the future.

## Standing constraints

- **One session a week, two hours.** Not a target to beat — the pace is the plan. Six
  hours in one weekend does not replace three weeks of spacing.
- **Missing a week is not falling behind**; it moves the sequence, nothing else. There
  is ~37 weeks of slack precisely so this is true.
- **Every note is written in A0's style** or it gets rewritten. The style is the point:
  material understood in plain language is material you can defend in an interview
  without reciting it.
- **The reading list stays in the vault** (`01_Projects/EdgeLedger/02-Learning/Reading
  List.md`), not duplicated here.
