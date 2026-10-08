# LeakGuard — Mastodon Leak Detection Platform

LeakGuard is a full-stack security console for authorized Mastodon content. It connects to a user's Mastodon account with OAuth 2.0 + PKCE, synchronizes statuses, detects sensitive data, scores risk, creates incidents and alerts, and exports an evidence report.

## What is included

- React + Vite security dashboard with light/dark theme
- FastAPI + PostgreSQL + SQLAlchemy + Alembic backend
- Genuine Mastodon OAuth 2.0 authorization-code flow with PKCE and server-side state/verifier cookies
- Encrypted-at-rest Mastodon access/refresh tokens
- Automatic backend Mastodon synchronization every 60 seconds
- Automatic analysis of newly synchronized statuses
- Explainable PII/credential detection for email, phone, API keys, JWTs, credit-card-like values, IPs and secret phrases
- Optional OpenAI explanation layer
- Incident lifecycle: open, acknowledged, investigating, resolved or false positive
- Alerts with unread badge and mark-as-read workflow
- OCR image scanning using Tesseract when installed
- JSON and CSV evidence reports
- Argon2 passwords, HttpOnly JWT cookies, refresh rotation, CSRF protection, rate limiting, security headers and audit logs

## Architecture

```text
Mastodon OAuth + PKCE
        │
        ▼
FastAPI ── encrypted token storage ── PostgreSQL
        │
        ├── background sync (60s)
        │        │
        │        ▼
        │   SocialContent
        │        │
        │        ▼
        │   AI leak detector ── optional OpenAI explanation
        │        │
        │        ├── AnalysisResult
        │        ├── Incident
        │        └── Alert
        │
        └── React security console
```

## Quick start — Windows / local PostgreSQL

1. Copy `.env.example` to `.env`.
2. Set `DATABASE_URL` to your PostgreSQL database.
3. Generate `JWT_SECRET_KEY`, `CSRF_SECRET`, and a Fernet `TOKEN_ENCRYPTION_KEY`.
4. Create a Mastodon application and set its redirect URI to:

`http://localhost:8000/api/oauth/mastodon/callback`

5. Install backend dependencies:

```powershell
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

6. Install frontend dependencies:

```powershell
cd frontend
npm install
npm run dev
```

Frontend: `http://localhost:5173`  
Backend: `http://localhost:8000`  
Swagger: `http://localhost:8000/docs`

## OCR

The Python dependencies include Pillow and pytesseract. The Tesseract executable itself must also be installed on the host and available on `PATH`. If it is unavailable, the image endpoint returns a clear `503` instead of pretending OCR succeeded.

## API highlights

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/oauth/mastodon/start`
- `GET /api/oauth/mastodon/callback`
- `GET /api/accounts`
- `POST /api/accounts/{id}/sync`
- `POST /api/scan`
- `POST /api/scan/image`
- `GET /api/dashboard`
- `GET /api/incidents`
- `PATCH /api/incidents/{id}`
- `GET /api/alerts`
- `POST /api/alerts/{id}/read`
- `GET /api/reports/json`
- `GET /api/reports/csv`

## Security

- OAuth tokens are encrypted with Fernet before database storage.
- OAuth state and Mastodon PKCE verifier are HttpOnly and short-lived.
- Passwords use Argon2.
- JWT access tokens are short-lived and delivered via HttpOnly cookies.
- State-changing API requests require the CSRF double-submit token.
- Users can only access their own accounts, content, incidents, alerts and reports.
- Audit logs intentionally exclude credentials and raw secrets.
- Uploads are restricted by MIME type and configured size, and images are verified before OCR.
- SQLAlchemy and Pydantic handle database/query and input validation.

## Testing

```powershell
cd backend
pytest -q
```

Health check:

```powershell
curl http://localhost:8000/health
```

For the full manual verification checklist see `docs/TESTING.md`.

## Production notes

Run the FastAPI application behind TLS, set `COOKIE_SECURE=true`, use a managed PostgreSQL instance, configure a real frontend origin, keep OAuth redirect URIs exact, use a secrets manager, and run a single scheduler instance (or move the scheduler to a dedicated worker) when horizontally scaling the API.
