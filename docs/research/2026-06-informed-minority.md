# Prediction market accuracy comes from ~3% of traders, not the crowd

**Paper:** Gómez-Cram, Roberto; Guo, Yunhan; Jensen, Theis Ingerslev; Kung, Howard.
"Prediction Market Accuracy: Crowd Wisdom or Informed Minority?" Working paper.
SSRN: <https://ssrn.com/abstract=6617059> (DOI 10.2139/ssrn.6617059).

**Date note:** the paper was cited to this project as 25 June 2026. Sources found put the
SSRN posting at **20 April 2026**, with an SSRN "Closer Look" blog feature on
[29 June 2026](https://blog.ssrn.com/2026/06/29/a-closer-look-prediction-market-accuracy-crowd-wisdom-or-informed-minority-by-roberto-gomez-cram-yunhan-guo/).
The June date is most likely that feature, not the working paper. **Unverified — the SSRN
abstract page has not been read directly** (no web-fetch tool in the session that wrote this
note; everything below is from search summaries and secondary coverage, not the PDF).

## Claimed findings

Sample: every Polymarket transaction 2023–2025 — ~1.72M accounts, ~210,322 markets,
~$13.76B volume. [Likely — figures consistent across several secondary sources, not read
from the paper.]

- Accuracy is **neither** crowd wisdom **nor** insider trading. It comes from a small,
  persistently skilled minority: **3.14% of accounts** (~54,000), averaging ~79 markets each.
- Those traders show **depth and breadth**, unlike insiders whose edge is localised to one
  market: they react to *public* news as it arrives, eliminate law-of-one-price violations
  across related contracts, and trade against the crowd's behavioural mistakes.
- The majority **funds** the accuracy rather than producing it — most of the volume, little
  of the information, and their losses are the minority's profits.
- **Persistence:** skilled classification carried out-of-sample at **44%**, versus ~10% for
  skilled mutual funds. Identified via a sign-randomisation test — each trader's actual trade
  sequence with the buy/sell direction randomised 10,000 times, separating directional skill
  from luck.

## Why this matters for EdgeLedger

The project's framing is that the market price is the baseline to beat (invariant 6). This
paper sharpens *what that baseline is*: not an aggregate of many weakly-informed opinions,
but a price set at the margin by a few hundred to a few thousand genuinely skilled
participants who are fast on public news and arbitrage related contracts against each other.

Four consequences, none of which change any invariant:

1. **It raises the bar for `brier_delta`, and explains why.** Beating the market mid means
   out-forecasting that minority, not out-forecasting a crowd. A null result on
   `market_mirror` was already the expectation
   (`../horizon-analysis-2026-08-21.md`); this is a mechanism for why edge is hard, which is
   worth stating in the write-up rather than discovering at month 12.

2. **It is an argument for CLV over Brier as the near-term signal.** If informed traders move
   price quickly on public news, then price movement after a forecast is largely *their*
   revision. CLV measures whether a forecast anticipated that revision — a direct read on
   whether the model saw what the informed minority saw, available long before resolution.
   This supports the existing in-clock / long-dated split (`../methodology.md`).

3. **Law-of-one-price violations are a named, documented inefficiency.** The paper says
   skilled traders profit by eliminating them across related contracts. EdgeLedger already
   ingests mirrored contract pairs (Dem/Rep on one race) — the same structure. Worth noting
   as a *potential* future signal; **explicitly not a commitment**, since which markets to
   track and what to model are human-owned decisions (CLAUDE.md, automation boundary).

4. **It does not validate the model.** Nothing here says a systematic outside forecaster can
   beat that price. If anything it argues the opposite for a naive baseline. Cite it as
   context for the difficulty, never as evidence that the project's approach works.

## Honesty note

This is a working paper, not peer-reviewed, and it has had heavy and somewhat breathless
press coverage ("a tiny elite", "donate to 3% insider traders"). The headline number (3.14%)
is definition-dependent — it falls out of the authors' skill classification, so it is not a
natural constant and should always be quoted with that caveat. If any of this is used on the
public site or in an interview, **read the paper first**; this note is second-hand.

## Secondary coverage read

- [Yale Insights — "Wisdom of the Few?"](https://insights.som.yale.edu/insights/wisdom-of-the-few-prediction-markets-are-driven-by-small-number-of-skilled-traders)
- [SSRN blog "A Closer Look"](https://blog.ssrn.com/2026/06/29/a-closer-look-prediction-market-accuracy-crowd-wisdom-or-informed-minority-by-roberto-gomez-cram-yunhan-guo/)
- [Cointelegraph, via TradingView](https://www.tradingview.com/news/cointelegraph:d86b9f35f094b:0-prediction-markets-reflect-wisdom-of-an-informed-minority-not-crowd-study/)
- predictiontalent.com, "Who really makes prediction markets accurate"
  (<https://predictiontalent.com/insights/who-really-makes-prediction-markets-accurate>) —
  supplied by Jonas; **not retrieved**, not indexed by search and no fetch tool available in
  this session. Content unread; listed here only for provenance.
