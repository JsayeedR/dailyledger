"""
Sends the periodic (daily/weekly/monthly/yearly) summary notifications.

Intended to be run once a day at 12:01 AM Asia/Dhaka time via cron (or any
scheduler) — NOT continuously. It figures out for itself which of the four
periods apply to "today" and only sends those:

    Daily   -> every run, summarizes the day that just ended
    Weekly  -> only when today is Friday, summarizes the last 7 days
    Monthly -> only when today is the 1st, summarizes the previous month
    Yearly  -> only when today is Jan 1st, summarizes the previous year

Example crontab entry (server already runs in Asia/Dhaka per TIME_ZONE, but
cron uses the OS's local time — check `date` on the server and adjust the
hour/minute below if the OS is on UTC instead of Asia/Dhaka):

    1 0 * * * cd /path/to/dailyledger && /path/to/venv/bin/python manage.py send_summaries >> /var/log/dailyledger_summaries.log 2>&1

Safe to run more than once on the same day — each send is guarded by a
`last_*_sent_date` field on NotificationPreference so nobody gets duplicates.
"""
import calendar
from datetime import timedelta, date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.utils import timezone

from accounts.models import NotificationPreference, NotificationSettings, SummaryFrequency
from accounts import notifications, message_templates
from ledger.models import Transaction, TransactionType


def _totals_for_range(tenant, start_date, end_date):
    qs = Transaction.objects.filter(tenant=tenant, date__gte=start_date, date__lte=end_date)
    income = qs.filter(type=TransactionType.INCOME).aggregate(t=Sum('amount'))['t'] or Decimal('0')
    expense = qs.filter(type=TransactionType.EXPENSE).aggregate(t=Sum('amount'))['t'] or Decimal('0')
    top_categories = list(
        qs.filter(type=TransactionType.EXPENSE, category__isnull=False)
        .values('category__name')
        .annotate(total=Sum('amount'))
        .order_by('-total')[:5]
    )
    top_categories = [(row['category__name'], row['total']) for row in top_categories]
    return income, expense, top_categories


class Command(BaseCommand):
    help = "Sends daily/weekly/monthly/yearly summary notifications to users who have an approved, active preference."

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Ignore the once-per-day guard (useful for manual testing).')
        parser.add_argument('--dry-run', action='store_true', help="Print what would be sent without actually sending or marking as sent.")

    def handle(self, *args, **options):
        force = options['force']
        dry_run = options['dry_run']

        today = timezone.localtime(timezone.now()).date()
        settings_obj = NotificationSettings.get_solo()

        periods = self._build_periods(today)
        if not periods:
            self.stdout.write("No summary periods apply today. Nothing to do.")
            return

        for frequency, period_label, start_date, end_date, sent_field in periods:
            self._send_for_frequency(frequency, period_label, start_date, end_date, sent_field, today, settings_obj, force, dry_run)

    def _build_periods(self, today):
        periods = []

        # Daily — always, covering the day that just ended.
        yesterday = today - timedelta(days=1)
        periods.append((SummaryFrequency.DAILY, yesterday.strftime('%b %d, %Y'), yesterday, yesterday, 'last_daily_sent_date'))

        # Weekly — only on Fridays, covering the last 7 days.
        if today.weekday() == 4:  # Monday=0 ... Friday=4
            week_start = today - timedelta(days=7)
            week_end = today - timedelta(days=1)
            label = f"{week_start.strftime('%b %d')} – {week_end.strftime('%b %d, %Y')}"
            periods.append((SummaryFrequency.WEEKLY, label, week_start, week_end, 'last_weekly_sent_date'))

        # Monthly — only on the 1st, covering the previous calendar month.
        if today.day == 1:
            last_month_end = today - timedelta(days=1)
            last_month_start = last_month_end.replace(day=1)
            label = last_month_end.strftime('%B %Y')
            periods.append((SummaryFrequency.MONTHLY, label, last_month_start, last_month_end, 'last_monthly_sent_date'))

        # Yearly — only on Jan 1st, covering the previous calendar year.
        if today.month == 1 and today.day == 1:
            prev_year = today.year - 1
            start = date(prev_year, 1, 1)
            end = date(prev_year, 12, 31)
            periods.append((SummaryFrequency.YEARLY, str(prev_year), start, end, 'last_yearly_sent_date'))

        return periods

    def _send_for_frequency(self, frequency, period_label, start_date, end_date, sent_field, today, settings_obj, force, dry_run):
        # Multi-select: a user's active_frequencies is a list, so we filter in
        # Python rather than at the DB level to stay portable across backends.
        prefs = NotificationPreference.objects.select_related('user', 'user__tenant').exclude(
            active_frequencies=[]
        )

        count_sent = 0
        for pref in prefs:
            if frequency not in pref.active_frequencies:
                continue
            if not (pref.active_email_enabled or pref.active_telegram_enabled):
                continue
            if not force and getattr(pref, sent_field) == today:
                continue  # already sent today's run for this frequency

            user = pref.user
            if not hasattr(user, 'tenant'):
                continue
            tenant = user.tenant

            income, expense, top_categories = _totals_for_range(tenant, start_date, end_date)

            if dry_run:
                self.stdout.write(f"[DRY RUN] Would send {frequency} summary to {user.email} for {period_label}: "
                                   f"income={income} expense={expense}")
                continue

            if pref.active_email_enabled and user.email:
                subject, body = message_templates.build_email(
                    user, tenant, frequency, period_label, income, expense, top_categories)
                ok, detail = notifications.send_email(settings_obj, user.email, subject, body)
                if not ok:
                    self.stderr.write(f"Email failed for {user.email} ({frequency}): {detail}")

            if pref.active_telegram_enabled and user.telegram_id:
                text = message_templates.build_telegram(
                    user, tenant, frequency, period_label, income, expense, top_categories)
                ok, detail = notifications.send_telegram(settings_obj, user.telegram_id, text)
                if not ok:
                    self.stderr.write(f"Telegram failed for {user.email} ({frequency}): {detail}")

            setattr(pref, sent_field, today)
            pref.save(update_fields=[sent_field])
            count_sent += 1

        self.stdout.write(f"{frequency}: processed {count_sent} user(s) for {period_label}.")
