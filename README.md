# Portal — UI/UX Design System & Django Template Architecture

Cloud-based **Outlook Email Aggregation** dashboard. This repository contains the complete, polished, production-ready **Django Template UI** for Portal, plus a production-grade **Microsoft Account Management & Background Synchronization module** (Microsoft Graph + MSAL + Django 6 Tasks/Redis).

> **Scope:** UI + Django's built-in authentication/authorization + Microsoft account management, OAuth, and a background email synchronization engine built on Django's Task framework. Unified Inbox UI is out of scope for the sync module; emails are stored and exposed for the inbox layer to consume.

---

## Quick Start

```bash
pip install -r requirements.txt        # Django 5.2+ (Django 6 compatible)
docker compose up -d postgres redis    # start PostgreSQL + Redis (see .env)
python manage.py migrate               # apply auth/admin/session + portal tables
python manage.py createsuperuser       # your login account
python manage.py scheduled_tasks --once  # run recurring background jobs now
python manage.py runserver             # http://127.0.0.1:8000/
```

Then sign in at `/login/` with the superuser you created. App pages (dashboard, accounts, inbox) require authentication; Django Admin at `/admin/` manages Users, Groups, Permissions and the sync cluster tables.

- Light theme only (dark mode removed).
- Background tasks use Django's `immediate` backend (run synchronously in-process, no worker/Redis broker needed). Recurring jobs are driven by `manage.py scheduled_tasks` — set it up in cron/systemd timer for a truly background schedule.

---

## Microsoft Account Management & Background Synchronization

Connects multiple Outlook.com mailboxes via Microsoft Graph OAuth 2.0 and synchronizes their Inbox emails automatically in the background with a hybrid strategy:

| Strategy | Mechanism |
|---|---|
| **Primary** | Microsoft Graph Change Notifications (webhooks) |
| **Secondary** | Microsoft Graph Delta Queries (`@odata.deltaLink` per account) |
| **Fallback** | Django task scheduled every 5 minutes |

### OAuth flow (`/accounts/connect/` → `/accounts/callback/`)

1. `AccountsAddView` collects display name/nickname and stores them in the session.
2. `MicrosoftAuthService.build_auth_url` builds the MSAL authorization URL (state stored in session for CSRF protection).
3. `AccountsCallbackView` → `MicrosoftAuthService.handle_callback` validates state, exchanges the code via MSAL, fetches `/me`, and stores the account.
4. Tokens are **encrypted with Fernet** (key derived from `SECRET_KEY`) before storage — never plaintext, never logged.
5. Expired access tokens are refreshed automatically using the stored refresh token (`refresh_token`); failures mark the account for reauthorization and emit a notification.

### Sync engine (`portal/services/sync_services.py`)

- `SyncService.sync_account(account, worker)` — walks the delta feed, applies pages in bulk, tracks added/updated/removed, persists the next `deltaLink` only after a fully successful run (interrupted runs are replayed), records a `SyncLog`, and updates `AccountHealth`.
- Idempotent by construction: emails are keyed on `(outlook_account, graph_message_id)`; delta updates only touch properties present in the payload; paused accounts are skipped.
- `SyncService.sync_all`, `refresh_expired_tokens`, `renew_webhooks`, `download_attachment`, `sync_metrics`.

### Django Tasks (`portal/tasks.py`)

| Task | Purpose |
|---|---|
| `portal.tasks.sync_account` | Sync one account, with `SyncJob` tracking |
| `portal.tasks.sync_all_accounts` | Scheduled entry point; runs one sync per syncable account |
| `portal.tasks.refresh_expired_tokens` | Refresh all expired access tokens |
| `portal.tasks.renew_webhook_subscriptions` | Renew expiring Graph subscriptions |
| `portal.tasks.download_attachment` | Fetch one attachment's binary content |
| `portal.tasks.cleanup_old_logs` | Purge `SyncLog` older than the retention window |
| `portal.tasks.run_system_health_checks` | Job backlog / failure checks → notifications |

The recurring set is orchestrated by `manage.py scheduled_tasks`, which replaces Celery Beat. Each job cadence is tunable via env vars (`SYNC_INTERVAL_SECONDS`, `TOKEN_REFRESH_INTERVAL_MINUTES`, `WEBHOOK_RENEW_INTERVAL_MINUTES`, etc.).

### Monitoring pages

| URL | Purpose |
|---|---|
| `/system-monitor/` | Overview tab: system health, KPI cards, activity (HTMX auto-refresh) |
| `/system-monitor/logs/` | Filterable sync logs (`?q=&status=&account=`) + detail pages |
| `/system-monitor/health/` | OAuth/Graph/Webhook health badges + webhook expiration |
| `/system-monitor/queue/` | `SyncJob` and attachment download job queues |
| `/system-monitor/oauth/` | OAuth/token lifecycle per account |
| `/system-monitor/` | Tabbed Sync/Queue/Integrations/Audit views |
| `/accounts/<uuid>/` | Account detail: metadata, rename, pause/resume, syncs, emails |

### Models

`OutlookAccount` (extended), `OAuthToken`, `Email`, `EmailSyncState`, `GraphSubscription`, `Attachment`, `SyncLog`, `SyncJob`, `AttachmentDownloadJob`, `AccountHealth`, plus the existing `Notification` / `AuditLog`. All in `portal/models.py`; admin registered in `portal/admin.py`.

### Management commands

```bash
python manage.py scheduled_tasks       # run all recurring background jobs (cron/timer)
python manage.py sync --all            # run a sync now (or --account <pk>)
python manage.py renew_webhooks        # renew expiring subscriptions
python manage.py cleanup_logs          # prune old sync logs
python manage.py health_check          # redis/db/job summary
```

### Tests

```bash
python manage.py test portal
```

Covers the delta engine (create/idempotent/removal), paused and tokenless accounts, webhook renewal, health updates, account actions and the monitoring views. The Graph HTTP layer is mocked; repositories run against the test database.

---

## Deploy to Render

The repo ships a `render.yaml` blueprint (`blueprint` / "New + → Blueprint" in Render) and a `Dockerfile`.

1. Push this repo to GitHub, then in Render create a **New Blueprint** from it (or use the Blueprint Run button).
2. Blueprint creates automatically:
   - **Web** service `mailfusion-web` — gunicorn (`migrate` + `collectstatic` run on boot).
   - **Cron** service `mailfusion-scheduler` — runs `manage.py scheduled_tasks` every minute (replaces Celery Beat). Each job self-throttles by its cadence in Redis, so concurrent cron triggers are safe.
   - **Redis** `mailfusion-redis` and **Postgres** `mailfusion-db` (free tiers).
3. Fill in env vars marked manual: `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, and `MICROSOFT_REDIRECT_URI` (point it at `https://<your-app>.onrender.com/accounts/callback/`). `SECRET_KEY`/`DEBUG` are auto-configured.
4. Once deployed, run `python manage.py createsuperuser` from the Render shell (or via `scheduled_tasks`'s `--once`) to create your admin login.

> Free-tier web services sleep; the first request may be slow to wake. Health check points at `/login/`.

---

## Authentication & Authorization (Django built-in)

The app uses Django's built-in auth framework end to end — no custom user model, no custom RBAC, no role enums, no permission seeders.

- **Auth views:** `LoginView`, `LogoutView`, `PasswordChangeView`, `PasswordResetView`, `PasswordResetConfirmView`, `PasswordResetCompleteView` (all Django `auth.views` subclasses, Bootstrap-styled).
- **Forms:** thin Bootstrap wrappers around `AuthenticationForm`, `PasswordChangeForm`, `PasswordResetForm`, `SetPasswordForm` (`portal/forms.py`).
- **User model:** Django's default `User`. App models live in `portal/models.py` (`Notification`, `AuditLog`) and are unrelated to auth — no custom user model.
- **Authorization:** Django Users / Groups / Permissions / Content Types, managed manually via Django Admin (`portal/admin.py` customizes search, filters, list display only).
- **Sessions:** inactivity logout (`SESSION_SAVE_EVERY_REQUEST` + `SESSION_INACTIVITY_TIMEOUT`), 14-day cookie for "remember me", `SESSION_COOKIE_AGE` — all env-driven.
- **Security:** full password validators (min 12), secure/HTTP-only/SameSite cookies, HSTS/SSL redirect, XSS/clickjacking/nosniff headers — env-driven via `.env`.
- **Password reset email:** console backend by default (prints the reset link to stdout); switch `EMAIL_BACKEND` in `.env` to SMTP for production.

### Auth routes

| URL | View | Purpose |
|---|---|---|
| `/login/` | `LoginView` | Sign in + remember me |
| `/logout/` | `LogoutView` | Sign out (POST) |
| `/forgot-password/` | `PasswordResetView` | Request reset link |
| `/reset-password/<uidb64>/<token>/` | `PasswordResetConfirmView` | Set new password |
| `/change-password/` | `PasswordChangeView` | Change own password |
| `/profile/` | `ProfileView` | Edit name/email |
| `/admin/` | Django Admin | Users, Groups, Permissions |

---

## Notifications & Audit Logs

In-app management for the `Notification` and `AuditLog` models, exposed in the app shell (Notifications in the sidebar + navbar bell dropdown, Audit Logs under sidebar Tools).

### Notifications — `/notifications/`

- Paginated list (10/page) with summary strip (total / unread / read).
- Row actions: toggle read/unread, delete (POST forms). Header checkbox select-all + selected counter feed the bulk action bar.
- Bulk actions: mark as read or delete the selected rows. `POST /notifications/bulk/`.
- Global actions: `POST /notifications/<id>/toggle/`, `POST /notifications/<id>/delete/`, `POST /notifications/read-all/` (all POST-only, `405` on GET).
- `?status=unread|read|all` server filter; client-side search via `static/js/tables.js`.
- Navbar bell shows the unread badge, top 4 recent items, and a "View all notifications" link.

### Audit Logs — `/audit-logs/`

- Read-only paginated trail (15/page): timestamp, actor/user, action, target, IP, status badge.
- Filters: `?q=` (actor/action/target), `?status=success|error`. Pagination preserves the querystring.
- `GET /audit-logs/export/` streams a CSV (`timestamp,actor,action,target,ip,status`).


Seeds 4 notifications and 8 audit log entries (user links resolved to the first superuser, else `System`).

---

## 1. Page Wireframe Structure

```
APP SHELL (every authed page)
├─ Top Navbar ................ sticky, blurred, 64px
│  ├─ Sidebar toggle (mobile)   ├─ Page title        ├─ Global search ⌘K
│  ├─ Notification center bell  └─ User menu
├─ Left Sidebar ............. fixed 264px, collapsible off-canvas on mobile
│  ├─ Brand logo + name        ├─ Workspace nav      ├─ Administration nav
│  └─ User footer + version
├─ Main Content ............. fluid, max-width 1440px
│  ├─ Page header (title + subtitle + breadcrumb + actions)
│  ├─ Message alerts          ├─ Page body          └─ Pagination (where relevant)
└─ Footer .................. slim, version + links
```

| Page | Layout |
|---|---|
| Login / Forgot / Reset | Split-screen: brand aside (hidden ≤992px) + 380px form card |
| Change Password / Profile | 2-col: form (8) + summary/security (4) |
| Dashboard | Stat cards ×4 → sync strip → chart(8)+donut(4) → recent emails(7)+activity(5) |
| Outlook Accounts | Health strip ×4 → toolbar → responsive table → pagination |
| Add Account | Centered wizard (≤720px) with 3-step indicator |
| Unified Inbox | 3-pane grid: folders(220px) + list + preview(480px) |
| Email Detail | Detail card(8) + meta/related(4) |
| Search | Search bar → stat cards ×4 → results(8) + saved searches(4) |
| Analytics | KPI ×4 → charts(8+4) → top senders(5) + account activity(7) |
| Notifications | Settings(7) + history(5) |
| Synchronization | Worker/queue cards → status table → sync history |
| Audit Logs | Toolbar → table → pagination |
| Settings | Left pill-nav(3) + tab panels(9) |
| Users | Role summary ×4 → toolbar → table → pagination |
| 403 / 404 / 500 / Maintenance | Full-screen centered, minimal |

---

## 2. Django Template Hierarchy

```
templates/
├── base.html                      # HTML shell, CSS/JS, theme, blocks
├── partials/
│   ├── navbar.html                # top bar, search, bell, user, theme
│   ├── sidebar.html               # brand + nav + footer
│   ├── footer.html
│   ├── breadcrumbs.html
│   ├── messages.html              # django.contrib.messages → alerts
│   ├── pagination.html
│   ├── modals.html                # confirm / delete-account / notice
│   └── auth_aside.html            # shared split-screen brand panel
├── authentication/
│   ├── login.html  forgot_password.html  reset_password.html
│   ├── change_password.html  profile.html
├── dashboard/index.html
├── accounts/
│   ├── list.html  add.html  add_step2.html  add_step3.html
├── emails/
│   ├── inbox.html  detail.html
├── search/index.html
├── analytics/index.html
├── notifications/index.html
├── sync/index.html
├── logs/index.html
├── settings/index.html
├── users/index.html
└── errors/  403.html  404.html  500.html  maintenance.html
```

**Template block contract** (`base.html`):

| Block | Purpose |
|---|---|
| `title` | Page title → `{title} · Portal` |
| `body_class` | Page-level body classes (`mf-body-auth`, `mf-body-error`) |
| `page_subtitle` | Text under the page header |
| `page_actions` | Action buttons in the page header |
| `content` | Main page body (authed pages) |
| `auth_content` | Standalone layout (login, error pages) |
| `extra_head` / `extra_js` | Per-page assets |
| `navbar_title` | Override navbar title |

---

## 3. Navigation Flow

```
Login ──> Dashboard
Dashboard ─┬─ Outlook Accounts ─> Add Account (Step 1 → 2 → 3) → Accounts
           ├─ Unified Inbox ──> Email Detail ─> (reply/forward/more)
           ├─ Search ──> Email Detail
           ├─ Analytics ──> (export)
           ├─ Synchronization ─> (retry job)
           ├─ Notifications
           ├─ Audit Logs
           ├─ Users ─> Create/Edit user (modal/placeholder)
           ├─ Settings (tabs: General, Appearance, Email, Security, API, About)
           └─ Profile ─> Change Password
Any authed page ─> Sign out ─> Login
```

**Nav item active state:** the view passes `active_page` (e.g. `dashboard`, `accounts`, `inbox`) and `sidebar.html` applies the `.active` class + left indicator bar.

---

## 4. Component Hierarchy

```
Button
├─ .btn-primary / .btn-outline-secondary / .btn-ghost / .btn-icon
├─ .btn-microsoft (branded OAuth CTA)        └─ .btn-sm / .btn-lg
Card
├─ .mf-card > .mf-card__header + .mf-card__body (+ .mf-card__body--flush)
└─ .mf-stat (icon + value + label + trend)
Table  .mf-table  ──> thead(uppercase labels) + hover rows + badges
Badge  .mf-badge--{success|danger|warning|info|neutral|primary}
Alert  .alert-{success|danger|warning|info}  (messages → auto-dismiss)
Dropdown .dropdown-menu (+ .mf-notif-menu, .mf-user-menu)
Modal  #mfConfirmModal / #mfDeleteAccountModal / #mfNoticeModal
Form   .form-label + .form-control + input-group icons + form-switch
Toast  #mf-toast-container  (JS helper: data-mf-toast)
Empty state .mf-empty (icon + title + text + action)
Skeleton .mf-skeleton (shimmer)
Chart  .mf-chart--bars / .mf-donut (pure CSS, JS renders from data attrs)
Badge  / Chip  .mf-chip   /  Avatar  .mf-avatar--{tone} / .mf-user-avatar
```

### Reusable JS behaviors (`static/js/main.js`, vanilla only)

| Attribute | Behavior |
|---|---|
| `data-mf-toggle="sidebar"` | Mobile off-canvas sidebar |
| `data-mf-toast="msg"` | Success toast |
| `data-mf-confirm` + `-title`/`-message` | Confirmation dialog |
| `data-mf-delete-account` | Delete-account modal with checkbox gate |
| `data-mf-password-toggle` | Show/hide password |
| `data-mf-copy="text"` | Copy to clipboard |
| `data-mf-goto="/url/"` | Navigate |
| `data-mf-table-search` / `data-mf-table-filter` | Client-side table filter + empty state |
| `data-mf-chart="bars"` + `data-mf-bars=[…]` | Render CSS bar chart |

---

## 5. Responsive Layout Plan

| Breakpoint | Behavior |
|---|---|
| ≥1200px | Full 3-pane inbox; preview pane visible |
| 992–1199px | Inbox preview moves below list; full-width |
| <992px | Sidebar slides off-canvas (`transform: translateX`), backdrop blur; main content full-width; search trigger collapses to icon |
| <768px | Inbox becomes single column (folders scroll horizontally-limited); stats go 2-up; page action buttons stack full-width; table scrolls horizontally |
| Print | Sidebar, navbar, footer hidden |

`mf-hide-sm` hides non-essential elements on phones.

---

## 6. Bootstrap 5 Implementation

- **Bootstrap 5.3.3 + Bootstrap Icons 1.11.3** via CDN.
- Light theme only (`data-bs-theme="light"` hardcoded on `<html>`); dark mode was removed.
- Everything else is custom `.mf-*` classes layered on top — no Bootstrap theme compilation needed.
- Components map 1:1 to Bootstrap: `dropdown`, `modal`, `toast`, `nav-pills`, `progress`, `form-switch`, `pagination`, `input-group`, `table`.

---

## 7. Recommended Icons (Bootstrap Icons)

| Menu / Action | Icon |
|---|---|
| Dashboard | `bi-grid-1x2-fill` |
| Outlook Accounts | `bi-envelope-paper-fill` |
| Unified Inbox | `bi-inbox-fill` |
| Search | `bi-search` |
| Analytics | `bi-graph-up-arrow` |
| Synchronization | `bi-arrow-repeat` |
| Notifications | `bi-bell-fill` |
| Audit Logs | `bi-journal-text` |
| Users | `bi-people-fill` |
| Settings | `bi-gear-fill` |
| Add Account | `bi-plus-lg` |
| Sync Now | `bi-lightning-charge` / `bi-arrow-clockwise` |
| Reconnect / Retry | `bi-arrow-repeat` |
| Remove | `bi-trash` |
| Edit | `bi-pencil` |
| Mark read/unread | `bi-check2` / `bi-envelope-open` |
| Attachments | `bi-paperclip` |
| Export | `bi-download` / `bi-filetype-csv` |
| Theme | `bi-moon-stars` / `bi-sun` |

---

## 8. Professional SaaS Styling Guidelines

- **Elevation:** flat cards with `1px` borders + soft shadows (`0 1px 2px` + `0 4px 16px`); heavier `0 8px 30px` only for dropdowns/modals.
- **Radius scale:** 8 / 12 / 16px (inputs, cards, hero). Pills stay `999px`.
- **Borders:** neutral `#e2e8f0`; never pure black.
- **Color usage:** blue for primary actions & active nav; green = healthy/success; orange = warnings/attention; red = destructive & errors; muted gray for secondary text — consistent meaning across every page.
- **No gradients on surfaces** except brand logo, auth hero panel, and chart bars (Linear/Vercel aesthetic).
- **Focus rings:** `0 0 0 3px rgba(37,99,235,.15)` on form controls.
- **Content density:** `Comfortable` default; tables keep generous `0.8rem` cell padding; compact utility via `Density` setting.
- **Accessibility:** visible focus states, `aria-label`s on icon buttons, keyboard navigable menus.

---

## 9. Spacing & Typography System

**Typography** — Inter (400–800), system fallback:

| Element | Size | Weight |
|---|---|---|
| Page title | 1.35rem | 800, -0.02em |
| Card title | 0.95rem | 700 |
| Stat value | 1.45rem | 800 |
| Body | 0.9375rem | 400 |
| Table / form text | 0.875rem | 500/600 |
| Meta / captions | 0.72–0.8rem | 500–700, uppercase labels |

**Spacing scale** (8px base, consistent everywhere):

`2 · 4 · 6 · 8 · 12 · 16 · 20 · 24 · 32 · 40 · 48px`
- Card body padding `1.25rem`, header `1rem 1.25rem`
- Section gutter `1.5rem` (row `g-4`), stat gutter `1rem` (row `g-3`)
- Nav item padding `0.5rem 0.7rem`; page content `1.5rem 1.75rem`

All tokens live as CSS custom properties in `:root`, so the entire system is themeable from one place.

---

## 10. Ready-to-Implement Architecture

```
core/          # Django project (settings, urls, wsgi/asgi)
│  settings.py              # UI-only config, reads .env, STATICFILES_DIRS → static/
portal/        # Django app that renders the templates
│  base_view.py             # shell context + sample data (nav, user, notifications)
│  views/                   # views package
│  │  auth_views.py         # Django built-in auth views (styled) + audit/notify side-effects
│  │  __init__.py           # app pages (dashboard, accounts, emails) + error handlers
│  services/                # business logic only (auth, notifications, audit)
│  │  auth_service.py       # AuthService - login/logout/password side-effects
│  │  notification_service.py  # NotificationService - notification center ops
│  │  audit_service.py      # AuditService - security event recording
│  repositories/            # data access only (never business logic)
│  │  notification_repository.py  # NotificationRepository - persistence
│  │  audit_repository.py   # AuditRepository - persistence/filter/search
│  forms.py                 # Bootstrap wrappers for Django's auth forms + profile form
│  admin.py                 # User/Group admin customization (search, filters, list display)
│  models.py                # no models - Django's default User is used as-is
│  templatetags/ui_extras.py# initials, add_class, unread_badge, nav_is_active
│  urls.py                  # named routes + handler403/404/500
templates/     # hierarchy in §2
static/
│  css/mailfusion.css       # full design system (≈900 lines)
│  js/  main.js  inbox.js  tables.js  charts.js
│  images/  logo.svg  favicon.svg
│  icons/
```

**Integration path (no UI changes required):**

1. Replace `portal/base_view.py` sample data with real querysets / API clients.
2. Swap template loops (`for acc in accounts`) with model data — field names already match.
3. Submit forms to real endpoints; keep `messages.*` for alerts.
4. Wire OAuth button (`/accounts/add/step2/`) to the Microsoft Graph consent flow.
5. Enable `DEBUG=False` and the `handler403/404/500` in `portal/urls.py` take over.

---

## Design Tokens

| Token | Value |
|---|---|
| Primary | `#2563eb` |
| Success / Warning / Danger / Info | `#16a34a` / `#f59e0b` / `#dc2626` / `#0ea5e9` |
| Surface | `#ffffff` |
| Surface soft (page bg) | `#f8fafc` |
| Border | `#e2e8f0` |
| Text / Muted | `#0f172a` / `#94a3b8` |
