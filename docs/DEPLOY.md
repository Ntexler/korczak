# Deploying Korczak to the Cloud

Get Korczak running 24/7 so you can access it from any device — and so
Chappie can run nightly learning missions.

## Architecture

```
Vercel (frontend, free) → Railway (backend, ~$5/mo) → Supabase (DB, existing)
```

## 1. Backend on Railway

1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
2. Select `Ntexler/korczak` and the branch you want to deploy
3. Railway auto-detects `railway.json` (build + start commands are preconfigured)
4. Add environment variables (Settings → Variables):

```
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...          (optional, embeddings)
OPENALEX_EMAIL=you@email.com   (optional, faster rate limits)
CORS_ORIGINS=https://YOUR-APP.vercel.app
```

5. Deploy. Copy the public URL (e.g. `https://korczak-production.up.railway.app`)

## 2. Frontend on Vercel

1. Go to [vercel.com](https://vercel.com) → Add New Project → Import `Ntexler/korczak`
2. Set **Root Directory** to `frontend`
3. Add environment variable:

```
NEXT_PUBLIC_API_URL=https://YOUR-RAILWAY-URL.up.railway.app/api
```

4. Deploy. Your app is live at `https://YOUR-APP.vercel.app`
5. Go back to Railway and set `CORS_ORIGINS` to this Vercel URL

## 3. Nightly Chappie runs (optional)

Railway supports cron. Add a new service in the same project:

- Start command: `python -m backend.agents.deep_learner --field Anthropology --depth 2 --limit 5`
- Cron schedule: `0 2 * * *` (2 AM daily)

Or use Railway's cron jobs UI on the same service.

## Auto-deploy

Both Vercel and Railway redeploy automatically on every push to the
connected branch. Push → live in ~2 minutes.
