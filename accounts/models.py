import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone


class Role(models.TextChoices):
    USER = 'USER', 'User'
    ADMIN = 'ADMIN', 'Admin'
    SUPER_ADMIN = 'SUPER_ADMIN', 'Super Admin'


class ApprovalStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Users must have an email address.')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', Role.SUPER_ADMIN)
        extra_fields.setdefault('approval_status', ApprovalStatus.APPROVED)
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.USER)

    phone_number = models.CharField(max_length=32, blank=True)
    whatsapp_number = models.CharField(max_length=32, blank=True)
    telegram_id = models.CharField(max_length=64, blank=True, help_text="Your numeric Telegram Chat ID (message @userinfobot to find it)")

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    approval_status = models.CharField(max_length=10, choices=ApprovalStatus.choices, default=ApprovalStatus.APPROVED)

    date_joined = models.DateTimeField(default=timezone.now)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email

    @property
    def is_admin_or_above(self):
        return self.role in (Role.ADMIN, Role.SUPER_ADMIN)

    @property
    def display_name(self):
        if self.full_name:
            parts = self.full_name.strip().split()
            if parts:
                return ' '.join(parts[:2])
        return self.email.split('@')[0]


class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='tenant')
    name = models.CharField(max_length=150, default='My Workspace')
    currency = models.CharField(max_length=10, default='BDT')
    timezone = models.CharField(max_length=50, default='Asia/Dhaka')
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    setup_completed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class AuditAction(models.TextChoices):
    LOGIN = 'LOGIN', 'Login'
    LOGOUT = 'LOGOUT', 'Logout'
    LOGIN_FAILED = 'LOGIN_FAILED', 'Login Failed'
    USER_REGISTER = 'USER_REGISTER', 'User Registered'
    USER_APPROVED = 'USER_APPROVED', 'User Approved'
    USER_REJECTED = 'USER_REJECTED', 'User Rejected'
    USER_DEACTIVATED = 'USER_DEACTIVATED', 'User Deactivated'
    USER_REACTIVATED = 'USER_REACTIVATED', 'User Reactivated'
    PASSWORD_CHANGE = 'PASSWORD_CHANGE', 'Password Changed'
    PROFILE_UPDATE = 'PROFILE_UPDATE', 'Profile Updated'
    SETTINGS_UPDATE = 'SETTINGS_UPDATE', 'Settings Updated'
    SETUP_COMPLETED = 'SETUP_COMPLETED', 'Setup Completed'
    TRANSACTION_CREATE = 'TRANSACTION_CREATE', 'Transaction Created'
    TRANSACTION_UPDATE = 'TRANSACTION_UPDATE', 'Transaction Updated'
    TRANSACTION_DELETE = 'TRANSACTION_DELETE', 'Transaction Deleted'
    BUDGET_CREATE = 'BUDGET_CREATE', 'Budget Created'
    BUDGET_DELETE = 'BUDGET_DELETE', 'Budget Deleted'


class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(CustomUser, null=True, blank=True, on_delete=models.SET_NULL, related_name='audit_logs')
    action = models.CharField(max_length=30, choices=AuditAction.choices)
    target_type = models.CharField(max_length=50, blank=True)
    target_id = models.CharField(max_length=100, blank=True)
    detail = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['actor', 'action']), models.Index(fields=['created_at'])]

    def __str__(self):
        who = self.actor.email if self.actor else 'Unknown'
        return f"{who} — {self.action} — {self.created_at:%Y-%m-%d %H:%M}"


class PageViewCounter(models.Model):
    id = models.PositiveIntegerField(primary_key=True, default=1)
    count = models.PositiveBigIntegerField(default=0)

    @classmethod
    def increment(cls):
        cls.objects.get_or_create(id=1)
        cls.objects.filter(id=1).update(count=models.F('count') + 1)

    @classmethod
    def current(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        obj.refresh_from_db()
        return obj.count


class NotificationSettings(models.Model):
    """
    Single global row holding the SMTP + Telegram credentials Super Admin
    configures from the web UI. Secrets are stored encrypted (see crypto.py),
    never in plain text — and never exposed back in the form after saving.
    """
    id = models.PositiveIntegerField(primary_key=True, default=1)

    smtp_host = models.CharField(max_length=255, blank=True)
    smtp_port = models.PositiveIntegerField(default=587)
    smtp_use_tls = models.BooleanField(default=True)
    smtp_username = models.CharField(max_length=255, blank=True)
    smtp_password_encrypted = models.TextField(blank=True)
    from_display_name = models.CharField(max_length=100, blank=True, default='DailyLedger')
    reply_to_email = models.EmailField(blank=True, help_text="Defaults to the SMTP email above if left blank")

    telegram_bot_token_encrypted = models.TextField(blank=True)
    telegram_bot_username = models.CharField(max_length=100, blank=True, help_text="e.g. @DailyLedgerBot, shown to users so they know which bot to message")

    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj

    @property
    def smtp_password(self):
        from .crypto import decrypt_value
        return decrypt_value(self.smtp_password_encrypted)

    @smtp_password.setter
    def smtp_password(self, raw):
        from .crypto import encrypt_value
        self.smtp_password_encrypted = encrypt_value(raw)

    @property
    def telegram_bot_token(self):
        from .crypto import decrypt_value
        return decrypt_value(self.telegram_bot_token_encrypted)

    @telegram_bot_token.setter
    def telegram_bot_token(self, raw):
        from .crypto import encrypt_value
        self.telegram_bot_token_encrypted = encrypt_value(raw)

    def is_email_configured(self):
        return bool(self.smtp_host and self.smtp_username and self.smtp_password_encrypted)

    def is_telegram_configured(self):
        return bool(self.telegram_bot_token_encrypted)


class SummaryFrequency(models.TextChoices):
    DAILY = 'DAILY', 'Daily'
    WEEKLY = 'WEEKLY', 'Weekly (Friday)'
    MONTHLY = 'MONTHLY', 'Monthly (1st)'
    YEARLY = 'YEARLY', 'Yearly (Jan 1)'


class PreferenceReviewStatus(models.TextChoices):
    NONE = 'NONE', 'No request yet'
    PENDING = 'PENDING', 'Pending'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'


class NotificationPreference(models.Model):
    """
    Per-user summary notification setting. A user can select ANY combination
    of frequencies (e.g. Daily + Weekly + Monthly all at once — "select all"
    is supported). The *active* setting is what the scheduler actually uses
    to send messages. Any change a user makes is stored as a *requested*
    setting and only becomes active once a Super Admin approves it — so an
    in-flight request never silently changes what gets sent until reviewed.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='notification_preference')

    # ── Currently active (approved) configuration — used by the scheduler ──
    # Stored as a list of SummaryFrequency codes, e.g. ["DAILY", "WEEKLY"]. An empty list means off.
    active_frequencies = models.JSONField(default=list, blank=True)
    active_email_enabled = models.BooleanField(default=False)
    active_telegram_enabled = models.BooleanField(default=False)

    # ── Requested (not-yet-reviewed or most-recently-reviewed) configuration ──
    requested_frequencies = models.JSONField(default=list, blank=True)
    requested_email_enabled = models.BooleanField(default=False)
    requested_telegram_enabled = models.BooleanField(default=False)

    review_status = models.CharField(max_length=10, choices=PreferenceReviewStatus.choices, default=PreferenceReviewStatus.NONE)
    requested_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(CustomUser, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    rejection_reason = models.CharField(max_length=255, blank=True)

    # ── Idempotency: last date each frequency was actually sent for this user ──
    last_daily_sent_date = models.DateField(null=True, blank=True)
    last_weekly_sent_date = models.DateField(null=True, blank=True)
    last_monthly_sent_date = models.DateField(null=True, blank=True)
    last_yearly_sent_date = models.DateField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-requested_at']

    def __str__(self):
        return f"{self.user.email} — active: {self.active_frequencies or 'Off'}"

    @property
    def has_pending_request(self):
        return self.review_status == PreferenceReviewStatus.PENDING

    def active_frequency_labels(self):
        return [SummaryFrequency(f).label for f in self.active_frequencies if f in SummaryFrequency.values]

    def requested_frequency_labels(self):
        return [SummaryFrequency(f).label for f in self.requested_frequencies if f in SummaryFrequency.values]

    def submit_request(self, frequencies, email_enabled, telegram_enabled):
        self.requested_frequencies = list(frequencies)
        self.requested_email_enabled = email_enabled
        self.requested_telegram_enabled = telegram_enabled
        self.review_status = PreferenceReviewStatus.PENDING
        self.requested_at = timezone.now()
        self.reviewed_at = None
        self.reviewed_by = None
        self.rejection_reason = ''
        self.save()

    def approve(self, reviewer):
        self.active_frequencies = list(self.requested_frequencies)
        self.active_email_enabled = self.requested_email_enabled
        self.active_telegram_enabled = self.requested_telegram_enabled
        self.review_status = PreferenceReviewStatus.APPROVED
        self.reviewed_at = timezone.now()
        self.reviewed_by = reviewer
        self.save()

    def reject(self, reviewer, reason=''):
        self.review_status = PreferenceReviewStatus.REJECTED
        self.reviewed_at = timezone.now()
        self.reviewed_by = reviewer
        self.rejection_reason = reason
        self.save()
