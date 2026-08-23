from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Transaction, Category, PaymentMethod, Budget, TransactionType


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
