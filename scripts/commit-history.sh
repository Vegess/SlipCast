#!/usr/bin/env bash
# Commits the project in logical steps. Works on a fresh `git init` or on top of an
# existing Plotline repo (for example one that still has the old React frontend).
# Usage, from the repo root:  bash scripts/commit-history.sh
set -euo pipefail

commit() {
  local msg="$1"; shift
  for p in "$@"; do git add -A -- "$p" 2>/dev/null || true; done
  if git diff --cached --quiet; then
    echo "skip: $msg (no changes)"
  else
    git commit -q -m "$msg"
    echo "✓ $msg"
  fi
}

commit "chore: repo setup, license, env template and gitignore" \
  .gitignore LICENSE .env.example

commit "feat(api): settings, database session and core data model" \
  backend/requirements.txt backend/app/__init__.py backend/app/config.py \
  backend/app/db.py backend/app/models.py backend/app/timeutil.py

commit "feat(db): alembic migrations for schema and ticket history" \
  backend/alembic.ini backend/alembic

commit "feat(auth): JWT auth, bcrypt hashing and personal workspaces" \
  backend/app/schemas.py backend/app/security.py backend/app/deps.py \
  backend/app/routers/__init__.py backend/app/routers/auth.py

commit "feat(api): projects and tickets with recorded status history" \
  backend/app/routers/projects.py backend/app/routers/tasks.py \
  backend/app/services/__init__.py backend/app/services/insights.py

commit "feat(data): CSV import with quality report and demo dataset generator" \
  backend/app/services/importer.py backend/app/services/demo_data.py \
  backend/app/routers/data.py backend/app/main.py

commit "test: auth, CRUD, history, import, demo data and tenant isolation" \
  backend/tests backend/pytest.ini backend/ruff.toml backend/requirements-dev.txt

commit "refactor(web): replace React frontend with Angular 19 scaffold" \
  frontend web/package.json web/package-lock.json web/angular.json \
  web/tsconfig.json web/tsconfig.app.json web/tailwind.config.js web/.editorconfig web/.gitignore \
  web/src/index.html web/src/main.ts web/src/styles.css web/public

commit "feat(web): API client, auth, guards and interceptor" \
  web/src/app/app.ts web/src/app/app.config.ts web/src/app/app.routes.ts \
  web/src/app/core web/src/app/features/auth

commit "feat(web): workspace shell, CSV import and project board" \
  web/src/app/shared web/src/app/features/shell web/src/app/features/project

commit "chore: Docker images, compose stack and deploy configs" \
  backend/Dockerfile backend/.dockerignore web/Dockerfile web/.dockerignore \
  web/docker web/vercel.json docker-compose.yml render.yaml

commit "ci: lint, Postgres migration check, tests and web build" \
  .github/workflows/ci.yml

commit "docs: README, architecture notes and screenshots" \
  README.md docs scripts

git add -A
git diff --cached --quiet || { git commit -q -m "chore: remaining project files"; echo "✓ remaining files"; }

echo
git log --oneline | head -20
