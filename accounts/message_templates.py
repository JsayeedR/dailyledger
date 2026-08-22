"""
Formats for the scheduled summary messages sent by the `send_summaries`
management command. Keeping these in one place makes it easy to tweak
wording without touching the sending/scheduling logic.
"""

PERIOD_LABELS = {
    'DAILY': "Daily Summary",
    'WEEKLY': "Weekly Summary",
    'MONTHLY': "Monthly Summary",
    'YEARLY': "Yearly Summary",
}


def _fmt(amount):
    return f"{amount:,.2f}"


def build_email(user, tenant, frequency, period_label, income_total, expense_total, top_categories):
    """Returns (subject, body) for the summary email."""
    net = income_total - expense_total
    subject = f"DailyLedger {PERIOD_LABELS.get(frequency, 'Summary')} — {period_label}"

    lines = [
        f"Hi {user.display_name},",
        "",
        f"Here's your {PERIOD_LABELS.get(frequency, 'summary').lower()} for {period_label} ({tenant.name}):",
        "",
        f"  Income:   {tenant.currency} {_fmt(income_total)}",
        f"  Expense:  {tenant.currency} {_fmt(expense_total)}",
        f"  Net:      {tenant.currency} {_fmt(net)}",
        "",
    ]

    if top_categories:
        lines.append("Top expense categories:")
        for name, amount in top_categories:
            lines.append(f"  - {name}: {tenant.currency} {_fmt(amount)}")
        lines.append("")

    lines.append("Log in to DailyLedger to see the full breakdown.")
    lines.append("")
    lines.append("— DailyLedger")

    return subject, "\n".join(lines)


def build_telegram(user, tenant, frequency, period_label, income_total, expense_total, top_categories):
    """Returns plain text for the summary Telegram message."""
    net = income_total - expense_total
    label = PERIOD_LABELS.get(frequency, 'Summary')

    lines = [
        f"📒 DailyLedger {label} — {period_label}",
        "",
        f"Income:  {tenant.currency} {_fmt(income_total)}",
        f"Expense: {tenant.currency} {_fmt(expense_total)}",
        f"Net:     {tenant.currency} {_fmt(net)}",
    ]

    if top_categories:
        lines.append("")
        lines.append("Top expense categories:")
        for name, amount in top_categories:
            lines.append(f"  • {name}: {tenant.currency} {_fmt(amount)}")

    return "\n".join(lines)
