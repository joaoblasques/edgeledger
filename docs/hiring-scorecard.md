# Am I on track? A pre-registered hiring scorecard

Date: 2026-09-12
Status: first draft — checkpoints are stated in advance, on purpose

## Why this file exists

Every other measurement in this project is pre-registered: `docs/methodology.md` states the
expected sample size *before* the results, and pre-commits to reporting a null. **The hiring
goal had no equivalent.** The repo defined rigorous research success (Brier delta, calibration,
CLV) and left "am I employable yet?" entirely to vibes.

That gap matters more than it looks, because of a tension the project never reconciled:

> `methodology.md` pre-registers that **a null result is the expected outcome**.

A null is a *passing research result* — it is honest, it is reported, it is the point. But
"I measured carefully and found no edge" is an **ambiguous hiring result** unless the artifact
is framed so the rigour, not the edge, is the product. This file exists so that framing is
decided in advance rather than rationalised afterwards.

## The role this targets

Three adjacent roles get conflated. Being specific changes what to build and what to study.

| Role | What they do | Fit |
|---|---|---|
| **Quant developer / trading-systems engineer** | Ingestion, point-in-time correctness, append-only logs, backtest integrity, the measurement layer | **Primary target.** Closest to Jonas's existing data-engineering career, and what EdgeLedger most strongly demonstrates |
| **Quantitative researcher** | Builds models producing probabilities; validates whether edge is real | **Secondary.** What Tracks A and B teach; a stretch without a stats/ML background |
| **Trader** | Takes positions, sizes risk, watches markets | **Ruled out** — does not fit the lifestyle, and worst fit for remote work |

The repo's own pitch — *"the measurement and modelling layer that lets a desk know whether
its edge is real"* — is **quant dev**, not pure research. That is the honest read of what this
project proves, and it is the stronger angle: it is data engineering with a quant vocabulary,
not a career change.

**Positioning consequence:** lead with the infrastructure (invariants, leakage firewall,
hash chain, point-in-time discipline), and present the modelling as evidence you can speak
the researchers' language. Not the other way round.

## The constraint that dominates everything

**Remote from Portugal, permanently, no relocation.**

This filters the employer pool harder than any portfolio widens it. Prediction markets is a
small niche and most desks want on-site in London, NYC or Chicago. Be realistic: the project
is not competing against other candidates' projects, it is competing against a desk's default
preference to hire someone in the building.

That is an argument for the project being *unusually* rigorous rather than merely good — the
rigour is what makes a remote hire feel safe.

## Compensation expectation

`[Likely — from general knowledge, NOT from current listings. Verify against real postings.]`

| Role | Remote-EU realistic band |
|---|---|
| Quant dev, mid-level | €70–110k |
| Quant researcher | €80–130k |
| London/NYC on-site equivalent | £120k–200k+ |

**€100k is achievable but sits toward the top of the remote-EU band, not the middle.** Remote
roles pay on geography-adjusted bands. Treat €100k as a stretch target that requires the
project to land well, not as a baseline.

**Action:** verify this against 5–10 real postings before making any decision that depends on
the number. A guess from training data is not a salary expectation.

## Checkpoints — stated in advance

The point of pre-registering these is that "am I on track?" becomes answerable without
self-deception. Each is pass/fail, not a feeling.

### Month 6 (≈2027-02) — does the artifact hold up?

- [ ] The log has run unattended for 6 months with **no gap in `seq`** that is not explained
      in writing. (A missed window is acceptable; an unexplained one is not.)
- [ ] `verify_chain` passes from genesis, and the published head hash is reproducible by a
      stranger following the README alone.
- [ ] At least one **baseline** is beaten or explicitly not beaten, with a confidence interval
      attached. (Rung B2. Not "a model exists" — a *comparison* exists.)
- [ ] A stranger can read `README.md` + `methodology.md` and state what the project measures
      and why, without asking a question.

**If these fail:** the problem is the artifact, not the timeline. Fix before continuing.

### Month 12 (≈2027-08) — is there anything to say?

- [ ] The original 2027-08-03 clock has closed and **results are published** — including, and
      especially, if the result is null.
- [ ] A written post-mortem exists that a reviewer would find *more* credible than a positive
      result would be: what was predicted in advance, what happened, what that implies.
- [ ] Rungs A1–A3 and B1–B3, B6 are complete (see `learning/ROADMAP.md`), meaning leakage and
      inference are understood well enough to defend in an interview.
- [ ] **The real test:** can you explain the point-in-time contract and why it matters, to a
      technical interviewer, without notes, in two minutes?

**If the result is null:** that is a pass, provided the write-up makes the *method* the
product. "I built a system that could have detected an edge, proved it was working, and
reported honestly that there wasn't one" is a credible quant-dev story. It is only a failure
if the write-up is defensive about it.

### Month 18 (≈2028-02) — start applying

- [ ] Applications going out. **Do not wait for month 24.** The project's value in an
      interview is that it is *running*, not that it is finished; a live two-year system with
      six months left to run is a better conversation than a completed one.
- [ ] The portfolio one-pager exists (see the AIOS vault's owed one-pagers) and explains
      EdgeLedger in plain language to a non-specialist recruiter.
- [ ] At least one piece of the work is public beyond the repo — a write-up, a talk, a post.
      A GitHub repo nobody is pointed at persuades nobody.

### Month 24 (≈2028-08) — the honest review

- [ ] Two full years of timestamped forecasts, spanning the 2026 midterms and the 2028
      primaries, scored and published.
- [ ] If no job has come from it: **write the retrospective and stop.** Two years is the
      pre-registered horizon. Extending it again would be the sunk-cost version of the same
      mistake this project exists to avoid in backtests.

## Leading indicators (check quarterly, not just at checkpoints)

These move before the checkpoints do:

1. **Is the log still growing?** A stalled cron is a dead project. (It stalled silently for
   weeks in 2026-09 — see `forecast-runtime-2026-09-12.md`.)
2. **Are study sessions actually happening?** 2 hrs/week is the plan; four consecutive missed
   weeks means the plan is wrong, not that you are behind.
3. **Can you explain the last rung you studied, out loud, in plain language?** This is the
   ROADMAP's comprehension gate. If not, the rung is not done.
4. **Would a stranger understand the README?** Re-read it cold every quarter.
5. **Has anything been written publicly yet?** The month-18 checkpoint requires work public
   beyond the repo, which means the writing starts long before month 18 — realistically
   alongside the month-12 results. A repo nobody is pointed at persuades nobody, and this is
   the indicator that goes quiet without anyone noticing.

## What would make this project fail

Named in advance so they are recognisable early:

- **It stops running.** The single biggest risk. An unattended system that quietly dies is
  worse than no system, because the commit history shows exactly when you stopped caring.
- **It is never shown to anyone.** A rigorous private repo is a hobby.
- **The null result is buried or spun.** The entire credibility thesis collapses. The honest
  null *is* the deliverable.
- **Scope creep into trading.** Sizing, execution and live trading are out of scope and also
  the wrong signal for the target role.
- **Studying replaces shipping.** 200 hours of study with no published analysis is a course,
  not a portfolio.
