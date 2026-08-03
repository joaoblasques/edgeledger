# HANDOFF — EdgeLedger, start the repo session

**For:** a fresh Claude Code session rooted in `~/Dev/edgeledger`
**From:** vault session (2NDBRAIN), 2026-08-03
**Owner:** Jonas

---

## 0. Where things stand

The scaffold is done and committed (`b22898e`, local only, no remote yet, nothing pushed). What
exists:

- `README.md` (hiring-manager-facing), `CLAUDE.md` (agent instructions + the 8 design
  invariants), `pyproject.toml` (uv-managed), `Makefile`, `.env.example`, `.gitignore`
- `src/edgeledger/forecast/schema.py` — **fully implemented**, the one non-stub module. Pydantic
  v2 mirror of the `forecast_log` DDL, enforces invariants 2/3/6/7/8 at the type level
- Everything else (`clients/`, `bronze/`, `forecast/log.py`, `forecast/baselines.py`, `dags/*`,
  `scoring/views.sql`) is stubbed with docstrings stating intent/signature/week-due — no logic
- `tests/test_forecast_schema.py` — 9 passing tests against the real schema
- `tests/test_hash_chain.py`, `tests/test_point_in_time.py` — executable specs, currently
  failing with clean `ImportError`s pointing at exactly the stub functions to build (expected —
  this is correct per the original spec, not a bug)
- `docs/methodology.md`, `docs/data-model.md`, `docs/adr/0001-append-only-forecast-log.md`
- `docs/learning/` — **just added this session** (see §2 below), moved from the vault
- `.claude/agents/` (data-engineer, python-pro, database-optimizer) and `.claude/skills/`
  (airflow-dag-patterns, python-pro, uv-package-manager, test-driven-development) — installed
  via `/equip`, all real copies (not symlinks)
- Local mirror at `~/Dev/awesome-claude-code-subagents` if more subagents are wanted later —
  no network fetch needed

**`make setup && make test && make lint`** all run clean (lint clean; test = 9 pass / 4 fail
against stubs / 1 skip, as designed).

Companion planning docs (not in the repo, still on Desktop / in the vault if needed again):
`prediction-markets-12-month-roadmap.md`, `month-01-spec-ingestion-and-forecast-log.md`. The
full 12-month roadmap and month-1 spec are also mirrored in the vault at
`01_Projects/EdgeLedger/01-Roadmap/`.

---

## 1. Session split — code lives here now, not in the vault

**Decision this session:** all EdgeLedger code, tests, docs, methodology, ADRs, AND learning
material now live in `~/Dev/edgeledger`. Root future EdgeLedger work in a **dedicated session in
this repo**, same pattern as Vitals/Nora/Corpus — don't mix EdgeLedger work into the shared vault
session.

The vault (`01_Projects/EdgeLedger/`) still holds: the MOC (`EdgeLedger.md`), Charter,
Milestone Tracker, weekly Research Log, ADR mirror-template, Venue notes, Reports template, and
the Reading List. Update those from the repo session when a milestone closes or a decision is
made — the vault is now the thin cross-cutting layer, the repo is the technical + learning
source of truth.

---

## 2. Learning moved to the repo this session

**Reversed an earlier in-session choice.** The original scaffold put Track A/B learning indexes
in the vault (`01_Projects/EdgeLedger/02-Learning/`), following the planning handoff literally.
Jonas then asked for learning to happen in the repo instead — this matches the two-layer
doctrine used everywhere else and means one copy of the content, since it also feeds the public
site (§3).

Done this session:
- `docs/learning/README.md` — top-level index, links both tracks
- `docs/learning/track-a/README.md` — Track A table (A1–A6), ported verbatim from the roadmap
- `docs/learning/track-b/README.md` — Track B table (B1–B7), ported verbatim
- Vault's `02-Learning/` folder now has a pointer note
  (`Learning (moved to repo).md`, `status: superseded`) redirecting here; the old Track A/B vault
  files were left in place (not deleted — only delete on explicit instruction) but are stale.

**Not yet done:** no atomic concept notes exist yet (Bayes theorem, Brier score, Kelly
criterion, etc.) — per the original design, don't pre-create them; add one file per concept
under `docs/learning/track-a/` or `track-b/` as each is actually learned, and link it from that
track's `README.md`.

---

## 3. New requirement: a public website

Jonas wants a publicly visible website covering the whole process — build progress, results
(Brier/CLV/calibration as they exist), the learning journey, and the learning materials
themselves. This is new scope, not in the original planning handoff.

**Decided:**
- **Stack:** plain HTML/CSS/JS, hosted via **GitHub Pages** from this repo (not MkDocs/Quarto/a
  framework — a deliberate deviation from the Vitals pattern, which uses MkDocs Material).
- **Explicit forward note from Jonas:** he wants to improve the site's visual design later using
  **Claude Design** (the `frontend-design` skill / a dedicated design pass). So: this session
  should get structure and real content flowing — don't over-invest in polish or a bespoke visual
  system yet. Build it plain and functional; a design iteration is coming later as its own
  pass.

**Not yet decided / to work out in this session, with Jonas in the loop:**
- Where site source lives in the repo (`site/`? `docs/site/`? a `gh-pages` branch via Actions?
  — Vitals uses a docs-site generator with GitHub Actions auto-deploy; for a hand-rolled
  HTML/CSS/JS site, simplest is probably a `site/` directory built (or just static) and deployed
  via a GitHub Actions workflow to Pages, or Pages serving straight from `/docs` if that doesn't
  conflict with the existing `docs/` content — needs a decision).
- Content structure: likely maps to what already exists (README's pitch → landing page,
  `docs/methodology.md` → methodology page, `docs/learning/` → learning section, Milestone
  Tracker / future quarterly letters → results section) but this needs its own scoping pass, not
  a silent assumption.
- Whether it goes live now (with "month 1 in progress, no results yet" framing) or waits for
  the first real numbers (month 3-4). Ask Jonas — don't default silently.
- Domain / URL (joaoblasques.com/edgeledger, to match the Vitals/MBTA pattern, or
  `github.com/joaoblasques/edgeledger` Pages default? — again, ask, don't assume, given the
  Claude-Ecosystem-Education precedent where a custom domain was explicitly skipped).

**Recommend using `superpowers:brainstorming` or a short scoping conversation for this before
writing any site code** — it's a real design decision (IA, what "results" section shows before
there are results, how much the month-1 "nothing to show yet" state should be hidden vs. owned
honestly, which fits the project's whole ethos of honest reporting even when the number is
zero).

---

## 4. Immediate next work items (unchanged from the original spec)

Week 1, still not started:
- `src/edgeledger/clients/base.py` — retry, backoff, token-bucket rate limiter, `capture_ts_utc`
  stamping
- `src/edgeledger/clients/kalshi.py`, `clients/polymarket.py` — real API clients
- Kalshi account + API key pair (Jonas, human step — needed for order-book access)
- Manual fetch → bronze Delta tables

See `docs/methodology.md`, `docs/data-model.md`, and the month-01 spec (vault or Desktop copy)
for full detail. `CLAUDE.md`'s automation boundary still applies: client boilerplate/retry/DAG
scaffolding is agent-owned; the forecast log schema, point-in-time contract, hash-chain design,
and which markets to track are human-owned, never auto-decided.

---

## 5. Acceptance check before starting week 1 work

```
[ ] uv sync / make setup succeeds
[ ] make test shows 9 passed / 4 failed (ImportError against stubs) / 1 skipped
[ ] make lint clean
[ ] docs/learning/README.md + track-a/track-b READMEs render correctly
[ ] No order-placement code anywhere (still true as of this handoff)
[ ] Vault's 02-Learning/ pointer note doesn't contradict this file
```
