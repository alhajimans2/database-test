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
- For initial test login, blueprint creates a default admin (`admin` / `admin123`).
- After first successful login, change password and set `CREATE_DEFAULT_ADMIN=false` in Render env vars.
- After first deploy, verify environment values in Render dashboard and keep `CREATE_DEFAULT_ADMIN=false` unless doing first-time bootstrap.

## 3) Required backend environment variables
Use values from `.env.example`:
- `SECRET_KEY`
- `DATABASE_URL`
- `APP_ENV=production`
- `COOKIE_SECURE=true`
- `TRUST_PROXY=true`

`DATABASE_URL` examples:
- SQLite test mode: `sqlite:////tmp/tit_database.db`
- Postgres mode: `postgresql+psycopg://user:password@host:5432/database`

If deploy logs show `Could not parse SQLAlchemy URL`, your `DATABASE_URL` value is malformed (or contains placeholder text).

Production data persistence note:
- Do not use `/tmp` SQLite for production persistence.
- Set a valid persistent `DATABASE_URL` (recommended PostgreSQL).
- App now blocks production startup when `DATABASE_URL` is missing/invalid unless `ALLOW_EPHEMERAL_DB=true` is explicitly set for temporary testing.

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