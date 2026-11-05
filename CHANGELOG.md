# Changelog

All notable changes to SlipCast are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Multi-page app: public landing page, dashboard, imports history, settings, about page and
  a 404 page, with a top navigation bar (menu on mobile). Every page is lazy-loaded.
- Import history: each CSV import's data-quality report is stored (migration 0005) and listed.
- Light theme alongside the new default Dusk theme, switchable in the sidebar and settings.
- `PATCH /auth/me` (display name) and `GET /auth/ai-status`.

### Changed
- Softer, more colourful Dusk palette with colour accents; text meets WCAG AA in both themes.

## [1.0.0] - 2026-11-05

The first complete release: forecasting, the differentiators, models, advice and exports.

### Added
- **Flow analytics:** cycle time percentiles, 26 weeks of throughput, a 120-day cumulative
  flow diagram rebuilt from status events, breakdowns by type, theme and owner, and aging work.
- **Monte Carlo forecast:** 10,000 simulations from the last 12 complete weeks, target-date
  probability, burn-up, and a weekly backtest.
- **Reference-class forecast per ticket:** how long the 20 most similar finished tickets really
  took, compared with the plan.
- **Write-time ticket check:** quality score, reference class, slip risk and duplicates while a
  ticket is typed, plus a suggested rewrite.
- **Forecast ledger:** every forecast is stored and scored automatically; the Forecast tab shows
  hit rate and calibration, and the demo replays history to show a real track record.
- **Models:** ticket-type classifier, theme clustering, duplicate detection, quality score and
  a slip-risk model, all evaluated on time-based splits against baselines on a Model
  evaluation page.
- **Advice layer:** optional Groq LLM that turns numbered findings into validated suggestions
  and a weekly status report, with rule-based fallback, rate limits, privacy mode and feedback.
- **Exports:** Excel workbook and tidy CSVs for Tableau and Power BI, with a BI guide.
- **Notebooks:** exploratory analysis and model evaluation, saved with outputs.
- Docs: deployment guide (Neon + Render + Vercel, or Cloud Run) and a two-minute demo script.

### Fixed
- Demo data: tickets that bounced back to Planned could record "done" before being picked up
  again, so their history disagreed with their status.

## [0.5.1] - 2026-11-05

### Changed
- Product renamed to SlipCast across the UI, page title, README, API title, Render
  service (`slipcast-api`), Docker and CI configuration. The sign-in token is now stored
  under `slipcast_token`, so existing sessions are asked to sign in once more.

### Fixed
- Ticket dialog: the Owner, Due date and Description fields could not be focused by
  mouse, so typing went into the title. The modal backdrop's mousedown listener
  evaluated to `false` for clicks inside the dialog, which makes Angular call
  `preventDefault()`.

## [0.5.0] - 2026-10-15

Phase 1: the foundation.

### Added
- FastAPI backend with SQLAlchemy 2, Alembic migrations and Pydantic v2.
- JWT authentication with bcrypt, personal workspaces and tenant-isolated lookups.
- Projects and tickets, with every status change recorded in `task_events` and
  `started_at` / `completed_at` kept consistent.
- CSV import for Jira, GitHub Issues and Trello exports with a data-quality report.
- Deterministic demo dataset of about 430 tickets over six months.
- Rule-based project health checks (overdue, blocked, unowned, overloaded work).
- Angular 19 web app: sign-in, workspace shell, CSV import, project board.
- Dockerfiles, docker-compose stack, Render and Vercel configs.
- GitHub Actions CI: ruff, migrations on Postgres with `alembic check`, pytest and the
  Angular build.

