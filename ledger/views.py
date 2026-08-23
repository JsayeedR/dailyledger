import calendar as cal_module
from decimal import Decimal
from datetime import date as date_cls, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext as _
from django.utils import timezone
from django.db.models import Sum, Q, Count
from .models import Transaction, TransactionType, Budget, Category, PaymentMethod
from .forms import TransactionForm, BudgetForm
from accounts import audit


def about(request):
    from accounts.models import CustomUser, ApprovalStatus, Tenant

    total_users = CustomUser.objects.filter(approval_status=ApprovalStatus.APPROVED, is_active=True).count()
    total_transactions = Transaction.objects.count()
    total_categories = Category.objects.count()

    earliest_tenant = Tenant.objects.order_by('created_at').first()
    days_running = (timezone.localdate() - earliest_tenant.created_at.date()).days if earliest_tenant else 0

    return render(request, 'ledger/about.html', {
        'total_users': total_users,
        'total_transactions': total_transactions,
        'total_categories': total_categories,
        'days_running': days_running,
    })


@login_required
def dashboard(request):
    tenant = request.user.tenant
    today = timezone.localdate()

    def sum_for(start, end, ttype):
        return Transaction.objects.filter(
            tenant=tenant, type=ttype, date__gte=start, date__lte=end
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    today_income = sum_for(today, today, TransactionType.INCOME)
    today_expense = sum_for(today, today, TransactionType.EXPENSE)

    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    this_week_expense = sum_for(week_start, week_end, TransactionType.EXPENSE)

    last_week_start = week_start - timedelta(days=7)
    last_week_end = week_start - timedelta(days=1)
    last_week_expense = sum_for(last_week_start, last_week_end, TransactionType.EXPENSE)

    month_start = today.replace(day=1)
    month_income = sum_for(month_start, today, TransactionType.INCOME)
    month_expense = sum_for(month_start, today, TransactionType.EXPENSE)

    if today.month == 1:
        last_month, last_month_year = 12, today.year - 1
    else:
        last_month, last_month_year = today.month - 1, today.year
    last_month_days = cal_module.monthrange(last_month_year, last_month)[1]
    last_month_start = date_cls(last_month_year, last_month, 1)
    last_month_end = date_cls(last_month_year, last_month, last_month_days)
    last_month_expense = sum_for(last_month_start, last_month_end, TransactionType.EXPENSE)

    all_income = Transaction.objects.filter(tenant=tenant, type=TransactionType.INCOME).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    all_expense = Transaction.objects.filter(tenant=tenant, type=TransactionType.EXPENSE).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    total_balance = tenant.opening_balance + all_income - all_expense

    context = {
        'month_income': month_income,
        'month_expense': month_expense,
        'month_in_hand': month_income - month_expense,
        'today_income': today_income,
        'today_expense': today_expense,
        'this_week_expense': this_week_expense,
        'last_week_expense': last_week_expense,
        'last_month_expense': last_month_expense,
        'total_balance': total_balance,
        'recent_transactions': Transaction.objects.filter(tenant=tenant).select_related('category', 'payment_method')[:8],
        'currency': tenant.currency,
        'today_count': Transaction.objects.filter(tenant=tenant, date=today).count(),
    }
    return render(request, 'ledger/dashboard.html', context)


@login_required
def add_transaction(request):
    tenant = request.user.tenant
    if request.method == 'POST':
        form = TransactionForm(request.POST, request.FILES, tenant=tenant)
        if form.is_valid():
            txn = form.save(commit=False)
            txn.tenant = tenant
            txn.save()
            audit.log(actor=request.user, action='TRANSACTION_CREATE', target_type='Transaction', target_id=txn.id, request=request)
            messages.success(request, _('Transaction added successfully.'))
            return redirect('ledger:dashboard')
    else:
        form = TransactionForm(tenant=tenant, initial={'date': timezone.localdate()})
    return render(request, 'ledger/add_transaction.html', {'form': form, 'mode': 'add'})


@login_required
def edit_transaction(request, pk):
    tenant = request.user.tenant
    txn = get_object_or_404(Transaction, pk=pk, tenant=tenant)
    if request.method == 'POST':
        form = TransactionForm(request.POST, request.FILES, instance=txn, tenant=tenant)
        if form.is_valid():
            form.save()
            audit.log(actor=request.user, action='TRANSACTION_UPDATE', target_type='Transaction', target_id=txn.id, request=request)
            messages.success(request, _('Transaction updated successfully.'))
            return redirect('ledger:transaction_list')
    else:
        form = TransactionForm(instance=txn, tenant=tenant)
    return render(request, 'ledger/add_transaction.html', {'form': form, 'mode': 'edit', 'txn': txn})


@login_required
def delete_transaction(request, pk):
    tenant = request.user.tenant
    txn = get_object_or_404(Transaction, pk=pk, tenant=tenant)
    if request.method == 'POST':
        txn_id = txn.id
        txn.delete()
        audit.log(actor=request.user, action='TRANSACTION_DELETE', target_type='Transaction', target_id=txn_id, request=request)
        messages.success(request, _('Transaction deleted.'))
        return redirect('ledger:transaction_list')
    return render(request, 'ledger/confirm_delete.html', {'txn': txn})


@login_required
def transaction_list(request):
    tenant = request.user.tenant
    transactions = Transaction.objects.filter(tenant=tenant).select_related('category', 'payment_method')
    return render(request, 'ledger/transactions.html', {'transactions': transactions, 'currency': tenant.currency})


@login_required
def budget_list(request):
    tenant = request.user.tenant
    today = timezone.localdate()
    budgets = Budget.objects.filter(tenant=tenant, year=today.year, month=today.month).select_related('category')
    return render(request, 'ledger/budgets.html', {
        'budgets': budgets, 'currency': tenant.currency,
        'current_month': today.month, 'current_year': today.year,
    })


@login_required
def add_budget(request):
    tenant = request.user.tenant
    today = timezone.localdate()
    if request.method == 'POST':
        form = BudgetForm(request.POST, tenant=tenant)
        if form.is_valid():
            budget = form.save(commit=False)
            budget.tenant = tenant
            budget.save()
            audit.log(actor=request.user, action='BUDGET_CREATE', target_type='Budget', target_id=budget.id, request=request)
            messages.success(request, _('Budget saved.'))
            return redirect('ledger:budget_list')
    else:
        form = BudgetForm(tenant=tenant, initial={'month': today.month, 'year': today.year})
    return render(request, 'ledger/add_budget.html', {'form': form})


@login_required
def delete_budget(request, pk):
    tenant = request.user.tenant
    budget = get_object_or_404(Budget, pk=pk, tenant=tenant)
    if request.method == 'POST':
        budget_id = budget.id
        budget.delete()
        audit.log(actor=request.user, action='BUDGET_DELETE', target_type='Budget', target_id=budget_id, request=request)
        messages.success(request, _('Budget removed.'))
        return redirect('ledger:budget_list')
    return render(request, 'ledger/confirm_delete_budget.html', {'budget': budget})


def _month_nav(month, year):
    prev_month = month - 1 or 12
    prev_year = year - 1 if month == 1 else year
    next_month = month + 1 if month < 12 else 1
    next_year = year + 1 if month == 12 else year
    return prev_month, prev_year, next_month, next_year


@login_required
def calendar_view(request):
    tenant = request.user.tenant
    today = timezone.localdate()
    month = int(request.GET.get('month', today.month))
    year = int(request.GET.get('year', today.year))

    first_weekday, days_in_month = cal_module.monthrange(year, month)

    txns = Transaction.objects.filter(tenant=tenant, date__year=year, date__month=month)
    day_data = {}
    for t in txns:
        entry = day_data.setdefault(t.date.day, {'expense': Decimal('0'), 'income': Decimal('0')})
        if t.type == TransactionType.EXPENSE:
            entry['expense'] += t.amount
        else:
            entry['income'] += t.amount

    weeks, week = [], [None] * first_weekday
    for day in range(1, days_in_month + 1):
        week.append({'day': day, **day_data.get(day, {'expense': Decimal('0'), 'income': Decimal('0')})})
        if len(week) == 7:
            weeks.append(week)
            week = []
    if week:
        week += [None] * (7 - len(week))
        weeks.append(week)

    prev_month, prev_year, next_month, next_year = _month_nav(month, year)

    return render(request, 'ledger/calendar.html', {
        'weeks': weeks, 'month': month, 'year': year, 'currency': tenant.currency,
        'month_name': cal_module.month_name[month],
        'prev_month': prev_month, 'prev_year': prev_year,
        'next_month': next_month, 'next_year': next_year,
    })


@login_required
def day_detail(request, year, month, day):
    tenant = request.user.tenant
    target_date = date_cls(year, month, day)
    transactions = Transaction.objects.filter(tenant=tenant, date=target_date).select_related('category', 'payment_method')
    income = transactions.filter(type=TransactionType.INCOME).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    expense = transactions.filter(type=TransactionType.EXPENSE).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    return render(request, 'ledger/day_detail.html', {
        'transactions': transactions, 'target_date': target_date,
        'income': income, 'expense': expense, 'net': income - expense,
        'currency': tenant.currency,
    })


@login_required
def spreadsheet_view(request):
    tenant = request.user.tenant
    today = timezone.localdate()
    month = int(request.GET.get('month', today.month))
    year = int(request.GET.get('year', today.year))
    _, days_in_month = cal_module.monthrange(year, month)
    day_range = list(range(1, days_in_month + 1))

    # Include active categories (even if unused this month) PLUS any deactivated
    # category that actually has spending this month — deactivating must never
    # hide historical data from this view.
    categories = Category.objects.filter(tenant=tenant, type=TransactionType.EXPENSE).filter(
        Q(is_active=True) | Q(transactions__date__year=year, transactions__date__month=month)
    ).distinct().order_by('sort_order', 'name')
    expense_txns = Transaction.objects.filter(tenant=tenant, type=TransactionType.EXPENSE, date__year=year, date__month=month)

    matrix = {c.id: {d: Decimal('0') for d in day_range} for c in categories}
    daily_totals = {d: Decimal('0') for d in day_range}
    for t in expense_txns:
        daily_totals[t.date.day] += t.amount
        if t.category_id in matrix:
            matrix[t.category_id][t.date.day] += t.amount

    category_totals = {c.id: sum(matrix[c.id].values()) for c in categories}
    monthly_total = sum(daily_totals.values())

    income_txns = Transaction.objects.filter(tenant=tenant, type=TransactionType.INCOME, date__year=year, date__month=month)
    daily_income = {d: Decimal('0') for d in day_range}
    for t in income_txns:
        daily_income[t.date.day] += t.amount
    monthly_income = sum(daily_income.values())

    rows = [{'category': c, 'amounts': matrix[c.id], 'total': category_totals[c.id]} for c in categories]

    prev_month, prev_year, next_month, next_year = _month_nav(month, year)

    return render(request, 'ledger/spreadsheet.html', {
        'rows': rows, 'day_range': day_range, 'daily_totals': daily_totals,
        'daily_income': daily_income, 'monthly_total': monthly_total, 'monthly_income': monthly_income,
        'month': month, 'year': year, 'currency': tenant.currency,
        'month_name': cal_module.month_name[month],
        'prev_month': prev_month, 'prev_year': prev_year,
        'next_month': next_month, 'next_year': next_year,
    })


def _resolve_range(request, today):
    """Shared period-filter logic used by both Reports and Detail Reports."""
    range_type = request.GET.get('range', 'month')

    if range_type == 'week':
        start_date, end_date, label = today - timedelta(days=6), today, 'Last 7 Days'
    elif range_type == '15days':
        start_date, end_date, label = today - timedelta(days=14), today, 'Last 15 Days'
    elif range_type == 'year':
        start_date, end_date, label = today.replace(month=1, day=1), today, str(today.year)
    elif range_type == 'custom':
        start_str, end_str = request.GET.get('start'), request.GET.get('end')
        try:
            start_date = date_cls.fromisoformat(start_str) if start_str else today.replace(day=1)
            end_date = date_cls.fromisoformat(end_str) if end_str else today
        except ValueError:
            start_date, end_date = today.replace(day=1), today
        label = f'{start_date} to {end_date}'
    else:
        range_type = 'month'
        start_date, end_date, label = today.replace(day=1), today, today.strftime('%B %Y')

    return range_type, start_date, end_date, label


@login_required
def reports_view(request):
    tenant = request.user.tenant
    today = timezone.localdate()
    range_type, start_date, end_date, label = _resolve_range(request, today)

    txns = Transaction.objects.filter(tenant=tenant, date__gte=start_date, date__lte=end_date)
    total_income = txns.filter(type=TransactionType.INCOME).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    total_expense = txns.filter(type=TransactionType.EXPENSE).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    savings = total_income - total_expense

    expense_by_category = (
        txns.filter(type=TransactionType.EXPENSE, category__isnull=False)
        .values('category__name')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )
    category_labels = [row['category__name'] for row in expense_by_category]
    category_values = [float(row['total']) for row in expense_by_category]

    return render(request, 'ledger/reports.html', {
        'range_type': range_type, 'start_date': start_date, 'end_date': end_date, 'label': label,
        'total_income': total_income, 'total_expense': total_expense, 'savings': savings,
        'total_income_float': float(total_income), 'total_expense_float': float(total_expense), 'savings_float': float(savings),
        'txn_count': txns.count(),
        'category_labels': category_labels, 'category_values': category_values,
        'currency': tenant.currency,
    })


@login_required
def detail_reports_view(request):
    tenant = request.user.tenant
    today = timezone.localdate()
    range_type, start_date, end_date, label = _resolve_range(request, today)

    txns = Transaction.objects.filter(tenant=tenant, date__gte=start_date, date__lte=end_date)
    total_income = txns.filter(type=TransactionType.INCOME).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    total_expense = txns.filter(type=TransactionType.EXPENSE).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    expense_categories = list(
        txns.filter(type=TransactionType.EXPENSE, category__isnull=False)
        .values('category__name')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('-total')
    )
    income_sources = list(
        txns.filter(type=TransactionType.INCOME, category__isnull=False)
        .values('category__name')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('-total')
    )

    for row in expense_categories:
        row['pct'] = round((row['total'] / total_expense) * 100, 1) if total_expense else 0
    for row in income_sources:
        row['pct'] = round((row['total'] / total_income) * 100, 1) if total_income else 0

    payment_qs = (
        txns.filter(payment_method__isnull=False)
        .values('payment_method__name', 'type')
        .annotate(total=Sum('amount'), count=Count('id'))
    )
    payment_map = {}
    for row in payment_qs:
        name = row['payment_method__name']
        entry = payment_map.setdefault(name, {'income': Decimal('0'), 'expense': Decimal('0'), 'count': 0})
        if row['type'] == TransactionType.EXPENSE:
            entry['expense'] = row['total']
        else:
            entry['income'] = row['total']
        entry['count'] += row['count']

    payment_names = sorted(payment_map.keys())
    payment_breakdown = [{'name': n, **payment_map[n]} for n in payment_names]

    top_category = expense_categories[0]['category__name'] if expense_categories else None
    top_payment = max(payment_map, key=lambda n: payment_map[n]['income'] + payment_map[n]['expense']) if payment_map else None

    return render(request, 'ledger/detail_reports.html', {
        'range_type': range_type, 'start_date': start_date, 'end_date': end_date, 'label': label,
        'total_income': total_income, 'total_expense': total_expense,
        'expense_categories': expense_categories,
        'income_sources': income_sources,
        'payment_breakdown': payment_breakdown,
        'top_category': top_category,
        'top_payment': top_payment,
        'expense_labels': [r['category__name'] for r in expense_categories],
        'expense_values': [float(r['total']) for r in expense_categories],
        'income_labels': [r['category__name'] for r in income_sources],
        'income_values': [float(r['total']) for r in income_sources],
        'payment_labels': payment_names,
        'payment_income_values': [float(payment_map[n]['income']) for n in payment_names],
        'payment_expense_values': [float(payment_map[n]['expense']) for n in payment_names],
        'currency': tenant.currency,
    })


@login_required
def manage_settings(request):
    from accounts.signals import DEFAULT_EXPENSE_CATEGORIES, DEFAULT_INCOME_CATEGORIES, DEFAULT_PAYMENT_METHODS

    tenant = request.user.tenant
    expense_categories = Category.objects.filter(tenant=tenant, type=TransactionType.EXPENSE).order_by('sort_order', 'name')
    income_categories = Category.objects.filter(tenant=tenant, type=TransactionType.INCOME).order_by('sort_order', 'name')
    payment_methods = PaymentMethod.objects.filter(tenant=tenant).order_by('sort_order', 'name')

    existing_expense_names = set(expense_categories.values_list('name', flat=True))
    existing_income_names = set(income_categories.values_list('name', flat=True))
    existing_payment_names = set(payment_methods.values_list('name', flat=True))

    return render(request, 'ledger/manage_settings.html', {
        'expense_categories': expense_categories,
        'income_categories': income_categories,
        'payment_methods': payment_methods,
        'suggested_expense': [n for n in DEFAULT_EXPENSE_CATEGORIES if n not in existing_expense_names],
        'suggested_income': [n for n in DEFAULT_INCOME_CATEGORIES if n not in existing_income_names],
        'suggested_payment': [n for n in DEFAULT_PAYMENT_METHODS if n not in existing_payment_names],
    })


@login_required
def add_category(request):
    tenant = request.user.tenant
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        cat_type = request.POST.get('type')
        if name and cat_type in (TransactionType.EXPENSE, TransactionType.INCOME):
            Category.objects.get_or_create(tenant=tenant, type=cat_type, name=name, parent=None)
            messages.success(request, _('Category "%(name)s" added.') % {'name': name})
        else:
            messages.error(request, _('Please provide a valid name.'))
    return redirect('ledger:manage_settings')


@login_required
def toggle_category(request, pk):
    tenant = request.user.tenant
    cat = get_object_or_404(Category, pk=pk, tenant=tenant)
    if request.method == 'POST':
        cat.is_active = not cat.is_active
        cat.save()
    return redirect('ledger:manage_settings')


@login_required
def add_payment_method(request):
    tenant = request.user.tenant
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            PaymentMethod.objects.get_or_create(tenant=tenant, name=name)
            messages.success(request, _('Payment method "%(name)s" added.') % {'name': name})
        else:
            messages.error(request, _('Please provide a name.'))
    return redirect('ledger:manage_settings')


@login_required
def toggle_payment_method(request, pk):
    tenant = request.user.tenant
    pm = get_object_or_404(PaymentMethod, pk=pk, tenant=tenant)
    if request.method == 'POST':
        pm.is_active = not pm.is_active
        pm.save()
    return redirect('ledger:manage_settings')
