# TIT Database App – Test Deployment Guide

## 1) Free-host target (recommended)
- Backend: Render Web Service (free) or Railway hobby
- Frontend proxy: Netlify (already configured in `netlify/functions/proxy.js` + `netlify.toml`)

## 2) Backend start command
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app -c gunicorn.conf.py`

## 2.1) One-click Render blueprint
- This repo now includes `render.yaml`.
- In Render: **New +** → **Blueprint** → select this repository.
- Render will create `tit-database-app` web service.
- For free-tier test deployments, blueprint uses SQLite in `/tmp` (ephemeral).
- Optional upgrade for persistent data: set `DATABASE_URL` to external Postgres (Neon/Supabase/Render Postgres) and redeploy.
- After first deploy, verify environment values in Render dashboard and keep `CREATE_DEFAULT_ADMIN=false` unless doing first-time bootstrap.

## 3) Required backend environment variables
Use values from `.env.example`:
- `SECRET_KEY`
- `DATABASE_URL`
- `APP_ENV=production`
- `COOKIE_SECURE=true`
- `TRUST_PROXY=true`

Recommended:
- `CREATE_DEFAULT_ADMIN=false` (or `true` only on first deploy)
- `CORS_ORIGINS=https://<your-netlify-domain>`

## 4) Netlify environment variable
- `BACKEND_URL=https://<your-backend-domain>`

## 5) Health check
- `GET /healthz` should return status JSON.

## 6) First test deployment checklist
- Confirm login works.
- Open `/students` and run one bulk reminder action.
- Open `/reports` and `/governance/audit-logs`.
- Verify no 500 errors in host logs.