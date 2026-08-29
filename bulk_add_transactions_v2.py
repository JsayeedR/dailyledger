#!/usr/bin/env python3
"""
DailyLedger — Bulk Transaction Import for a Specific User (v2, paste-safe)
============================================================================
Run this ON THE SERVER, inside the project directory, with the venv active:

    cd ~/dailyledger && source venv/bin/activate
    python bulk_add_transactions.py

WHY v2: the original version asked "Create category? [y/N]" mid-loop, which
breaks if you paste multiple lines at once — a missing-category prompt would
silently swallow your NEXT pasted transaction line as its y/N answer, and
that line would vanish with no record of it. v2 fixes this by never asking
anything in the middle of processing your lines:

  Phase 1 — READ: collects every line you paste/type, no DB access, no
            prompts. Ends on a line that's just "done" (or "cancel" to
            discard everything typed so far).
  Phase 2 — VALIDATE: parses every line (format/type/date/amount) and
            figures out which Categories / Payment Methods referenced
            don't exist yet. Anything malformed is reported now, before
            anything is touched.
  Phase 3 — ONE confirmation: if anything is missing, shows the full list
            once and asks a single y/N to auto-create all of them. No
            per-line prompts.
  Phase 4 — SAVE: creates the categories/payment methods (if approved),
            then creates every valid transaction, printing each as it
            saves.
  Phase 5 — SUMMARY: exact count of created vs skipped, with every
            skipped line's reason listed explicitly — nothing vanishes
            silently.

This means you can paste the entire block in one go — email, "y" to
confirm the user, every transaction line, then "done" — and every single
line is accounted for in the final summary.

Format (unchanged):
    Type-DD-Mon-YYYY-Amount-Category-PaymentMethod-Description
Example:
    Expense-05-Nov-2025-609.00-House & Utility-Credit Card-Desco Prepaid
============================================================================
"""
import os
import sys
import django
from decimal import Decimal, InvalidOperation
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.getcwd())
django.setup()

from django.contrib.auth import get_user_model
from ledger.models import Transaction, Category, PaymentMethod, TransactionType
from accounts import audit

User = get_user_model()


def find_user():
    while True:
        email = input("Enter the user's email address: ").strip().lower()
        if not email:
            continue
        user = User.objects.filter(email__iexact=email).first()
        if user:
            print(f"  -> Matched: {user.display_name} <{user.email}> (tenant owner: {user.tenant.owner.email})")
            confirm = input("  Is this the right user? [y/N]: ").strip().lower()
            if confirm == 'y':
                return user
            print("  Okay, try again.")
        else:
            print(f"  No user found with email '{email}'.")
            retry = input("  Try another email? [Y/n]: ").strip().lower()
            if retry == 'n':
                sys.exit("Aborted: no user selected.")


def show_reference_lists(tenant):
    print("\nExisting categories for this user's tenant:")
    for t in (TransactionType.EXPENSE, TransactionType.INCOME):
        names = list(Category.objects.filter(tenant=tenant, type=t).order_by('sort_order', 'name').values_list('name', flat=True))
        print(f"  {t.label}: {', '.join(names) if names else '(none yet)'}")
    pm_names = list(PaymentMethod.objects.filter(tenant=tenant).order_by('sort_order', 'name').values_list('name', flat=True))
    print(f"  Payment Methods: {', '.join(pm_names) if pm_names else '(none yet)'}")
    print()


def read_lines():
    """Phase 1: buffer every pasted/typed line. No DB access, no prompts."""
    print("Enter one transaction per line, format:")
    print("  Type-DD-Mon-YYYY-Amount-Category-PaymentMethod-Description")
    print("Example:")
    print("  Expense-05-Nov-2025-609.00-House & Utility-Credit Card-Desco Prepaid")
    print("You can paste many lines at once. Finish with a line that says 'done',")
    print("or 'cancel' to discard everything entered so far.\n")

    lines = []
    while True:
        raw = input("> ").strip()
        if not raw:
            continue
        if raw.lower() == 'done':
            break
        if raw.lower() == 'cancel':
            print("Cancelled — discarding everything entered.")
            return []
        lines.append(raw)
    return lines


def parse_line(line):
    """Structural parse only — no DB lookups yet. Returns (fields_dict, error)."""
    parts = line.split('-')
    if len(parts) != 8:
        return None, (f"expected 8 dash-separated fields (Type-DD-Mon-YYYY-Amount-Category-PaymentMethod-Description), "
                       f"got {len(parts)}: {parts}")

    type_raw, dd, mon, yyyy, amount_raw, category_name, pm_name, description = [p.strip() for p in parts]

    type_map = {'EXPENSE': TransactionType.EXPENSE, 'INCOME': TransactionType.INCOME}
    ttype = type_map.get(type_raw.upper())
    if ttype is None:
        return None, f"Type must be 'Expense' or 'Income', got '{type_raw}'"

    try:
        date_val = datetime.strptime(f"{dd}-{mon}-{yyyy}", "%d-%b-%Y").date()
    except ValueError:
        return None, f"couldn't parse date '{dd}-{mon}-{yyyy}' (expected DD-Mon-YYYY, e.g. 05-Nov-2025)"

    try:
        amount_val = Decimal(amount_raw)
        if amount_val <= 0:
            return None, f"amount must be positive, got '{amount_raw}'"
    except InvalidOperation:
        return None, f"couldn't parse amount '{amount_raw}'"

    return {
        'type': ttype,
        'date': date_val,
        'amount': amount_val,
        'category_name': category_name,
        'pm_name': pm_name,
        'description': description,
    }, None


def main():
    print("=" * 76)
    print("DailyLedger — Bulk Transaction Import (paste-safe)")
    print("=" * 76)
    user = find_user()
    tenant = user.tenant
    show_reference_lists(tenant)

    raw_lines = read_lines()
    if not raw_lines:
        print("Nothing to do.")
        return

    # ---- Phase 2: validate structurally, collect what's missing ----
    parsed = []       # list of (line, fields) for structurally-valid lines
    skipped = []      # list of (line, reason) for lines that fail outright
    missing_categories = {}   # (name_lower, ttype) -> (display_name, ttype)
    missing_pms = {}          # name_lower -> display_name

    existing_cats = {
        (c.name.lower(), c.type): c
        for c in Category.objects.filter(tenant=tenant)
    }
    existing_pms = {
        pm.name.lower(): pm
        for pm in PaymentMethod.objects.filter(tenant=tenant)
    }

    for line in raw_lines:
        fields, err = parse_line(line)
        if err:
            skipped.append((line, err))
            continue
        parsed.append((line, fields))
        key = (fields['category_name'].lower(), fields['type'])
        if key not in existing_cats and key not in missing_categories:
            missing_categories[key] = (fields['category_name'], fields['type'])
        pm_key = fields['pm_name'].lower()
        if pm_key not in existing_pms and pm_key not in missing_pms:
            missing_pms[pm_key] = fields['pm_name']

    # ---- Phase 3: one confirmation for everything missing ----
    create_missing = False
    if missing_categories or missing_pms:
        print("\nThe following don't exist yet in this user's tenant:")
        for name, ttype in missing_categories.values():
            print(f"  - Category: '{name}' ({ttype.label})")
        for name in missing_pms.values():
            print(f"  - Payment method: '{name}'")
        ans = input("\nCreate all of the above automatically? [y/N]: ").strip().lower()
        create_missing = (ans == 'y')
        if not create_missing:
            print("Not creating them — any line referencing these will be skipped.")

    if create_missing:
        for name, ttype in missing_categories.values():
            cat = Category.objects.create(tenant=tenant, type=ttype, name=name)
            existing_cats[(name.lower(), ttype)] = cat
            print(f"  [+] Created category: {name} ({ttype.label})")
        for name in missing_pms.values():
            pm = PaymentMethod.objects.create(tenant=tenant, name=name)
            existing_pms[name.lower()] = pm
            print(f"  [+] Created payment method: {name}")

    # ---- Phase 4: save ----
    created = 0
    for line, fields in parsed:
        cat_key = (fields['category_name'].lower(), fields['type'])
        pm_key = fields['pm_name'].lower()
        category = existing_cats.get(cat_key)
        payment_method = existing_pms.get(pm_key)
        if category is None:
            skipped.append((line, f"category '{fields['category_name']}' not found and not created"))
            continue
        if payment_method is None:
            skipped.append((line, f"payment method '{fields['pm_name']}' not found and not created"))
            continue

        txn = Transaction.objects.create(
            tenant=tenant,
            type=fields['type'],
            date=fields['date'],
            amount=fields['amount'],
            category=category,
            payment_method=payment_method,
            description=fields['description'],
        )
        audit.log(
            actor=user, action='TRANSACTION_CREATE',
            target_type='Transaction', target_id=txn.id,
            detail=f"Bulk-imported via admin script for {user.email}: "
                    f"{txn.type} {txn.amount} on {txn.date} ({category.name})",
        )
        print(f"  [OK] Saved: {txn.type} {txn.amount} on {txn.date} — {category.name} / {payment_method.name} "
              f"— {txn.description or '(no description)'}")
        created += 1

    # ---- Phase 5: summary ----
    print("\n" + "=" * 76)
    print(f"Pasted lines: {len(raw_lines)}   Created: {created}   Skipped: {len(skipped)}")
    if skipped:
        print("Skipped lines:")
        for line, err in skipped:
            print(f"  - '{line}' -> {err}")
    assert created + len(skipped) == len(raw_lines), "Line count mismatch — please report this."
    print("=" * 76)


if __name__ == '__main__':
    main()
