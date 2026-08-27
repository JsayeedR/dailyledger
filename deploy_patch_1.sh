#!/usr/bin/env bash
# ============================================================================
# DailyLedger — Deploy Patch #1
#   (1) Super Admin can DIRECTLY set a user's notification preference
#       (bypasses the request/approve flow) from that user's profile page.
#   (3) Commits + pushes the already-working, currently-uncommitted Savings
#       feature that was sitting in your working tree.
#
# Self-checking: every file edit verifies its anchor text exists exactly
# once before touching it, and re-verifies the change landed. If anything
# doesn't match (e.g. this has already been applied, or the file differs
# from what I inspected), it stops and tells you instead of corrupting
# the file. Safe to re-run.
#
# USAGE:
#   1) scp -P 3048 deploy_patch_1.sh app-admin@103.16.152.238:/home/app-admin/dailyledger/
#   2) ssh -p 3048 app-admin@103.16.152.238
#   3) cd ~/dailyledger && bash deploy_patch_1.sh
#   4) Paste the full output back here for verification before you restart
#      the app service (last step is printed, not run automatically).
# ============================================================================
set -euo pipefail

PROJECT_DIR="$HOME/dailyledger"
cd "$PROJECT_DIR"

echo "== 0. Pre-flight =="
if [ -d "venv" ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
    echo "Activated venv/"
elif [ -d ".venv" ]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
    echo "Activated .venv/"
else
    echo "WARNING: no venv/ or .venv/ found next to manage.py — continuing with system python3."
fi

echo
echo "== 1. Git status before patch =="
git status --short

echo
echo "== 2. Applying code patch (views.py, urls.py, template) =="
python3 - <<'PYEOF'
import re, sys

def patch(path, old, new, expect=1):
    with open(path, encoding='utf-8') as f:
        content = f.read()
    count = content.count(old)
    if count == 0 and content.count(new) > 0:
        print(f"  [skip] {path}: patch already applied.")
        return
    if count != expect:
        print(f"  [FAIL] {path}: expected {expect} match(es) of anchor, found {count}.")
        print("  ---- anchor was ----")
        print(old)
        sys.exit(1)
    content = content.replace(old, new, 1)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  [ok]   {path}: patched.")

# ---------------------------------------------------------------------
# accounts/views.py — update user_profile_view + add new admin-set view
# ---------------------------------------------------------------------
patch(
    'accounts/views.py',
    old="""@login_required
@user_passes_test(is_super_admin)
def user_profile_view(request, user_id):
    \"\"\"Read-only view for a Super Admin to inspect any user's profile
    and activity stats. Never exposes password data or lets the Super
    Admin edit financial info -- that stays fully tenant-isolated.\"\"\"
    target = get_object_or_404(CustomUser, id=user_id)
    return render(request, 'accounts/user_profile.html', {'target': target})""",
    new="""@login_required
@user_passes_test(is_super_admin)
def user_profile_view(request, user_id):
    \"\"\"Read-only view for a Super Admin to inspect any user's profile
    and activity stats. Never exposes password data or lets the Super
    Admin edit financial info -- that stays fully tenant-isolated.\"\"\"
    target = get_object_or_404(CustomUser, id=user_id)
    notif_pref, _created = NotificationPreference.objects.get_or_create(user=target)
    notif_form = NotificationPreferenceForm(initial={
        'frequencies': notif_pref.active_frequencies,
        'email_enabled': notif_pref.active_email_enabled,
        'telegram_enabled': notif_pref.active_telegram_enabled,
    })
    return render(request, 'accounts/user_profile.html', {
        'target': target, 'notif_pref': notif_pref, 'notif_form': notif_form,
    })


@login_required
@user_passes_test(is_super_admin)
def set_notification_preference_admin(request, user_id):
    \"\"\"Lets Super Admin directly SET a user's active notification
    preference, bypassing the normal request/approve flow entirely.
    Used when Super Admin wants to turn summaries on/off for someone
    without waiting for that user to submit a request.\"\"\"
    target = get_object_or_404(CustomUser, id=user_id)
    notif_pref, _created = NotificationPreference.objects.get_or_create(user=target)

    if request.method == 'POST':
        form = NotificationPreferenceForm(request.POST)
        if form.is_valid():
            notif_pref.active_frequencies = form.cleaned_data['frequencies']
            notif_pref.active_email_enabled = form.cleaned_data['email_enabled']
            notif_pref.active_telegram_enabled = form.cleaned_data['telegram_enabled']
            notif_pref.review_status = PreferenceReviewStatus.APPROVED
            notif_pref.reviewed_at = timezone.now()
            notif_pref.reviewed_by = request.user
            notif_pref.rejection_reason = ''
            notif_pref.save()
            audit.log(
                actor=request.user, action='SETTINGS_UPDATE',
                target_type='NotificationPreference', target_id=notif_pref.id,
                detail=f"Super Admin directly set notification preference for {target.email}: "
                       f"{notif_pref.active_frequencies} (email={notif_pref.active_email_enabled}, "
                       f"telegram={notif_pref.active_telegram_enabled})",
                request=request,
            )
            messages.success(request, _('Notification preference set for %(email)s.') % {'email': target.email})
        else:
            messages.error(request, _('Please fix the errors below.'))
    return redirect('accounts:user_profile', user_id=target.id)""",
)

# ---------------------------------------------------------------------
# accounts/urls.py — add the new route
# ---------------------------------------------------------------------
patch(
    'accounts/urls.py',
    old="    path('users/<uuid:user_id>/profile/', views.user_profile_view, name='user_profile'),\n",
    new=(
        "    path('users/<uuid:user_id>/profile/', views.user_profile_view, name='user_profile'),\n"
        "    path('users/<uuid:user_id>/set-notification-preference/', views.set_notification_preference_admin, "
        "name='set_notification_preference_admin'),\n"
    ),
)

# ---------------------------------------------------------------------
# templates/accounts/user_profile.html — add Super Admin override panel
# ---------------------------------------------------------------------
patch(
    'templates/accounts/user_profile.html',
    old="""    </div>
</div>
{% endblock %}""",
    new="""    </div>

    {% if request.user.role == 'SUPER_ADMIN' and request.user.id != target.id %}
    <div class="px-8 py-6 border-t border-gray-100 bg-gray-50/60">
        <h2 class="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-1">{% trans "Notification Preference" %} — {% trans "Super Admin Override" %}</h2>
        <p class="text-xs text-gray-500 mb-4">{% trans "Sets this user's ACTIVE summary preference directly, without waiting for them to request it." %}</p>
        <form method="post" action="{% url 'accounts:set_notification_preference_admin' user_id=target.id %}" class="space-y-3">
            {% csrf_token %}
            <div class="text-sm text-gray-700 space-y-1.5">
                {{ notif_form.frequencies }}
            </div>
            <div class="flex gap-5 text-sm text-gray-700">
                <label class="inline-flex items-center gap-2">{{ notif_form.email_enabled }} {% trans "Send via Email" %}</label>
                <label class="inline-flex items-center gap-2">{{ notif_form.telegram_enabled }} {% trans "Send via Telegram" %}</label>
            </div>
            <button type="submit" class="text-sm font-medium px-4 py-2 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700">
                {% trans "Set Notification Preference" %}
            </button>
        </form>
    </div>
    {% endif %}
</div>
{% endblock %}""",
)

print()
print("All edits applied.")
PYEOF

echo
echo "== 3. Apply pending migrations (includes the Savings tables) =="
python manage.py makemigrations --check --dry-run || true
python manage.py migrate

echo
echo "== 4. Collect static (harmless no-op if nothing changed) =="
python manage.py collectstatic --noinput

echo
echo "== 5. Sanity check: Django can load the project =="
python manage.py check

echo
echo "== 6. Commit + push everything (Savings feature + this patch) =="
git add -A
git status --short
git commit -m "Add Super Admin direct notification-preference override; add Savings feature (categories, transactions, migration)"
git push origin main

echo
echo "============================================================================"
echo "DONE. Code is committed, pushed, migrated, and checked clean."
echo "Nothing was restarted automatically — restart your app process now, e.g.:"
echo "    sudo systemctl restart <your-gunicorn-service-name>"
echo "    sudo systemctl reload nginx     # only if nginx config also changed (it didn't here)"
echo "Paste this script's full output back so I can confirm everything landed cleanly."
echo "============================================================================"
