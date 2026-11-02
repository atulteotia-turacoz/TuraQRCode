# Deploy TuraQRcode on CloudPanel

This guide deploys the current React customer app, React administrator app, and FastAPI service with Supabase PostgreSQL. It also explains how to recreate everything excluded from Git and how to update an existing installation.

**This is a deployment runbook, not a claim that a CloudPanel server has already been configured.** Local builds, browser/API tests, and Supabase persistence were verified; actual server/DNS/SMTP settings must be provided by the operator.

## 1. Deployment layout

Replace these example values consistently with your own domains and CloudPanel site users:

| Purpose | Example |
|---|---|
| Customer domain | `qr.example.com` |
| Administrator domain | `admin.qr.example.com` |
| Customer/backend Linux site user | `tura` |
| Administrator Linux site user | `turaadmin` |
| Private source checkout | `/home/tura/apps/TuraQRcode` |
| Private backend environment | `/home/tura/apps/TuraQRcode/backend/.env` |
| Customer public document root | `/home/tura/htdocs/qr.example.com` |
| Administrator public document root | `/home/turaadmin/htdocs/admin.qr.example.com` |
| FastAPI listener | `127.0.0.1:8000` only |
| Systemd service | `turaqrcode.service` |

The two public sites serve only the contents of their compiled `dist` directories. Their `/api/` requests are proxied to the same local FastAPI service. The customer site also proxies `/r/` and `/c/`. No separate public API domain is required, and cookies stay first-party on each application origin.

Keep the source checkout and `backend/.env` **outside both public document roots**. Do not set a site's root to the repository root or to `backend`. The database stays in Supabase; you do not need to create a CloudPanel MySQL database.

## 2. Server prerequisites

You need an existing CloudPanel v2 Linux server, SSH access, a sudo/root administrator for systemd/Nginx operations, your domain DNS access, and your Supabase PostgreSQL URI. Install Git, rsync, Node.js 22/npm, and Python 3.13 with its venv support before application setup.

Verify as the application site user:

```bash
git --version
node --version
npm --version
python3.13 --version
```

Python 3.13 is the tested runtime. If it is missing, have the server administrator install it using the host's approved runtime method; do not replace CloudPanel's system `python` binary. CloudPanel documents [adding an additional Python version](https://www.cloudpanel.io/docs/v2/python/guides/adding-a-python-version/). Its example is an older version: select the supported 3.13 runtime for this application instead. Node is needed to build the React apps; you will not run Vite in production.

Allow the server to reach GitHub/npm/PyPI and the Supabase connection host. If Supabase network restrictions are enabled, allow this server's outbound IP. Keep port 8000 private; public web traffic goes through CloudPanel's HTTPS Nginx sites.

## 3. Create sites, DNS, and certificates

1. Point DNS records for the customer and administrator hostnames to the server. Configure IPv6 records only if IPv6 is actually available.
2. In CloudPanel → **Sites → Add Site**, create two **Static HTML** sites using the respective domains/site users above. These are compiled React applications; they do not need Node development servers. See [CloudPanel site creation](https://www.cloudpanel.io/docs/v2/frontend-area/add-site/).
3. In each site's Settings, confirm its Root Directory is the intended `htdocs` directory. CloudPanel allows changing this in [Domain Settings](https://www.cloudpanel.io/docs/v2/frontend-area/settings/).
4. In each site's SSL/TLS area, use **Actions → New Let's Encrypt Certificate**, include the correct hostname, and install the certificate after DNS resolves. The initial self-signed certificate is not the final public certificate. See [CloudPanel SSL/TLS](https://www.cloudpanel.io/docs/v2/frontend-area/tls/).

The commands below use the example users/paths from section 1. Check the actual values shown by CloudPanel and adjust them before running commands.

## 4. Clone source as the application user

Log in as `tura` using SSH, or switch from a privileged session:

```bash
sudo -iu tura
mkdir -p /home/tura/apps
cd /home/tura/apps
git clone https://github.com/liyakhath-turacoz/TuraQRcode.git
cd TuraQRcode
git switch main
```

For a private repository, use a read-only GitHub deploy key or your approved credential helper. An SSH alternative is `git clone git@github.com:liyakhath-turacoz/TuraQRcode.git`. Do not put a personal access token in a URL, tracked file, deployment script, or shell history.

## 5. Recreate Python dependencies

Still as `tura`:

```bash
cd /home/tura/apps/TuraQRcode/backend
python3.13 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

Use `requirements.txt` in production. `requirements-dev.txt` adds tests, decoding tools, and audit tooling and is intended for development/staging. Do not copy a Windows `.venv` to Linux: create a new Linux virtual environment on the server.

## 6. Create the private backend environment

Create the template only on the first installation; never overwrite an existing `.env` during an update:

```bash
cd /home/tura/apps/TuraQRcode/backend
umask 077
test -f .env || cp .env.example .env
chmod 600 .env
nano .env
```

Use deployment-specific values, for example:

```dotenv
DATABASE_URL=postgresql+psycopg://DATABASE_USER:URL_ENCODED_PASSWORD@SUPABASE_SESSION_POOLER_HOST:5432/postgres?sslmode=require
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_PUBLISHABLE_KEY=YOUR_PROJECT_PUBLISHABLE_KEY

PUBLIC_BASE_URL=https://qr.example.com
FRONTEND_URL=https://qr.example.com
CORS_ORIGINS=https://qr.example.com,https://admin.qr.example.com
COOKIE_SECURE=true
SESSION_HOURS=24

INITIAL_ADMIN_EMAIL=Admin@turacoz.com
INITIAL_ADMIN_PASSWORD=

SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
SMTP_STARTTLS=true
```

These placeholders are not working credentials. Copy the exact PostgreSQL URI from Supabase **Connect → Session pooler**. Its hostname/username depend on the project; do not infer them from the HTTPS URL. URL-encode reserved characters in the password. The publishable key cannot replace `DATABASE_URL`. The application uses a direct server-side SQL connection; it does not need a Supabase service-role key.

### What each value controls

| Variable | What to set or update |
|---|---|
| `DATABASE_URL` | Real PostgreSQL/session-pooler URI. Change after database credential rotation or when choosing a different project; restart FastAPI afterward. Keep it server-side. |
| `SUPABASE_URL` | Your project's HTTPS URL, used by the optional Supabase endpoint diagnostic. It does not authenticate PostgreSQL. |
| `SUPABASE_PUBLISHABLE_KEY` | Optional HTTPS diagnostic key. This is a public key, not a database password or service-role key. |
| `PUBLIC_BASE_URL` | Stable HTTPS hostname where `/r/` and `/c/` are publicly reachable. Choose before printing codes. This determines newly generated managed QR/card URLs. |
| `FRONTEND_URL` | Customer origin, used in recovery links. |
| `CORS_ORIGINS` | Exact customer/admin origins, comma-separated, with no paths; keep synchronized with the real domains. Also used by Origin protection. |
| `COOKIE_SECURE` | `true` for HTTPS production. Local HTTP development uses `false`. |
| `SESSION_HOURS` | Login session lifetime, default 24 hours. |
| `INITIAL_ADMIN_EMAIL` | Bootstrap administrator email. It is not an administrator-management interface. |
| `INITIAL_ADMIN_PASSWORD` | Required only if initializing a database without the administrator. Set a private temporary password, initialize, change it on first sign-in, then clear this value. Existing accounts are not reset by initialization. |
| `SMTP_*` | Your mail provider's host, port, credentials, sender, and STARTTLS choice. Configure and test actual email delivery before relying on emailed recovery. |
| `SECRET_KEY` | Reserved setting in the current config/template; current sessions use random server-stored opaque tokens, so this is not a JWT signing key. Do not publish a value if you choose to set it. |

### Changing the public link domain

The public origin is configuration-driven. Generated managed QR addresses, tracked Code 128 addresses, short links, and digital-card addresses use `PUBLIC_BASE_URL`; no frontend source edit or rebuild is needed to change that hostname. For example, to move new links from `https://qr.example.com` to `https://go.example.com`:

1. Add the new hostname in CloudPanel, point its DNS record to the same server, and issue its HTTPS certificate.
2. Merge [`backend/deploy/cloudpanel/short-domain.locations.conf`](backend/deploy/cloudpanel/short-domain.locations.conf) into that hostname's Nginx server block. It routes `/r/` and `/c/` to FastAPI and returns 404 for unrelated paths.
3. Set `PUBLIC_BASE_URL=https://go.example.com` in `backend/.env`. Keep `FRONTEND_URL` on the customer application domain. Include the real customer/admin origins in `CORS_ORIGINS`. The configured public/customer origins are also trusted for CORS and protected-form requests. Any retained old link hostname that must accept password-form submissions must remain explicitly listed in `CORS_ORIGINS`.
4. Run `.venv/bin/python -m app.manage check-deployment`, restart FastAPI with `sudo systemctl restart turaqrcode`, and verify `/api/ready`, a new editable QR redirect, a short link, a tracked barcode, and a business-card profile over HTTPS.

This changes URLs generated from then on. A QR code already printed with the old hostname still points to that old hostname, so keep its DNS and redirect routes active or update/reprint the affected code before retiring the old domain. Choose the permanent hostname before distributing codes whenever possible.

Linked business-card QR redirects resolve the card profile using the current configured public domain, including after a future domain change. This does not rewrite database records, alter user-entered external website destinations, or change downloaded image bytes. Explicitly customized QR destinations and mobile destinations are preserved. Password-protected QR and tracked barcode forms retain their scan channel across incorrect-password retries and successful redirects; short-link visits remain link clicks.

### Fresh production data and URL preflight

Development/demo data is not part of the production release. Use a separate, empty production Supabase project/database and set its PostgreSQL URI in the server's private `backend/.env`. Do not copy the development `.env`, `backend.env`, database backup, `.local`, test inventories, demo images, browser sessions, or sample-account scripts to production. `app.manage init` creates only the bootstrap administrator/default project and runs schema migrations; it does not populate demonstration QR codes, barcodes, links, or business cards. An existing database is never automatically emptied by deployment.

Set final domains **before initialization and before generating anything intended for distribution**. Choose one of these layouts:

| Setting | One customer/link hostname | Separate branded link hostname |
|---|---|---|
| `PUBLIC_BASE_URL` | `https://qr.example.com` | `https://go.example.com` |
| `FRONTEND_URL` | `https://qr.example.com` | `https://qr.example.com` |
| `CORS_ORIGINS` | `https://qr.example.com,https://admin.qr.example.com` | `https://qr.example.com,https://admin.qr.example.com` |
| `COOKIE_SECURE` | `true` | `true` |
| Customer/admin `VITE_API_URL` | Unset/blank; same-origin `/api/` proxy | Unset/blank; same-origin `/api/` proxy |

`PUBLIC_BASE_URL`, `FRONTEND_URL`, and every `CORS_ORIGINS` entry must be an HTTP/HTTPS **origin**, not a page URL: no `/app`, `/api`, `/r`, `/c`, query, fragment, username/password, or wildcard. Trailing slashes, hostname case, and default ports are normalized. Invalid values stop startup rather than emitting malformed links. Generated addresses never use an incoming Host or forwarding header as their source of truth.

Run this configuration check using the same private environment and interpreter as the service:

```bash
cd /home/tura/apps/TuraQRcode/backend
.venv/bin/python -m app.manage check-deployment
.venv/bin/python -m app.manage check
.venv/bin/python -m app.manage init
```

`check-deployment` is read-only and does not connect to or change the database. It rejects insecure cookies, non-HTTPS production origins, loopback/private IPs, localhost domains, and an empty allowed-origin list. It prints only public URL settings and configuration diagnostics, never database credentials. Local development intentionally uses HTTP/loopback and is expected to fail this **production-only** check. `check` separately verifies PostgreSQL; DNS, certificate validity, proxy routing, and SMTP still need real server checks. Remove any legacy checkout-root `backend.env` from the production checkout: it is loaded after `backend/.env` and can override that file. Keep environment variables supplied by systemd consistent as they take precedence over both files.

URL responsibilities after configuration:

| Flow | Behavior |
|---|---|
| Dynamic QR and tracked barcode | Encode the configured `/r/{slug}` address and preserve `via=qr` / `via=barcode`; a visit redirects to the saved destination and records the appropriate channel. |
| Short link | Uses the configured `/r/{slug}` address; ordinary short-link visits count as link clicks. |
| Static QR and product/inventory barcode | Encode the user's actual URL/text/product value; neither the value nor its tracking behavior is changed by the hosting domain. |
| Business card | Public profile and vCard use `/c/{slug}` on the configured public host; the linked managed QR resolves its profile against that host. |
| Password, expiry, pause | Checked on the managed public endpoint before redirecting. Incorrect passwords do not record successful interactions. |
| Mobile destination | The explicitly supplied mobile URL is preserved; it is not replaced with the application's domain. |
| Password recovery | Uses `FRONTEND_URL/reset-password?token=...`, never the short-link-only host or request Host header. |
| QR Scanner | Decodes on the device. Opening a managed URL produces its normal redirect event; merely reading an image does not record a server visit. |

On a separate branded link site, install the `short-domain.locations.conf` fragment for `/r/` and `/c/`. The customer and admin sites must each proxy `/api/` to the same backend/database. Preserve path **and query string** when proxying; avoid rewrite rules that discard `via`, reset tokens, or aliases. Do not cache `/api/`, `/r/`, or `/c/` at Nginx/CDN level. Do not add an extra restrictive `form-action 'self'` CSP to protected `/r/` pages; it can block cross-site destination navigation after a password POST. Proxy to the API as shown, with no trailing slash on `proxy_pass http://127.0.0.1:8000;`.

After the first deployment, generate fresh static/dynamic QR, a short link, a tracked Code 128, and a card. Decode the downloaded files and confirm that managed URLs contain the production hostname, never `localhost`, `127.0.0.1`, a LAN IP, or port 8000. Test public navigation in a signed-out browser and on a phone, incorrect/correct access passwords, desktop/mobile destinations, pause/expiry, profile/vCard links, and analytics channel counts. Test a recovery link against the customer domain after SMTP configuration. Record results before printing/distributing codes.

If using the same Supabase database already initialized during development, its administrator/data remain present; `init` does not replace that administrator's password. For a new production database, set a private strong temporary bootstrap password rather than publishing a shared password in documentation.

For stronger database certificate identity verification, use Supabase's provided CA/trust configuration with `sslmode=verify-full`. The backend enforces encrypted remote PostgreSQL connections and preserves a supplied `verify-ca`/`verify-full` setting. Keep `tura` private and do not add it to Supabase exposed API schemas. See [Supabase connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres).

### Do the React apps need environment files?

Not for the recommended same-origin proxy deployment. Leave `VITE_API_URL` unset/blank in both apps so requests use `/api/...` on their own domain.

If you deliberately use an external API origin, set `VITE_API_URL` in each app's private build environment and rebuild that app. Any `VITE_*` value is bundled into public JavaScript. Never put database passwords, SMTP credentials, bootstrap passwords, service-role keys, or other secrets in frontend/admin environment variables. `API_PROXY_TARGET` is for Vite development only and does not configure production Nginx.

## 7. Check PostgreSQL and apply migrations

```bash
cd /home/tura/apps/TuraQRcode/backend
.venv/bin/python -m app.manage check
.venv/bin/python -m app.manage init
```

`init` applies migrations and creates the initial administrator only if missing. Later deployments normally use `app.manage migrate`. Do not recreate tables manually or delete the existing application tables to update the application.

If connection checking fails, fix the URI/password/SSL/network access before starting the service. Never run destructive test launchers against Supabase. Establish a protected Supabase backup/restore procedure before applying future migrations to valuable data.

For a fresh production installation, first run the production-only URL preflight in section 6 and initialize the separate empty production database. Local demo accounts and generated records are intentionally not migrated.

## 8. Build both React applications

As `tura`:

```bash
cd /home/tura/apps/TuraQRcode/frontend
npm ci --include=dev
npm run build

cd /home/tura/apps/TuraQRcode/admin
npm ci --include=dev
npm run build
```

Use `npm ci` because the repository includes lockfiles. Build tooling is in dev dependencies, hence `--include=dev` even if your server has `NODE_ENV=production`. The output is `frontend/dist` and `admin/dist`; `node_modules` is not a public web root. You do not need `backend/tools` or its local PostgreSQL binaries on production.

Publish only compiled files. From a **root/sudo session**, after checking that these are the two CloudPanel document roots:

```bash
test -f /home/tura/apps/TuraQRcode/frontend/dist/index.html
test -f /home/tura/apps/TuraQRcode/admin/dist/index.html
rsync -a --chown=tura:tura /home/tura/apps/TuraQRcode/frontend/dist/ /home/tura/htdocs/qr.example.com/
rsync -a --chown=turaadmin:turaadmin /home/tura/apps/TuraQRcode/admin/dist/ /home/turaadmin/htdocs/admin.qr.example.com/
```

The trailing source slash copies the contents. These commands intentionally retain old hashed assets so browsers with an earlier loaded page do not immediately lose their assets. Review/prune obsolete assets separately after the relevant cache period. If CloudPanel initially created a placeholder `index.html`, this publication replaces it with the React build.

## 9. Run FastAPI with systemd

Use [the supplied service example](backend/deploy/cloudpanel/turaqrcode.service.example). Adapt the user, group, and paths if you changed them. As root:

```bash
sudo nano /etc/systemd/system/turaqrcode.service
```

Paste:

```ini
[Unit]
Description=TuraQRcode FastAPI
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=tura
Group=tura
WorkingDirectory=/home/tura/apps/TuraQRcode/backend
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/home/tura/apps/TuraQRcode/backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips=127.0.0.1 --no-access-log
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
UMask=0077

[Install]
WantedBy=multi-user.target
```

The app reads its protected `backend/.env` itself; do not duplicate secrets into the service unit. One worker matches the current in-process rate limiter. Before scaling workers/servers, use a shared gateway limiter.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now turaqrcode
sudo systemctl status turaqrcode --no-pager
curl --fail http://127.0.0.1:8000/api/ready
```

If the service fails, inspect `sudo journalctl -u turaqrcode -n 100 --no-pager`. Check the executable path, private `.env` ownership/read access, PostgreSQL connectivity, and whether another process owns port 8000. Do not make the environment world-readable to fix permissions.

## 10. Configure CloudPanel's Nginx Vhosts

CloudPanel's [Vhost Editor](https://www.cloudpanel.io/docs/v2/frontend-area/vhost/) is the supported place to adjust routing. Preserve CloudPanel's generated hostnames, TLS certificate directives, HTTP-to-HTTPS redirects, logs, and ACME challenge handling. Edit the application server containing the static document root; do not paste an entire second `server` block into it.

Replace the site's existing catch-all `location /` with the appropriate fragment below, and add the other location blocks at the same server level. Merge/replace duplicate locations instead of creating two `location /` blocks. Keep or merge existing hidden-file protection.

### Customer site

Use [frontend.locations.conf](backend/deploy/cloudpanel/frontend.locations.conf):

```nginx
client_max_body_size 3m;

location ^~ /api/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 60s;
    proxy_cache off;
    proxy_no_cache 1;
}
location ^~ /r/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_cache off;
    proxy_no_cache 1;
}
location ^~ /c/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_cache off;
    proxy_no_cache 1;
}
location ^~ /assets/ { expires 1y; try_files $uri =404; }
location = /index.html { expires -1; }
location ~ (^|/)\.(?!well-known(?:/|$)) { return 404; }
location / { try_files $uri $uri/ /index.html; }
```

Keep the prefixes exactly `/api/`, `/r/`, and `/c/`: using `/r` would also match `/register`. `proxy_pass` has **no trailing slash**, preserving the FastAPI route prefix. Do not cache authenticated APIs, redirects, password forms, or published cards with a page cache/Varnish layer.

### Administrator site

Use [admin.locations.conf](backend/deploy/cloudpanel/admin.locations.conf):

```nginx
client_max_body_size 3m;
location ^~ /api/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 60s;
    proxy_cache off;
    proxy_no_cache 1;
}
location ^~ /assets/ { expires 1y; try_files $uri =404; }
location = /index.html { expires -1; }
location ~ (^|/)\.(?!well-known(?:/|$)) { return 404; }
location / { try_files $uri $uri/ /index.html; }
```

The SPA fallback makes direct visits/refreshes such as `/app/codes` and `/users` work. The checked-in `frontend/nginx.conf` and `admin/nginx.conf` target the optional Docker network's `backend` hostname; use these **CloudPanel loopback fragments** on this host instead.

Save through CloudPanel. If changing files outside the panel, validate before reloading:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 11. Post-deployment checks

```bash
curl --fail https://qr.example.com/api/ready
curl --fail https://admin.qr.example.com/api/ready
curl -I https://qr.example.com/register
curl -I https://qr.example.com/app/codes
curl -I https://admin.qr.example.com/users
curl -I https://qr.example.com/.env
```

Readiness should be 200; SPA routes should serve HTML; `.env` should be blocked/not found, not downloadable. Then use the browser:

1. Register a real account with required policy acceptance, sign out, and sign back in.
2. Create an editable QR, download it, scan it from a phone outside the server network, and confirm the public destination and analytics.
3. Update its destination and confirm the printed QR still resolves. Check pause, access password, and expiry where relevant.
4. Create a business card and test its public page/contact download.
5. Sign in to administration, replace the temporary password if required, and verify account/code access is restricted.
6. If SMTP is configured, request recovery and verify actual delivery and link hostname. Otherwise use the tested administrator-assisted recovery workflow.

After initial administrator setup, clear `INITIAL_ADMIN_PASSWORD` from the private server `.env` and restart the API. Do not change `PUBLIC_BASE_URL` casually after distributing codes: previously printed URLs retain their original hostname and require continued routing there.

## 12. What is excluded from Git and how it comes back

| Not committed | Recreate/manage on the server |
|---|---|
| `frontend/node_modules`, `admin/node_modules` | Run `npm ci --include=dev` in each app from its committed manifest/lockfile. |
| `backend/.venv` | Create with Python 3.13, then install committed `requirements.txt`. |
| Real `.env` files / `backend.env` | Create privately from `.env.example`; fill the database URI, domains, mail credentials, and bootstrap configuration. Keep separate protected backups. |
| `frontend/dist`, `admin/dist` | Run `npm run build`, then publish each build's contents to the corresponding document root. |
| `.local` and local test PostgreSQL data | Not required in production. Production records stay in Supabase. |
| Test reports, caches, logs | Generated when running tests or services; keep logs/backups under appropriate private server retention policies. |
| Database contents/backups | Managed through Supabase and your backup process; Git contains migrations, not live records. |
| SSL/private keys and Git deployment credentials | Managed through CloudPanel/your secrets/SSH configuration; never in repository files. |

Commit `package.json`, **package-lock.json**, requirement files, migrations, source, documentation, and redacted `.env.example` templates. A publishable Supabase key is public by design, but a database password or service-role key is not.

Ordinary `git pull` leaves untracked ignored `.env` files alone. **Do not run `git clean -fdx`, `git clean -fdX`, or overwrite `.env` from the template** on the server: these can remove ignored secrets/runtime files. Do not run `npm update` during deployment; update and test dependencies in development and commit the changed lockfiles first.

## 13. Deploy an update from GitHub

The following is a straightforward in-place update with a short maintenance window, not a zero-downtime release system.

### Before changing the server

- Push the reviewed code/lockfiles/migrations to `main` and run tests in development/staging.
- Take a protected database backup/restore point before schema changes and verify your recovery procedure. Back up the current public builds and private configuration outside the public roots. CloudPanel site backups may not include the private `/home/tura/apps` checkout or the external Supabase database; cover them separately.
- Record the currently deployed commit using `git rev-parse HEAD` and retain the old build artifacts for rollback.

Stop the API as root so old application code is not running while the source/schema changes:

```bash
sudo systemctl stop turaqrcode
```

As `tura`, run the following **in order**, stopping on any failure:

```bash
set -e
cd /home/tura/apps/TuraQRcode
git status --short
git rev-parse HEAD
git fetch origin
git pull --ff-only origin main

cd /home/tura/apps/TuraQRcode/backend
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m app.manage check
.venv/bin/python -m app.manage migrate

cd /home/tura/apps/TuraQRcode/frontend
npm ci --include=dev
npm run build

cd /home/tura/apps/TuraQRcode/admin
npm ci --include=dev
npm run build
```

If the checkout has local tracked edits, resolve them intentionally before pulling; do not force-reset the server. After review, publish the new `dist` contents using the two `rsync` commands from section 8, then as root:

```bash
sudo systemctl start turaqrcode
sudo systemctl status turaqrcode --no-pager
curl --fail https://qr.example.com/api/ready
curl --fail https://admin.qr.example.com/api/ready
```

Repeat the browser checks from section 11. Static asset changes do not require a Vite process or Nginx restart; Nginx serves the newly published files. Reload Nginx only if its configuration changed, after `nginx -t`. If the systemd unit changed, run `systemctl daemon-reload` before restarting the service.

### Which changes require which actions?

| Change | Required action |
|---|---|
| Backend Python source | Pull code and restart FastAPI. |
| `backend/requirements.txt` | Install requirements in the server venv and restart FastAPI. |
| `backend/migrations/versions/*` | Back up first, run `app.manage migrate`, then start the matching application code. |
| Frontend/admin React/CSS/source | Rebuild the changed app and publish its `dist`; building/publishing both is the simple default. |
| `package.json` / lockfile | Run that app's `npm ci --include=dev`, build, and publish. |
| Backend `.env` values | Edit only the private server file and restart FastAPI. No React rebuild for a backend database/SMTP change. |
| A `VITE_*` public build value | Update that app's private build environment, rebuild, and republish. |
| New keys in `.env.example` | Review the template diff; add only the required new values to your existing private `.env`. Never replace the whole file. |
| Domain/cookie/origin change | Update DNS/certificates, routing, `PUBLIC_BASE_URL`/`FRONTEND_URL`/`CORS_ORIGINS`, and restart FastAPI; preserve old printed link hostnames. |
| Nginx/service configuration | Review settings separately; validate/reload Nginx or daemon-reload/restart systemd as appropriate. |

To review new environment keys without printing private values:

```bash
git diff PREVIOUS_COMMIT..HEAD -- backend/.env.example frontend/.env.example admin/.env.example
```

Replace `PREVIOUS_COMMIT` with the SHA recorded before the pull.

## 14. Rollback

If a deployment fails, leave the service stopped while investigating. Restore the previously retained customer/admin build artifacts, the recorded application revision, and its dependencies as appropriate. Use a reviewed checkout/deployment revision rather than blindly resetting a live worktree. Never delete `.env`, the Supabase database, or the application tables to repair a deployment.

Database migrations may change data or remove columns. Reverting Git does not revert PostgreSQL. Decide whether the previous application is compatible with the new schema; otherwise use your tested database restore procedure or a reviewed corrective migration. Do not blindly execute an Alembic downgrade against valuable production data.

Retain a protected copy of the previous production environment as well as the commit and both `dist` builds. Keep production domain values when rolling back application code; never replace them with development defaults. If you deliberately roll back a domain setting, preserve DNS/TLS and `/r/`/`/c/` routing for every hostname already distributed, and keep password-form origins allowed. A code rollback cannot change the URL inside a printed image or reverse DNS/certificate changes. This redirect/configuration update introduces no schema migration, so its application rollback does not require an Alembic downgrade. Rerun `check-deployment` when the chosen revision includes that command, plus public redirect/profile/password checks, after restoring a revision.

## 15. Troubleshooting

| Symptom | Check |
|---|---|
| 502 from `/api/` | `systemctl status turaqrcode`, journal, loopback port 8000, and proxy target. |
| `/register`, `/users`, or refreshed workspace returns 404 | Correct SPA `try_files`; use exact proxy prefixes ending in `/`. |
| Sign-in works locally but not over production HTTP | Production requires HTTPS with `COOKIE_SECURE=true`; use real certificates/domains. |
| Mutation returns “request could not be verified” | Exact Origin is in `CORS_ORIGINS`; avoid changing/stripping Origin in Nginx. |
| Readiness is 503 | Private `.env`, PostgreSQL URI/password/SSL, Supabase network rules, migrations. |
| `tsc`/Vite missing during build | Run `npm ci --include=dev` in the correct app. |
| Changed public URL has no effect in the browser | Distinguish server `PUBLIC_BASE_URL` from build-time `VITE_API_URL`; restart/rebuild the relevant component. |
| Code works on the server but not on a phone | QR still contains localhost/private hostname, public DNS/TLS is missing, or `/r/` is not routed. Regenerate undistributed codes using the correct public base. |
| Recovery email never arrives | SMTP host/credentials/sender/STARTTLS and provider logs; administrator-assisted recovery is available. |
| Every visitor seems rate-limited together | Ensure Uvicorn trusts only the local Nginx proxy and Nginx supplies a trusted client address; review upstream CDN real-IP settings before scaling. |

## Official platform references

- [CloudPanel: add sites](https://www.cloudpanel.io/docs/v2/frontend-area/add-site/)
- [CloudPanel: domain/root/runtime settings](https://www.cloudpanel.io/docs/v2/frontend-area/settings/)
- [CloudPanel: Vhost editor](https://www.cloudpanel.io/docs/v2/frontend-area/vhost/)
- [CloudPanel: SSL/TLS certificates](https://www.cloudpanel.io/docs/v2/frontend-area/tls/)
- [CloudPanel: add a Python version](https://www.cloudpanel.io/docs/v2/python/guides/adding-a-python-version/)
- [Supabase: PostgreSQL connections](https://supabase.com/docs/guides/database/connecting-to-postgres)

These platform references support the panel/DNS/TLS operations. The application-specific systemd, proxy, dependency, and update configuration above is tailored to this repository and must be validated on the target server.

## 16. Deploying the blue design and generator update

This release adds `python-barcode==0.16.1` and migration `20261029_default_projects`; it does not require new environment variables. Keep your existing server `.env`. Firecrawl, Scrape.do, and Chrome DevTools MCP were development research tools; their keys, packages, and capture files are not needed on CloudPanel.

Follow the normal backup/update procedure above, then run these commands as the site user before restarting the service:

```bash
cd /home/tura/apps/TuraQRcode/backend
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m app.manage migrate
.venv/bin/python -m app.manage check

cd /home/tura/apps/TuraQRcode/frontend
npm ci --include=dev
npm run build

cd /home/tura/apps/TuraQRcode/admin
npm ci --include=dev
npm run build
```

Publish both `dist` directories using the paths and `rsync` commands from section 8, then restart `turaqrcode` and check `/api/ready`. Do not use global Python packages for the API; systemd must use the project venv, which includes the new barcode dependency.

The migration creates a default project for every existing account and assigns only codes whose project was empty. Existing named project assignments, users, codes, and business cards remain. Deleting a custom project subsequently moves its codes into the default project.

After publishing, verify:

1. Sign in and confirm the default project appears. Save a code without selecting a project and check its assignment.
2. Create a password-protected editable QR, scan it on a phone, enter an incorrect password and then the correct one, and confirm destination navigation. Test the configured mobile destination as well.
3. Open `/barcode-generator`, export an EAN-13 barcode, and confirm its check digit and scan result. Sign in and save a barcode from `/app/barcodes/new`.
4. Create a link from `/app/links/new`, add campaign tags and an alias, copy the short URL, and confirm its destination.
5. Change QR pattern, corner style, frame text, colors, and logo; clear the top/bottom labels and frame text, switch all four frames, save/reopen, and export/scan the final PNG/SVG/PDF. Also try a photographic JPG logo and an invalid file; the valid logo should survive edits and a rejected file should leave the previous design usable. Create a business card using a light brand color and verify readable text and its QR.

The server supplies the updated Content Security Policy for protected-link forms. If a CDN or custom Nginx rule injects an additional `form-action 'self'` policy on `/r/`, remove that conflicting rule for these public password pages: Chrome can apply it to the destination after a form submission. Preserve HTTPS and the remaining security headers. Hard-refresh a previously opened password form after deploying the fix.

## Updating square exports and professional business cards

After pulling this release, install the updated `backend/requirements.txt` using the service's Python environment. `resvg-py` supplies Windows/Linux wheels for the SVG-to-PNG renderer; no Cairo service is required. ReportLab's bundled fonts keep label metrics consistent between preview and download. `nh3` sanitizes public profile formatting. Rebuild the customer frontend after `npm ci`, run `python -m app.manage migrate`, then restart FastAPI. The `20261029_card_media` migration adds profile/cover/logo image fields and JSON experience/social fields; `20261029_card_rich_text` adds `bio_html` with an empty default. Both preserve existing cards and plain-text content.

The inline business-card toolbar is bundled in a separate customer-app chunk; deploy all files from `frontend/dist/assets`, including the generated `Organization-*.js`. The backend's `app/profile.css` belongs in the private source checkout and is embedded into published card pages. Do not deploy only `.py` files. No third-party editor service or API key is required.

Image uploads accept PNG/JPG/WebP up to 8 MB in the browser and are prepared before submission. Portraits save at 512 × 512 px and covers at 1,280 × 720 px; logos save on a transparent 512 × 512 px canvas with fit/crop choices. All three slots show width/height limits and offer crop controls, including for saved images. Use a 3 MB proxy request limit to accommodate three prepared images and formatted profile sections. The API allows up to 3 MB for card writes and 2 MB for other requests. The API validates the smaller submitted images (500 KB, four megapixels) and their minimum dimensions. See the root README for the full image table and crop behavior. This crop update requires a backend restart and frontend rebuild, with no database migration.

The five-row bulk example is a static asset at `/examples/bulk-5.csv`. Copy it with the rest of `frontend/dist`; it does not require a database seed. Social-handle normalization is server-side and uses the platform's public URL structure. No YouTube, Meta, or LinkedIn API credentials are needed.

Card uploads are compressed in the browser and bounded again server-side. Set the Nginx `client_max_body_size 3m` setting; card records (including images) live in PostgreSQL and are included in the normal database backup. Keep page/API caching disabled for `/c/` so profile changes and deletions take effect promptly.

Verify after updating: download the same labeled QR at 354 and 1,200 px and inspect the actual file dimensions; ordinary PDF pages must also have different square physical dimensions. A4 is an explicit paper layout. Create a card with images, experience and a social profile, check its public page, then delete the linked QR and confirm both records are removed. Generate and edit a tracked Code 128 barcode with a long destination; its preview and downloaded image must remain readable.

Sizing references: [QRStuff printing and minimum-size guidance](https://www.qrstuff.com/en-gb/faqs), [DENSO WAVE four-module quiet zone](https://www.qrcode.com/en/howto/code.html/index.html). The default export is 1,024 px square; the business-card insert is 354 px (3 cm at 300 DPI). Test printed artwork at the intended viewing distance.

### Barcode dependency repair

The required encoder is **`python-barcode==0.16.1`**. The unrelated package named `barcode` is a genetics tool and can shadow the encoder, causing preview errors (including the old `pkg_resources` failure). Use the project's virtual environment for the service and all dependency commands. If an existing environment contains the wrong package, run these commands with the same Python interpreter that starts FastAPI:

```powershell
python -m pip uninstall -y barcode
python -m pip install --force-reinstall python-barcode==0.16.1
python -m pip install -r requirements.txt
```

Run from `backend`, restart FastAPI, then verify `/barcode-generator` and a saved tracked barcode. Fresh installations using `requirements.txt` install the correct encoder and `resvg-py` directly.

## Deploying QR Scanner

This update adds the customer route `/app/scanner` and its final Manage navigation item below Bulk & print. It changes only the customer frontend and documentation. No backend restart, database migration, environment variable, camera API key, or scanning service is required for this feature.

After pulling the updated source, install from the committed lockfile and rebuild as the application user:

```bash
cd /home/tura/apps/TuraQRcode/frontend
npm ci --include=dev
npm run build
```

Publish the entire `frontend/dist` using the customer deployment procedure in section 8. Include the lazy-loaded `Scanner-*.js` and `Scanner-*.css` files as well as the main assets. Do not copy `node_modules`; `npm ci` recreates the pinned browser decoder dependencies. The existing SPA fallback must serve `/app/scanner` on direct navigation and refresh. The administrator build and backend dependencies are unchanged by this feature.

Camera access uses the browser's [getUserMedia API](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia), which requires a secure context and user permission. Issue a valid HTTPS certificate for the customer domain. Localhost development works; ordinary HTTP on a LAN hostname/IP generally does not allow camera access. Image scanning remains available as a camera-free alternative.

If CloudPanel, Nginx, or a CDN already sets `Permissions-Policy: camera=()`, replace that camera restriction on the **customer site only** with `camera=(self)` while preserving the other directives. For example, the existing header could become `Permissions-Policy: camera=(self), microphone=(), geolocation=()`. Avoid duplicate conflicting headers. No microphone permission is requested, and no camera frames or uploaded images are sent to FastAPI or an external decoder. The [ZXing browser decoder](https://github.com/zxing-js/browser) is bundled locally; no CDN script is required. If a custom Content Security Policy is present, allow the site's own script/style assets and local `blob:` image sources for the scanner.

Verify on the deployed customer domain:

1. Sign in, open QR Scanner below Bulk & print, and refresh `/app/scanner` directly.
2. Upload a clear QR PNG with text, then one with an HTTPS URL. Confirm contents and Copy contents; Open link should open the URL. Automatic navigation must remain off until selected.
3. Upload Code 128, Code 39, EAN-13, EAN-8, and UPC-A samples. Product-number barcodes display their value without inventing a destination.
4. Start the camera, grant permission, and scan a code. Confirm the camera indicator turns off after success, Stop camera, switching to Upload image, switching tabs, and leaving the page. Try denying permission and then use the image fallback.
5. Check front/rear camera selection on the intended phones and desktop cameras. Test real devices after deployment; automated virtual-camera tests cannot confirm physical focus, exposure, browser permissions, or hardware behavior.

If Start camera fails, check HTTPS, browser site permissions, the customer response's Permissions-Policy, camera availability, and whether another application is using the camera. No database configuration change is needed.
