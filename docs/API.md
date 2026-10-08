# API Contract

Base URL: `/api`

## Authentication

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `GET /auth/me`

## OAuth

- `GET /oauth/mastodon/start?instance=https://mastodon.social`
- `GET /oauth/mastodon/callback`

## Social accounts

- `GET /accounts`
- `DELETE /accounts/{account_id}`
- `POST /accounts/{account_id}/sync`

## Content

- `GET /content`

## AI

- `POST /scan`
- `POST /scan/image`

## Incidents and alerts

- `GET /incidents`
- `PATCH /incidents/{incident_id}`
- `GET /alerts`
- `POST /alerts/{alert_id}/read`

## Dashboard

- `GET /dashboard`

## Reports

- `GET /reports/json`
- `GET /reports/csv`

FastAPI automatically exposes the complete OpenAPI schema at `/openapi.json`.


Mastodon OAuth endpoints:
- `GET /oauth/mastodon/start`
- `GET /oauth/mastodon/callback`
