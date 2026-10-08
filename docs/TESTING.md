# Testing

## Automated backend tests

```powershell
cd backend
pytest -q
```

The AI tests verify detection and risk classification without calling external services.

## Backend smoke checks

```powershell
curl http://localhost:8000/health
```

Open Swagger at `/docs` and verify:

- `/health`
- `/api/auth/register`
- `/api/auth/login`
- `/api/accounts`
- `/api/scan`
- `/api/scan/image`
- `/api/incidents`
- `/api/alerts`
- `/api/reports/json`
- `/api/reports/csv`

## End-to-end Mastodon checklist

1. Register or sign in.
2. Open **Mastodon** and connect an authorized Mastodon account.
3. Confirm the Mastodon consent screen appears.
4. Confirm the callback returns to the Accounts page.
5. Confirm `/api/accounts` shows the account but never exposes an access token.
6. Click **Sync now** and confirm `synced` and `analyzed` counts.
7. Publish a controlled test status containing a dummy email or dummy API-key-shaped value.
8. Wait for the next background sync or use **Sync now**.
9. Confirm the status is analyzed once.
10. Confirm a high/critical test creates an incident and alert.
11. Open **Alerts**, mark the alert read, and verify the sidebar badge decreases.
12. Open **Incidents**, inspect evidence/source/recommendations, update status and save notes/resolution.
13. Export JSON and CSV reports.
14. Disconnect the Mastodon account and confirm it no longer syncs.

## OCR checklist

1. Install Tesseract and make sure `tesseract --version` works in the same terminal used to run FastAPI.
2. Open **AI Scanner → Image OCR**.
3. Upload a PNG/JPEG/WebP containing a dummy sensitive value.
4. Confirm OCR text is analyzed and a normal `AnalysisOut` result is returned.
5. Try an unsupported file type and confirm HTTP 415.
6. Try a file over `MAX_UPLOAD_MB` and confirm HTTP 413.

## Security checks

- Wrong password is rejected.
- Unauthenticated dashboard/accounts/incidents access is rejected.
- Changing another user's incident ID does not disclose it.
- State-changing requests without the CSRF token are rejected.
- OAuth state mismatch is rejected.
- OAuth state/verifier cookies are HttpOnly and short-lived.
- API responses never contain OAuth access/refresh tokens.
- Uploaded files are MIME, size and image-structure validated.
- Audit records do not contain raw passwords, OAuth tokens or API keys.
