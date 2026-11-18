# CLAUDE.md — Project brief for Claude Code

Read this file fully before doing anything in this repo. It is the source of truth for
what this project is, why it exists, and what to build next.

> **Product name:** **SlipCast** (display "SlipCast"; lowercase `slipcast` in identifiers,
> keys and URLs). The repo is `Vegess/slipcast`; it was formerly called Plotline.

---

## 1. What this product is

A delivery analytics tool for software teams. It imports ticket history from Jira,
GitHub Issues, Trello or Linear (CSV), and helps teams answer two questions:
**"When will this really be done?"** and **"Which tickets are going to slip, and why?"**

### Why we are building it this way (market position)

Flow metrics (cycle time, throughput, cumulative flow) and Monte Carlo forecasting
already exist in many tools: Jira Advanced Roadmaps, Smart Metrics AI, AgileLens,
Axify, Allstacks, and the open-source MCS-MCP (which even does backtesting).
**These are table stakes, not our pitch.** We build them compactly as a foundation.

Our differentiation (build these with the most care):

1. **Reference-class forecasting per ticket.** For any ticket, find the most similar
   *finished* past tickets by text and show how long they really took:
   "Tickets like this took 4–11 days (n=23). You planned 3."
   (Reference-class forecasting, Kahneman and Flyvbjerg, applied to ticket text.)
2. **Write-time risk check.** While a person is typing a new ticket, show its quality
   score, slip risk and reference-class estimate *before work starts*, plus a suggested
   rewrite. Competitors analyse after the fact; we shift risk detection left.
3. **Forecast ledger.** Every forecast the product makes is stored. When the real
   outcome arrives, it is scored automatically. Each team can see how accurate the
   product has actually been for them (hit rate, calibration). Honesty is a feature.
4. **Tool-agnostic and private.** CSV import from any tracker, no plugin to install,
   and a privacy mode that never sends ticket text to an LLM.

**Pitch:** "Other tools tell you a project is late. SlipCast tells you a ticket will be
late while you're still writing it, and proves how often it's right."

### Principles

- **Models measure, the LLM advises.** Classical NLP and ML (scikit-learn) do all
  measurement and prediction, because they can be evaluated with real metrics and
  explained. The LLM (Groq) only turns computed findings into advice, and its output is
  validated before anyone sees it.
- **Every model is evaluated** on a time-based split (train on older tickets, test on
  newer ones) and compared against a simple baseline. No metric without a baseline.
- **Not RAG, not agentic.** The owner already has RAG (DocuMind) and agentic projects.
  Keep LLM use to single, grounded calls.

---

## 2. Current state (Phase 1, done, CI green)

- **Backend** (`backend/`): FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, pandas.
  JWT auth with bcrypt; personal workspaces; projects; tickets; every status change
  stored in `task_events`, with `started_at` and `completed_at` kept consistent in
  `routers/tasks.py:apply_status`; CSV import with a data-quality report
  (`services/importer.py`); deterministic demo dataset of about 430 tickets
  (`services/demo_data.py`); rule-based health checks (`services/insights.py`).
- **Web** (`web/`): Angular 19, standalone components, signals, functional guards and
  interceptor, lazy routes, Tailwind, dark theme. Runtime API URL from
  `web/public/config.js`.
- **Ops:** Dockerfiles for both, `docker-compose.yml`, `render.yaml`, `web/vercel.json`,
  GitHub Actions CI (ruff, `alembic upgrade head && alembic check` on Postgres, pytest,
  Angular build).
- **Tests:** 22 pytest tests including tenant isolation (`tests/test_isolation.py`).

### Known bug (fix first)
In the ticket dialog (`web/src/app/features/project/task.dialog.ts`), the **Owner** and
**Due date** fields do not respond to clicks or typing for the owner. Reproduce, find
the root cause, fix it, and add a note in the commit message explaining the cause.

---

## 3. How to work in this repo

- **Never touch files outside this repo.** The owner has other projects (DocuMind,
  DebateSphere, JobPilot); do not read, edit or move them.
- Work in **small steps**. One task = one or a few commits with conventional messages
  (`feat(api): ...`, `fix(web): ...`, `test: ...`). Never rewrite history or change
  commit dates.
- Before every commit, run and pass:
  - `cd backend && ruff check . && ruff format --check . && pytest`
  - `cd backend && alembic upgrade head && alembic check` (on a fresh SQLite file)
  - `cd web && npm run build`
- Every schema change gets a new Alembic migration. Never edit an existing migration.
- Every new endpoint goes through `deps.get_project_for_user` or
  `deps.get_task_for_user`, and gets a line in `tests/test_isolation.py`.
- Every model or statistic gets a test, including a "small project" test where there
  isn't enough data (the endpoint must return `available: false` with a reason, never
  crash).
- Use `python -m pip` and `python -m uvicorn` on Windows so the venv is always used.
- Keep the UI copy plain and specific. Explain every chart in one sentence above it.
- Stop and ask the owner before: adding a paid service, adding a new top-level
  dependency not listed here, or changing the product direction.
- **Usage is limited.** Prefer focused edits over rewriting whole files, and don't
  re-read large files unnecessarily.

---

## 4. Roadmap

Do the tasks in order. Check off each acceptance criterion before moving on.

### Phase 1.5: Housekeeping

**1.1 Rename**
- Replace "Plotline" with SlipCast in the UI text, page title, README, docs,
  `render.yaml` service name, the FastAPI title, and the localStorage keys
  (`plotline_token` becomes `slipcast_token`).
- Do not rename the Python package `app` or the folder structure.
- Acceptance: `grep -ri plotline` finds nothing except the git history note in the README.

**1.2 Fix the ticket dialog bug** (see section 2).
- Acceptance: owner and due date can be edited and saved; verified manually in the browser.

**1.3 Repo hygiene**
- Add a `CHANGELOG.md` starting at `0.5.0` (Phase 1).
- Acceptance: CI green.

### Phase 2A: Flow analytics and forecasting (foundation, keep compact)

Add `scikit-learn==1.5.2` to `backend/requirements.txt` and `echarts@5.5.1` to the web app.

- `services/analysis.py`: load a project's tickets and events into pandas, run the
  models once, and cache the result in memory keyed by (ticket count, max
  `updated_at`, event count, today's date).
- `services/flow.py`: cycle time per finished ticket (`completed_at` minus
  `started_at`, falling back to `created_at`), P50/P85/P95, weekly throughput for 26
  weeks, cumulative flow for 120 days (status of each ticket at the end of each day,
  from events), breakdowns by type, theme and owner (open, done, median and P85 cycle
  time, late rate), and aging work in progress flagged when older than P85.
- `services/forecast.py`: Monte Carlo with 10,000 simulations, resampling the last 12
  complete weeks of throughput until the remaining tickets are done, interpolating
  within the final week. Return P50, P85 and P95 dates, a histogram, the probability of
  hitting an optional target date, and burn-up data.
- Endpoints: `GET /projects/{id}/analytics/overview`, `/flow`, `/forecast?target=`.
- Web: project tabs (Board, Delivery, Forecast) and a shared `ChartComponent` that
  wraps ECharts with tree-shaken imports and the dark theme.
- Acceptance: on the demo project, P50 < P85 < P95; histogram probabilities sum to
  about 1; a constant-throughput unit test gives an exact answer (5 per week with 20
  remaining gives 4.0 weeks).

### Phase 2B: The differentiators (highest priority for quality)

**2B.1 Reference-class forecast per ticket**
- `services/reference_class.py`: TF-IDF (1–2 grams, sublinear, English stop words) over
  title plus description of *finished* tickets. For a query ticket, take the k=20 most
  similar by cosine similarity (minimum similarity 0.15; if fewer than 8 qualify, say
  so). Return n, P10, P50 and P90 of their cycle days, their late rate, and the 3 most
  similar tickets with their real durations.
- Compare with the ticket's plan (due date minus created date) and flag when the plan
  is below the reference-class P25: "planned 3 days; similar tickets took 4–11".
- Endpoints: `GET /tasks/{id}/reference-class`, and
  `POST /projects/{id}/reference-class` taking `{title, description}` for unsaved drafts.
- Evaluation: on the time-based test split, report how often the real cycle time fell
  inside the P10–P90 band (target about 80%) and the mean absolute error of P50
  compared with a baseline of the project-wide median.

**2B.2 Write-time risk check**
- `POST /projects/{id}/ticket-check` taking `{title, description, owner, due, priority, kind}`
  and returning the quality score with reasons, the reference-class estimate, the slip
  risk (once 2C exists; return null before that), and likely duplicates. It must
  respond in under 300 ms for a project of 2,000 tickets, so reuse the cached analysis.
- Web: in the new-ticket dialog, call it with a 600 ms debounce as the user types and
  show a compact side panel. Never block saving.
- Acceptance: typing "Fix stuff" shows a low quality score with reasons; typing a
  detailed bug report raises it.

**2B.3 Forecast ledger**
- New table `forecasts`: id, project_id, kind (`project_completion` or
  `ticket_reference_class`), subject_id (nullable), made_at, inputs (JSON),
  p50_date, p85_date (or p10, p50 and p90 days for tickets), resolved_at, actual,
  hit_p85 (nullable).
- Record a project forecast at most once per project per day when the Forecast tab
  loads, and a ticket forecast when a ticket moves to in progress.
- A resolver runs on each analysis load: when the forecast's subject is done, fill in
  actual and hit.
- Endpoint: `GET /projects/{id}/forecast-ledger` returning hit rate, calibration
  (predicted P85 against actual hit rate), the latest 50 entries, and how many are
  still unresolved.
- Web: a "Track record" section on the Forecast tab.
- Seed: the demo generator back-fills ledger entries by replaying history, so the demo
  shows a real track record.

### Phase 2C: NLP and ML models, plus the evaluation page

- `services/nlp.py`:
  - **Ticket type classifier:** TF-IDF and logistic regression (class_weight balanced),
    trained on tickets whose `kind_source == "label"` and used to predict unlabelled
    ones. Needs at least 40 labelled tickets.
  - **Themes:** K-means on TF-IDF with domain stop words, `max_df=0.2`, choosing k
    from 3 to 8 by cosine silhouette, and naming each cluster by its top 3 terms.
  - **Duplicates:** TF-IDF cosine similarity of at least 0.72, with open tickets listed first.
  - **Quality score** (0–100) with reasons: short title, vague wording, missing or
    short description, no acceptance criteria or reproduction steps, no owner, no due date.
- `services/risk_model.py`: logistic regression predicting "finished after due date",
  using only features known at creation: planned days, the owner's open load at
  creation, description length (log), risky terms, quality score, unassigned, priority
  and type. Per-ticket explanations come from coefficient times standardised value.
- Endpoints: `/analytics/text`, `/analytics/risk`, `/analytics/evaluation`, `/tasks/{id}/analysis`.
- **Model evaluation page:**
  - Classifier: accuracy and macro F1 against a majority-class baseline, per-class
    table, confusion matrix heatmap, top terms per class.
  - Risk model: ROC-AUC and average precision against a heuristic baseline, ROC,
    precision-recall and calibration charts, Brier score, top weights.
  - Monte Carlo backtest: P85 hit rate and P50 mean absolute error.
  - Reference-class coverage.
  - Forecast ledger summary.
  - Theme silhouette score.
- Expected on the demo data (sanity check, not a target to tune toward): classifier
  around 0.9 accuracy against about 0.35 baseline; risk ROC-AUC around 0.8 against about
  0.6; backtest P85 hit rate around 0.8.

### Phase 2D: LLM advice layer (Groq)

- Config: `GROQ_API_KEY` (optional), `GROQ_MODEL=llama-3.3-70b-versatile`, plus
  per-user rate limits (6 per minute, 100 per day).
- `services/findings.py`: turn analytics into numbered findings (F1, F2 and so on) such
  as overdue, blocked, overload, slowest type, theme with the highest late rate, aging
  work, throughput drop, forecast, high-risk tickets, duplicates, low quality and
  under-planned tickets from the reference class.
- `services/advisor.py`:
  - **Suggestions:** 3 to 5 JSON suggestions, each citing finding IDs.
  - **Validator:** reject any suggestion that cites no valid finding or contains a
    number not present in the findings (integers up to 5 are allowed).
  - **Fallback:** rule-based suggestions when there's no key or every LLM suggestion fails.
  - **Ticket rewrite:** a template fallback, and never LLM in privacy mode.
  - **Weekly status report** in Markdown.
- Log generated, accepted and rejected counts per request; store helpful or not-helpful
  feedback; show the grounding pass rate and helpfulness on the evaluation page.
- Privacy mode (a sidebar toggle saved in localStorage): findings contain no ticket
  titles or theme names, and rewrites use the template only.
- Tests use a fake LLM: one test checks that the validator rejects invented numbers,
  one checks the fallback runs on bad output, and one checks privacy mode never calls
  the LLM.

### Phase 2E: Exports and data-analysis notebooks

Add `openpyxl==3.1.5` to `backend/requirements.txt`. Notebook-only dependencies (jupyter,
matplotlib, seaborn, pandas, numpy, scikit-learn) live in `notebooks/requirements.txt`
and are never installed in the API image.

- `GET /projects/{id}/export.xlsx`: an Excel workbook built with pandas and openpyxl,
  with sheets Tickets, Status history, Cycle times, Weekly throughput, Forecast, Model
  metrics, plus a README sheet explaining each column. Bold header row, frozen panes,
  sensible column widths, dates as real Excel dates.
- `GET /projects/{id}/export/bi.zip`: tidy CSVs (`tickets.csv`, `events.csv`,
  `cycle_times.csv`, `weekly_throughput.csv`, `forecasts.csv`) for Tableau or Power BI,
  one row per entity, ISO dates, snake_case columns.
- `docs/bi-guide.md`: how to connect these CSVs in Tableau and Power BI, with 3
  suggested dashboards (cycle-time control chart, throughput trend, slip rate by theme).
- Web: "Export to Excel" and "Export for Tableau / Power BI" buttons on the Delivery tab.
- Both endpoints use tenant-scoped lookups and get isolation tests; a test checks the
  workbook opens with openpyxl and has the expected sheets.
- `notebooks/01_exploratory_analysis.ipynb`: load the demo data through the backend
  services; explore cycle-time distributions, throughput, and slip rate by type, theme
  and owner with matplotlib/seaborn charts and short markdown commentary.
- `notebooks/02_model_evaluation.ipynb`: reproduce the classifier, risk model,
  reference-class coverage and Monte Carlo backtest results with charts, explaining
  the time-based split and baselines.
- `notebooks/README.md`: how to run them. Notebooks are saved with outputs so they
  render on GitHub. `notebooks/` is excluded from the API Docker image.

### Phase 3: Launch

- Deploy: Neon for Postgres, Render for the API (`render.yaml`), Vercel for the web app
  (set `web/public/config.js`). Alternatively, Google Cloud Run for both using the
  Dockerfiles (`API_URL` env var for the web image).
- README: problem and market research (competitors and our differentiation), feature
  tour with screenshots, architecture diagram, evaluation results table, "Why
  classical ML plus a constrained LLM" section, and the live link.
- A 2-minute demo video script in `docs/demo-script.md`.
- Make the repo public. Tag `v1.0.0`.

---

## 4b. Phase 4: Beyond tickets (approved by the owner, 2026-11-18)

**Status:** Phases 1–3 are done and live (web `https://slip-cast.vercel.app`, API
`https://slipcast-api.onrender.com`, Neon Postgres in Singapore). This phase widens the
product. It is an approved change of direction, so do not stop to ask about it, but still
ask before anything listed in section 3 (paid services, unlisted dependencies).

**New one-line pitch:** "SlipCast predicts what will be late, for tickets, projects,
shipments or stock, while there is still time to act, and proves how often it's right."

**The rule that keeps this one product:** one engine, many templates. Every new kind of
work is a *work item* with stages, a start, a promised date and a finish. Forecasting,
reference classes, slip risk and the forecast ledger stay shared. A template only adds
wording, stages, a few fields, a demo dataset and its own breakdowns. Never fork the
engine per template.

Do the tasks in order. Ship each as its own minor version with a CHANGELOG entry.

### 4.0 Release v1.1.0 first
- CHANGELOG `Unreleased` becomes `[1.1.0] - 2026-11-14`; version `1.1.0` in
  `backend/app/main.py` and `web/package.json`; README "Live demo" line points at the
  Vercel URL with a note that the first load can take up to a minute.
- `docs/DEPLOY.md`: note `region` and `plan: free` in `render.yaml`, and that
  `CORS_ORIGINS` must have no trailing slash.
- Fix: clicking **Demo data** twice must not create a second demo project.
- Acceptance: tag `v1.1.0` exists; CI green.

### 4.1 Accounts and teams (v1.2)
Approved new dependency: `httpx==0.28.1` (server-side OAuth token exchange). No auth SaaS.

- **Sign in with Google and GitHub** (OAuth 2.0 authorization-code flow with `state`
  and PKCE). New table `oauth_accounts` (user_id, provider, provider_user_id, email,
  created_at; unique on provider + provider_user_id). `users.password_hash` becomes
  nullable via a new migration. Matching email on an existing account links it only
  when the provider says the email is verified.
- Config: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GITHUB_CLIENT_ID`,
  `GITHUB_CLIENT_SECRET`, `PUBLIC_WEB_URL`. Buttons are hidden when a provider isn't
  configured, so local runs and CI work without keys.
- **Teams:** invite by link (token, expires in 7 days, single use) to a workspace with
  role `admin`, `member` or `viewer`. Viewers can read everything and change nothing.
  Enforce roles in `deps.py`, not in routers. Isolation tests cover each role.
- **Auth pages (each its own lazy route):** sign in, create account, accept invite,
  OAuth callback, forgot password (shows "ask your workspace admin" until an email
  service is approved), and Settings → Account (connected sign-in methods, change
  password, sign out everywhere) and Settings → Team (members, roles, invite links).
- Acceptance: a new user can sign in with Google or GitHub on the live site; an
  invited viewer sees the board but gets 403 on any write; all old accounts still work.

### 4.2 Work items and real-time engine (v1.3)
- Rename "ticket" to "work item" in the UI copy only where a project's template is not
  `software`. Keep the `tasks` table and the `app` package names.
- New columns on `projects`: `template` (`software`, `project_work`, `shipments`,
  `inventory`, `product_launch`; default `software`). New table `workflow_stages`
  (project_id, key, label, order, category `todo|doing|blocked|done`). The engine maps
  every stage to a category, so flow, forecast and risk code does not change.
- New column `tasks.item_type` and a JSON column `tasks.attributes` for template fields.
- **Event ingestion:** `POST /api/projects/{id}/events` with a per-project API key
  (table `project_api_keys`, store only a hash, shown once). Body: external_id, stage,
  occurred_at, optional fields. Idempotent on (external_id, stage, occurred_at). Creates
  the item if it doesn't exist. Rate limit 600 per minute per key.
- **Live screens:** `GET /api/projects/{id}/stream` as Server-Sent Events (auth by a
  short-lived stream token in the query string). The board, Delivery and Forecast tabs
  update without reload. The analysis cache invalidates on each event.
- **Alerts:** when the P85 date moves by 2 or more days, or a new item scores high
  risk, record an alert and show it in a bell menu. Outbound webhooks (Slack-compatible
  JSON) per project are optional.
- Acceptance: posting 50 events with `curl` updates an open browser within 2 seconds
  and the forecast date moves; duplicate events change nothing.

### 4.3 Templates (one minor version each, in this order)
Each template ships with: stages, fields, a deterministic demo dataset of 300 to 500
items, wording, its breakdowns, and a "small data" test. Show the template picker in
the new-project dialog.

1. **Software delivery+ (v1.4):** pull requests and releases from GitHub via a
   repository webhook (signature verified with the webhook secret). PR stages: opened,
   in review, approved, merged. Release stages: tagged, deployed. Adds review wait time,
   PR-size reference classes, and the four DORA metrics on the Delivery tab.
2. **Project work (v1.5):** tasks and client deliverables; stages To do, Doing, Review,
   Done; fields client, deliverable, billable hours. Breakdowns by client.
3. **Goods shipments (v1.6):** stages Ordered, Packed, Dispatched, In transit, Out for
   delivery, Delivered, plus Exception. Fields origin, destination, carrier, promised
   date, weight. Late-delivery risk by route and carrier; reference class "orders like
   this on this route took 3 to 6 days". **Stage updates only: no live GPS, maps or
   driver app.**
4. **Inventory (v1.7):** items are stock-keeping units, not jobs. Track stock-on-hand
   events (received, sold or used, adjusted). Forecast the **stockout date** with Monte
   Carlo on daily demand (same engine, demand instead of throughput), reorder point, and
   whether a pending purchase order arrives in time. The ledger scores stockout forecasts.
5. **Product launch (v1.8):** a product as milestones through stage gates (Idea,
   Design, Build, Test, Launch), each milestone holding work items. Forecast per
   milestone and for launch day; show which gate is the bottleneck.

### 4.4 Out of scope for Phase 4
Live GPS tracking, driver or courier apps, payments and billing, payroll, chat, time
tracking, and a full sprint board. Each is a separate product with large competitors.

---

## 5. Definition of done (every task)

- Lint, migrations check, tests and web build all pass locally and in CI.
- New endpoints are covered by isolation tests.
- Small-data cases return `available: false` with a human-readable reason.
- UI text explains what the user is seeing in plain language.
- Commit messages are conventional and describe why, not just what.
