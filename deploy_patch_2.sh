#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$HOME/dailyledger"
cd "$PROJECT_DIR"

echo "== 0. Pre-flight =="
if [ -d "venv" ]; then source venv/bin/activate; echo "Activated venv/"
elif [ -d ".venv" ]; then source .venv/bin/activate; echo "Activated .venv/"
else echo "WARNING: no venv/ found — using system python3."; fi

echo
echo "== 1. Git status before patch =="
git status --short

echo
echo "== 2. Applying template patch =="
python3 - <<'PYEOF'
import sys

def patch(path, old, new, expect=1):
    with open(path, encoding='utf-8') as f:
        content = f.read()
    count = content.count(old)
    if count == 0 and content.count(new) > 0:
        print(f"  [skip] {path}: already applied.")
        return
    if count != expect:
        print(f"  [FAIL] {path}: expected {expect}, found {count}.")
        sys.exit(1)
    content = content.replace(old, new, 1)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  [ok]   {path}: patched.")

patch(
    'templates/accounts/preference_approvals.html',
    old="""                {% else %}<span class="text-red-600">{% trans "Rejected" %}</span>{% endif %}
            </td>
            <td>{{ p.requested_frequency_labels|join:", "|default:"—" }}</td>
            <td>{{ p.reviewed_by.email|default:"—" }}</td>""",
    new="""                {% else %}<span class="text-red-600">{% trans "Rejected" %}</span>{% endif %}
            </td>
            <td>
                {% if p.requested_frequency_labels %}{{ p.requested_frequency_labels|join:", " }}
                {% elif p.active_frequency_labels %}{{ p.active_frequency_labels|join:", " }} <span class="text-xs text-gray-400">({% trans "set by Super Admin" %})</span>
                {% else %}—{% endif %}
            </td>
            <td>{{ p.reviewed_by.email|default:"—" }}</td>""",
)
print()
print("Edit applied.")
PYEOF

echo
echo "== 3. Sanity check =="
python manage.py check

echo
echo "== 4. Commit + push =="
git add -A
git status --short
git commit -m "Show active frequency (tagged 'set by Super Admin') for override rows in preference approvals history"
git push origin main

echo
echo "============================================================================"
echo "DONE. Template-only change — no migration, no static files affected."
echo "Restart your app process for it to take effect:"
echo "    sudo systemctl restart <your-gunicorn-service-name>"
echo "============================================================================"
