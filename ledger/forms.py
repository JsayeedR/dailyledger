from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Transaction, Category, PaymentMethod, Budget, TransactionType, SavingsTransaction, SavingsCategory, Loan, LoanRepayment


class CategorySelect(forms.Select):
    """Adds a data-type attribute to each <option> so JS can filter by Expense/Income client-side."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        raw_value = getattr(value, 'value', value)
        if raw_value:
            try:
                cat = Category.objects.only('type').get(pk=raw_value)
                option['attrs']['data-type'] = cat.type
            except Exception:
                pass
        return option


class CategoryChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.name


class TransactionForm(forms.ModelForm):
    category = CategoryChoiceField(
        queryset=Category.objects.none(),
        required=False,
        widget=CategorySelect(attrs={'class': 'border rounded px-3 py-2 w-full'}),
    )

    class Meta:
        model = Transaction
        fields = ['type', 'date', 'amount', 'category', 'payment_method', 'description']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'border rounded px-3 py-2 w-full'}),
            'type': forms.Select(attrs={'class': 'border rounded px-3 py-2 w-full'}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'class': 'border rounded px-3 py-2 w-full'}),
            'payment_method': forms.Select(attrs={'class': 'border rounded px-3 py-2 w-full'}),
            'description': forms.TextInput(attrs={'class': 'border rounded px-3 py-2 w-full', 'placeholder': _('Optional note (e.g. what this was for)')}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['category'].queryset = Category.objects.filter(tenant=tenant, is_active=True)
            self.fields['payment_method'].queryset = PaymentMethod.objects.filter(tenant=tenant, is_active=True)


class BudgetForm(forms.ModelForm):
    class Meta:
        model = Budget
        fields = ['category', 'month', 'year', 'limit_amount']
        widgets = {
            'category': forms.Select(attrs={'class': 'border rounded px-3 py-2 w-full'}),
            'month': forms.NumberInput(attrs={'class': 'border rounded px-3 py-2 w-full', 'min': 1, 'max': 12}),
            'year': forms.NumberInput(attrs={'class': 'border rounded px-3 py-2 w-full'}),
            'limit_amount': forms.NumberInput(attrs={'step': '0.01', 'class': 'border rounded px-3 py-2 w-full'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['category'].queryset = Category.objects.filter(tenant=tenant, type=TransactionType.EXPENSE, is_active=True)


class SavingsTransactionForm(forms.ModelForm):
    class Meta:
        model = SavingsTransaction
        fields = ['entry_type', 'category', 'date', 'amount', 'payment_method', 'note']
        widgets = {
            'entry_type': forms.Select(attrs={'class': 'border rounded px-3 py-2 w-full'}),
            'category': forms.Select(attrs={'class': 'border rounded px-3 py-2 w-full'}),
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'border rounded px-3 py-2 w-full'}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'class': 'border rounded px-3 py-2 w-full'}),
            'payment_method': forms.Select(attrs={'class': 'border rounded px-3 py-2 w-full'}),
            'note': forms.TextInput(attrs={'class': 'border rounded px-3 py-2 w-full', 'placeholder': _('Optional note')}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        if tenant:
            self.fields['category'].queryset = SavingsCategory.objects.filter(tenant=tenant, is_active=True)
            self.fields['payment_method'].queryset = PaymentMethod.objects.filter(tenant=tenant, is_active=True)

    def clean(self):
        cleaned = super().clean()
        entry_type = cleaned.get('entry_type')
        category = cleaned.get('category')
        amount = cleaned.get('amount')
        if entry_type == 'WITHDRAWAL' and category and amount:
            current_balance = category.balance()
            # If editing an existing entry, add back its own current amount
            # before checking, so re-saving the same withdrawal doesn't
            # falsely trip the insufficient-balance check.
            if self.instance and self.instance.pk and self.instance.entry_type == 'WITHDRAWAL':
                current_balance += self.instance.amount
            if amount > current_balance:
                raise forms.ValidationError(
                    _('Cannot withdraw %(amount)s — "%(cat)s" only has %(balance)s saved.') % {
                        'amount': amount, 'cat': category.name, 'balance': current_balance,
                    }
                )
        return cleaned


class LoanForm(forms.ModelForm):
    class Meta:
        model = Loan
        fields = ['source', 'amount', 'date', 'payment_method', 'note']
        widgets = {
            'source': forms.TextInput(attrs={'class': 'border rounded px-3 py-2 w-full', 'placeholder': _("e.g. Dutch-Bangla Bank, or a person's name")}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'class': 'border rounded px-3 py-2 w-full'}),
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'border rounded px-3 py-2 w-full'}),
            'payment_method': forms.Select(attrs={'class': 'border rounded px-3 py-2 w-full'}),
            'note': forms.TextInput(attrs={'class': 'border rounded px-3 py-2 w-full', 'placeholder': _('Optional note')}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['payment_method'].queryset = PaymentMethod.objects.filter(tenant=tenant, is_active=True)


class LoanRepaymentForm(forms.ModelForm):
    class Meta:
        model = LoanRepayment
        fields = ['loan', 'amount', 'date', 'payment_method', 'note']
        widgets = {
            'loan': forms.Select(attrs={'class': 'border rounded px-3 py-2 w-full'}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'class': 'border rounded px-3 py-2 w-full'}),
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'border rounded px-3 py-2 w-full'}),
            'payment_method': forms.Select(attrs={'class': 'border rounded px-3 py-2 w-full'}),
            'note': forms.TextInput(attrs={'class': 'border rounded px-3 py-2 w-full', 'placeholder': _('Optional note')}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        if tenant:
            # Only loans still carrying a balance can be repaid — once a
            # loan hits 0 outstanding it drops out of this dropdown.
            outstanding_ids = [loan.pk for loan in Loan.objects.filter(tenant=tenant) if loan.outstanding() > 0]
            if self.instance and self.instance.pk:
                # Editing an existing repayment: keep its own loan selectable
                # even though the queryset above was built before this
                # instance's amount is "added back" — the clean() balance
                # check (not this queryset) is what actually enforces the
                # not-more-than-outstanding rule for edits.
                outstanding_ids = list(set(outstanding_ids) | {self.instance.loan_id})
            self.fields['loan'].queryset = Loan.objects.filter(tenant=tenant, pk__in=outstanding_ids)
            self.fields['payment_method'].queryset = PaymentMethod.objects.filter(tenant=tenant, is_active=True)

    def clean(self):
        cleaned = super().clean()
        loan = cleaned.get('loan')
        amount = cleaned.get('amount')
        if loan and amount:
            outstanding = loan.outstanding()
            if self.instance and self.instance.pk and self.instance.loan_id == loan.id:
                outstanding += self.instance.amount
            if amount > outstanding:
                raise forms.ValidationError(
                    _('Cannot pay back %(amount)s — only %(outstanding)s is still outstanding on the loan from %(source)s.') % {
                        'amount': amount, 'outstanding': outstanding, 'source': loan.source,
                    }
                )
        return cleaned
