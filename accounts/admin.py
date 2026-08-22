from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Tenant, AuditLog


class CustomUserAdmin(UserAdmin):
    model = CustomUser
    ordering = ('email',)
    list_display = ('email', 'full_name', 'role', 'is_active', 'date_joined')
    list_filter = ('role', 'is_active')
    search_fields = ('email', 'full_name')

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('full_name',)}),
        ('Role & Permissions', {'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'full_name', 'role', 'password1', 'password2'),
        }),
    )


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'actor', 'action', 'target_type', 'detail')
    list_filter = ('action',)
    search_fields = ('actor__email', 'detail')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Tenant)
