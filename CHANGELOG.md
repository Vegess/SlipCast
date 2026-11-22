# Changelog

All notable changes to SlipCast are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.6.0] - 2026-11-22

The Serve module (Phase 4.3, step 3): service jobs and appointments.

### Added
- **Serve** in the new-project dialog, with a link to the demo jobs. Job stages: booked,
  scheduled, assigned, en route, on site, done, plus rescheduled and cancelled. Job fields:
  service type, area, technician, appointment window and hours booked.
- **Missed visits:** a visit counts as missed when the technician arrives after the window
  or the job is rescheduled; cancelled jobs don't count either way.
- **Missed-visit risk** combines the technician's miss rate over the last 6 weeks, the miss
  rate on days as busy as this one for them (up to 2 jobs, 3, or 4 or more), and the miss
  rate for that time of day, each pulled toward the overall rate when based on few visits.
  The area was tested and added nothing, so it only appears in the breakdowns. A window that
  passed with nobody on site counts as missed.
- **Job length** from a reference class (same service by the same technician, else the same
  service, else the technician's jobs, with at least 8 jobs): "jobs like this took 1.5–3
  hours", flagged when the hours booked are shorter than 3 in 4 of them took.
- **Delivery tab, "Visits and technicians":** on-time arrivals for the last 4 weeks against
  the 4 before, typical job length, visits in the next 7 days, visits likely to be missed
  with reasons and the technician's load that day, weekly on-time chart, "busy days run
  late", technicians (on time, took vs booked, load for the next 7 days and their busiest
  day), services (booked vs real length, reschedules), areas, and where jobs wait.
- **Job check** in the new-job dialog: how long jobs like it took, the chance the visit is
  missed, and who else does the service with how many jobs they already have that day.
- Demo jobs: eleven weeks from a made-up home-services company in Bengaluru, with each
  technician's day simulated job by job (travel, overruns, under-booked AC repairs, a slow
  technician, far areas, reschedules for parts).
- Endpoints `GET /projects/{id}/analytics/serve` and `POST /projects/{id}/serve/estimate`;
  `POST /workspaces/{id}/demo-project?template=services`.
- Health checks and the board in job words: "Underway", "Rescheduled", "no technician".

### Fixed
- The on-time trend on the Ship and Serve cards could read "▼ 0 pts"; it now compares the
  same rounded percentages it shows.

## [1.5.0] - 2026-11-22

The Ship module (Phase 4.3, step 2): customer orders and deliveries, on simulated data and
the event API. No courier tracking service, GPS or maps.

### Added
- **Pick a module when creating a project:** Build (tickets) or Ship (orders). Projects keep
  one engine; Ship adds its stages, order fields, wording and breakdowns.
- Order stages: ordered, packed, dispatched, in transit, out for delivery, delivered, plus
  exception. Order fields: origin, destination, carrier, service (standard or express),
  promised date, weight and order value.
- **Delivery tab, "Orders and deliveries":** on-time rate for the last 4 weeks against the 4
  before, typical delivery time, orders on the way and with exceptions, the weekly on-time
  rate, where orders wait between stages, carriers and routes ranked by on-time rate, and
  open orders likely to arrive late with their reasons and expected date.
- **Late-delivery risk** combines the route's late rate (same service level) and the
  carrier's late rate over the last 6 weeks, each pulled toward the overall rate when based
  on few orders. Past the promised date, an exception, or being slower than 9 in 10 similar
  orders raise it. Back-tested against the carrier's record alone.
- **Reference class per order:** "orders like this on this route took 3–6 days", from the
  most specific group with at least 8 delivered orders (route, carrier and service; then
  route; then destination; then carrier).
- **Order check** in the new-order dialog: how long similar orders took, how many would have
  missed your promised date, and the on-time rate of each carrier on that route.
- Demo orders: four months from a made-up D2C brand shipping from Chennai and Mumbai, with
  under-promised remote routes, a cheap slow carrier, a carrier that got slower and a sale
  that doubled orders this week. Open them from the new-project dialog.
- `scripts/simulate_orders.py` sends realistic order events to any Ship project, so you can
  watch the screens update. Plain Python, no packages.
- Endpoints `GET /projects/{id}/analytics/ship` and `POST /projects/{id}/ship/estimate`;
  `POST /workspaces/{id}/demo-project?template=shipments`.
- Tasks accept `stage`, `item_type` and `attributes`, so orders can be added and moved by hand.

### Changed
- The board, project header, health checks and dialogs use the module's words: "order",
  "On the way", "promised date", "no carrier".

## [1.4.0] - 2026-11-22

The Build module (Phase 4.3, step 1): pull requests, releases and deployments from GitHub.

### Added
- **Connect GitHub** on a project's Live feed tab: SlipCast shows a webhook URL and secret
  with step-by-step instructions. Every delivery is checked against its HMAC signature; the
  secret is derived from the server secret, so it is never stored, and can be rotated.
- Pull requests move through opened, in review, approved and merged (or closed); releases are
  tagged and marked deployed when their first production deployment succeeds; deployments
  succeed or fail. GitHub's retries change nothing; authors reviewing their own PR don't count.
- **Delivery tab, "Pull requests and releases":** the four DORA metrics over the last 4 weeks
  with the change against the 4 before (deployments a week, lead time, failed deployments,
  recovery time), deployments per week, the wait for a first review, merge time by PR size,
  and open PRs with the time similar-size PRs took. Without deployments, lead time falls back
  to opened-to-merged and says so.
- **Module picker** in the new-project dialog: Build now; Ship and Serve marked as coming.
- The demo project now includes six months of pull requests, weekly releases and
  deployments (bigger PRs wait longer, Friday PRs wait over the weekend, about 1 in 9
  deployments fails and is fixed within hours).
- `GET /projects/{id}/tasks?types=all` includes pull requests, releases and deployments.
- Migration 0008.

### Changed
- Pull requests, releases and deployments are kept out of ticket counts, health checks,
  forecasts and models, so a PR is never counted as a second ticket.
- The ticket event code is shared by the event API and the GitHub webhook.

### Fixed
- The "Continue with Google / GitHub" buttons no longer disappear when the API is still
  waking up: the page retries for about 20 seconds and doesn't remember a failure.

## [1.3.0] - 2026-11-21

The real-time engine (Phase 4.2).

### Added
- **Event API:** `POST /api/projects/{id}/events` takes one event or up to 500 from another
  system (an order app, a courier feed, CI, a script) with a per-project API key in
  `X-SlipCast-Key`. Unknown items are created; an exact repeat (same id, stage and time)
  changes nothing; an event that changes nothing is counted as unchanged; late, out-of-order
  events are kept without moving an item backwards. 600 events a minute per key.
- **Live screens:** the board, Delivery and Forecast tabs update by themselves over
  Server-Sent Events, including changes made by teammates in the app. Changed cards glow
  briefly, and the project header shows a Live dot. In a test, 50 events reached an open
  board in under a second.
- **Alerts:** a bell in the top bar and toasts when the 85% finish date moves by 2 days or
  more, or new work looks likely to miss its date (grouped when a batch brings many).
- **Live feed tab:** an animated diagram of how events flow, the project's stages, API keys
  (admins), copy-paste examples for curl and PowerShell, and everything that arrived live.
- **Stages per project:** each project has its own stages mapped to the four states the
  engine uses, ready for the Ship and Serve modules.
- **Privacy policy and Terms of use** pages, linked from sign-in and the landing page.
- Landing page: an animated "how SlipCast reads a ticket" diagram.
- Migration 0007: `workflow_stages`, `project_api_keys`, `ingested_events`, `alerts`, and
  `template`, `last_p85`, `stage`, `item_type`, `attributes` columns.

### Fixed
- Sign-in keys pasted with a trailing space or line break (which broke GitHub sign-in) are
  now trimmed.

## [1.2.0] - 2026-11-21

Accounts and teams (Phase 4.1).

### Added
- **Sign in with Google and GitHub** (OAuth 2.0 with state and PKCE). The API runs the whole
  flow, so no provider secret or token reaches the browser. A verified email address links
  to an existing account; an unverified one never does. Buttons only appear when the server
  has that provider's keys.
- **Teams:** invite links (single use, 7 days) with three roles. Viewers can see everything
  and change nothing; members add and edit work; admins also delete projects and manage the
  team. Roles are enforced in the API's shared access checks, and every write is tested
  against a viewer.
- **New pages:** create account (`/signup`), sign-in callback, accept invite, forgot password,
  and Settings tabs for General, Account (sign-in methods, set or change password, sign out
  everywhere) and Team (members, roles, invite links).
- **Workspace switcher** in the sidebar for people in more than one workspace, and a
  view-only notice that hides editing controls for viewers.
- Sign-in now returns you to the page you were heading to, e.g. an invite.
- Migration 0006: `oauth_accounts`, `invites`, `users.token_version`, nullable password.

### Changed
- The personal workspace role is now `admin` (was `owner`).
- Changing your password signs you out on every other device.

## [1.1.0] - 2026-11-18

Live at <https://slip-cast.vercel.app> (web on Vercel, API on Render, Postgres on Neon).

### Added
- Multi-page app: public landing page, dashboard, imports history, settings, about page and
  a 404 page, with a top navigation bar (menu on mobile). Every page is lazy-loaded.
- Import history: each CSV import's data-quality report is stored (migration 0005) and listed.
- Light theme alongside the new default Dusk theme, switchable in the sidebar and settings.
- `PATCH /auth/me` (display name) and `GET /auth/ai-status`.
- **Motion:** page and tab changes animate with the browser's View Transitions (the tab
  underline slides between tabs), charts draw themselves in, board cards and dialogs rise
  into place and lift under the pointer, the landing page reveals sections as you scroll and
  counts its headline numbers up, the sign-in chart draws its history and forecast cone,
  and loading states show shimmer placeholders. Built with Angular's router, CSS and two
  small directives, so no new dependency. Everything is off when the system asks for
  reduced motion.

### Fixed
- **Demo data** no longer creates a second demo project: the endpoint returns the
  workspace's existing demo (HTTP 200) instead. It happened when someone signed up from
  "Try the demo" and then clicked **Demo data** again.

### Changed
- Deployment: `render.yaml` pins the Singapore region and the free plan, so Render no
  longer asks for payment details; the web app points at the live API.
- README: live demo link and a Windows (Command Prompt) setup section.
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

