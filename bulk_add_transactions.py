#!/usr/bin/env python3
"""
DailyLedger — Bulk Transaction Import for a Specific User
============================================================================
Run this ON THE SERVER, inside the project directory, with the venv active:

    scp -P 3048 bulk_add_transactions.py app-admin@103.16.152.238:/home/app-admin/dailyledger/
    ssh -p 3048 app-admin@103.16.152.238
    cd ~/dailyledger && source venv/bin/activate   # or .venv/bin/activate
    python bulk_add_transactions.py

What it does:
  1. Asks for the target user's email address and confirms a match.
  2. Shows that user's existing Categories & Payment Methods (so you type
     names that will actually match).
  3. Then repeatedly asks for one transaction per line in this format:

        Type-DD-Mon-YYYY-Amount-Category-PaymentMethod-Description

     Example:
        Expense-05-Nov-2025-609.00-House & Utility-Credit Card-Desco Prepaid

     Type must be "Expense" or "Income" (case-insensitive).
     Date must be DD-Mon-YYYY (e.g. 05-Nov-2025).
     Category and Payment Method must match existing names for that user's
     tenant (shown at the start) — if not found, you'll be asked whether to
     create it on the spot.
     Type "done" on its own line to finish, or "cancel" to abort with
     nothing saved from the current line.
  4. Prints a running confirmation for every row saved, and a final summary
     (created / skipped, with reasons) so nothing silently fails.

Nothing is written until each individual row is validated — a bad row is
reported and skipped; it does not stop the rest of the batch.
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


def get_or_create_category(tenant, name, ttype):
    cat = Category.objects.filter(tenant=tenant, type=ttype, name__iexact=name).first()
    if cat:
        return cat, False
    ans = input(f"    Category '{name}' ({ttype.label}) doesn't exist yet. Create it? [y/N]: ").strip().lower()
    if ans == 'y':
        cat = Category.objects.create(tenant=tenant, type=ttype, name=name)
        return cat, True
    return None, False


def get_or_create_payment_method(tenant, name):
    pm = PaymentMethod.objects.filter(tenant=tenant, name__iexact=name).first()
    if pm:
        return pm, False
    ans = input(f"    Payment method '{name}' doesn't exist yet. Create it? [y/N]: ").strip().lower()
    if ans == 'y':
        pm = PaymentMethod.objects.create(tenant=tenant, name=name)
        return pm, True
    return None, False


def parse_line(line, tenant):
    """Returns (transaction_kwargs, error_message). Exactly one is None."""
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

    category, _created_cat = get_or_create_category(tenant, category_name, ttype)
    if category is None:
        return None, f"category '{category_name}' not found and not created"

    payment_method, _created_pm = get_or_create_payment_method(tenant, pm_name)
    if payment_method is None:
        return None, f"payment method '{pm_name}' not found and not created"

    return {
        'tenant': tenant,
        'type': ttype,
        'date': date_val,
        'amount': amount_val,
        'category': category,
        'payment_method': payment_method,
        'description': description,
    }, None


def main():
    print("=" * 76)
    print("DailyLedger — Bulk Transaction Import")
    print("=" * 76)
    user = find_user()
    tenant = user.tenant
    show_reference_lists(tenant)

    print("Enter one transaction per line, format:")
    print("  Type-DD-Mon-YYYY-Amount-Category-PaymentMethod-Description")
    print("Example:")
    print("  Expense-05-Nov-2025-609.00-House & Utility-Credit Card-Desco Prepaid")
    print("Type 'done' when finished, 'cancel' to abort without saving remaining input.\n")

    created, skipped = 0, []
    while True:
        line = input("> ").strip()
        if not line:
            continue
        if line.lower() == 'done':
            break
        if line.lower() == 'cancel':
            print("Cancelled — stopping without processing further lines.")
            break

        kwargs, err = parse_line(line, tenant)
        if err:
            print(f"  [SKIPPED] {err}")
            skipped.append((line, err))
            continue

        txn = Transaction.objects.create(**kwargs)
        audit.log(
            actor=user, action='TRANSACTION_CREATE',
            target_type='Transaction', target_id=txn.id,
            detail=f"Bulk-imported via admin script for {user.email}: "
                    f"{txn.type} {txn.amount} on {txn.date} ({txn.category.name if txn.category else '-'})",
        )
        print(f"  [OK] Saved: {txn.type} {txn.amount} on {txn.date} — {txn.category.name if txn.category else '-'} "
              f"/ {txn.payment_method.name if txn.payment_method else '-'} — {txn.description or '(no description)'}")
        created += 1

    print("\n" + "=" * 76)
    print(f"Done. Created: {created}   Skipped: {len(skipped)}")
    if skipped:
        print("Skipped lines:")
        for line, err in skipped:
            print(f"  - '{line}' -> {err}")
    print("=" * 76)


if __name__ == '__main__':
    main()
