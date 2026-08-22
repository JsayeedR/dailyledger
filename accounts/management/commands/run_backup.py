"""
Nightly backup: dumps the database and archives the project folder (code +
media + .env), keeping only the last 30 days. Notifies every Super Admin by
Email and Telegram when it finishes (success or failure).

Intended to run once a day at 12:05 AM Asia/Dhaka via cron:
    5 0 * * * cd /home/app-admin/dailyledger && /home/app-admin/dailyledger/venv/bin/python manage.py run_backup >> /home/app-admin/dailyledger/backups/backup.log 2>&1

Backups land in backups/database/ and backups/project/ inside the project
folder — both already excluded from git via .gitignore.
"""
import os
import shutil
import subprocess
import tarfile
from datetime import datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import CustomUser, NotificationSettings, Role
from accounts import notifications

RETENTION_DAYS = 30


class Command(BaseCommand):
    help = "Backs up the database and project folder, prunes backups older than 30 days, and notifies Super Admins."

    def add_arguments(self, parser):
        parser.add_argument('--skip-notify', action='store_true', help='Skip sending the admin notification (useful for manual testing).')

    def handle(self, *args, **options):
        base_dir = settings.BASE_DIR
        db_backup_dir = base_dir / 'backups' / 'database'
        project_backup_dir = base_dir / 'backups' / 'project'
        db_backup_dir.mkdir(parents=True, exist_ok=True)
        project_backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M%S')
        errors = []
        db_result = None
        project_result = None

        # ---- 1. Database dump ----
        try:
            db_result = self._dump_database(db_backup_dir, timestamp)
            self.stdout.write(f"Database dumped: {db_result}")
        except Exception as e:
            errors.append(f"Database dump failed: {e}")
            self.stderr.write(str(e))

        # ---- 2. Project folder archive ----
        try:
            project_result = self._archive_project(base_dir, project_backup_dir, timestamp)
            self.stdout.write(f"Project archived: {project_result}")
        except Exception as e:
            errors.append(f"Project archive failed: {e}")
            self.stderr.write(str(e))

        # ---- 3. Retention cleanup ----
        try:
            removed = self._cleanup_old_backups(db_backup_dir, project_backup_dir)
            if removed:
                self.stdout.write(f"Removed {removed} backup(s) older than {RETENTION_DAYS} days.")
        except Exception as e:
            errors.append(f"Cleanup failed: {e}")
            self.stderr.write(str(e))

        # ---- 4. Notify Super Admins ----
        if not options['skip_notify']:
            self._notify_admins(db_result, project_result, errors, timestamp)

        if errors:
            self.stderr.write(self.style.ERROR(f"Backup finished with {len(errors)} error(s)."))
        else:
            self.stdout.write(self.style.SUCCESS("Backup finished successfully."))

    def _dump_database(self, db_backup_dir, timestamp):
        db_settings = settings.DATABASES['default']
        dump_path = db_backup_dir / f"dailyledger_db_{timestamp}.sql.gz"

        env = os.environ.copy()
        if db_settings.get('PASSWORD'):
            env['PGPASSWORD'] = db_settings['PASSWORD']

        pg_dump_cmd = [
            'pg_dump',
            '-h', db_settings.get('HOST') or 'localhost',
            '-p', str(db_settings.get('PORT') or 5432),
            '-U', db_settings.get('USER') or '',
            '-d', db_settings.get('NAME') or '',
        ]

        try:
            with open(dump_path, 'wb') as f:
                dump_proc = subprocess.Popen(pg_dump_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
                gzip_proc = subprocess.Popen(['gzip'], stdin=dump_proc.stdout, stdout=f, stderr=subprocess.PIPE)
                dump_proc.stdout.close()
                _, gzip_err = gzip_proc.communicate()
                _, dump_err = dump_proc.communicate()

            if dump_proc.returncode != 0:
                dump_path.unlink(missing_ok=True)
                raise RuntimeError(f"pg_dump failed: {dump_err.decode(errors='ignore')}")
        except Exception:
            dump_path.unlink(missing_ok=True)
            raise

        size_kb = dump_path.stat().st_size // 1024
        return f"{dump_path.name} ({size_kb} KB)"

    def _archive_project(self, base_dir, project_backup_dir, timestamp):
        archive_path = project_backup_dir / f"dailyledger_project_{timestamp}.tar.gz"
        exclude_dirs = {'venv', 'staticfiles', '__pycache__', 'backups', '.git'}

        def _filter(tarinfo):
            parts = set(tarinfo.name.split('/'))
            if parts & exclude_dirs:
                return None
            if tarinfo.name.endswith('.pyc'):
                return None
            return tarinfo

        with tarfile.open(archive_path, 'w:gz') as tar:
            tar.add(base_dir, arcname=base_dir.name, filter=_filter)

        size_mb = archive_path.stat().st_size / (1024 * 1024)
        return f"{archive_path.name} ({size_mb:.1f} MB)"

    def _cleanup_old_backups(self, db_backup_dir, project_backup_dir):
        cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
        removed = 0
        for directory, prefix in [(db_backup_dir, 'dailyledger_db_'), (project_backup_dir, 'dailyledger_project_')]:
            for f in directory.glob(f"{prefix}*"):
                if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                    f.unlink()
                    removed += 1
        return removed

    def _notify_admins(self, db_result, project_result, errors, timestamp):
        settings_obj = NotificationSettings.get_solo()
        admins = CustomUser.objects.filter(role=Role.SUPER_ADMIN, is_active=True)

        if not admins.exists():
            return

        success = not errors
        subject = f"DailyLedger Backup {'Succeeded' if success else 'FAILED'} — {timestamp}"

        lines = [f"Backup run at {timestamp} (Asia/Dhaka):", ""]
        if db_result:
            lines.append(f"✓ Database: {db_result}")
        if project_result:
            lines.append(f"✓ Project archive: {project_result}")
        if errors:
            lines.append("")
            lines.append("Errors:")
            for e in errors:
                lines.append(f"  - {e}")
        lines.append("")
        lines.append(f"Backups older than {RETENTION_DAYS} days are automatically removed.")
        body = "\n".join(lines)

        telegram_text = f"{'✅' if success else '❌'} " + subject + "\n\n" + "\n".join(
            [l for l in lines if l and not l.startswith(" ")]
        )

        for admin in admins:
            if admin.email:
                ok, detail = notifications.send_email(settings_obj, admin.email, subject, body)
                if not ok:
                    self.stderr.write(f"Admin email notify failed for {admin.email}: {detail}")
            if admin.telegram_id:
                ok, detail = notifications.send_telegram(settings_obj, admin.telegram_id, telegram_text)
                if not ok:
                    self.stderr.write(f"Admin telegram notify failed for {admin.email}: {detail}")
