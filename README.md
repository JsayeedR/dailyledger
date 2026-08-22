# DailyLedger

A self-hosted, multi-tenant personal income & expense tracker — built to replace a manual spreadsheet with a proper web app. Every registered user gets a fully isolated financial workspace: categorized transactions, custom payment methods, monthly budgets with alerts, calendar and spreadsheet-style views, visual reports, and scheduled Email/Telegram summaries.

Built for a small, trusted group where each person's numbers stay completely private — not even a Super Admin can see another user's transactions.

## Features

- Multi-user, fully isolated workspaces (enforced in code on every request, not just hidden in the UI)
- Budgets with 80% / 100% usage warnings
- Calendar & spreadsheet-style monthly views
- Detail reports with charts and JPG export
- Email & Telegram summary notifications (daily / weekly / monthly / yearly), gated behind Super Admin approval
- Full audit log for Super Admins
- New-account approval workflow
- Guided setup wizard for new users

## Tech stack

- Django 5.2
- PostgreSQL
- Tailwind CSS (CDN)
- Chart.js
- Gunicorn + Nginx
- Self-hosted VM

## Local setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your own values
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Scheduled summaries

Summary notifications are sent by a management command intended to run once a day via cron:

```bash
python manage.py send_summaries
```

It figures out internally which periods apply (daily always; weekly on Fridays; monthly on the 1st; yearly on Jan 1st) and is safe to re-run — duplicate sends are guarded against per user, per period.

## Security & privacy

- Every transaction, category, and budget is scoped to the owning user's tenant at the query level
- Financial data is never reachable through the Django admin panel, even for superuser accounts
- Passwords are hashed with Django's standard one-way hashing
- New accounts require Super Admin approval before login is possible

## Developed by

**Jikrul Sayeed** — KUET · EEE · 2k15
[LinkedIn](https://www.linkedin.com/in/jikrulsayeed/)
