import uuid
from django.db import models
from accounts.models import Tenant


class TransactionType(models.TextChoices):
    EXPENSE = 'EXPENSE', 'Expense'
    INCOME = 'INCOME', 'Income'


class Category(models.Model):
    """
    Expense or income category, scoped to one Tenant. Users can create,
    rename, disable, and reorder their own — never shared across tenants.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='categories')
    type = models.CharField(max_length=10, choices=TransactionType.choices)
    name = models.CharField(max_length=100)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='sub_categories')
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_system_default = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'name']
        unique_together = ('tenant', 'type', 'name', 'parent')

    def __str__(self):
        return f"{self.name} ({self.type})"


class PaymentMethod(models.Model):
    """Configurable payment method (Cash, bKash, Card, etc.), per tenant."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='payment_methods')
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_system_default = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'name']
        unique_together = ('tenant', 'name')

    def __str__(self):
        return self.name


class Transaction(models.Model):
    """
    A single income or expense entry, always scoped to a Tenant.
    This is the core financial record of the entire application.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='transactions')

    type = models.CharField(max_length=10, choices=TransactionType.choices)
    date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name='transactions')
    # Free-text source label for INCOME rows (Salary, Bonus, etc.)
    source = models.CharField(max_length=150, blank=True)

    payment_method = models.ForeignKey(PaymentMethod, null=True, blank=True, on_delete=models.SET_NULL, related_name='transactions')
    description = models.CharField(max_length=500, blank=True)
    attachment = models.FileField(upload_to='receipts/%Y/%m/', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['tenant', 'date']),
            models.Index(fields=['tenant', 'type', 'date']),
        ]

    def __str__(self):
        return f"{self.type} — {self.amount} on {self.date} ({self.tenant.owner.email})"


class Budget(models.Model):
    """Monthly spending limit per category, scoped to a Tenant."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='budgets')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='budgets')
    month = models.PositiveSmallIntegerField()
    year = models.PositiveIntegerField()
    limit_amount = models.DecimalField(max_digits=14, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('tenant', 'category', 'month', 'year')
        ordering = ['-year', '-month']

    def __str__(self):
        return f"{self.category.name} budget {self.month}/{self.year} — {self.tenant.owner.email}"

    def spent(self):
        from django.db.models import Sum
        total = Transaction.objects.filter(
            tenant=self.tenant, category=self.category, type=TransactionType.EXPENSE,
            date__year=self.year, date__month=self.month,
        ).aggregate(total=Sum('amount'))['total']
        return total or 0

    def remaining(self):
        return self.limit_amount - self.spent()

    def percent_used(self):
        if self.limit_amount == 0:
            return 0
        return round((self.spent() / self.limit_amount) * 100, 1)
