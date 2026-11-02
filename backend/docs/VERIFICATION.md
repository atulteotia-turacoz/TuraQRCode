# TuraQRcode verification

Initial verification was executed on **29 October 2026** in `E:\TuraQRcode`. The latest full backend and browser regression runs passed on **2 November 2026**; dated follow-up sections distinguish local tests from earlier live Supabase checks.

## Results

| Check | Result |
|---|---|
| Application layout | `backend`, `admin`, and `frontend` are independently runnable/buildable application folders. Subsequently consolidated under one root Git repository for the requested GitHub remote, with root README/deployment documentation. |
| Customer production build | Passed: TypeScript and Vite |
| Administrator production build | Passed: TypeScript and Vite |
| Backend/PostgreSQL test suite | Latest full rerun, 2 November: 288 passed against isolated local PostgreSQL in 235.21 seconds |
| Browser end-to-end suite | Latest full rerun, 2 November: 41 scenarios passed in Chromium in 5.7 minutes, including optional QR text/logo recovery, scanner, and protected barcode navigation; public-card checks at 390, 768, and 1280 px |
| Automated accessibility | No violations for the selected WCAG A/AA checks on public, account, workspace, and administrator activity pages |
| QR decoding | Seven module patterns, supported independent corner-frame/center combinations, scan-safe gradient palettes, individually styled labels, frames, and logos decoded with ZXing-C++ |
| Supabase connection | Passed with client-to-Supabase TLS verified through libpq |
| Supabase migrations | Revision `20261029_card_rich_text` applied; eight application tables plus the Alembic version table |
| Supabase data isolation | Private `tura` schema; RLS enabled; Supabase anonymous/authenticated API roles denied schema access |
| Live persistence smoke | Registration, sessions, QR creation/read-back, redirect, scan reporting, downloads, role restriction, and deletion passed |
| Initial administrator | Exists server-side, Argon2id hash verified, administrator role verified, mandatory password change verified |

The live smoke account and its data were removed after testing. The real Supabase administrator’s temporary password was **not changed by tests**. Administrator password changes in browser tests occur only in the local `tura_e2e` database.

## Feature coverage

| Feature | Evidence |
|---|---|
| Registration and required policies | API rejects either missing consent; browser requires checkbox; timestamp and policy version persist |
| Sign-in/logout and profile | Correct/incorrect credentials, case normalization, session expiry, logout revocation, browser profile read-back |
| Password change and recovery | First-admin-login restriction, strong password validation, other-session revocation, invalid/expired/reused tokens, administrator-assisted browser recovery |
| Authorization | Member-to-admin rejection; cross-user read/edit/delete/download/export/analytics denial; role injection rejected |
| URL shortening and aliases | Custom slug resolution, collision rejection, short-link mode, immutable QR redirect address after destination updates |
| QR content | Website, exact plain text, email, telephone, SMS, Wi-Fi escaping/whitespace, UPI, form/app/file URLs, validated social destinations, WhatsApp links, UTF-8 SSID length, and vCard; supported URL-based types can be dynamic and editable |
| QR appearance | Colors/contrast, square/rounded/dot patterns, raster logo validation/normalization, frame; actual PNG decoding |
| Export formats | PNG, SVG, PDF signatures, browser downloads, ZIP content, A4 print PDF |
| Link controls | Pause/reactivate, expiry, password form/retry/unlock/removal; actual Chromium form navigation to another origin for signed-in desktop and anonymous mobile visitors; 303 GET redirect; disconnected-body handling |
| Analytics | Distinct scan/click channels, counts, UTC daily aggregates, device categories, referrer-host redaction, CSV, top codes |
| Saved-code organization | Search, filters, pagination, alphabetical sort, deletion, default assignment and safe reassignment on project removal |
| Barcodes | All five standards saved/exported and decoded; EAN/UPC check digits; invalid standards/values rejected; separate barcode history, appearance controls, tracked Code 128 redirects, barcode scan analytics, and static-value protection covered in API and browser tests |
| Default projects | Registration and migration create defaults, create/bulk/edit assign automatically, default deletion blocked, custom deletion reassigns |
| Business cards | Any brand color with readable public profile and decodable QR; create/edit/delete, escaped public HTML, public profile, vCard, downloadable QR; browser flow verified |
| Bulk creation | CSV parsing/column mapping in browser; validation, alias conflicts, partial success without transaction corruption, ZIP/print |
| Administration | Counts, account search, suspension/session revocation, public-content suspension, restoration, code moderation, confidential recovery links, audit history |
| Request protection | Origin checks, login rate limiting, bounded mutation bodies, no password echo in validation errors |
| Scan reliability | Over-capacity static content is rejected before persistence; accessible contrast enforced for generated QR images |

## Commands to reproduce

Start local PostgreSQL from `backend/tools` with `npm ci` and `npm run db:local`. Then:

```powershell
# From backend
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m pip_audit --progress-spinner off
.venv\Scripts\python.exe scripts\supabase-smoke.py

# From frontend
npm run test:e2e
npm run build
npm audit

# From admin
npm run build
npm audit
```

Destructive tests refuse a non-loopback database. Pytest uses `tura_test`; browser tests use `tura_e2e` on 55432. The existing Supabase `.env` is not overwritten. Test HTML reports remain in `frontend/playwright-report`, and representative screenshots are in `frontend/tests/screenshots`.

## Configuration-dependent limits

- **Email delivery:** No SMTP credentials were supplied. Administrator-assisted recovery works and was tested; actual recovery-email delivery remains unverified until SMTP is configured.
- **Public deployment and branded domains:** Local browser tests do not establish public hosting, DNS, or HTTPS certificates. One deployment-level branded link hostname is supported by `PUBLIC_BASE_URL`; self-service per-user domain registration is outside the initial release. Configure a stable public hostname before printing dynamic codes.
- **Docker:** Docker/Nginx deployment files are included, but container deployment was not run because Docker Desktop was unavailable. Both static application builds and the API were tested directly.
- **Static QR behavior:** Static content cannot be edited or tracked after printing, and disabling/deleting a saved record cannot erase a downloaded static QR image. Managed-link controls apply to editable codes and short links.
- **Activity semantics:** Requests include repeat visits and bots; reports do not claim unique people, precise locations, or verified human scans. CSV exports include at most 50,000 activity rows per request.
- **Accessibility:** Automated selected WCAG checks and keyboard-friendly primitives are covered; this is not a claim of a comprehensive assistive-technology certification.
- **Load:** Functional/security tests were executed, not a sustained production load test. The supplied application limiter is local to one API process; add shared gateway limits before running multiple workers.
- **Policy text:** Terms and Privacy pages are supplied as initial product content and should reflect Turacoz’s final operational practices before public launch.

One upstream deprecation warning concerns Starlette’s test client using `httpx`; all tests pass. It does not affect the running application.

## Blue design and generator expansion

The existing migration/backfill verification remains valid. Code types and QR appearance remain in existing JSON records. Business-card profile/theme/media migrations add the fields for images, experience, social links, and professional sections; the current schema head is `20261029_card_rich_text`. A read-only Supabase check this run confirmed connection/TLS and the current application schema revision. The prior migration/backfill verification established: before/after counts for users, codes, and business cards matched; every existing account has a default project and no code remains unassigned. Existing custom project assignments and the real administrator password/state were preserved. The live smoke script verifies current Alembic head, default-project protection, protected unlock, barcode storage/exports, ordinary CRUD/analytics, and removes only its temporary account.

The 29 browser scenarios include public/account/workspace accessibility checks, coordinated QR color presets, blocked low-contrast custom pairs, module and corner-marker shape controls, independently styled movable QR labels, gradient palette and editor controls for expiry/alias/password/mobile destination, frame choices, mobile design layout, EAN check-digit validation, barcode exports/saving, tracked Code 128 scan history and appearance, QR type selection and dynamic form links, custom short links, bulk-import row errors, image upload limits, and desktop/mobile password navigation. QR image tests also decode gradient exports, labels, and supported marker combinations with ZXing-C++.

Firecrawl captured both reference pages and screenshots. Chrome DevTools MCP captured QRStuff and the updated local pages; its Bitly navigation timed out, with Firecrawl providing that page evidence. Reference capture files and tools remain ignored under `backend/.local`. No reference-site login was required for the public-page review. See the design-system reference review for feature scope.

The running development setup was also checked at customer port 5173, administrator port 5174, and API port 8000 with the project virtual environment: QR preview, barcode preview, Supabase readiness, and the administrator sign-in screen passed with no browser JavaScript exceptions. The combined launcher now re-executes inside the project venv when available, preventing accidental use of missing global Python dependencies.

## Square export and professional profile verification

- PNG/SVG files with labels, borders and logos have exact square dimensions at 256, 354, 1,024, 1,080, 1,200, 2,480 and 3,000 px. PNGs report 300 DPI. PDF MediaBox dimensions vary with the selected size; only the explicit A4 option adds a rectangular paper sheet.
- All 100 original palette combinations and all 96 new featured linear/radial multicolor combinations decode with ZXing-C++; classic and inverted designs are also covered. Browser tests confirm the 198-option picker starts with the two classics and then the featured gradients.
- Labels at zero sit at the outer clear-margin boundary; maximum positions reach the square canvas edge. The four-module scan margin stays clear. Raster and SVG use one vector composition, including proportional logo placement.
- Barcode tests cover all five standards, check digits, long tracked destinations, saved/unsaved appearance, exact requested width where the standard permits it, caption units, and PNG/SVG/PDF. The actual running local API was checked after replacing the unrelated `barcode` package with `python-barcode==0.16.1`; both QR and barcode PNGs decoded.
- Browser tests verify nested-editor scroll chaining, separate `/app/barcodes/:id` navigation, and completed record creation rather than matching `/new` during a pending save.
- Card media tests create, reload, edit/remove profile photos, covers, and company logos. Structured experience and ten supported social platforms persist and render on the public profile. Public mobile rendering and automated accessibility pass. Light brand accents retain a decorative role in the hero while white panels use a readable link color.
- Deleting a card's QR from Overview removes the card, public profile, linked QR and activity consistently. Valid bulk rows keep their default project, invalid/duplicate rows report failures, ZIP images decode as square QR artwork, and empty/oversized batches are rejected.
- A fresh Supabase smoke account verified image/experience/social persistence, linked deletion, long tracked barcode export, existing QR/auth/analytics flows, migration head, TLS, and access restrictions. Its data was removed in the cleanup block; existing administrator credentials/state were preserved.

Physical camera/printer testing, sustained production load, and deployment-specific SMTP delivery are outside these automated results.

## Inline profile editor and export follow-up

- Bio, experience descriptions, and custom sections now use an inline Tiptap toolbar. The browser test exercises every formatting action, including nested list indentation, undo/redo, and clearing formatting, then saves, reopens, and checks the published HTML. Automatic trailing paragraphs were disabled to prevent empty list items when switching list styles.
- `nh3` sanitizes saved and published rich text with a strict tag allowlist and no attributes. Script, style, SVG, iframe, event-handler, and unsafe-link inputs are removed. Plain text remains separately available. Existing plain-text records render as escaped text.
- Profile photos and covers have validated minimums and fixed output canvases; logos preserve their proportions. Browser tests upload all three slots, adjust crops, save/reopen, and remove media. Backend tests cover too-small dimensions, oversized images, malformed data, and all three output sizes. A complete card request over 2 MB saves successfully within the dedicated 3 MB card limit; oversized card and ordinary API bodies are rejected.
- The published profile uses a continuous header, professional timeline, contact column, and responsive sections. Desktop and mobile screenshots were reviewed. Tests check full-width covers, no horizontal overflow, vCard downloads, and selected WCAG A/AA rules at 390, 768, and 1280 px.
- Social fields normalize handles and URLs before saving. YouTube channel IDs and legacy paths, LinkedIn company paths, international-safe URL quoting, supported card social platforms, unsafe-host rejection, and invalid display-name inputs are covered. QR previews, saved destinations, destination edits, and redirects use the normalized address.
- All 16 QR content types were exported at 354 px with a logo and labels. PNGs decode directly, SVGs decode after rendering, and PDF-embedded images are extracted with pypdf and decoded with ZXing-C++. Seven module patterns × four frames × three small/standard sizes also decode with logos and labels (84 combinations). Square modules now use crisp-edge rendering at native export resolution.
- The actual five-row CSV in `frontend/public/examples/bulk-5.csv` is tested through the API for editable/static QR and short-link modes, default project assignment, redirects, and decodable ZIP images. The browser downloads that same file, creates five short links, verifies separate Links/QR histories, and checks invalid-row feedback.
- Both application production builds passed. The business-card editor is loaded separately from the public generator; the main JavaScript bundle is about 450 KB before compression. The live Supabase smoke test verifies rich text, normalized social handles, image persistence, migration head, protected redirects, analytics, exports, and cleanup of its temporary account. The actual running API at port 8000 returned readiness 200 and generated decodable 1,200 px QR/barcode PNGs.

Image-layout research used [HiHello's official image guidance](https://support.hihello.com/hc/en-us/articles/14639880824475-What-format-size-and-resolution-should-I-use-for-pictures-and-videos) and [Blinq's image layout guidance](https://support.blinq.me/en/articles/68009-changing-your-card-image-layout); TuraQRcode's limits are product-specific. Channel input handling follows [YouTube's URL guidance](https://support.google.com/youtube/answer/6180214).

## Saved demonstration workspace and three-image crop controls

- After the logo-crop update, 74 focused backend/PostgreSQL cases passed and eight focused browser scenarios passed (the seven profile/export scenarios plus the new image-limit scenario). The customer production build passed. The existing full-suite results above remain the broader regression baseline.
- Portrait, cover, and logo slots display saved width/height, minimum source width/height, maximum width/height, pixel-area and file-size limits, and dimensions of a newly loaded source. Each has zoom, horizontal/vertical positioning, Reset crop, and saved-image Adjust crop controls. Logos support both Fit entire logo and Crop to square. API-generated logo canvases are consistently 512 × 512 px with transparency and preserved proportions.
- Browser checks confirm that a 32 px source, an 8 MB-plus file, and an image wider than 8,000 px are rejected without replacing the valid image already in the slot. All three saved image dimensions are checked, along with cropped/fitted logo output and reset behavior.
- A user-authorized demonstration account was populated with three fictional professional profiles in blue, green, and plum themes, four custom short links (one intentionally paused), and six barcode examples covering all five standards plus tracked Code 128. All thirteen saved items belong to its default project. Profiles include fictional portraits, coordinated cover/logo graphics, two experience entries, two custom sections, contact details, and example links.
- The live account review checked sign-in, public desktop/mobile profiles, vCard downloads, linked QR redirects, saved photo controls, link-only editing and pause/reactivation, six-item barcode history, barcode appearance save/download, analytics CSV export, validation failures, alias conflicts, and temporary-record deletion. No browser JavaScript exceptions were observed. The requested examples remain saved for the user to review; test interactions are demonstration data.
- All nine saved images have their expected dimensions. All 27 sample PNG/SVG/PDF exports were decoded with ZXing-C++, including SVG rasterization and PDF image extraction; the separately edited barcode PNG also decoded. Account-specific URLs, screenshots, original generated image assets/prompts, export files, and private verification notes remain ignored under `backend/.local/review-account`. No account password or session data is committed.

## Verification in the existing customer account

- Confirmed the existing account identity through sign-in and `/api/auth/me` at the actual customer origin, `http://localhost:5173`. A similar email address belongs to a separate account; demonstration records are private to their owner and do not appear across accounts or browser origins with different sessions.
- Added three fictional profiles in Signature blue, Emerald, and Plum themes to the confirmed existing account. Each has a portrait, cover, logo, formatted introduction, two experience entries, two professional sections, contact details, a social profile, and a website link. All three headings remain visible after a full page reload. A desktop screenshot includes the existing account display name and all three cards.
- Added four demonstration short links and six demonstration barcodes. The eleven pre-existing saved items remain present. The account now has twenty-four saved items: eleven QR codes (including the three profile codes), five short links, and eight barcodes. The thirteen new items use the default project; existing records were not moved or edited.
- Live checks at the customer origin covered card edit/crop controls, public mobile profiles, vCard downloads, linked QR redirects, the separate Links editor, pause/reactivation, barcode appearance save/download, analytics CSV, invalid URL rejection, duplicate alias rejection, and deletion of a temporary test record. No JavaScript exceptions occurred.
- Decoded all twenty-seven demonstration PNG/SVG/PDF exports and the separately edited barcode PNG. Also downloaded and decoded thirty PNG/SVG/PDF exports belonging to the ten pre-existing QR/barcode records. The remaining pre-existing record is a short link. Confirmed saved portrait/logo dimensions of 512 × 512 px and cover dimensions of 1,280 × 720 px.
- Reran the complete backend suite (234 passed), complete browser suite (29 passed), customer production build, and administrator production build. Automated destructive tests continued to use isolated local databases, while the live account checks used its configured Supabase database.
- Account-specific inventories, screenshots, downloaded files, and live-check logs are private and ignored under `backend/.local/trail-account`. Before reporting a live workspace ready, verify the requested hostname, signed-in account identity, expected saved record IDs, and visible names after a reload. Never infer that samples saved to one account are visible in another.

These checks do not establish physical phone-camera/printer compatibility, live email delivery, public hosting, or sustained production load; those limits above still apply.

## QR Scanner addition

- Added only the customer scanner page, its last Manage navigation entry below Bulk & print, a lazy route, decoder dependencies, and scanner documentation/tests. The backend, administrator application, saved records, generators, and analytics behavior are unchanged.
- Eight scanner browser scenarios passed. They decode actual PNGs from all five generated barcode standards, ordinary/inverted QR images, and real video frames from a virtual camera. QR and Code 128 video decoding stop the stream after a result. Tests cover plain text/HTML-like payloads, copying, manual web links, optional automatic HTTP/HTTPS navigation, and non-web/credential-bearing URL handling.
- File tests cover unsupported types, over-12-MB files, invalid image bytes, images wider than 8,000 px, empty images, and retrying the same file. Camera tests cover denied permission, missing/busy devices, cancellation before permission resolves, camera selection, input-method changes, stopping, and leaving the route. A follow-up run also verified hidden-page track cleanup and the two existing mobile/cached-navigation scenarios: three passed.
- Keyboard tab navigation, mobile layout at 390 px, and selected WCAG A/AA checks passed. The customer TypeScript/Vite production build passed; the decoder is isolated in the scanner chunk. The dependency installation audit reported no vulnerabilities.
- A live check at `http://localhost:5173/app/scanner` in the existing customer account read all nine previously saved example PNGs: three branded profile QR designs and six barcode designs. The page and decoded-link result were visually inspected at desktop and mobile widths. No browser exceptions occurred, and all twenty-four saved record IDs remained present. Private screenshots and results are ignored under `backend/.local/scanner`.
- README and CloudPanel deployment instructions include the new route, image limits, `npm ci`/frontend rebuild, all lazy assets, HTTPS and camera permission requirements, and optional restrictive Permissions-Policy/CSP adjustments. This feature needs no new backend setting, database migration, external API key, or administrator build.

Camera tests use actual browser MediaStreams generated from canvas frames. Physical phone/webcam hardware and deployed HTTPS/proxy policies still require verification on the target devices/server.

## Production domain and redirect verification — 2 November 2026

- The complete backend suite passed: **275 tests in 79.68 seconds**, with one existing Starlette test-client deprecation warning. The complete browser suite passed: **38 scenarios in 3.1 minutes**. Both used isolated loopback PostgreSQL databases; this follow-up did not migrate, delete, or write to Supabase or existing demonstration accounts.
- The 41 new backend cases cover origin normalization and invalid configuration rejection (including wildcard hosts), exact CORS/mutation origins, production-only preflight failures, configured-domain generation for QR codes/short links/tracked barcodes/business cards, malicious Host/forwarded headers, mobile destinations, recovery URLs, and protected redirects. Bulk-generated managed QR and barcode PNGs are decoded to verify their actual embedded public addresses. Static URLs and product barcode values retain their original content.
- Password forms retain the barcode scan channel after incorrect-password retries and successful unlock. The new browser scenario follows the real form between separate application/API origins, checks signed-in desktop and anonymous mobile destinations, and verifies two barcode scans versus a separate link click. Unsuccessful password attempts do not add events.
- A linked business-card redirect resolves its managed card path on the configured public domain without rewriting stored data. Explicit alternate QR destinations and mobile overrides remain explicit. Retained old hostnames require an allowed origin for password-form POST requests, as documented.
- `python -m app.manage check-deployment` checks production origin/cookie configuration without accessing the database. A CLI smoke run with temporary HTTPS domain settings passed; local HTTP settings intentionally fail this production-only check. No application schema migration is required by these changes.
- README, backend setup guidance, and DEPLOYMENT.md describe fresh production databases, final-domain configuration, separate public/customer/admin hosts, preserving proxy query strings and password POSTs, deployment checks, and rollback. No development records or private environment files are included in a production release.

Real CloudPanel routing, public DNS/TLS, physical cameras/printers, production SMTP delivery, and sustained load were not exercised by this local follow-up. They require verification on the deployed server; passing local tests does not establish those external conditions.

## Optional QR text, frames, and logo recovery — 2 November 2026

- Fixed two interacting caption problems: the API required a nonempty frame label even when the frame was hidden, and the controlled input visually restored the default when cleared. Frame text is now optional; empty values persist through all four frame choices, preview, create, reopen, update, and export. Top/bottom labels can also remain empty. Callout frames retain their selected shape without drawing empty text.
- Thirteen new backend cases passed. They cover empty/whitespace-only labels across every frame, creation and editing with a logo, exact square 354 px PNG/SVG/PDF exports decoded with ZXing-C++, invalid captions, a photographic JPG whose PNG representation exceeds the input limit, and very thin transparent logos. Normalized logos retain proportions/transparency, honor EXIF orientation, and remain valid for a subsequent save within the existing byte/pixel limits.
- Three new targeted browser scenarios passed for editable/static QR creation and upload recovery. They clear all labels, switch every frame, upload a logo, save/reload/update, and download square PNGs. Invalid formats, broken bytes, oversized files, too-small dimensions, and over-budget pixel counts display inline errors while preserving the previous design; removing/re-uploading the same file recovers cleanly. The final full browser rerun is recorded in the Results table.
- Renamed the customer navigation, history heading, breadcrumb, public navigation, and project shortcut to **Link shortener**. Its existing `/app/links` routes and saved-link behavior are unchanged; business-card portfolio link labels are separate.
- The complete backend suite passed with **288 tests in 235.21 seconds**, the complete browser suite passed with **41 scenarios in 5.7 minutes**, and the customer TypeScript/Vite production build passed. A read-only check against the running development API at port 8000 returned **200** SVG previews for all four frames with empty labels. Automated account writes used isolated local databases; no live customer records or Supabase schema were changed.

Deploy this correction by restarting the backend and rebuilding the customer frontend. It needs no new dependency, database migration, or administrator UI change. Physical camera/printer and deployed-server checks remain outside this automated evidence.
