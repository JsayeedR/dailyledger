# Intentionally NOT registering Transaction, Category, PaymentMethod, or
# Budget here. Financial data must only ever be reachable through this app's
# own tenant-scoped views (request.user.tenant) — never through the Django
# admin, which would otherwise let any is_staff/is_superuser account browse
# every tenant's transactions. This file is deliberately left empty.
