# ClinOva — Backend API

REST API for **ClinOva**, a clinical practical assessment platform for nursing and midwifery training colleges. It replaces paper scoring sheets with a dual-examiner digital workflow: two examiners independently score a clinical procedure, then one of them reconciles the results into a single official score.

Built with **Django** and **Django REST Framework**. The companion web app lives in the ClinOva frontend repository.

> **Confidentiality note.** This document intentionally covers setup and operation only. Security configuration, authorization rules and the detailed API specification are not reproduced here — read the source, or the private internal documentation, if you are authorized to. Do not copy internal details from this repository into public issues, forums or chat tools.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Security](#security)
- [Domain Overview](#domain-overview)
- [API Overview](#api-overview)
- [Bulk Import & Export](#bulk-import--export)
- [Management Commands](#management-commands)
- [Deployment](#deployment)
- [Backups](#backups)
- [Testing & Quality Checks](#testing--quality-checks)
- [Troubleshooting](#troubleshooting)
- [Known Limitations](#known-limitations)
- [Roadmap](#roadmap)
- [License](#license)

---

## Features

- Dual-examiner, step-based scoring of clinical procedures, with autosave
- Reconciliation of the two examiners' scores into one official result
- Care plan assessment
- Programs, academic levels, students and a procedure library
- Procedure **categories** (e.g. basic vs. advanced procedures) so examiners can narrow down before scoring
- Per-examiner "My Assessments" tracking by status
- Role-based access for administrators and examiners
- Bulk import (Excel / CSV) and export (CSV / Excel / PDF), grades reporting and dashboard statistics
- Django admin site for low-level data access

---

## Tech Stack

| Area | Technology |
|------|------------|
| Language | Python 3.12+ |
| Framework | Django 6, Django REST Framework 3 |
| Authentication | Token-based, delivered in HttpOnly cookies |
| Admin UI | `django-unfold`, `django-import-export` |
| Spreadsheets / PDF | `openpyxl`, `reportlab` |
| Database | SQLite |

Pinned dependency versions are in `requirements.txt`. Keep them current and review dependency advisories regularly.

---

## Architecture

```
Browser ──▶ Web app (Next.js) ──/api──▶ This API ──▶ Database
```

The web app forwards its API calls to this service, so browsers talk to a single origin. You can also call the API directly for development and testing.

---

## Project Structure

```
.
├── manage.py
├── requirements.txt
├── nursing_practical/   # Project configuration
├── accounts/            # Users and authentication
└── exams/               # Assessment domain (models, API, admin, commands)
```

---

## Getting Started

### Prerequisites

- Python **3.12 or newer**
- Git

### 1. Clone and create a virtual environment

```bash
git clone <repository-url>
cd <repository-folder>

# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure the environment

Create a `.env` file in the project root. It is git-ignored — **never commit it**.

```env
DJANGO_SECRET_KEY=<generate a unique value>
DEBUG=True

FRONTEND_DEV_URL=http://localhost:3000
BACKEND_DEV_URL=127.0.0.1
LOCALHOST=localhost
```

Generate a secret key:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

`DEBUG=True` is for **local development only**. Production settings are described under [Deployment](#deployment).

### 4. Create the database

```bash
python manage.py migrate
```

### 5. Create an administrator

```bash
python manage.py createsuperuser
```

Then give the account the application **admin** role — `createsuperuser` alone does not, and without it the account cannot use the web app's admin features:

```bash
python manage.py shell -c "from accounts.models import User; User.objects.filter(username='<your-username>').update(role='admin')"
```

Examiner accounts are created from the web app's admin area (or imported) and must have the **examiner** role.

### 6. Run the server

```bash
python manage.py runserver
```

Start the web app next and point its `API_DESTINATION` at this server.

---

## Configuration

Settings are read from environment variables (via `.env`).

| Variable | Required | Description |
|----------|----------|-------------|
| `DJANGO_SECRET_KEY` | **Yes** | Unique, long, random secret. Never commit or share it. Rotating it signs everyone out. |
| `DEBUG` | No (default off) | Local development only. **Must be off in production.** |
| `FRONTEND_URL` | Production | Public origin of the web app (allowed for cross-origin requests). |
| `FRONTEND_DEV_URL` | Local | Local web app origin. |
| `BACKEND_URL` | Production | Public **hostname** of this API (no scheme, no port). |
| `BACKEND_DEV_URL` | Local | Local hostname. |
| `LOCALHOST` | Local | Additional allowed local hostname. |

Host variables take **bare hostnames** (no `http://`, no port). Any other variables present in a `.env` file are ignored.

---

## Security

- **Secrets** live only in environment variables or a secrets manager — never in source control, tickets or chat. Use a different `DJANGO_SECRET_KEY` for every environment.
- **Production requires** `DEBUG` off, HTTPS everywhere, and restricted `BACKEND_URL` / `FRONTEND_URL` values.
- **Least privilege:** give people the lowest role they need; deactivate accounts of people who leave. Set strong, unique passwords for every account and require examiners to change any temporary password on first use.
- **Restrict the Django admin site** in production (network allow-list, VPN or reverse-proxy rules) and limit it to a small number of trusted staff.
- **Authorization is enforced by the API**, not by the web app. Do not treat hidden UI as a security control.
- **Protect data at rest and in backups:** the database and any exports contain student and assessment records. Encrypt backups, restrict access, and delete exports you no longer need.
- **Keep dependencies patched** and re-run the checks under [Testing & Quality Checks](#testing--quality-checks) after upgrades.
- **Reporting a vulnerability:** do **not** open a public issue. Contact the maintainers privately with the details.

---

## Domain Overview

The main concepts are: **programs**, **levels**, **students**, **procedures** (made of ordered **steps**, optionally grouped into **categories**), **assessments** of a student on a procedure, examiners' **scores** and the final **reconciled score**, and **care plans**.

In short: two different examiners score the same procedure independently; when both have finished, the examiner who finished last reconciles the two score sheets into the official result, which is then locked.

---

## API Overview

The API is served under `/api/` and is split into an authentication area and an assessment area. All endpoints require authentication except login. Some capabilities are restricted to administrators.

- Endpoint definitions: `accounts/urls.py`, `exams/urls.py`
- Permission rules: `exams/permissions.py` and the views themselves
- List endpoints are paginated; most accept search and filter query parameters
- Routes are registered **without a trailing slash** (call `/api/exams/programs`, not `/api/exams/programs/`)

A full endpoint reference is intentionally not published in this README. Maintain it in private documentation if your team needs one.

---

## Bulk Import & Export

Always start from the current template (available in the web app's admin area) rather than writing files by hand. Files may be Excel or CSV (UTF-8). Imports run in a transaction and report per-row errors.

- **Students, procedures, steps and examiners** can be imported from templates.
- **Procedure categories** can be supplied per procedure; unknown names are created automatically, and a blank category leaves an existing procedure's category unchanged.
- **New examiners:** if a password is not supplied, a unique random temporary password is generated and shown **once** in the import result. It cannot be retrieved later — record it securely, share it privately, and require a change at first login.
- Imported files and exports contain personal data: store them securely and delete them when no longer needed.

---

## Management Commands

Run `python manage.py <command> --help` for options.

| Command | Purpose |
|---------|---------|
| `create_import_template` | Generate sample import templates |
| `import_data` | Import reference data from separate files |
| `export_all_data` | Export reference data |
| `export_complete_data` | Export reference data to one multi-sheet Excel file |
| `import_complete_data` | Import that Excel file (supports `--dry-run`) |

> These cover **reference data only** (programs, students, procedures, steps). They do not include examiners, assessments, scores, care plans or categories, and are **not** a backup mechanism — see [Backups](#backups).

---

## Deployment

1. **Environment** — `DEBUG` off, a unique `DJANGO_SECRET_KEY`, correct `BACKEND_URL` / `FRONTEND_URL`.
2. **HTTPS** — required. If TLS is terminated at a reverse proxy, make sure the proxy is configured correctly for this application.
3. **Install and migrate**
   ```bash
   pip install -r requirements.txt
   python manage.py migrate
   python manage.py collectstatic --noinput
   ```
4. **Serve with a production WSGI server** behind a reverse proxy — never `runserver`.
5. **Run the deployment check** and resolve its warnings:
   ```bash
   python manage.py check --deploy
   ```
6. **Create the first admin** and set its role (see [Getting Started](#5-create-an-administrator)).
7. **Verify end to end** from the web app before an exam period.

**Upgrades:** back up first, then run `python manage.py migrate` after pulling. Schema changes ship as migrations in each app's `migrations/` folder.

---

## Backups

The database contains student and assessment records — treat every copy as sensitive.

- Use the database's online backup rather than copying the file while the app is running. For SQLite:
  ```bash
  sqlite3 <database-file> ".backup '<backup-file>'"
  ```
- For a portable dump:
  ```bash
  python manage.py dumpdata --natural-foreign --exclude contenttypes --exclude auth.permission --exclude sessions > backup.json
  ```
- Encrypt backups, store them off the server with restricted access, and schedule them around exam periods.
- **Test a restore** at least once.

---

## Testing & Quality Checks

There is no automated test suite yet. Before every release run:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
```

When adding tests, use `python manage.py test`; it uses a throw-away database and never touches your real data.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| Error about `SECRET_KEY` on start | `DJANGO_SECRET_KEY` is missing from `.env`. |
| Redirected to `https://` locally, or login does not persist | `DEBUG` is off. Turn it on for local HTTP development only. |
| `DisallowedHost` | Set the host variables to bare hostnames (no scheme, no port). |
| Requests fail with `401` after login | Requests are not reaching the API through the web app's proxy, or HTTPS is not used in production. |
| Cross-origin (CORS) error | The web app's origin is not configured. |
| `404` calling an endpoint directly | Remove the trailing slash. |
| `429 Too Many Requests` | Rate limiting is active; wait and retry. |
| Admin user is redirected away in the web app | The account has not been given the admin role — see [Getting Started](#5-create-an-administrator). |
| `no such table` / `no such column` | Run `python manage.py migrate`. |
| `database is locked` | Another process holds a write lock; avoid heavy imports during live scoring. |

---

## Known Limitations

- Uses SQLite; other database drivers are installed but not configured. Suitable for a single-server deployment.
- The data import/export commands are partial and not a backup mechanism.
- No automated test suite yet.

---

## Roadmap

- [ ] Mobile-friendly offline scoring
- [ ] Real-time collaboration between examiners
- [ ] Advanced reporting and analytics
- [ ] Reconciliation suggestions for score discrepancies
- [ ] Email notifications for examiners
- [ ] Audit logging for assessments

---

## License

No license file is currently included. Until one is added, all rights are reserved by the project maintainers.
