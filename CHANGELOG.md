# Changelog

All notable changes to SlipCast are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

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

