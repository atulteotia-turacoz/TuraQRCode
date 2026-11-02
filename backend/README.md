# TuraQRcode · Backend

TuraQRcode is the Turacoz QR-code, barcode, and short-link platform. One root Git repository contains three independently runnable application folders: `backend`, `frontend`, and `admin`. The root also contains project documentation and Git configuration.

[Complete project README](../README.md) · [CloudPanel deployment and updates](../DEPLOYMENT.md)

## Local setup (Windows PowerShell)

Run these commands from `E:\TuraQRcode\backend`:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
# Copy .env.example to .env only when .env does not already exist.
.venv\Scripts\python.exe -m app.manage check
.venv\Scripts\python.exe -m app.manage init
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Run the API with `.venv\Scripts\python.exe` as shown. The system Python may contain an unrelated package named `barcode`; installing `requirements.txt` in the project environment provides the barcode generator used here.

The supplied Supabase project is connected using `DATABASE_URL` in `backend/.env`. The project URL and publishable key alone cannot authorize direct PostgreSQL access. Get a session-pooler PostgreSQL URI from Supabase → Connect, and URL-encode special characters in its password. All connection credentials stay on the server. Environment variables override environment files. An optional root `backend.env` is also recognized for compatibility, but keep configuration in `backend/.env` to preserve the three-folder layout.

`app.manage init` applies Alembic migrations and creates the initial administrator if it does not exist. It never resets an existing administrator password. The initial email is **Admin@turacoz.com**; its temporary password is configured privately through `INITIAL_ADMIN_PASSWORD` before first initialization. The password is hashed with Argon2id and the account is blocked from product and administration operations until it changes its password. Clear `INITIAL_ADMIN_PASSWORD` after initialization. Never put bootstrap credentials in a frontend environment file or publish them in deployment documentation.

The API is at `http://127.0.0.1:8000`, API documentation at `/api/docs`, liveness at `/api/health`, and readiness at `/api/ready`. Start the two React applications using their own READMEs.

For later local starts, from the backend directory, run `.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`. Install dependencies only for a fresh environment or changed requirements, and run `app.manage migrate` when migrations change. Do not replace an existing `.env` with its template.

After dependencies are installed in all three folders, start them together from the backend terminal with `.venv\Scripts\python.exe scripts\dev.py`. Ctrl+C stops all three. This uses your existing Supabase configuration; the local PostgreSQL helper is needed only for the automated test suites.

## Implemented capabilities

- Registration with recorded Terms & Conditions and Privacy Policy acceptance; sign-in, logout, profile updates, strong-password changes, session revocation, and expiring single-use recovery links.
- Seven QR content types: URL, text, email, phone, SMS, Wi-Fi, and vCard. Editable URL QR codes and short links support custom aliases, changing destinations, expiration, access passwords, mobile destinations, and pausing.
- Seven QR patterns and independent corner styles; 20 scan-safe color palettes including gradients; contrast validation; movable, individually styled labels; customizable frames; normalized raster logos; PNG, SVG, and PDF exports.
- Code 128, Code 39, EAN-13, EAN-8, and UPC-A barcode generation with validated check digits, captions, and PNG/SVG/PDF exports.
- A default project per account, including existing users and previously unassigned codes; safe project deletion moves codes to the default.
- Ownership-protected saved codes, search, filters, pagination, projects, business cards, bulk creation with row-level results, ZIP bundles, and A4 print sheets.
- Scan/click request tracking, UTC daily aggregates, devices, referrer hosts, and CSV activity exports (up to 50,000 rows per export).
- Separate administrator APIs for account suspension/restoration, managed-code moderation, recovery assistance, platform counts, and audit history.

Static content is immutable and does not report scans. Downloaded static QR codes continue to work independently of their saved status or deletion. Activity counts requests rather than verified individuals. No precise geolocation or visitor IP addresses are stored in analytics.

## Database and security

Application tables live in the PostgreSQL `public` schema, with RLS enabled and table privileges revoked from `PUBLIC`, Supabase `anon`, and `authenticated`. Use the trusted server owner/database role, never the publishable key, for backend connections. The server enforces ownership and administrator roles independently of RLS. Migrations are in `migrations/versions`; run `python -m app.manage migrate` for later schema upgrades.

Remote connections require TLS. A supplied `verify-ca` or `verify-full` setting is preserved; otherwise the backend enforces `sslmode=require`. For certificate identity verification in production, configure `sslmode=verify-full` and an appropriate trusted root certificate using Supabase’s SSL guidance.

Sessions use random opaque tokens in HttpOnly, SameSite=Lax cookies; only SHA-256 token hashes are stored. Password changes revoke all prior sessions. Unsafe requests check the allowed Origin and authenticated requests require an Origin. Use `CORS_ORIGINS` with exact first-party origins. API errors avoid returning SQL, connection strings, or validation inputs. Logs do not include password or recovery-token bodies. Request sizes, QR colors, logo formats/dimensions, aliases, content types, URLs, and bulk row counts are validated.

The bundled limiter is for a **single API process**. Keep one worker, or put a shared rate limiter at the gateway before scaling. Configure a trusted reverse proxy if per-client limits are needed behind a proxy; untrusted forwarding headers are not used by the application. CORS and origins must match your deployment.

## Testing

The optional local PostgreSQL utility runs genuine PostgreSQL binaries; Docker is not required. It listens only on loopback, uses SCRAM authentication and a generated local password, and stores its files in `backend/.local`.

```powershell
cd tools
npm ci
npm run db:local
```

Leave that terminal running. In another backend terminal:

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m pip_audit --progress-spinner off
.venv\Scripts\python.exe scripts\supabase-smoke.py
```

Pytest refuses destructive tests unless the host is loopback and the database is `tura_test`. Browser tests use a separate `tura_e2e` database on port 55432, enforce the same guard, and never overwrite `.env`. See `frontend/README.md` for browser commands. The live smoke check creates one temporary account in the configured database and removes only that account’s test data afterward. It verifies initial administrator state and should be adapted after the real administrator changes its temporary password.

See [verification](docs/VERIFICATION.md) for the executed feature checks and practical limits.

## Production URL configuration

Before creating production records, set final HTTPS `PUBLIC_BASE_URL`, `FRONTEND_URL`, exact customer/admin `CORS_ORIGINS`, and `COOKIE_SECURE=true` in the production service environment. URL settings accept origins only and normalize trailing slashes/default ports. Run `.venv/Scripts/python.exe -m app.manage check-deployment` on Windows, or `.venv/bin/python -m app.manage check-deployment` on Linux, followed by the existing database check/init commands. This read-only production preflight rejects local/insecure settings; it is expected to fail for a local HTTP development environment.

Use a separate empty production database; no demo data migration or reset is required. Managed URLs come from configuration rather than request Host headers. Protected QR/barcode forms preserve their scan channel. Linked business-card redirects follow the configured public hostname without rewriting stored records; explicit website/mobile overrides retain their destination. See [the deployment guide](../DEPLOYMENT.md) for same/separate public domains, proxy/query routing, retained-domain origins, deployment verification, and rollback constraints.

## Recovery email

Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, `SMTP_USER`, and `SMTP_PASSWORD` to enable recovery messages. STARTTLS is enabled by default. Without SMTP, the public recovery page provides private, non-enumerating instructions and an administrator can create a confidential recovery link in the admin application. The app never displays a reset token to an unauthenticated requester. SMTP delivery requires your own credentials and has not been verified without them.

## Production and a branded link domain

1. Deploy the API behind HTTPS and set `COOKIE_SECURE=true`.
2. Set `FRONTEND_URL` to the customer app origin, `CORS_ORIGINS` to the customer and admin origins, and `PUBLIC_BASE_URL` to your stable public link hostname. Configure these **before distributing dynamic codes**; changing the hostname cannot change codes already printed.
3. Route `/r/*`, `/c/*`, and `/api/*` from the public hostname to FastAPI. Serve each React `dist` with SPA fallback. The supplied Nginx/Docker files provide this routing. If the two apps are on different origins, proxy their `/api` paths to the API so cookies remain first-party.
4. Create DNS records and issue TLS certificates for your own domain. This release supports one configured branded link hostname per deployment. It does not provision DNS, offer self-service per-account domains, or claim to verify a hostname that has not been provided.
5. Apply migrations once, initialize the administrator, change the temporary password, configure mail, and establish PostgreSQL backups and restore procedures.

The optional `compose.yml` builds all three applications using the existing Supabase database. Set origins and public URLs for your deployment before using it. With the sample port mapping, use customer `http://localhost:8080`, admin `http://localhost:8081`, and matching environment origins. For production terminate HTTPS at a trusted edge proxy. Run initialization explicitly:

```powershell
docker compose run --rm backend python -m app.manage init
docker compose up --build -d
```

Docker Desktop was not running in the development environment; Docker deployment is supplied but not an executed verification result. Review the initial Terms and Privacy content for your operating practices before public launch.

## SaaS mode and administration

The administration app controls the commercial model under **SaaS and plans**. With SaaS off (the default), the website shows sign in only, `/api/auth/register` is refused, and accounts are created under **Accounts**. With SaaS on, the website shows plans and sign-up, and each account's plan limits apply to new codes, business cards and projects. Existing items keep working when a limit is reached or a plan lapses.

Creating a QR code or barcode always requires signing in. Administrator accounts sign in only through the administration app.

**Landing page** edits all public website text, **Email (SMTP)** replaces the `SMTP_*` environment values, and **Payment gateways** configures Razorpay, Stripe and CCAvenue. Customers pay on the provider's hosted page; plans are prepaid for 30 or 365 days and do not renew automatically. SMTP passwords and gateway keys are encrypted with a key derived from `SECRET_KEY`, so changing `SECRET_KEY` means re-entering them.

Reference sources: [Supabase PostgreSQL connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres), [FastAPI security guidance](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/). QRStuff was consulted for [feature reference only](https://www.qrstuff.com/).

### Barcode dependency repair

The required encoder is **`python-barcode==0.16.1`**. The unrelated package named `barcode` is a genetics tool and can shadow the encoder, causing preview errors (including the old `pkg_resources` failure). Use the project's virtual environment for the service and all dependency commands. If an existing environment contains the wrong package, run these commands with the same Python interpreter that starts FastAPI:

```powershell
python -m pip uninstall -y barcode
python -m pip install --force-reinstall python-barcode==0.16.1
python -m pip install -r requirements.txt
```

Run from `backend`, restart FastAPI, then verify `/barcode-generator` and a saved tracked barcode. Fresh installations using `requirements.txt` install the correct encoder and `resvg-py` directly.
