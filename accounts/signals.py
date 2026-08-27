from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import CustomUser, Tenant

DEFAULT_EXPENSE_CATEGORIES = [
    'Daily Cost', 'Notable Purchase', 'Transport', 'Food & Restaurant',
    'House & Utility', 'Medical', 'Family', 'Shopping', 'Education',
    'Bills', 'Miscellaneous',
]
DEFAULT_INCOME_CATEGORIES = [
    'Salary', 'Allowance', 'Business Income', 'Refund', 'Bonus', 'Other Income',
]
DEFAULT_PAYMENT_METHODS = [
    'Cash', 'Debit Card', 'Bank Account', 'Cheque', 'Credit Card', 'MFS', 'Others',
]
DEFAULT_SAVINGS_CATEGORIES = [
    'DPS', 'FDR', 'Bank', 'Loan to Others', 'Land', 'Sanchay Patro',
]


@receiver(post_save, sender=CustomUser)
def create_tenant_for_new_user(sender, instance, created, **kwargs):
    """Every user gets an isolated workspace. Categories/payment methods are
    chosen by the user in the setup wizard, not auto-seeded here."""
    if created:
        Tenant.objects.create(
            owner=instance,
            name=f"{instance.full_name or instance.email}'s Workspace",
        )
