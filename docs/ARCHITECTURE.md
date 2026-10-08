# LeakGuard architecture

```text
React/Vite
   │ HTTPS + HttpOnly cookies + CSRF header
   ▼
FastAPI
   ├── Auth / RBAC / rate limit / security headers
   ├── Mastodon OAuth + PKCE
   ├── Mastodon sync API
   ├── Manual text + OCR image scanner
   ├── Incidents / alerts / reports
   └── 60-second background scheduler
          │
          ▼
PostgreSQL
   ├── users / refresh_tokens
   ├── social_accounts
   ├── social_content
   ├── analysis_results
   ├── incidents / alerts
   └── audit_logs
```

## Analysis flow

1. Mastodon status is normalized into `social_content`.
2. Each content row is analyzed once by the deterministic sensitive-data engine.
3. Optional OpenAI explanation enriches the result; it does not replace the deterministic detector.
4. `analysis_results` stores risk, severity, decision, confidence, findings and recommendations.
5. Risk ≥ 61 creates an incident and alert.
6. The dashboard, incident queue and reports read the persisted evidence.

## Ownership

`analysis_results.user_id` ties every manual or synchronized analysis to its owner. The second Alembic migration backfills existing incident-linked analyses.

## Background synchronization

The scheduler is started and stopped through FastAPI lifespan. A lock prevents overlapping sync cycles in one process. For multi-instance production deployments, move this job to a dedicated worker or use a distributed job lock so only one scheduler performs provider synchronization.
