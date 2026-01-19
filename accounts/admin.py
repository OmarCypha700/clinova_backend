from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, School


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "subdomain", "is_active", "created_at", "user_count")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "subdomain")
    ordering = ("name",)
    
    def user_count(self, obj):
        return obj.users.count()
    user_count.short_description = "Users"


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "school", "role", "is_staff")
    list_filter = ("school", "role", "is_staff", "is_superuser", "is_active")
    search_fields = ("username", "email", "first_name", "last_name", "school__name")
    ordering = ("school", "username")

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email")}),
        ("School", {"fields": ("school",)}),
        ("Permissions", {"fields": ("role", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'school', 'password1', 'password2', 'role'),
        }),
    )
    
    def get_queryset(self, request):
        """Superusers see all users, school admins see only their school"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, 'school') and request.user.school:
            return qs.filter(school=request.user.school)
        return qs.none()