# Deploying SlipCast

Two supported setups:

- **A. Neon (Postgres) + Render (API) + Vercel (web).** Free tiers are enough for a demo.
- **B. Google Cloud Run** for both services, with Neon (or Cloud SQL) for Postgres.

You need: a GitHub account with access to `Vegess/SlipCast`, and about 20 minutes. Nothing here
needs a credit card except Google Cloud (option B), which asks for billing even on the free tier.

The API runs `alembic upgrade head` on every start, so the database schema is created and
upgraded automatically. `GROQ_API_KEY` is optional; without it, advice is rule-based.

---

## A. Neon + Render + Vercel

### 1. Create the database (Neon)

1. Sign in at <https://neon.tech> with GitHub.
2. **Create project** → name `slipcast`, Postgres 16, the region closest to your Render region
   (for example *AWS US East (Ohio)* with Render *Ohio*, or *Frankfurt* with Render *Frankfurt*).
3. On the project dashboard, click **Connect**, choose the default branch and database, and copy
   the connection string. It looks like:
   `postgresql://USER:PASSWORD@ep-xxxx.REGION.aws.neon.tech/neondb?sslmode=require`
4. Keep it somewhere safe; it's your `DATABASE_URL`. (SlipCast converts `postgres://` and
   `postgresql://` URLs to the psycopg 3 driver itself.)

### 2. Deploy the API (Render)

1. Sign in at <https://render.com> with GitHub and allow access to the `SlipCast` repository.
2. **New → Blueprint**, pick the repository and branch `main`. Render reads `render.yaml` and
   proposes a web service called `slipcast-api` (Docker, root directory `backend`, health check
   `/api/health`). If the repository isn't listed, click **Configure account** and give
   Render's GitHub app access to it.

   `render.yaml` sets `region: singapore` and `plan: free`. Change the region to match your
   Neon region before the first deploy (Render can't move a service later). Keep
   `plan: free`: without it Render assumes a paid instance and asks for a card.
3. Render asks for the values marked `sync: false`:
   - `DATABASE_URL`: the Neon string from step 1.
   - `CORS_ORIGINS`: leave as `http://localhost:4200` for now; you'll set it after step 3.
   - `GROQ_API_KEY`: optional. Create one at <https://console.groq.com/keys>, or leave empty.
   - Sign in with Google / GitHub (optional): `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
     `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, and `PUBLIC_WEB_URL` (your Vercel URL). See
     "Sign in with Google and GitHub" below for where to get them.
   `JWT_SECRET` is generated automatically; `ENVIRONMENT=production` and
   `AUTO_CREATE_TABLES=false` are already set.
4. Click **Apply**. The first build takes 5–10 minutes (it installs pandas and scikit-learn).
5. When the deploy is live, open `https://slipcast-api-XXXX.onrender.com/api/health`. You should
   see `{"status":"ok","version":"1.1.0"}`. In the logs you should see the
   `Running upgrade` lines for each migration.
6. Copy the service URL (without `/api`). That is your API URL.

> Free Render services sleep after about 15 minutes idle; the first request after that takes
> 30–60 seconds. Upgrade the instance type if you want it always on.

### 3. Deploy the web app (Vercel)

1. In the repo, edit `web/public/config.js` so it points at the API:
   ```js
   window.SLIPCAST_CONFIG = { apiUrl: "https://slipcast-api-XXXX.onrender.com" };
   ```
   Commit and push this change to `main`.
2. Sign in at <https://vercel.com> with GitHub → **Add New → Project** → import `SlipCast`.
   If it isn't listed, click **Adjust GitHub App Permissions** and give Vercel access to it.
3. Set **Root Directory** to `web`. Vercel detects Angular; `web/vercel.json` already sets the
   build command (`npm run build`), output directory (`dist`) and the SPA rewrite.
4. Click **Deploy**. When it finishes, copy the production URL, for example
   `https://slipcast.vercel.app`.

### 4. Connect them

1. In Render → `slipcast-api` → **Environment**, set `CORS_ORIGINS` to your Vercel production
   URL, e.g. `https://slip-cast.vercel.app`. It must match the address bar exactly: `https://`,
   no trailing slash, no path. `https://slip-cast.vercel.app/` fails with "Can't reach the
   SlipCast API". Use the short production domain, not a per-deploy URL with random
   letters. Several origins can be comma-separated with no spaces.
2. **Save changes**; Render redeploys automatically.
3. Open the Vercel URL, create an account, click **Demo data**, and check that every tab loads.
   If the browser console shows a CORS error, the `CORS_ORIGINS` value does not exactly match
   the URL in the address bar.

### 5. Optional: custom domain

Add the domain in Vercel (**Settings → Domains**), then add it to `CORS_ORIGINS` on Render.

---

## B. Google Cloud Run (both services)

Use Neon from step A1 for the database (simplest), or Cloud SQL for PostgreSQL.

### 1. One-time setup

```bash
gcloud auth login
```

```bash
gcloud config set project YOUR_PROJECT_ID
```

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
```

Pick a region and store the secrets (replace the values):

```bash
export REGION=europe-west1
```

```bash
printf '%s' 'postgresql://USER:PASSWORD@ep-xxxx.neon.tech/neondb?sslmode=require' | gcloud secrets create slipcast-database-url --data-file=-
```

```bash
python -c "import secrets; print(secrets.token_urlsafe(48), end='')" | gcloud secrets create slipcast-jwt-secret --data-file=-
```

Optional:

```bash
printf '%s' 'YOUR_GROQ_KEY' | gcloud secrets create slipcast-groq-key --data-file=-
```

Let Cloud Run read the secrets (the default compute service account):

```bash
export SA="$(gcloud projects describe $(gcloud config get-value project) --format='value(projectNumber)')-compute@developer.gserviceaccount.com"
```

```bash
for s in slipcast-database-url slipcast-jwt-secret; do gcloud secrets add-iam-policy-binding $s --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor; done
```

### 2. Deploy the API

From the repository root:

```bash
gcloud run deploy slipcast-api --source backend --region $REGION --allow-unauthenticated --memory 1Gi --set-env-vars ENVIRONMENT=production,AUTO_CREATE_TABLES=false,CORS_ORIGINS=http://localhost:4200 --set-secrets DATABASE_URL=slipcast-database-url:latest,JWT_SECRET=slipcast-jwt-secret:latest
```

(Add `,GROQ_API_KEY=slipcast-groq-key:latest` to `--set-secrets` if you created it, after
granting the same secret-accessor role on it.) Cloud Build uses `backend/Dockerfile`; the
container listens on `$PORT`, which Cloud Run sets. Note the service URL it prints, then check
`https://slipcast-api-….run.app/api/health`.

### 3. Deploy the web app

The web image writes `config.js` from `API_URL` at start-up, so no code change is needed:

```bash
gcloud run deploy slipcast-web --source web --region $REGION --allow-unauthenticated --set-env-vars API_URL=https://slipcast-api-XXXX.run.app
```

### 4. Connect them

```bash
gcloud run services update slipcast-api --region $REGION --update-env-vars CORS_ORIGINS=https://slipcast-web-XXXX.run.app
```

Open the web URL, sign up, load the demo data and check every tab.

---

## After deploying

- Put the live URL in the README ("Live demo" line near the top).
- **Make the repository public** on GitHub: *Settings → General → Danger Zone → Change
  visibility*. Check first that no secrets were ever committed (`.env` is git-ignored; the
  only keys live in Render, Vercel or Secret Manager).
- **Tag each release** (`git tag -a v1.1.0 -m "SlipCast 1.1.0"` and push the tag), then create
  a GitHub Release from the tag and paste that version's section of `CHANGELOG.md`.

## Sign in with Google and GitHub (optional)

Each button appears only when both of its keys are set on the API. Register these callback
URLs with the provider (add the `localhost` one too if you want to test locally):

- Google: `https://<your API>/api/auth/google/callback`
- GitHub: `https://<your API>/api/auth/github/callback`

**GitHub:** Settings → Developer settings → OAuth Apps → New OAuth App. Homepage URL is your
Vercel URL. Copy the Client ID and generate a client secret.

**Google:** in Google Cloud Console create a project, open **Google Auth Platform**, set up the
consent screen (External), then **Clients → Create client → Web application** with the
callback URLs above as *Authorized redirect URIs* (no JavaScript origins needed). Copy the
Client ID and secret. While the app is in *Testing*, add yourself under **Audience → Test
users**; publish it when sign-in works.

On Render set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GITHUB_CLIENT_ID`,
`GITHUB_CLIENT_SECRET` and `PUBLIC_WEB_URL` (e.g. `https://slip-cast.vercel.app`, no trailing
slash). The API works out its own callback URL from the request; set `PUBLIC_API_URL` only if
it sits behind an unusual proxy.

## Live updates

Live screens use Server-Sent Events from the API, held in memory by the one API process, so
run a single instance (the default on Render). Each connection closes after 5 minutes by
design and the page reconnects on its own. Nothing else needs configuring; to send events,
create a key on a project's **Live feed** tab.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Web shows "Can't reach the SlipCast API" | `config.js` (Vercel) or `API_URL` (Cloud Run) points at the wrong URL, or the free Render instance is still waking up. |
| Browser console shows a CORS error | `CORS_ORIGINS` must exactly match the web origin (scheme and host, no trailing slash). |
| API crashes with `JWT_SECRET must be set in production` | Set `JWT_SECRET` (Render generates it from `render.yaml`; on Cloud Run use the secret above). |
| API crashes with `unable to open database file` | `DATABASE_URL` is not set, so it fell back to SQLite. Set it to the Neon string. |
| Google says `redirect_uri_mismatch` | The callback URL registered with Google must match `https://<your API>/api/auth/google/callback` exactly. |
| Sign-in returns to the login page with "took too long" | The sign-in was started more than 10 minutes earlier, or in a different browser. Try again. |
| The project header says "Connecting…" | The API is asleep or unreachable, or `CORS_ORIGINS` doesn't include the site. The page keeps retrying. |
| Events return 401 | The key was revoked, belongs to another project, or isn't in the `X-SlipCast-Key` header. |
| Neon connection errors | Keep `?sslmode=require` on the URL; check the Neon project is not suspended. |
| Advice always says "Rule-based" | Expected without `GROQ_API_KEY`. With a key, check the API logs for `LLM call failed`. |
