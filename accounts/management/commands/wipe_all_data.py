"""
Wipes ALL project data — users, tenants, transactions, budgets, categories,
payment methods, audit logs, notification settings/preferences, sessions,
and uploaded receipt files — while leaving the PageViewCounter untouched.

This is intentionally hard to run by accident:
    python manage.py wipe_all_data --yes-i-am-sure

After running this, the database has zero users. Immediately run:
    python manage.py createsuperuser
to create a fresh Super Admin (it will prompt for email + password, then
you may need to set role=SUPER_ADMIN manually — see the printed instructions
at the end of this command).
"""
import shutil
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "DESTRUCTIVE: wipes all project data except the page view counter."

    def add_arguments(self, parser):
        parser.add_argument('--yes-i-am-sure', action='store_true',
                             help='Required flag to actually run the wipe.')
        parser.add_argument('--keep-media', action='store_true',
                             help='Skip deleting uploaded receipt files.')

    def handle(self, *args, **options):
        if not options['yes_i_am_sure']:
            self.stderr.write(self.style.ERROR(
                "Refusing to run without --yes-i-am-sure. This permanently deletes "
                "ALL users, tenants, transactions, budgets, categories, payment "
                "methods, audit logs, and notification settings/preferences."
            ))
            return

        from accounts.models import (
            CustomUser, Tenant, AuditLog, NotificationSettings,
            NotificationPreference,
        )
        from ledger.models import Category, PaymentMethod, Transaction, Budget
        from django.contrib.sessions.models import Session

        with transaction.atomic():
            counts = {}
            counts['Transaction'] = Transaction.objects.all().delete()[0]
            counts['Budget'] = Budget.objects.all().delete()[0]
            counts['Category'] = Category.objects.all().delete()[0]
            counts['PaymentMethod'] = PaymentMethod.objects.all().delete()[0]
            counts['NotificationPreference'] = NotificationPreference.objects.all().delete()[0]
            counts['AuditLog'] = AuditLog.objects.all().delete()[0]
            counts['Tenant'] = Tenant.objects.all().delete()[0]
            counts['CustomUser'] = CustomUser.objects.all().delete()[0]
            counts['NotificationSettings'] = NotificationSettings.objects.all().delete()[0]
            counts['Session'] = Session.objects.all().delete()[0]

        for model_name, count in counts.items():
            self.stdout.write(f"  Deleted {count} {model_name} row(s).")

        if not options['keep_media']:
            media_root = settings.MEDIA_ROOT
            if media_root.exists():
                for item in media_root.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    else:
                        item.unlink(missing_ok=True)
                self.stdout.write(f"  Cleared media directory: {media_root}")

        self.stdout.write(self.style.SUCCESS(
            "\nWipe complete. PageViewCounter was left untouched.\n"
            "Now create a fresh Super Admin:\n\n"
            "    python manage.py createsuperuser\n\n"
            "It will ask for email and password (CustomUser has no separate "
            "username field). This automatically sets role=SUPER_ADMIN and "
            "approval_status=APPROVED because of create_superuser() in "
            "accounts/models.py — no manual follow-up needed."
        ))
