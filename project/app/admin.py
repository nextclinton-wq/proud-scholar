from django.contrib import admin

from .models import (
    AuditLog,
    FailedLoginAttempt,
    LoginHistory,
    MFAMethod,
    Permission,
    RefreshToken,
    Role,
    RolePermission,
    User,
    UserRole,
)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("username", "email", "tenant", "is_active", "is_locked", "is_deleted")
    search_fields = ("username", "email", "tenant")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "is_system", "is_active", "is_deleted")
    search_fields = ("name", "tenant")


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("code", "module", "action", "tenant", "is_active")
    search_fields = ("module", "action", "tenant")


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ("role", "permission", "tenant")


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "tenant")


@admin.register(RefreshToken)
class RefreshTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "jti", "is_blacklisted", "expires_at", "revoked_at")


@admin.register(LoginHistory)
class LoginHistoryAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "device", "ip_address", "created_at")


@admin.register(FailedLoginAttempt)
class FailedLoginAttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "attempt_count", "locked_until", "created_at")


@admin.register(MFAMethod)
class MFAMethodAdmin(admin.ModelAdmin):
    list_display = ("user", "method", "is_enabled", "last_verified_at")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("user", "action", "resource_type", "created_at")
