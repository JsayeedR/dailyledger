from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.utils.translation import gettext as _
from django.contrib.auth import login as auth_login, logout as auth_logout, update_session_auth_hash, get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from .forms import RegistrationForm, StyledPasswordChangeForm as PasswordChangeForm, ProfileForm, NotificationPreferenceForm
from .models import (
    CustomUser, AuditLog, ApprovalStatus, NotificationSettings,
    NotificationPreference, PreferenceReviewStatus,
)
from .signals import DEFAULT_EXPENSE_CATEGORIES, DEFAULT_INCOME_CATEGORIES, DEFAULT_PAYMENT_METHODS
from . import audit, notifications

User = get_user_model()


def login_view(request):
    if request.user.is_authenticated:
        return redirect('ledger:dashboard')

    error = None
    submitted_email = ''
    if request.method == 'POST':
        submitted_email = request.POST.get('username', '').strip().lower()
        password = request.POST.get('password', '')

        try:
            user_obj = User.objects.get(email=submitted_email)
        except User.DoesNotExist:
            user_obj = None

        if user_obj and user_obj.check_password(password):
            if user_obj.approval_status == ApprovalStatus.PENDING:
                audit.log(actor=user_obj, action='LOGIN_FAILED', detail='Account pending approval', request=request)
                error = 'Your account is pending admin approval. Please contact your administrator.'
            elif user_obj.approval_status == ApprovalStatus.REJECTED:
                audit.log(actor=user_obj, action='LOGIN_FAILED', detail='Account was rejected', request=request)
                error = 'Your account request was not approved. Please contact your administrator.'
            elif not user_obj.is_active:
                audit.log(actor=user_obj, action='LOGIN_FAILED', detail='Account deactivated', request=request)
                error = 'This account has been deactivated. Please contact your administrator.'
            else:
                auth_login(request, user_obj)
                audit.log(actor=user_obj, action='LOGIN', request=request)
                return redirect('ledger:dashboard')
        else:
            if user_obj:
                audit.log(actor=user_obj, action='LOGIN_FAILED', detail='Incorrect password', request=request)
            error = 'Invalid email or password.'

    return render(request, 'registration/login.html', {'error': error, 'submitted_email': submitted_email})


def logout_view(request):
    if request.user.is_authenticated:
        audit.log(actor=request.user, action='LOGOUT', request=request)
    auth_logout(request)
    return redirect('login')


def register(request):
    if request.user.is_authenticated:
        return redirect('ledger:dashboard')

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.approval_status = ApprovalStatus.PENDING
            user.save()
            audit.log(actor=user, action='USER_REGISTER', target_type='User', target_id=user.id, detail=user.email, request=request)

            review_url = request.build_absolute_uri(reverse('accounts:user_approvals'))
            subject = 'New DailyLedger signup pending approval'
            email_body = (
                f'A new user has signed up and is waiting for approval.\n\n'
                f'Name: {user.full_name or "-"}\n'
                f'Email: {user.email}\n\n'
                f'Review it here: {review_url}'
            )
            telegram_text = (
                f'🆕 New DailyLedger signup pending approval\n'
                f'Name: {user.full_name or "-"}\n'
                f'Email: {user.email}\n'
                f'{review_url}'
            )
            notifications.notify_super_admins(subject, email_body, telegram_text, actor=user)

            return render(request, 'registration/pending_approval.html', {'email': user.email})
    else:
        form = RegistrationForm()

    return render(request, 'registration/register.html', {'form': form})


@login_required
def setup_wizard(request):
    from ledger.models import Category, PaymentMethod, TransactionType

    tenant = request.user.tenant
    if tenant.setup_completed:
        return redirect('ledger:dashboard')

    existing_expense = set(Category.objects.filter(tenant=tenant, type=TransactionType.EXPENSE).values_list('name', flat=True))
    existing_income = set(Category.objects.filter(tenant=tenant, type=TransactionType.INCOME).values_list('name', flat=True))
    existing_payment = set(PaymentMethod.objects.filter(tenant=tenant).values_list('name', flat=True))

    if request.method == 'POST':
        selected_expense = request.POST.getlist('expense_categories')
        selected_income = request.POST.getlist('income_categories')
        selected_payment = request.POST.getlist('payment_methods')

        Category.objects.bulk_create([
            Category(tenant=tenant, type=TransactionType.EXPENSE, name=n, is_system_default=True)
            for n in selected_expense if n not in existing_expense
        ])
        Category.objects.bulk_create([
            Category(tenant=tenant, type=TransactionType.INCOME, name=n, is_system_default=True)
            for n in selected_income if n not in existing_income
        ])
        PaymentMethod.objects.bulk_create([
            PaymentMethod(tenant=tenant, name=n, is_system_default=True)
            for n in selected_payment if n not in existing_payment
        ])

        tenant.setup_completed = True
        tenant.save()
        audit.log(actor=request.user, action='SETUP_COMPLETED', request=request)
        messages.success(request, _('Setup complete! Your categories and payment methods are ready.'))
        return redirect('ledger:dashboard')

    context = {
        'expense_categories': [(n, n in existing_expense) for n in DEFAULT_EXPENSE_CATEGORIES],
        'income_categories': [(n, n in existing_income) for n in DEFAULT_INCOME_CATEGORIES],
        'payment_methods': [(n, n in existing_payment) for n in DEFAULT_PAYMENT_METHODS],
        'has_existing_data': bool(existing_expense or existing_income or existing_payment),
    }
    return render(request, 'accounts/setup_wizard.html', context)


@login_required
def change_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            audit.log(actor=user, action='PASSWORD_CHANGE', request=request)
            messages.success(request, _('Your password has been changed.'))
            return redirect('ledger:dashboard')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'accounts/change_password.html', {'form': form})


@login_required
def profile_view(request):
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            audit.log(actor=request.user, action='PROFILE_UPDATE', request=request)
            messages.success(request, _('Profile updated.'))
            return redirect('accounts:profile')
    else:
        form = ProfileForm(instance=request.user)
    return render(request, 'accounts/profile.html', {'form': form})


def is_super_admin(user):
    return user.is_authenticated and user.role == 'SUPER_ADMIN'


@login_required
def notification_preference_view(request):
    """Lets any user choose their summary frequency + channels. Every change
    is queued as a request and only takes effect once a Super Admin approves it."""
    pref, _created = NotificationPreference.objects.get_or_create(user=request.user)
    settings_obj = NotificationSettings.get_solo()

    if request.method == 'POST':
        form = NotificationPreferenceForm(request.POST)
        if form.is_valid():
            pref.submit_request(
                frequencies=form.cleaned_data['frequencies'],
                email_enabled=form.cleaned_data['email_enabled'],
                telegram_enabled=form.cleaned_data['telegram_enabled'],
            )
            audit.log(
                actor=request.user, action='SETTINGS_UPDATE',
                detail=f"Requested notification preference: {pref.requested_frequencies} "
                       f"(email={pref.requested_email_enabled}, telegram={pref.requested_telegram_enabled})",
                request=request,
            )

            review_url = request.build_absolute_uri(reverse('accounts:preference_approvals'))
            subject = 'New notification preference request pending approval'
            email_body = (
                f'{request.user.full_name or request.user.email} requested a change to their '
                f'notification preferences and it is waiting for approval.\n\n'
                f'Review it here: {review_url}'
            )
            telegram_text = (
                f'🆕 Notification preference change pending approval\n'
                f'User: {request.user.email}\n'
                f'{review_url}'
            )
            notifications.notify_super_admins(subject, email_body, telegram_text, actor=request.user)

            messages.success(request, _('Your request was submitted and is pending Super Admin approval.'))
            return redirect('accounts:notification_preference')
    else:
        initial = {
            'frequencies': pref.requested_frequencies if pref.has_pending_request else pref.active_frequencies,
            'email_enabled': pref.requested_email_enabled if pref.has_pending_request else pref.active_email_enabled,
            'telegram_enabled': pref.requested_telegram_enabled if pref.has_pending_request else pref.active_telegram_enabled,
        }
        form = NotificationPreferenceForm(initial=initial)

    return render(request, 'accounts/notification_preference.html', {
        'form': form, 'pref': pref, 'settings': settings_obj,
    })


@login_required
@user_passes_test(is_super_admin)
def preference_approvals(request):
    pending = NotificationPreference.objects.select_related('user').filter(
        review_status=PreferenceReviewStatus.PENDING).order_by('requested_at')
    history = NotificationPreference.objects.select_related('user', 'reviewed_by').exclude(
        review_status=PreferenceReviewStatus.PENDING).exclude(
        review_status=PreferenceReviewStatus.NONE).order_by('-reviewed_at')[:100]
    return render(request, 'accounts/preference_approvals.html', {
        'pending': pending, 'history': history,
    })


@login_required
@user_passes_test(is_super_admin)
def approve_preference(request, pref_id):
    pref = get_object_or_404(NotificationPreference, id=pref_id, review_status=PreferenceReviewStatus.PENDING)
    if request.method == 'POST':
        pref.approve(reviewer=request.user)
        audit.log(
            actor=request.user, action='SETTINGS_UPDATE',
            target_type='NotificationPreference', target_id=pref.id,
            detail=f"Approved {pref.user.email}: {pref.active_frequencies} "
                   f"(email={pref.active_email_enabled}, telegram={pref.active_telegram_enabled})",
            request=request,
        )
        messages.success(request, _('Approved notification preference for %(email)s.') % {'email': pref.user.email})
    return redirect('accounts:preference_approvals')


@login_required
@user_passes_test(is_super_admin)
def reject_preference(request, pref_id):
    pref = get_object_or_404(NotificationPreference, id=pref_id, review_status=PreferenceReviewStatus.PENDING)
    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        pref.reject(reviewer=request.user, reason=reason)
        audit.log(
            actor=request.user, action='SETTINGS_UPDATE',
            target_type='NotificationPreference', target_id=pref.id,
            detail=f"Rejected request from {pref.user.email}" + (f": {reason}" if reason else ''),
            request=request,
        )
        messages.success(request, _('Rejected request from %(email)s.') % {'email': pref.user.email})
    return redirect('accounts:preference_approvals')


@login_required
@user_passes_test(is_super_admin)
def notification_settings_view(request):
    settings_obj = NotificationSettings.get_solo()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'save_email':
            settings_obj.smtp_host = request.POST.get('smtp_host', '').strip()
            try:
                settings_obj.smtp_port = int(request.POST.get('smtp_port') or 587)
            except ValueError:
                settings_obj.smtp_port = 587
            settings_obj.smtp_use_tls = request.POST.get('smtp_use_tls') == 'on'
            settings_obj.smtp_username = request.POST.get('smtp_username', '').strip()
            new_password = request.POST.get('smtp_password', '').strip().replace(' ', '')  # Gmail App Passwords display with spaces but contain none
            if new_password:
                settings_obj.smtp_password = new_password
            settings_obj.from_display_name = request.POST.get('from_display_name', 'DailyLedger').strip() or 'DailyLedger'
            settings_obj.reply_to_email = request.POST.get('reply_to_email', '').strip()
            settings_obj.save()
            audit.log(actor=request.user, action='SETTINGS_UPDATE', detail='Email/SMTP settings updated', request=request)
            messages.success(request, _('Email settings saved.'))

        elif action == 'save_telegram':
            settings_obj.telegram_bot_username = request.POST.get('telegram_bot_username', '').strip()
            new_token = request.POST.get('telegram_bot_token', '').strip()
            if new_token:
                settings_obj.telegram_bot_token = new_token
            settings_obj.save()
            audit.log(actor=request.user, action='SETTINGS_UPDATE', detail='Telegram bot settings updated', request=request)
            messages.success(request, _('Telegram bot settings saved.'))

        elif action == 'test_email':
            ok, detail = notifications.send_email(
                settings_obj, request.user.email,
                'DailyLedger — Test Email',
                'This is a test email from DailyLedger. If you received this, your email settings are working correctly.'
            )
            messages.success(request, _('Test email sent to %(email)s.') % {'email': request.user.email}) if ok else messages.error(request, _('Test email failed: %(detail)s') % {'detail': detail})

        elif action == 'test_telegram':
            if not request.user.telegram_id:
                messages.error(request, _('Set your Telegram Chat ID in your Profile first, then try the test again.'))
            else:
                ok, detail = notifications.send_telegram(
                    settings_obj, request.user.telegram_id,
                    'This is a test message from DailyLedger. If you received this, your Telegram bot settings are working correctly.'
                )
                messages.success(request, _('Test Telegram message sent.')) if ok else messages.error(request, _('Test Telegram message failed: %(detail)s') % {'detail': detail})

        return redirect('accounts:notification_settings')

    return render(request, 'accounts/notification_settings.html', {'settings': settings_obj})


@login_required
@user_passes_test(is_super_admin)
def user_approvals(request):
    pending = CustomUser.objects.filter(approval_status=ApprovalStatus.PENDING).order_by('-date_joined')
    approved = CustomUser.objects.filter(approval_status=ApprovalStatus.APPROVED).order_by('-date_joined')
    rejected = CustomUser.objects.filter(approval_status=ApprovalStatus.REJECTED).order_by('-date_joined')
    return render(request, 'accounts/user_approvals.html', {
        'pending': pending, 'approved': approved, 'rejected': rejected,
    })


@login_required
@user_passes_test(is_super_admin)
def approve_user(request, user_id):
    target = get_object_or_404(CustomUser, id=user_id, approval_status=ApprovalStatus.PENDING)
    if request.method == 'POST':
        target.is_active = True
        target.approval_status = ApprovalStatus.APPROVED
        target.save()
        audit.log(actor=request.user, action='USER_APPROVED', target_type='User', target_id=target.id, detail=target.email, request=request)

        settings_obj = NotificationSettings.get_solo()
        subject = 'Your DailyLedger account has been approved'
        body = (
            f'Hello {target.full_name or target.email},\n\n'
            'Your DailyLedger account has been approved by the administrator. '
            'You can now log in and use the system.\n\n'
            'Regards,\n'
            'DailyLedger'
        )
        notifications.send_email(
            settings_obj,
            target.email,
            subject,
            body,
            actor=request.user,
        )

        messages.success(request, _('%(email)s has been approved.') % {'email': target.email})
    return redirect('accounts:user_approvals')


@login_required
@user_passes_test(is_super_admin)
def reject_user(request, user_id):
    target = get_object_or_404(CustomUser, id=user_id, approval_status=ApprovalStatus.PENDING)
    if request.method == 'POST':
        target.approval_status = ApprovalStatus.REJECTED
        target.is_active = False
        target.save()
        audit.log(actor=request.user, action='USER_REJECTED', target_type='User', target_id=str(target.id), detail=target.email, request=request)
        messages.success(request, _('%(email)s has been rejected.') % {'email': target.email})
    return redirect('accounts:user_approvals')


@login_required
@user_passes_test(is_super_admin)
def audit_log_view(request):
    logs = AuditLog.objects.select_related('actor').all()[:300]
    return render(request, 'accounts/audit_log.html', {'logs': logs})


@login_required
@user_passes_test(is_super_admin)
def user_activity_view(request):
    users = CustomUser.objects.filter(is_active=True).order_by('-total_active_seconds')
    activity = [{
        'user': u,
        'total_minutes': round(u.total_active_seconds / 60, 1),
        'sessions': u.session_count,
    } for u in users]
    return render(request, 'accounts/user_activity.html', {'activity': activity})


@login_required
@user_passes_test(is_super_admin)
def user_list(request):
    users = CustomUser.objects.all().order_by('-date_joined')
    return render(request, 'accounts/user_list.html', {'users': users})


@login_required
@user_passes_test(is_super_admin)
def toggle_user_active(request, user_id):
    target = get_object_or_404(CustomUser, id=user_id)
    if target == request.user:
        messages.error(request, _('You cannot deactivate your own account.'))
        return redirect('accounts:user_list')
    if request.method == 'POST':
        target.is_active = not target.is_active
        target.save()
        action = 'USER_REACTIVATED' if target.is_active else 'USER_DEACTIVATED'
        audit.log(actor=request.user, action=action, target_type='User', target_id=target.id, detail=target.email, request=request)
        messages.success(request, _('%(email)s has been %(status)s.') % {'email': target.email, 'status': _('reactivated') if target.is_active else _('deactivated')})
    return redirect('accounts:user_list')

@login_required
@user_passes_test(is_super_admin)
def user_profile_view(request, user_id):
    """Read-only view for a Super Admin to inspect any user's profile
    and activity stats. Never exposes password data or lets the Super
    Admin edit financial info -- that stays fully tenant-isolated."""
    target = get_object_or_404(CustomUser, id=user_id)
    return render(request, 'accounts/user_profile.html', {'target': target})
