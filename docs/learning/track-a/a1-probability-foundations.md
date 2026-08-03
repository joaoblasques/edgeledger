# A1 — Probability Foundations

**Core question: what is a fair price?**

A binary event contract pays 1 if the event happens and 0 if it doesn't. Its fair price is
therefore just a probability wearing a currency sign. Everything in this note exists to make that
sentence precise enough to build on: how to reason about a probability conditional on what you
know, how to update it when new information arrives, how to convert between the three
representations the industry uses interchangeably, and how to strip the house's margin out of a
quoted price so you're comparing yourself against the market's *actual* belief rather than its
sales price.

Prerequisite framing for the whole note: throughout, a market "showing 0.0455 for Yes" means you
can buy the Yes contract at 4.55c and receive $1.00 if it resolves Yes. Kalshi quotes in cents,
Polymarket in dollars 0–1; EdgeLedger stores everything as `Decimal` in [0, 1]
(`mkt_yes_bid`, `mkt_yes_ask`, `mkt_yes_mid` in `ForecastLogRow`).

---

## 1. Probability as a price

### Intuition

If a contract pays $1 on Yes and you think Yes happens 30% of the time, then over many identical
independent bets you collect $1 thirty times per hundred. Your average receipt is $0.30. So $0.30
is the price at which you neither gain nor lose in the long run — the *fair* price. Above it you
are selling value; below it you are buying it.

This is the single most useful mental collapse in the whole business: **price and probability are
the same object**. When a trader says "this is trading at 30" and a modeller says "I have it at
0.34", they are disagreeing about a probability, and the disagreement is denominated in cents.

### The maths

For a contract with payoff $X \in \{0, 1\}$ and $P(X=1) = p$:

$$\mathbb{E}[X] = 1 \cdot p + 0 \cdot (1-p) = p$$

In prose: the expected payoff is the sum over outcomes of (payoff × probability of that outcome).
The zero-payoff branch contributes nothing, so the expectation collapses to $p$ exactly. A
contract whose payoff is 0 or 1 has an expected value numerically identical to the probability of
the "1" branch. Fair price = expected payoff = $p$.

### Worked example

A Kalshi market: *"Will the Fed cut rates at the March meeting?"* Yes is quoted 0.30 / 0.33
(bid/ask). Mid is 0.315. You believe $p = 0.38$.

- Buy Yes at the ask, 0.33. Expected payoff 0.38. Expected profit per contract:
  $0.38 - 0.33 = \$0.05$.
- Your `edge` field in `forecast_log` would record $\hat{p} - \text{mkt\_yes\_mid} = 0.38 - 0.315 = 0.065$.

Note EdgeLedger computes `edge` against the **mid**, not against the ask you'd actually pay. That
is deliberate: mid-based edge measures your disagreement with the market's belief; ask-based edge
measures your disagreement net of transaction cost. The first is the research question, the second
is the trading question, and conflating them is how people convince themselves a 2c edge is real
when the spread is 3c.

> **Why this matters for the desk.** Every conversation on a desk is conducted in price, not in
> probability. Being fluent in the identity means you can hear "we're paying 34 for that" and
> immediately think "so they need it to happen more than 34% of the time" without conscious
> conversion. It is also the reason a Brier score is directly interpretable as money: squared
> probability error and squared pricing error are the same number.

---

## 2. Conditional probability

### Intuition

$P(A)$ is your belief about $A$ knowing nothing in particular. $P(A \mid B)$ is your belief about
$A$ in the subset of worlds where $B$ is true. Conditioning is *restriction*: you throw away every
world inconsistent with $B$, then re-normalise so what's left sums to 1.

The reason this is the foundational concept for a forecasting system rather than a piece of exam
trivia is that **every forecast is conditional**. There is no such thing as $P(\text{home win})$.
There is $P(\text{home win} \mid \text{everything known at 14:00 UTC})$. The conditioning set is
the model's inputs.

### The maths

$$P(A \mid B) = \frac{P(A \cap B)}{P(B)}, \qquad P(B) > 0$$

In prose: the probability of $A$ given $B$ is the probability that both happen, divided by the
probability that the condition happens at all. The denominator is the re-normalisation — it
rescales the restricted world back up to total probability 1.

Rearranged, this is the **chain rule**:

$$P(A \cap B) = P(A \mid B)\, P(B)$$

The probability of both is the probability of the condition times the probability of the target
inside that condition.

Two events are **independent** when $P(A \mid B) = P(A)$ — learning $B$ moves nothing — which is
equivalent to $P(A \cap B) = P(A)P(B)$.

### Worked example

Polymarket lists two related contracts on an NFL game:

- *"Team A wins"* — 0.62
- *"Total points over 47.5"* — 0.55

Naively, *"Team A wins AND over 47.5"* would be $0.62 \times 0.55 = 0.341$. If a third contract on
exactly that joint event trades at 0.30, either the market thinks those events are negatively
dependent (a high-scoring game favours the underdog's chances of keeping up), or there's a
mispricing. Implied conditional:

$$P(\text{over} \mid \text{A wins}) = \frac{0.30}{0.62} = 0.484$$

So the market's conditional probability of the over given an A win is 0.484 versus an
unconditional 0.55 — the market is saying A winning makes a high-scoring game *less* likely.
That's a testable claim about a mechanism, and it's the kind of structure you can only see once
you're comfortable moving between joint, marginal and conditional.

### The EdgeLedger link

Invariant 3 — `feature_cutoff_ts_utc` — is literally a statement about the conditioning set. The
contract says: the features that produced $\hat{p}$ are derivable from bronze rows with
`capture_ts_utc <= feature_cutoff_ts_utc`. In probability language, the conditioning set is
$\mathcal{F}_t$, the information available at time $t$, and the forecast is
$\hat{p} = P(\text{yes} \mid \mathcal{F}_t)$.

Leakage is not a data-engineering bug that happens to have statistical consequences. Leakage is
*conditioning on the wrong set* — computing $P(\text{yes} \mid \mathcal{F}_{t'})$ for some
$t' > t$ and labelling it $t$. `tests/test_point_in_time.py` is the assertion that the conditioning
set in the code matches the conditioning set in the claim.

> **Why this matters for the desk.** Every model that has ever blown up in backtest-to-production
> transition did so because its training conditioning set was larger than its live conditioning
> set. The desk framing: "what did we actually know at the moment we would have had to press the
> button?" If you can't answer that to the second, the backtest is decoration.

---

## 3. Bayes' theorem

### Intuition

You have a belief. Evidence arrives. What should the new belief be?

Bayes says: weight your prior belief by how well it predicted the evidence you actually saw,
relative to how well all the alternatives predicted it. A hypothesis that expected this evidence
gains; one that was surprised by it loses. That's all it is — a bookkeeping rule for "surprise
should cost you belief, proportionally."

### The maths

$$P(H \mid E) = \frac{P(E \mid H)\, P(H)}{P(E)}$$

In prose, term by term:

- $P(H)$ — the **prior**: your belief in the hypothesis before seeing this evidence.
- $P(E \mid H)$ — the **likelihood**: how probable this evidence would be *if* the hypothesis were
  true. Note carefully this is not "how probable the hypothesis is" — the whole trick of Bayes is
  that it converts the easy-to-state direction into the one you want.
- $P(E)$ — the **evidence** or marginal likelihood: how probable the evidence was overall,
  averaged across all hypotheses. This is a normalising constant, expanded via the law of total
  probability as $P(E) = P(E \mid H)P(H) + P(E \mid \neg H)P(\neg H)$.
- $P(H \mid E)$ — the **posterior**: your updated belief.

The **odds form** is far more usable in practice and connects directly to section 4:

$$\underbrace{\frac{P(H \mid E)}{P(\neg H \mid E)}}_{\text{posterior odds}} = \underbrace{\frac{P(E \mid H)}{P(E \mid \neg H)}}_{\text{likelihood ratio}} \times \underbrace{\frac{P(H)}{P(\neg H)}}_{\text{prior odds}}$$

In prose: posterior odds equal prior odds multiplied by the likelihood ratio. Updating in odds
space is a *multiplication*, with no normalising constant to compute. Take logs and it becomes an
*addition* — which is exactly why log-odds is the working space for models (section 4, and B1).

### Worked example

An injury report drops 90 minutes before a game. Prior: home team wins with $p = 0.60$.

Historically, when the home team goes on to win, a starting-QB-out report on the away side appears
in 22% of cases. When the home team loses, such a report appears in 10% of cases. (These are the
likelihoods — note they're conditional on the *outcome*, which feels backwards, and that's the
point.)

Prior odds: $0.60 / 0.40 = 1.5$.

Likelihood ratio: $0.22 / 0.10 = 2.2$.

Posterior odds: $1.5 \times 2.2 = 3.3$.

Posterior probability: $3.3 / (1 + 3.3) = 0.767$.

So the report moves you from 0.60 to 0.767. If the market has only moved to 0.70, you have 6.7
points of edge — assuming your likelihoods are honest, which is exactly the assumption A3
(inference) and B6 (validation) exist to interrogate.

### The EdgeLedger link

Two places.

**B5 (hierarchical priors, months 7–8).** When you're estimating a team-strength parameter from 6
games, the maximum-likelihood estimate is garbage — high variance, driven by noise. Hierarchical
modelling puts a prior on the team effect centred on the league average and lets the data pull the
estimate away from it in proportion to how much data there is. That shrinkage *is* Bayes: prior =
league average, likelihood = this team's 6 games, posterior = a weighted blend. Small sample →
posterior sits near the prior. Large sample → likelihood dominates. Understanding it as a single
Bayes update rather than a modelling trick is what makes the partial-pooling maths readable.

**B7 (shrinking toward market price, months 11–12).** Blending your model with the market is a
Bayes update in log-odds space where the market is the prior and your model is the evidence. The
blend weight is the strength you assign to each. Do it in probability space and you get nonsense
at the tails; do it in log-odds space and it's a weighted sum — logarithmic opinion pooling.

> **Why this matters for the desk.** News arrives constantly and the question is always "how much
> should this move my number?" A desk that answers that by feel is running an unmeasurable process.
> A desk that answers it with an explicit likelihood ratio has a number it can backtest, and can
> tell the difference between "the news was worth 7 points" and "we panicked."

---

## 4. Expectation and variance

### Intuition

Expectation is the long-run average. Variance is how far individual outcomes scatter around it.
For a binary contract, the two are locked together by $p$ alone — you cannot choose them
independently, which is a genuinely important structural fact.

The practical consequence: a market at 0.50 is the *most* uncertain market on the board, and a
market at 0.02 is nearly deterministic. Your position sizing, your sample-size requirements, and
how long it takes to prove you have edge all depend on where on that curve you're trading.

### The maths

For a Bernoulli random variable $X$ with $P(X=1) = p$:

$$\mathbb{E}[X] = p, \qquad \operatorname{Var}(X) = \mathbb{E}[X^2] - (\mathbb{E}[X])^2 = p - p^2 = p(1-p)$$

In prose: since $X$ only takes values 0 and 1, $X^2 = X$, so $\mathbb{E}[X^2] = p$ and the variance
is $p - p^2$. This function is a downward parabola, maximised at $p = 0.5$ where it equals 0.25,
and falling to 0 at both ends.

For a **position**, expectation is linear and variance is not. If you buy a contract at price $c$,
your profit is $X - c$:

$$\mathbb{E}[\text{profit}] = p - c, \qquad \operatorname{Var}(\text{profit}) = p(1-p)$$

In prose: buying at a price shifts the mean by that price but doesn't change the spread at all —
subtracting a constant moves the whole distribution without stretching it. Your edge is $p - c$;
your risk is fixed by $p$.

Across $n$ independent positions each with edge $e$ and variance $v$, total expected profit is
$ne$ and total variance is $nv$, so the standard deviation grows as $\sqrt{n}$. Signal grows
linearly, noise grows as a square root — that ratio, $e\sqrt{n}/\sqrt{v}$, is why sample size is
the whole game.

### Worked example

Two positions, both with 3 points of edge:

| | Price | Your $\hat{p}$ | Edge | Variance $p(1-p)$ | SD | Edge / SD |
|---|---|---|---|---|---|---|
| Market A | 0.50 | 0.53 | 0.03 | 0.2491 | 0.499 | 0.060 |
| Market B | 0.05 | 0.08 | 0.03 | 0.0736 | 0.271 | 0.111 |

Identical edge, but B has less than half the noise per bet. To detect a 3-point edge at 2 standard
errors, market A needs roughly $n = (2 \times 0.499 / 0.03)^2 \approx 1{,}107$ resolved forecasts;
market B needs $(2 \times 0.271 / 0.03)^2 \approx 327$. That is a 3.4× difference in how long you
have to wait to know whether you're any good.

This is not an abstraction for a 12-month project. It's the reason the market-selection decision
(which CLAUDE.md correctly marks human-owned, never auto-decided) has statistical consequences,
not just business ones.

### The EdgeLedger link

Direct line into **A3** (is my edge luck?) and **A4** (Kelly sizing). Kelly's optimal fraction for
a binary contract bought at $c$ with true probability $p$ is $f^* = (p - c)/(1 - c)$ — edge divided
by the amount at risk — and the variance drag that motivates fractional Kelly is exactly the
$p(1-p)$ term above compounding against you.

It also explains why `p_hat_lo` / `p_hat_hi` are in the schema from day one. A point forecast
without an interval hides the fact that a 0.50 forecast and a 0.05 forecast carry radically
different amounts of information.

> **Why this matters for the desk.** A researcher who reports edge without reporting variance has
> reported half a number. The desk question is never "is the expected value positive" — it's
> "what's the expected value per unit of risk, and how many observations until we'd know we were
> wrong?" Sharpe ratio (A6) is precisely that ratio.

---

## 5. Odds ↔ probability ↔ log-odds

### Intuition

Three coordinate systems for the same quantity, each convenient somewhere different:

- **Probability** $p \in [0,1]$ — what resolves, what gets scored, what a price is.
- **Odds** $p/(1-p) \in [0,\infty)$ — the ratio of "happens" to "doesn't". Bayes updates are
  multiplications here.
- **Log-odds** (logit) $\log\frac{p}{1-p} \in (-\infty,\infty)$ — unbounded and symmetric around
  zero. Bayes updates are *additions* here, and adding features linearly is exactly what a
  regression does.

The reason log-odds is the modelling space and not just a curiosity: probability is bounded, and
bounded quantities are awful to do linear algebra on. Add 0.10 to a probability of 0.95 and you
get 1.05, which doesn't exist. Add 0.10 to a log-odds of 2.94 and you get 3.04, which is fine and
corresponds to $p = 0.954$. The logit transform buys you an unbounded space where "add a bit of
evidence" is a legal operation everywhere.

### The maths

$$\text{odds} = \frac{p}{1-p}, \qquad p = \frac{\text{odds}}{1 + \text{odds}}$$

$$\operatorname{logit}(p) = \log\frac{p}{1-p}, \qquad p = \sigma(z) = \frac{1}{1 + e^{-z}}$$

In prose: odds is "probability it happens over probability it doesn't"; inverting requires dividing
by one-plus-odds to get back onto the [0,1] scale. Log-odds is the natural logarithm of the odds;
the inverse is the logistic (sigmoid) function, which squashes any real number back into (0,1).
`logit` and `sigmoid` are exact inverses.

Useful anchors worth memorising, because they make model coefficients readable at a glance:

| $p$ | odds | logit |
|---|---|---|
| 0.01 | 0.0101 | −4.60 |
| 0.05 | 0.0526 | −2.94 |
| 0.10 | 0.111 | −2.20 |
| 0.25 | 0.333 | −1.10 |
| 0.50 | 1.00 | 0.00 |
| 0.75 | 3.00 | +1.10 |
| 0.90 | 9.00 | +2.20 |
| 0.95 | 19.0 | +2.94 |
| 0.99 | 99.0 | +4.60 |

Symmetry: $\operatorname{logit}(1-p) = -\operatorname{logit}(p)$. And one log-odds unit ≈ an odds
ratio of $e \approx 2.718$.

Also worth knowing because sportsbook data arrives in these formats:

- **Decimal odds** $d$ (European): implied $p = 1/d$. Decimal 2.50 → 0.40.
- **American odds** $a$: for $a > 0$, $p = 100/(a + 100)$; for $a < 0$, $p = |a|/(|a| + 100)$.
  +150 → 0.40. −200 → 0.667.

### Worked example

A market shows Yes at **0.0455** — a genuine Kalshi-style long-shot price.

- Odds: $0.0455 / 0.9545 = 0.04767$, i.e. roughly 21-to-1 against.
- Log-odds: $\log(0.04767) = -3.043$.

Now suppose your model finds a feature worth **+0.5 log-odds** — a coefficient of 0.5 on a binary
feature that's currently on. New log-odds: $-3.043 + 0.5 = -2.543$. Back to probability:
$\sigma(-2.543) = 1/(1 + e^{2.543}) = 0.0729$.

So half a log-odds unit moved a 4.55c contract to 7.29c — a **60% relative increase** in price. The
same +0.5 applied at 0.50 moves you to $\sigma(0.5) = 0.622$, a 24% relative increase. Identical
coefficient, wildly different price impact, because the sigmoid is steepest in the middle and flat
at the tails.

This asymmetry is the entire reason long-shot markets are dangerous and also where the money is: a
small absolute mispricing at 0.04 is an enormous relative mispricing, and models built and
validated at mid-range probabilities behave unrecognisably out there.

### The EdgeLedger link

**B3 (logistic regression, months 5–6)** fits $\operatorname{logit}(p) = \beta_0 + \sum \beta_i x_i$.
Every coefficient it produces is denominated in log-odds. If you are not fluent in the table above,
you cannot read your own model output — "$\beta = 0.5$" is meaningless until you can see it as
"multiplies the odds by 1.65."

**B7 (ensembling)** blends models in log-odds space, because averaging probabilities of 0.02 and
0.40 gives 0.21 (dominated by the confident-in-the-middle model) whereas averaging log-odds gives
$(-3.89 + -0.41)/2 = -2.15 \to p = 0.104$ — the geometric-style blend that respects how much each
model is actually claiming.

**Invariant 6** also lives here: comparing $\hat{p}$ to the market baseline is a comparison you'll
usually want to make in log-odds, because a 2-point difference at 0.50 and a 2-point difference at
0.04 are not the same disagreement.

> **Why this matters for the desk.** Model coefficients, Bayesian updates, ensemble weights, and
> news impacts are all additive in log-odds and messy in probability. A researcher who thinks in
> probability keeps writing special-case clamps to stop values escaping [0,1]. A researcher who
> thinks in log-odds never needs one.

---

## 6. Vig and overround removal

### Intuition

A book that quotes both sides of a market quotes them so that the implied probabilities sum to
*more* than 1. The excess is the house's margin — the **vig** (vigorish) or **overround**. It's
not a forecast error; it's the price of the service.

Which means: **the quoted price is not the market's belief.** It is the market's belief plus a
markup. If you score your model against the vigged price, you flatter yourself on one side and
penalise yourself on the other, and if you score against the vigged price on a two-sided market
you are effectively scoring against a probability distribution that doesn't sum to 1 — which is
not a probability distribution.

For a bid/ask market like Kalshi or Polymarket the same phenomenon appears as the **spread**: the
bid and the ask straddle the market's belief, and the mid is your best cheap estimate of the
de-vigged number.

### The maths

Given quoted implied probabilities $q_1, \dots, q_k$ for the $k$ mutually exclusive outcomes, the
**booksum** (overround) is:

$$S = \sum_{i=1}^{k} q_i$$

In prose: add up the implied probabilities of every outcome. A fair book sums to exactly 1.
Anything above 1 is margin; the vig as a percentage of stake is $(S-1)/S$.

**Method 1 — multiplicative (proportional) normalisation:**

$$p_i = \frac{q_i}{S}$$

In prose: divide every quoted probability by the booksum so they sum to 1. This assumes the book
applied its margin proportionally across outcomes. Simplest, and the default.

**Method 2 — additive normalisation:**

$$p_i = q_i - \frac{S-1}{k}$$

In prose: subtract an equal share of the excess from each outcome. This assumes the margin was
applied as a flat amount per outcome rather than proportionally.

**Method 3 — Shin's method / power method.** Multiplicative normalisation is known to be wrong in
one specific, well-documented direction: it under-corrects long shots. Real books load more margin
onto long shots than on favourites (the **favourite–longshot bias**), so proportional removal
leaves long-shot de-vigged probabilities still too high. The power method solves for an exponent
$\alpha$ such that $\sum q_i^{\alpha} = 1$ and takes $p_i = q_i^{\alpha}$; Shin's method models an
insider-trading fraction instead. Both push long-shot probabilities down more than favourites.

For EdgeLedger's two-sided binary markets the multiplicative method is a defensible default, and
the honest thing is to record which method was used rather than pretend the choice doesn't exist.

### Worked example

**Two-way (the EdgeLedger case).** A market quotes:

- Yes: 0.0500
- No: 0.9700

Booksum: $S = 0.0500 + 0.9700 = 1.0200$. Overround: 2.00%. Vig as a fraction of stake:
$0.02/1.02 = 1.96\%$.

Multiplicative de-vig:

- $p_{\text{yes}} = 0.0500 / 1.0200 = 0.04902$
- $p_{\text{no}} = 0.9700 / 1.0200 = 0.95098$
- Sum: 1.0000 ✓

So the market's true implied probability of Yes is **0.0490**, not the quoted 0.0500.

Now suppose your model says $\hat{p} = 0.0455$ (our long-shot from section 5). Scored against the
**quoted** 0.0500, you look like you disagree by 0.45 points. Scored against the **de-vigged**
0.0490, you disagree by 0.35 points. On a single market that's noise. Across 5,000 forecasts, a
systematic 0.1-point bias in your baseline is the difference between "beats the market" and
"doesn't", and it is a bias you introduced yourself, in your own scoring code.

**Three-way, to show the general case.** A football match:

| Outcome | Decimal odds | Quoted $q_i = 1/d$ |
|---|---|---|
| Home | 2.10 | 0.4762 |
| Draw | 3.40 | 0.2941 |
| Away | 4.20 | 0.2381 |

$S = 1.0084$. Overround 0.84%. Multiplicative de-vig:

- Home: $0.4762/1.0084 = 0.4722$
- Draw: $0.2941/1.0084 = 0.2917$
- Away: $0.2381/1.0084 = 0.2361$
- Sum: 1.0000 ✓

Additive de-vig subtracts $0.0084/3 = 0.0028$ from each: 0.4734 / 0.2913 / 0.2353. Note the
disagreement between the two methods is largest, in relative terms, on the away side — the long
shot. On a real book with a 6% overround that discrepancy becomes material, which is precisely why
the method choice is a documented decision and not a helper-function detail.

### The EdgeLedger link

This is **invariant 6** made operational. The invariant says every metric is reported against the
market baseline — `brier_market` alongside `brier`, always. But `brier_market` is only a meaningful
baseline if it's computed against the market's *true* implied probability. Score against the vigged
quote and your baseline is systematically biased, in a direction that depends on which side of the
market you're forecasting. You would be comparing yourself to a strawman and reporting the result
as evidence.

Concretely, the schema already gives you what you need: `mkt_yes_bid` and `mkt_yes_ask` are stored
separately (invariant 2 — captured at write time, never joined afterwards). The mid,
`mkt_yes_mid`, is the cheap de-vig for a two-sided book. Storing bid and ask rather than only the
mid is what makes it possible to revisit the de-vig method later without re-running history — which
you cannot do if you only ever persisted the mid.

It also connects forward to **A5 (microstructure)**: the spread isn't only margin, it's also
compensation for adverse selection and inventory risk. De-vigging assumes the spread is symmetric
around belief. When it isn't — when there's one-sided flow — the mid is a biased estimate of belief
and the CLV metric is where you'd see it.

> **Why this matters for the desk.** "We beat the market by 40bps" is the single most common claim
> in this industry and the single most commonly wrong one, because the speaker measured against a
> price that included the market maker's fee. A desk that de-vigs consistently and documents the
> method can compare results across venues and across time. One that doesn't is generating numbers
> that aren't comparable to anything, including their own last quarter.

---

## Check yourself

Six exercises. Work them on paper before opening the answers.

**1.** A Kalshi market shows Yes bid 0.0400, ask 0.0500. The No side shows bid 0.9500, ask 0.9600.
What's the two-sided booksum using asks? What's the de-vigged Yes probability using multiplicative
normalisation on the asks? How does that compare to the Yes mid?

**2.** Convert $p = 0.0455$ to log-odds. Add a feature coefficient of $-0.8$. Convert back. Express
the move both in absolute cents and as a relative change.

**3.** Your prior on an event is 0.25. New evidence arrives that occurs 40% of the time when the
event happens and 15% of the time when it doesn't. Compute the posterior using the odds form of
Bayes.

**4.** You have 3 points of edge on a market priced at 0.20. Compute expected profit per contract
and the standard deviation of profit per contract. How many independent resolved forecasts would
you need for your cumulative profit to be 2 standard errors above zero?

**5.** A three-way book quotes decimal odds 1.55 / 4.20 / 6.50. Compute the overround, then de-vig
both multiplicatively and additively. Which outcome do the two methods disagree on most in relative
terms, and why is that the expected direction?

**6.** Your model outputs $\hat{p} = 0.62$. The market shows bid 0.57, ask 0.61, and the No side
asks 0.44. Is your `edge` field positive? Would you actually take the trade? Explain the difference
between those two questions in one sentence.

<details>
<summary>Worked answers</summary>

**1.** Using asks (what you'd pay on each side): $S = 0.0500 + 0.9600 = 1.0100$. Overround 1.00%.
Multiplicative de-vig of Yes: $0.0500 / 1.0100 = 0.049505 \approx \mathbf{0.0495}$.

The Yes mid is $(0.0400 + 0.0500)/2 = 0.0450$.

These disagree by 0.45 points, which is large relative to a 4.5c contract — a 10% relative
difference. Why: the ask-based de-vig assumes you cross the spread on both sides, so it inherits
the full round-trip cost; the mid assumes the true price sits centrally between bid and ask. On a
thin long-shot market the spread is wide and this choice matters a lot. The mid is the better
estimate of *belief*; the ask-based number is closer to *executable* cost. EdgeLedger's `edge` uses
the mid (belief), which is right for a research metric — and this exercise is exactly why the raw
bid and ask are both persisted rather than only the derived mid.

---

**2.** $\operatorname{logit}(0.0455) = \log(0.0455/0.9545) = \log(0.047669) = -3.0433$.

Add $-0.8$: $-3.8433$.

$\sigma(-3.8433) = 1/(1 + e^{3.8433}) = 1/(1 + 46.68) = \mathbf{0.02097}$.

Absolute move: $0.0455 \to 0.0210$, i.e. **−2.45 cents**.
Relative move: $0.0210/0.0455 - 1 = \mathbf{-53.9\%}$ — the contract lost more than half its value.

Compare the same $-0.8$ applied at $p = 0.50$: $0 - 0.8 = -0.8 \to \sigma(-0.8) = 0.3100$. Absolute
move −19 cents, relative move −38%. So in *absolute* terms the mid-market move is far bigger; in
*relative* terms the long-shot move is bigger. That's the sigmoid's shape: steep in the middle,
flat at the tails, but the tails start from a small base.

---

**3.** Prior odds: $0.25 / 0.75 = 0.3333$.

Likelihood ratio: $0.40 / 0.15 = 2.6667$.

Posterior odds: $0.3333 \times 2.6667 = 0.8889$.

Posterior probability: $0.8889 / (1 + 0.8889) = \mathbf{0.4706}$.

Sanity check via the direct form: $P(E) = 0.40(0.25) + 0.15(0.75) = 0.10 + 0.1125 = 0.2125$, so
$P(H \mid E) = 0.10/0.2125 = 0.4706$ ✓.

In log-odds: prior $\log(0.3333) = -1.0986$, log-LR $\log(2.6667) = +0.9808$, posterior
$-0.1178 \to \sigma(-0.1178) = 0.4706$ ✓. Note the update was a single *addition* in log-odds
space. That is the whole argument for working there.

---

**4.** Price 0.20, so $\hat{p} = 0.23$.

Expected profit per contract: $0.23 - 0.20 = \mathbf{\$0.03}$.

Variance of the payoff: $p(1-p) = 0.23 \times 0.77 = 0.1771$. SD $= \sqrt{0.1771} = \mathbf{0.4208}$.
(Buying at a fixed price shifts the mean but not the spread, so this is also the SD of profit.)

For cumulative profit over $n$ bets: mean $= 0.03n$, SD $= 0.4208\sqrt{n}$. Setting
$0.03n = 2 \times 0.4208\sqrt{n}$:

$$\sqrt{n} = \frac{2 \times 0.4208}{0.03} = 28.05 \quad \Rightarrow \quad n = \mathbf{787}$$

Roughly 790 independent resolved forecasts. Two things to sit with: (a) this is the *optimistic*
case, because it assumes your 0.23 is correct — if your edge is really 1.5 points you need ~3,100;
(b) "independent" is doing enormous work, and correlated positions on the same slate inflate this
number substantially (A6). A 12-month log that produces a few thousand resolved forecasts is
right at the edge of being able to answer this question, which is precisely why the log starts in
month 1 rather than after the models are good.

---

**5.** Quoted: $1/1.55 = 0.6452$, $1/4.20 = 0.2381$, $1/6.50 = 0.1538$.

$S = 1.0371$. **Overround 3.71%.** Vig as fraction of stake: $0.0371/1.0371 = 3.58\%$.

Multiplicative ($q_i/S$):
- 0.6452/1.0371 = **0.6221**
- 0.2381/1.0371 = **0.2296**
- 0.1538/1.0371 = **0.1483**
- Sum 1.0000 ✓

Additive ($q_i - 0.0371/3 = q_i - 0.012367$):
- 0.6452 − 0.0124 = **0.6328**
- 0.2381 − 0.0124 = **0.2257**
- 0.1538 − 0.0124 = **0.1415**
- Sum 1.0000 ✓

Absolute disagreements are identical in size for the outer two (≈0.0107 and ≈0.0069) but the
*relative* disagreement is largest on the long shot: $(0.1483 - 0.1415)/0.1483 = 4.6\%$, versus
$1.7\%$ on the favourite.

Expected direction: the additive method removes an equal absolute amount from each outcome, which
is a proportionally much bigger haircut on a small probability. That happens to point the same way
as the empirically documented favourite–longshot bias — books load *more* margin onto long shots,
so the true de-vigged long-shot probability is lower than proportional removal suggests. It's the
reason Shin/power methods exist: multiplicative normalisation is the convenient default and it is
known to be biased on exactly the contracts where relative mispricings are largest.

---

**6.** `edge` in `forecast_log` = $\hat{p} - \text{mkt\_yes\_mid} = 0.62 - 0.59 = \mathbf{+0.03}$.
Yes, positive.

Would you take it? You'd pay the ask, 0.61, against a belief of 0.62 — **1 point of executable
edge**, before fees, before slippage, before the possibility that your model is 1 point
miscalibrated (which, at month 1, it certainly is). The de-vigged market belief here is roughly
$0.61/(0.61 + 0.44) = 0.581$ using both asks, so the market's true number is even a touch below
mid, nudging your disagreement to ~3.9 points of *belief* but leaving executable edge unchanged.

The one-sentence difference: **`edge` measures disagreement with the market's belief and is the
research quantity; executable edge measures disagreement net of the spread you must cross and is
the trading quantity — and a system that reports the first as though it were the second is
overstating itself by exactly half the spread on every single position.**

</details>
