# B1 — What a Model Is

**Core question: why does a model beat a guess?**

A model is a function from things you can observe to a probability of something you can't yet
observe. That's the whole definition. Everything interesting is in the qualifiers: *which*
observables, *when* they were observable, how the function is chosen, and — the question that
decides whether any of it was worth doing — whether the function found structure that will persist
or memorised noise that won't.

This note builds the vocabulary you need before B2 (baselines) tells you what you're competing
against and B3 (regression) shows you how the mapping is actually fitted. It also justifies the
choice of output space that the rest of Track B assumes without comment: log-odds.

---

## 1. Features → probability: the mapping

### Intuition

Strip away the machinery and a model is three things:

1. **A feature vector** $x$ — the numbers you extracted from the world at a specific moment.
2. **A functional form** $f$ — the shape of the relationship you're willing to entertain.
3. **Parameters** $\theta$ — the specific numbers within that shape, chosen by fitting to data.

$$\hat{p} = f(x; \theta)$$

In prose: your predicted probability is what you get when you push your observed features through
a chosen function, using parameters learned from history. Nothing more mysterious than that.

The reason a model beats a guess is not that it's clever. It's that it applies the *same* mapping
to every case, so its errors are measurable and correctable. A guess is a different function every
time — it can't be scored, can't be calibrated, can't be debugged. A model that is *worse* than a
guess on average is still more valuable to a desk, because you can find out by how much and in
which direction.

This is worth being blunt about, because it is the reason EdgeLedger's month-1 models are
deliberately terrible. `market_mirror` copies the market and `base_rate` returns a historical
frequency. Neither has edge by construction. Both are *models*: deterministic, versioned functions
with recorded inputs and recorded outputs. That property — not accuracy — is what makes the log
worth twelve months.

### The maths

Being precise about what's fixed and what's learned matters more than it looks.

- $x \in \mathbb{R}^d$ — the feature vector, computed at forecast time.
- $\theta$ — parameters, fitted once on training data and then **frozen** for the forecast.
- $y \in \{0, 1\}$ — the realised outcome, known only after resolution.
- $\hat{p} = f(x; \theta) \in (0,1)$ — the forecast.

The **training** step chooses $\theta$ to minimise a loss over historical pairs $(x_i, y_i)$:

$$\hat{\theta} = \arg\min_{\theta} \sum_{i=1}^{n} L\big(y_i,\, f(x_i; \theta)\big)$$

In prose: search the parameter space for the setting that made the smallest total error on the
data you've already seen. For binary outcomes $L$ is usually log loss (equivalently, maximising
likelihood) or Brier score.

The **inference** step is then trivial: plug in a new $x$, get $\hat{p}$ out. The asymmetry is
important — training is expensive and happens rarely; inference is cheap and happens constantly.
EdgeLedger's `model_version` field exists precisely to record which frozen $\theta$ produced a
given row.

### Worked example

Kalshi: *"Will Team A win?"* Suppose a two-feature model:

- $x_1$ = Elo rating difference / 400 = **0.25**
- $x_2$ = home indicator = **1**

Logistic form (B3 will fit this properly):

$$z = \beta_0 + \beta_1 x_1 + \beta_2 x_2 = -0.05 + 2.20(0.25) + 0.35(1) = 0.850$$

$$\hat{p} = \sigma(0.850) = \frac{1}{1 + e^{-0.850}} = 0.7006$$

So $\hat{p} = 0.70$. The market shows 0.66 / 0.68, mid 0.67. Your `edge` field:
$0.70 - 0.67 = +0.03$.

Notice what got logged in `ForecastLogRow` and why each field is there:

| Field | Value | Why it must be recorded |
|---|---|---|
| `p_hat` | 0.7006 | the claim |
| `feature_vector` | `{"elo_diff_norm": 0.25, "is_home": 1}` | so the claim is reproducible |
| `feature_set_version` | `v1` | features change; the log must know which definition |
| `model_version` | `1.0.0` | $\theta$ changed → different model, same name |
| `code_git_sha` | `b22898e…` | the $f$ itself changed |
| `feature_cutoff_ts_utc` | 2026-08-03T14:00:00Z | which world-state $x$ came from |
| `mkt_yes_mid` | 0.67 | captured now, never joined later (invariant 2) |

A forecast without those seven things is an opinion. With them, it's an experiment.

> **Why this matters for the desk.** The value of a research function isn't the model, it's the
> *record* of the model's claims. Any desk can generate probabilities. The one that can answer
> "what did version 1.2.0 say about this market class in Q2, and what were its inputs" is the one
> that can improve. Everyone else is re-running the same mistakes with new hyperparameters.

---

## 2. Generative vs discriminative

### Intuition

Two fundamentally different attacks on the same problem.

A **discriminative** model learns the boundary directly: given these features, what's the
probability of Yes? It never asks how the features came to be. Logistic regression is the
canonical example — it models $P(y \mid x)$ and nothing else.

A **generative** model learns the mechanism: what process produces outcomes in this domain, and
what does that process imply about this particular event? A Poisson goal-scoring model doesn't
learn "what's the probability of a home win" — it learns the rate at which each team scores, then
*simulates* matches and counts how often the home team ends up ahead.

The trade is real and it's not a matter of taste:

| | Discriminative | Generative |
|---|---|---|
| Models | $P(y \mid x)$ | $P(x, y)$ or the data-generating process |
| Data efficiency | needs more | needs less (structure substitutes for data) |
| If structure is right | fine | better |
| If structure is wrong | fine | badly wrong, confidently |
| Derived markets | one model per market | **one model, all markets** |
| Interpretability | coefficients | mechanism parameters |

The last row is the one that matters commercially and it's why Track B has both B3 and B4.

### The maths

**Discriminative:** parameterise the conditional directly.

$$P(y = 1 \mid x) = \sigma(\beta^\top x)$$

In prose: assume the log-odds of the outcome is a linear function of the features, and fit the
weights. You have learned nothing about the distribution of $x$ — you couldn't generate a
plausible new match from this model, and you don't need to.

**Generative:** parameterise the process, then derive.

$$G_{\text{home}} \sim \text{Poisson}(\lambda_H), \qquad G_{\text{away}} \sim \text{Poisson}(\lambda_A)$$

$$\lambda_H = \exp(\mu + \text{att}_H - \text{def}_A + \gamma), \qquad \lambda_A = \exp(\mu + \text{att}_A - \text{def}_H)$$

In prose: assume each team's goal count is Poisson-distributed with a rate driven by its attacking
strength, the opponent's defensive strength, a baseline, and a home advantage $\gamma$. The
exponential keeps rates positive. Fit the attack/defence parameters to historical scorelines.

Then **every** market is a query against the fitted joint distribution:

$$P(\text{home win}) = \sum_{h > a} P(G_H = h)\,P(G_A = a)$$

$$P(\text{over } 2.5) = P(G_H + G_A \ge 3), \qquad P(\text{both score}) = P(G_H \ge 1)\,P(G_A \ge 1)$$

In prose: sum the joint probability over every scoreline satisfying the condition. One fitted model
answers home/draw/away, totals, both-teams-to-score, correct score, and any exotic you're later
asked to price — from the same parameters.

### Worked example

Fitted rates: $\lambda_H = 1.6$, $\lambda_A = 1.1$.

Poisson pmf: $P(G = k) = e^{-\lambda}\lambda^k / k!$ — in prose, the probability of exactly $k$
events when events arrive independently at average rate $\lambda$.

| $k$ | $P(G_H = k)$ | $P(G_A = k)$ |
|---|---|---|
| 0 | 0.2019 | 0.3329 |
| 1 | 0.3230 | 0.3662 |
| 2 | 0.2584 | 0.2014 |
| 3 | 0.1378 | 0.0738 |
| 4 | 0.0551 | 0.0203 |
| ≥5 | 0.0237 | 0.0053 |

Derived markets, all from those same two numbers:

- **Home win** $P(G_H > G_A) \approx 0.4585$
- **Draw** $\approx 0.2408$
- **Away win** $\approx 0.3007$
- **Over 2.5 goals** $P(G_H + G_A \ge 3)$: the sum is Poisson(2.7), so
  $1 - e^{-2.7}(1 + 2.7 + 2.7^2/2) = 1 - 0.0672(1 + 2.7 + 3.645) = 1 - 0.4936 = \mathbf{0.5064}$
- **Both teams score** $(1 - 0.2019)(1 - 0.3329) = 0.7981 \times 0.6671 = \mathbf{0.5324}$

Four contracts priced from two parameters, all mutually consistent by construction. A
discriminative approach needs four separate models and gives you no guarantee they cohere — you can
easily end up with a home-win probability and a correct-score distribution that contradict each
other, which is both embarrassing and arbitrageable against you.

The catch, and it's serious: the Poisson model assumes goals are independent and that scoring
intensity is constant through the match. Both are false. Low-scoring matches (0-0, 1-0, 1-1) occur
more often than Poisson predicts, which is exactly what the **Dixon-Coles adjustment** (B4) exists
to correct. Get the structure wrong and a generative model doesn't degrade gracefully — it produces
confident nonsense in a specific, systematic region of the outcome space.

### The EdgeLedger link

The roadmap runs discriminative-first for good reason. **B3 (logistic regression, months 5–6)** is
discriminative — hard to get catastrophically wrong, easy to validate, honest about what it doesn't
know. **B4 (Poisson / Dixon-Coles, months 6–7)** is generative and unlocks the "simulate once,
price every derived market" capability that is genuinely differentiating on an event-contract desk
listing dozens of correlated contracts per game.

Building B4 before B3 would be building the higher-variance thing before you have the
lower-variance thing to check it against. The ordering is a risk decision, not a curriculum
convenience.

> **Why this matters for the desk.** A desk quoting 30 contracts on one game cannot afford 30
> independent models — they'd be mutually inconsistent and the inconsistencies are precisely what
> sharp counterparties trade against. The generative model is the answer to "why is our
> correct-score book consistent with our totals book?" But the discriminative model is what you
> ship first, because it fails visibly rather than silently.

---

## 3. Signal vs noise

### Intuition

Every observed outcome is structure plus randomness:

$$\text{observed} = \text{signal} + \text{noise}$$

Signal is the part that would repeat if you could re-run the world. Noise is the part that
wouldn't. The forecaster's entire job is separating them — and the difficulty is that noise, by
construction, looks exactly like signal in-sample. That's what makes it noise.

The trap specific to this domain: sports and event outcomes are *extremely* noisy. The best team
loses to the worst team routinely. A model that explains 60% of the variance in match outcomes
doesn't exist and never will, because most of the variance genuinely isn't explainable — a
deflection, a red card, a referee decision. The irreducible noise floor is high.

Which flips the goal on its head. You are not trying to predict outcomes well. **You are trying to
predict them slightly better than the market does.** A model with an R² of 0.06 that beats a market
consensus with an R² of 0.05 is a fantastic model. A model with an R² of 0.30 that beats nothing is
worthless. Absolute accuracy is not the objective, which is exactly what invariant 6 encodes.

### The maths

Decompose the expected squared error of a forecast $\hat{p}$ against the truth $y$:

$$\mathbb{E}[(y - \hat{p})^2] = \underbrace{\mathbb{E}[(y - p^*)^2]}_{\text{irreducible}} + \underbrace{(p^* - \hat{p})^2}_{\text{your error}}$$

where $p^*$ is the true conditional probability given all available information.

In prose: your total squared error splits into two pieces. The first is the randomness inherent in
a binary outcome even if you knew the true probability exactly — it equals $p^*(1-p^*)$ and no
model can reduce it. The second is how far your forecast sits from the truth, and it's the only
part you control.

Concretely: if the true probability is 0.55, then even a perfect forecaster has expected Brier
score $0.55 \times 0.45 = 0.2475$. A Brier of 0.24 is not evidence of a bad model. It might be a
*perfect* model. This is why a raw Brier score in isolation is uninterpretable, and why
`brier_market` must sit next to it.

The **skill score** normalises this away:

$$\text{Skill} = 1 - \frac{\text{Brier}_{\text{model}}}{\text{Brier}_{\text{baseline}}}$$

In prose: what fraction of the baseline's error did you remove? Positive means you beat the
baseline; zero means you matched it; negative means you'd have done better copying it.

### Worked example

100 resolved Polymarket contracts. Your model and the market both forecast each one.

- Model Brier: **0.2380**
- Market Brier: **0.2410**
- Skill score: $1 - 0.2380/0.2410 = \mathbf{0.0124}$

You removed 1.24% of the market's error. That sounds like nothing. In this business it would be
excellent — *if it's real*.

Is it? The per-forecast Brier difference has a standard deviation of, say, 0.11 in this sample. The
standard error of the mean difference over $n = 100$ is $0.11/\sqrt{100} = 0.011$. Your observed
mean difference is 0.0030. That's $0.0030/0.011 = 0.27$ standard errors from zero.

**You have no evidence of anything.** You'd need roughly $n = (2 \times 0.11 / 0.0030)^2 \approx
5{,}400$ resolved forecasts to detect a difference this size at two standard errors.

This calculation is the reason EdgeLedger is a twelve-month project rather than a weekend one, and
the reason the log starts in month 1 with models that are *known* to have no edge. You cannot
compress the sample-size requirement by having a better idea. The clock is the binding constraint,
so you start the clock first and improve the model while it runs.

### The EdgeLedger link

Invariant 6 — *every metric reported against the market baseline* — is this section compiled into
a rule. And `market_mirror` is the diagnostic that makes it enforceable: since it copies
`mkt_yes_mid` exactly, its Brier score *must* be statistically indistinguishable from
`brier_market`. If it isn't, the bug is in the pipeline — a timestamp misalignment, a resolution
join error, a de-vig inconsistency — not in the model. It's a null-hypothesis canary for the
measurement layer itself, which is a genuinely unusual thing to build and exactly the kind of
detail that reads as serious to a hiring desk.

**B6 (validation, months 9–10)** is where this becomes adversarial. The track README already flags
it as the highest-value rung, and the reason is this section: when signal is scarce and noise is
abundant, any sufficiently flexible search will find something. Deflated Sharpe, walk-forward
validation, and multiple-comparison correction (A3) all exist to answer one question — *is the
thing I found signal, or did I try enough things that noise was bound to look like signal
eventually?*

> **Why this matters for the desk.** The failure mode isn't a model that doesn't work. It's a model
> that worked in backtest for reasons nobody understood, deployed at size, and reverted. A
> researcher whose first instinct on seeing a good result is "how many observations, and what's the
> standard error" is the one you can trust with capital.

---

## 4. Bias-variance decomposition

### Intuition

Two ways to be wrong, and reducing one usually increases the other.

**Bias** is being systematically wrong — your functional form can't represent reality. A linear
model on a genuinely curved relationship is biased no matter how much data you feed it. It's wrong
in the same direction every time.

**Variance** is being unstable — refit on a different sample and you get a materially different
model. A deep tree with 40 features on 300 matches has low bias and enormous variance: it fits this
sample beautifully and the next one badly, because it fitted the sample's noise.

The intuition that makes this stick: bias is *underfitting* (too simple to see the pattern),
variance is *overfitting* (complex enough to see patterns that aren't there). Model complexity is
the dial between them, and it has an interior optimum, not a monotone one.

### The maths

For squared error, expected over training sets $D$:

$$\mathbb{E}_D\big[(y - \hat{f}(x))^2\big] = \underbrace{\big(\mathbb{E}_D[\hat{f}(x)] - f^*(x)\big)^2}_{\text{Bias}^2} + \underbrace{\mathbb{E}_D\big[(\hat{f}(x) - \mathbb{E}_D[\hat{f}(x)])^2\big]}_{\text{Variance}} + \underbrace{\sigma^2}_{\text{Irreducible}}$$

In prose, three terms:

1. **Bias²** — take the average prediction your procedure makes across all possible training sets,
   and see how far that average sits from the truth. Systematic offset. More data doesn't help.
2. **Variance** — how much your prediction bounces around that average as the training set
   changes. Instability. More data *does* help, because it damps the bounce.
3. **Irreducible error** — section 3's noise floor. Nothing helps.

The critical structural point: **bias and variance both contribute to error as squares, and
complexity trades them against each other.** Total error as a function of complexity is U-shaped.
Both ends are bad. The left end feels safe and isn't.

### Worked example

Forecasting home wins. Ground truth: $p^* = 0.62$ for this fixture profile. Three approaches, each
refit on 5 different 200-match samples:

| Model | Predictions across the 5 samples | Mean | Bias | Bias² | Variance |
|---|---|---|---|---|---|
| **A** Global base rate | 0.54, 0.54, 0.55, 0.54, 0.54 | 0.542 | −0.078 | 0.00608 | 0.00002 |
| **B** Logistic, 3 features | 0.60, 0.63, 0.59, 0.62, 0.61 | 0.610 | −0.010 | 0.00010 | 0.00020 |
| **C** Boosted trees, 40 features | 0.71, 0.48, 0.66, 0.55, 0.74 | 0.628 | +0.008 | 0.00006 | 0.01018 |

Reducible error (Bias² + Variance):

- **A:** 0.00610 — nearly all bias. Rock stable, systematically 8 points too low. Underfit.
- **B:** 0.00030 — **best.** Small bias, small variance.
- **C:** 0.01024 — nearly all variance. Its *average* prediction is the most accurate of the three
  (bias 0.008!) and it is the worst model by a factor of 34. Any single fit of C could be 0.48 or
  0.74 against a truth of 0.62 — a 26-point spread.

Model C is the one that produces a beautiful backtest. It is also the one that loses money. And
note that its bias — the thing that looks like accuracy — is genuinely excellent. Averaging over
training sets is not something you get to do in production; you get one fit.

Two levers move C leftward:

- **Regularisation** (B3): an L2 penalty $\lambda \sum \beta_j^2$ shrinks coefficients toward zero.
  In prose: you're telling the fit that large weights must earn their keep against a penalty, which
  deliberately introduces a little bias to buy a lot of variance reduction. L1 ($\lambda \sum
  |\beta_j|$) additionally drives weights exactly to zero, doing feature selection as a side
  effect.
- **Hierarchical pooling** (B5): shrink each team's estimate toward the league mean in proportion
  to how little data that team has. Same trade, applied per-parameter rather than globally, and
  it's a Bayesian posterior rather than a penalty — see A1 §3.

### The EdgeLedger link

This decomposition is the *reason* the roadmap is ordered the way it is. **B2's rule — never build
a model without beating a baseline first** — is a bias-variance statement: the baseline is the
maximally-biased, minimally-variant option, and if your low-bias model can't beat it out-of-sample,
its variance is eating the bias reduction and then some.

`base_rate` v1.0.0 is model A above, in the repo, from month 1. It's the honest floor. Every later
model has to clear it *and* the market, and the log makes both comparisons computable at any point
in the twelve months rather than asserted at the end.

**B6** then supplies the only reliable measurement of variance: out-of-sample, time-ordered
evaluation. In-sample error measures bias and *rewards* variance, which is why an in-sample number
is worse than no number — it's a number pointing the wrong way.

> **Why this matters for the desk.** Every quant interview includes some version of "your backtest
> looks great, why don't I believe it?" The answer is this section. And the practical desk instinct
> that follows from it — that a simple model you understand, sized appropriately, beats a complex
> model you don't — is not conservatism, it's the U-curve.

---

## 5. Why log-odds is the natural space

### Intuition

Four independent arguments converge on the same answer, which is usually a sign the answer isn't
arbitrary.

**Argument 1 — the range problem.** Probability lives in [0,1]. Linear models produce outputs in
$(-\infty, \infty)$. Fitting a linear model directly to a probability produces predictions like
1.15 and −0.08, which you then have to clamp, and the clamping is a lie that hides how wrong the
model is. Log-odds is unbounded, so a linear model in log-odds space can never produce an illegal
probability. The sigmoid guarantees it.

**Argument 2 — evidence is additive here.** From A1 §3: Bayes in odds space is multiplication, and
in log-odds space it's addition. So "combine independent pieces of evidence" is literally a sum in
log-odds. A model of the form $z = \beta_0 + \sum \beta_i x_i$ isn't a convenient approximation —
it's what Bayesian evidence accumulation *looks like* when each feature contributes independently.
The linear form is derived, not assumed.

**Argument 3 — uniform sensitivity.** In probability space, moving from 0.50 to 0.55 and from 0.95
to 1.00 are both "+0.05", but the second is impossible and the first is routine. In log-odds, equal
steps mean equal changes in evidential weight everywhere on the scale. Distances become meaningful,
which matters enormously for anything involving averaging, distance, or gradients.

**Argument 4 — the loss function agrees.** The natural loss for binary outcomes is log loss.
Fitting a logistic model by maximum likelihood under log loss gives a gradient of
$(\hat{p} - y)\,x$ — the residual times the feature. Clean, convex, single global optimum. The
parameterisation and the loss are matched; that's not a coincidence, it's the exponential family
doing its job.

### The maths

The **logit link** and its inverse:

$$z = \operatorname{logit}(p) = \log\frac{p}{1-p}, \qquad p = \sigma(z) = \frac{1}{1+e^{-z}}$$

In prose: the logit maps a probability onto the whole real line by taking the log of the odds; the
sigmoid maps it back. They're exact inverses, both monotone, both smooth.

**Logistic regression** is then just a linear model in that space:

$$\log\frac{\hat{p}}{1-\hat{p}} = \beta_0 + \beta_1 x_1 + \dots + \beta_d x_d$$

In prose: the log-odds of the outcome is a weighted sum of the features plus an intercept. Each
$\beta_i$ answers: *how much does the log-odds move per unit of $x_i$, holding everything else
fixed?* Exponentiating gives the **odds ratio** — $e^{\beta_i}$ is the multiplicative effect on the
odds, which is how the coefficient becomes speakable in English.

**Log loss:**

$$L = -\big[y\log\hat{p} + (1-y)\log(1-\hat{p})\big]$$

In prose: if the outcome is 1, you're penalised by the negative log of the probability you assigned
to 1; if 0, by the negative log of the probability you assigned to 0. Because $-\log$ blows up near
zero, being confidently wrong is punished savagely — assigning 0.01 to something that happens costs
you 4.61, versus 0.69 for a coin-flip forecast. That asymmetry is why log loss and Brier disagree
about tail behaviour and why methodology.md reports both.

**Blending in log-odds** (logarithmic opinion pooling, B7):

$$z_{\text{blend}} = w z_{\text{model}} + (1-w) z_{\text{market}}$$

In prose: take a weighted average of the log-odds, not of the probabilities. This is a geometric
mean of the odds, and it behaves correctly at the tails where the arithmetic mean of probabilities
does not.

### Worked example

Take our long shot: market shows **0.0455** for Yes.

$$z_{\text{mkt}} = \log(0.0455 / 0.9545) = -3.043$$

Your logistic model returns $z_{\text{model}} = -2.400$, i.e. $\hat{p} = 0.0832$.

**Blend at $w = 0.3$ (30% model, 70% market — appropriate humility for month 5).**

*In log-odds:*
$$z = 0.3(-2.400) + 0.7(-3.043) = -0.720 - 2.130 = -2.850 \quad\Rightarrow\quad \hat{p} = \sigma(-2.850) = \mathbf{0.0547}$$

*In probability space, for contrast:*
$$0.3(0.0832) + 0.7(0.0455) = 0.02496 + 0.03185 = \mathbf{0.0568}$$

A 0.21-point difference on a 5c contract — about 4% relative. Modest here. Now push the model to a
genuinely confident $\hat{p} = 0.30$ ($z = -0.847$):

- Log-odds blend: $0.3(-0.847) + 0.7(-3.043) = -2.384 \Rightarrow \mathbf{0.0844}$
- Probability blend: $0.3(0.30) + 0.7(0.0455) = \mathbf{0.1219}$

Now the gap is 3.75 points on a contract the market prices at 4.55c — the arithmetic blend is
**44% higher**. The probability-space blend lets the confident model drag the price up almost
linearly; the log-odds blend requires the model to overcome the market's strong evidential position
against, which is the correct behaviour. At the tails, arithmetic averaging systematically
over-weights whichever opinion is closer to 0.5.

**Reading coefficients.** A fitted $\beta_{\text{is\_home}} = 0.35$ means the odds ratio is
$e^{0.35} = 1.42$: playing at home multiplies the odds of winning by 1.42, everywhere on the scale.
At $p = 0.50$ (odds 1.00) that takes you to odds 1.42, i.e. $p = 0.587$ — a 8.7-point move. At
$p = 0.0455$ (odds 0.0477) it takes you to odds 0.0677, i.e. $p = 0.0634$ — a 1.8-point move but a
39% relative one. **One coefficient, correctly context-sensitive, with no special-casing.** Try
expressing "home advantage" as an additive probability bump and you'll need a different number for
every price level and you'll still produce values above 1 somewhere.

### The EdgeLedger link

- **B3** fits in log-odds. Every coefficient it emits is a log-odds quantity, and the
  `feature_vector` stored in `forecast_log` is the $x$ that got multiplied by them. Reproducing any
  historical forecast is a dot product away.
- **B7** blends in log-odds, per the worked example. Shrinking toward market price is the single
  most reliable improvement available to a young model, and it only behaves sensibly in this space.
- **A1 §5** established the conversions; this section is why you'll live in them.
- `p_hat` is stored as a `Decimal` in [0,1], not as log-odds, and that's correct: the log is the
  *working* space, the probability is the *contract* space — it's what resolves, what scores, and
  what a price is. The schema stores the thing being claimed, not the intermediate representation.
  Note the boundary condition that forces this: $\hat{p} = 0$ or $1$ has infinite log-odds and
  infinite log loss, so any model that can emit exactly 0 or 1 needs clipping before scoring.

> **Why this matters for the desk.** "The injury is worth 30 basis points" is unanswerable without
> knowing the current price. "The injury is worth −0.4 log-odds" is a complete statement that
> applies at any price. Desks that quantify news impact in log-odds can accumulate a library of
> reusable adjustments; desks that quantify it in cents are re-deriving the same fact for every
> market.

---

## Check yourself

Six exercises. Numbers are real; work them before opening the answers.

**1.** A logistic model has $\beta_0 = -0.30$, $\beta_{\text{elo}} = 2.10$,
$\beta_{\text{rest\_adv}} = 0.18$. For a fixture with normalised Elo difference 0.42 and rest
advantage 2 days, compute $z$ and $\hat{p}$. The market shows bid 0.58, ask 0.62 — what goes in the
`edge` field?

**2.** Fitted Poisson rates $\lambda_H = 1.9$, $\lambda_A = 0.8$. Compute $P(\text{0-0})$,
$P(\text{under 2.5 goals})$, and $P(\text{away team keeps a clean sheet})$. State one assumption
this model makes that is empirically false, and name the adjustment that fixes it.

**3.** Two models, evaluated by refitting on 4 disjoint samples. Model P predicts 0.48, 0.51, 0.49,
0.50; Model Q predicts 0.38, 0.67, 0.44, 0.71. True probability is 0.55. Compute bias², variance
and total reducible error for each. Which would you deploy, and what does the answer say about how
much you should trust a single impressive backtest?

**4.** Your model has $\hat{p} = 0.12$; the market (de-vigged) is at 0.06. Blend at $w = 0.25$ in
log-odds space and in probability space. Report both, and the relative difference. Which is the
defensible number and why?

**5.** Over 400 resolved forecasts your Brier is 0.2205 and the market's is 0.2240. The per-forecast
Brier difference has standard deviation 0.095. Compute the skill score and the t-statistic. What do
you write in the monthly update, and what is the smallest true edge you'd have been able to detect
here?

**6.** `market_mirror` posts a Brier of 0.2311 over the same window where `brier_market` is 0.2240.
By construction these should be equal. List three specific pipeline defects that would produce
exactly this signature, and say which invariant each one violates.

<details>
<summary>Worked answers</summary>

**1.** $z = -0.30 + 2.10(0.42) + 0.18(2) = -0.30 + 0.882 + 0.36 = \mathbf{0.942}$.

$\hat{p} = \sigma(0.942) = 1/(1 + e^{-0.942}) = 1/(1 + 0.3899) = \mathbf{0.7195}$.

Market mid $= (0.58 + 0.62)/2 = 0.60$. `edge` $= 0.7195 - 0.60 = \mathbf{+0.1195}$.

That is a **12-point** claim of edge against a liquid market. Treat it as a bug report, not a
signal. At month 5 the realistic prior on a 12-point disagreement is: leakage in a feature (does
`rest_adv` use the actual rest, knowable pre-game, or something derived from the played match?),
a stale `mkt_yes_mid`, or a coefficient fitted on a sample that included this fixture. Invariant 3
and `tests/test_point_in_time.py` exist because this is the *expected* first explanation. Edges
this size in efficient markets are almost always your own error looking back at you.

---

**2.** $P(G_H = 0) = e^{-1.9} = 0.14957$. $P(G_A = 0) = e^{-0.8} = 0.44933$.

**$P(0\text{-}0) = 0.14957 \times 0.44933 = \mathbf{0.06721}$.**

**Under 2.5** = $P(G_H + G_A \le 2)$. The sum is Poisson(2.7):
$e^{-2.7} = 0.067206$; $P(0) = 0.067206$, $P(1) = 0.181455$, $P(2) = 0.244964$.
Total $= \mathbf{0.49363}$.

**Away clean sheet** = $P(G_H = 0) = \mathbf{0.14957}$.
(Careful with the wording — the *away* team keeps a clean sheet when the *home* team fails to
score.)

**False assumption:** goals are not independent and the two rates are not independent of each
other — the Poisson model materially under-predicts 0-0, 1-0, 0-1 and 1-1 scorelines, and assumes
constant intensity across the match when in reality intensity rises after a red card, at 1-1 late
on, and so forth. **Fix:** the **Dixon-Coles adjustment** (B4), which applies a correction factor
$\tau(h, a, \lambda_H, \lambda_A)$ to exactly those four low-scoring cells while leaving the rest of
the grid alone. Modern variants also add a time-decay weight so recent matches count more.

---

**3.** **Model P:** mean $= (0.48+0.51+0.49+0.50)/4 = 0.495$.
Bias $= 0.495 - 0.55 = -0.055$; **Bias² $= 0.003025$.**
Deviations: −0.015, +0.015, −0.005, +0.005. Squares: 0.000225, 0.000225, 0.000025, 0.000025.
**Variance $= 0.000125$.**
**Total reducible $= 0.003150$.**

**Model Q:** mean $= (0.38+0.67+0.44+0.71)/4 = 0.550$.
Bias $= 0.000$; **Bias² $= 0.000000$.**
Deviations: −0.17, +0.12, −0.11, +0.16. Squares: 0.0289, 0.0144, 0.0121, 0.0256.
**Variance $= 0.02025$.**
**Total reducible $= 0.020250$.**

**Deploy P.** It is 6.4× better on total error despite being the *only one of the two with any
bias at all*. Q is perfectly unbiased in expectation and useless in practice.

What it says about a single impressive backtest: Q's best fit predicted 0.71 against a truth of
0.55 — if that happened to be the fit you saw, you'd conclude Q was a strong, confident model. You
would have observed one draw from a high-variance procedure and mistaken it for a property of the
model. **A single backtest is one sample from a distribution over backtests, and the impressive
ones are disproportionately drawn from high-variance procedures.** That is B6's entire thesis, and
the reason walk-forward evaluation over many refits is the only measurement that distinguishes P
from Q.

---

**4.** $z_{\text{model}} = \log(0.12/0.88) = \log(0.13636) = -1.99243$.
$z_{\text{mkt}} = \log(0.06/0.94) = \log(0.063830) = -2.75154$.

**Log-odds blend:** $0.25(-1.99243) + 0.75(-2.75154) = -0.498108 - 2.063655 = -2.561763$.
$\hat{p} = \sigma(-2.561763) = 1/(1 + 12.9569) = \mathbf{0.07158}$.

**Probability blend:** $0.25(0.12) + 0.75(0.06) = 0.03 + 0.045 = \mathbf{0.07500}$.

Difference: 0.342 points; relative $0.075/0.07158 - 1 = \mathbf{+4.8\%}$ for the arithmetic blend.

**The log-odds number is defensible.** Three reasons: (a) it's the Bayesian update — treating the
market as prior and the model as evidence makes the blend a weighted sum of evidential weights,
which is addition in log-odds and nothing sensible in probability space; (b) it can never leave
(0,1) for any weights or any inputs, whereas arithmetic blending of a probability with an
extrapolated model output can; (c) it's the correct behaviour at the tails — the arithmetic blend
systematically pulls toward whichever opinion is nearer 0.5, so on long shots it inherits an upward
bias from any less-confident model in the pool. On a 6c contract, a 4.8% relative overstatement of
fair value is a meaningful fraction of the whole edge you were hoping to capture.

---

**5.** **Skill score:** $1 - 0.2205/0.2240 = 1 - 0.984375 = \mathbf{0.015625}$, i.e. **1.56%** of
the market's error removed.

**Mean difference:** $0.2240 - 0.2205 = 0.0035$.
**Standard error:** $0.095/\sqrt{400} = 0.095/20 = 0.00475$.
**t-statistic:** $0.0035/0.00475 = \mathbf{0.737}$.

**What you write:** something like — *"Model beats the market baseline by 0.0035 Brier over 400
resolved forecasts (skill score 1.6%), t = 0.74. Not statistically distinguishable from zero;
consistent with no edge. Sample size required to detect an effect of this magnitude at t = 2 is
approximately 2,950 forecasts."* And nothing stronger, because nothing stronger is true.

$n$ required: $(2 \times 0.095 / 0.0035)^2 = (54.286)^2 \approx \mathbf{2{,}947}$.

**Smallest detectable true edge at this $n$:** $2 \times 0.00475 = \mathbf{0.0095}$ Brier — a skill
score of about 4.2%. Anything genuinely smaller than that is invisible at 400 observations no
matter how real it is. Worth internalising: the honest statement at month 6 will almost always be
"no detectable edge," and writing that down rather than reaching for a favourable subgroup is the
single most credible thing in the whole portfolio. It's also what A3's multiple-comparison
correction is defending — slice 400 forecasts twelve ways and one slice will look wonderful.

---

**6.** `market_mirror` sets $\hat{p} = \text{mkt\_yes\_mid}$, so its Brier must equal
`brier_market` up to floating-point noise. A 0.0071 gap is a pipeline defect. Three candidates:

1. **`mkt_yes_mid` in the forecast row and the mid used to compute `brier_market` come from
   different snapshots.** The scoring view joins a market price at query time instead of using the
   value embedded in the row — so the model is being scored against a *different* price than the
   one it copied. **Violates invariant 2** (market state captured at forecast write time, never
   joined afterwards). This is the most likely cause and the exact failure invariant 2 exists to
   prevent.

2. **De-vig applied on one side only.** `brier_market` computed from a de-vigged implied
   probability while `p_hat` copied the raw vigged mid (or vice versa). The gap would then be
   systematic and one-directional, and larger on wide-spread markets. **Violates invariant 6** in
   spirit — the baseline isn't the market's true implied probability, so the comparison is against
   a strawman.

3. **Timezone or timestamp misalignment in the resolution join.** A resolution attached to the
   wrong forecast because a local timestamp leaked into the join key, or the T-24h forecast matched
   against a T-1h closing price. **Violates invariant 7** (everything UTC), and would show up as a
   gap that varies by venue or by market close time — which is the diagnostic that separates it
   from cause 2.

Honourable mentions worth checking: a `seq` gap meaning some forecasts were written but lost
(**invariant 5** — a gapless monotonic `seq` is exactly the monitor for this), and superseded rows
being double-counted in the scoring view because it doesn't filter on
`supersedes_forecast_id` (**invariant 1** — corrections are new rows, and the reader has to know
that).

The general lesson: `market_mirror` is not a model, it's a **unit test for the measurement layer
that runs continuously in production**. Its only job is to fail loudly when the pipeline lies, and
a non-zero gap tells you the infrastructure is broken before any real model's results can mean
anything.

</details>
