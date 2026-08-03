# Track B — Modelling Foundations

*"Where does a probability actually come from?"*

| Months | Rung | Core question | Key concepts | Notes |
|---|---|---|---|---|
| 1–2 | B1. What a model is | Why does a model beat a guess? | Features → probability mapping, generative vs discriminative, signal vs noise, bias-variance decomposition, why log-odds space is the natural space for binary event pricing | [notes](b1-what-a-model-is.md) |
| 3–4 | B2. Baselines that are hard to beat | What am I competing against? | Market price as baseline, historical base rates, Elo, Bradley-Terry / paired-comparison models. **Rule: never build a model without beating a baseline first.** | |
| 5–6 | B3. Regression | How do I map features to probability? | Linear → logistic regression, link functions, coefficient interpretation in log-odds, regularisation (L1/L2), feature scaling and encoding | |
| 6–7 | B4. Process models | How do I model the mechanism, not just the outcome? | Poisson & negative binomial scoring processes, Dixon-Coles adjustment, simulation from a fitted process to derive any derived market | |
| 7–8 | B5. Bayesian & hierarchical | How do I handle small samples? | Priors and posteriors, conjugate updating, partial pooling / shrinkage for team & player effects, uncertainty quantification, credible intervals | |
| 9–10 | B6. Validation & overfitting | Is this backtest a lie? | Time-series cross-validation, walk-forward, look-ahead leakage, survivorship bias, deflated Sharpe, backtest overfitting, out-of-sample discipline | |
| 11–12 | B7. Ensembling & recalibration | How do I combine models and the market? | Model blending, logarithmic opinion pooling, shrinking toward market price, Platt scaling, isotonic regression, stacking | |

**Note:** B6 is the single highest-value rung for this project's specific risk — an AI agent
will cheerfully hand you a beautiful backtest built on leakage. B6 is what stops that.

Add a link in the "Notes" column as each concept gets its own file in this directory.
