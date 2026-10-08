# Security Controls

## OWASP-oriented controls

| Area | LeakGuard control |
|---|---|
| Broken access control | User ownership filters + admin dependency |
| Cryptographic failures | Argon2 passwords + Fernet OAuth-token encryption + TLS deployment requirement |
| Injection | SQLAlchemy parameterized queries + Pydantic validation |
| Insecure design | Provider adapters, normalized schemas, least-privilege scopes |
| Security misconfiguration | Security headers, CORS allowlist, production checklist |
| Vulnerable components | Pinned dependency versions |
| Identification/auth failures | Short-lived access JWT + rotating refresh sessions |
| Software/data integrity | Migrations and explicit API contracts |
| Logging failures | Audit log with secret exclusion |
| SSRF | Provider instances should be allowlisted in production if arbitrary instance input is enabled |

## CSRF

The application uses HttpOnly session cookies plus a non-HttpOnly CSRF cookie and `X-CSRF-Token` double-submit validation for authenticated state-changing requests. OAuth callbacks and authentication bootstrap endpoints are explicitly exempt because they have separate state/credential protections.

## File upload

The current image endpoint validates content type and size and fails closed because OCR is not bundled into the base image. Do not claim image text has been analyzed unless an OCR worker is installed and tested.

## Token handling

Provider access/refresh tokens are encrypted in PostgreSQL. They are never returned by API responses and must never be placed in audit metadata.
