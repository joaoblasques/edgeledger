# A0 — What a Probability Is

**Core question: what kind of thing is a probability, before it is a price?**

[A1](a1-probability-foundations.md) opens by asserting that price and probability are the same
object. That assertion is only useful if "probability" already means something concrete. This
page builds that meaning from nothing — no formulas, no market vocabulary, one idea at a time.

It is the on-ramp to A1, not a summary of it. If the first line of A1 already reads as obvious,
skip this page.

---

## 1. A probability is a share, not a prediction

### The bag

Ten marbles: three red, seven blue. Reach in without looking, pull one out, note the colour, put
it back, shake, repeat.

Any single pull is unpredictable. But something about the *pile* of results is stable: roughly
three in every ten pulls come out red. Pull a hundred times and the share sits near 0.3. Pull a
thousand and it sits nearer still.

That share is the probability. It lives in the pile, not in the pull.

### What this rules out

Two things follow immediately, and both are load-bearing.

**Nothing is ever "due."** After six blues in a row, red is not more likely. The bag has no memory
of what it gave you last — it is the same bag every time. The *gaps* between reds stay random
forever; only the *share* settles down.

**A single pull is red or blue, never 0.3.** The number 0.3 is not a claim about the next pull.
It is a claim about what the pile looks like once there is a pile.

### Why it matters here

This is why a single forecast can never be scored. Say 30% and it happens — you were not wrong.
Say 30% and it doesn't — you were not right. One outcome carries almost no information about the
number that produced it.

The only thing that can be tested is the pile. That is why EdgeLedger is a twelve-month
append-only log rather than a record of good calls: the log *is* the pile, and the append-only
constraint is what stops the misses from quietly leaving it.

---

## 2. One outcome cannot refute a probability

### The surgeon

A surgeon says an operation succeeds 90% of the time. The operation fails. The family says:
*"He lied."*

They are wrong, and the reason is worth stating precisely.

The 90% was never a claim about *this* operation. It was a claim about many operations: roughly
90 in 100 succeed — which is the same as saying **10 in 100 fail**. This failure is one of the
ten. It was included in the forecast, not contradicted by it.

> A single outcome cannot refute a probability, because the probability already said this outcome
> happens sometimes.

### What would actually test him

Not this one case. Gather every operation where he said 90%, and check the share:

- succeeded about 90 times in 100 → the number is honest
- succeeded 60 times in 100 → overconfident
- succeeded 99 times in 100 → underselling, which is also an error

Note what the test requires: many cases, all drawn from *the same claim*. "Lots of surgical
outcomes" in general will not do it. You need the ones where he said 90%.

### The three moves

Any version of this argument — surgeon, weather forecaster, model — is the same three steps:

1. **Say what the number claimed.** The pile, not the single event.
2. **Show the outcome was already included.** It is part of the share, not a counterexample.
3. **Say what would actually test it.** Many repeats of the same claim, then compare the share.

### Why it matters here

This is calibration, and it is the reason EdgeLedger reports Brier scores and reliability curves
over thousands of resolved forecasts rather than highlighting individual calls. A desk that judges
a forecaster on single outcomes is measuring luck. The pile is the only honest unit of assessment.

---

## 3. From a share to a price

### The deal

Same bag — ten marbles, three red. New rule: **pull one marble; if it is red you receive €10, if
it is blue you receive nothing.**

Play ten times. Roughly three pulls come out red, each paying €10, so you collect about **€30**.
Spread across ten plays, that is **€3 per play**.

No single play ever pays €3 — it pays €10 or nothing. But the pile averages €3 a go.

That average is what the deal is worth per play. The share (0.3) scaled by the prize (€10).

### The fair price

Now the deal costs money to play.

- At **€1** a pull you collect €3 on average. You would play all day.
- At **€8** a pull you collect €3 on average. You would refuse — and would rather be the one
  charging.

At **€3**, over a hundred plays, you pay €300 and collect about €300. Neither side comes out
ahead. Neither side would rather swap places.

That is what "fair" means here. Not fair as in courteous — fair as in **no side is better to be
on.** If you would prefer one side of a deal, the price is wrong.

### The collapse

Change the prize from €10 to €1. The share is still 0.3, so the fair price becomes **€0.30** — the
share itself, wearing a currency sign.

A binary event contract pays exactly €1 if the event happens and nothing if it doesn't. So:

> **The fair price of a binary contract is the probability, written as money.**

"Trading at 30 cents" and "30% likely" are the same statement. This is the identity A1 opens
with, and everything downstream — edge, Brier scores as money, closing-line value — depends on it
being automatic rather than a conversion you stop to perform.

---

## Where this goes next

[A1 §1](a1-probability-foundations.md) restates the price identity formally and connects it to
`mkt_yes_mid`. A1 §2 introduces conditioning — probabilities that depend on what you already know,
which is where `feature_cutoff_ts_utc` and the leakage firewall come from. A1 §3 covers Bayes:
what to do when new evidence arrives.

Two distinctions from this page are worth carrying into A1 §3, because they are the ones that most
often get fused:

- **How common something is** ("3% of widgets are defective") — the base rate.
- **How loud the clue is, given it** ("80% of defective widgets rattle") — the signal strength.

They are different statements and Bayes multiplies them separately. A statement of the second kind
never mentions how common the thing is: *"of defective widgets, 80% rattle"* stays true whether
defects are 1% or 99% of production. If a sentence contains both numbers, two ideas have been
fused into one and the update cannot be performed.
