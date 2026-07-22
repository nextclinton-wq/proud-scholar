from __future__ import annotations

import uuid
from typing import Optional

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.UUIDField(db_index=True, help_text="Tenant identifier")
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="%(class)s_created",
        on_delete=models.SET_NULL,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="%(class)s_updated",
        on_delete=models.SET_NULL,
    )
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def soft_delete(self, user: Optional[models.Model] = None) -> None:
        self.is_deleted = True
        self.is_active = False
        self.deleted_at = timezone.now()
        self.updated_by = user
        self.save(update_fields=["is_deleted", "is_active", "deleted_at", "updated_by", "updated_at"])


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.UUIDField(db_index=True, null=True, blank=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    last_login_device = models.CharField(max_length=255, blank=True)
    is_locked = models.BooleanField(default=False)
    lockout_until = models.DateTimeField(null=True, blank=True)
    password_last_changed_at = models.DateTimeField(null=True, blank=True)
    password_history = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "app_user"
        ordering = ["-date_joined"]

    def __str__(self) -> str:
        return self.get_full_name() or self.username

    def soft_delete(self) -> None:
        self.is_deleted = True
        self.is_active = False
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "is_active", "deleted_at", "updated_at"])


class Permission(BaseModel):
    module = models.CharField(max_length=100)
    action = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "app_permission"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "module", "action"], name="unique_permission_per_tenant_module_action")
        ]
        ordering = ["module", "action"]

    def __str__(self) -> str:
        return f"{self.module}.{self.action}"

    @property
    def code(self) -> str:
        return f"{self.module}.{self.action}"


class Role(BaseModel):
    name = models.CharField(max_length=100)
    code = models.SlugField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    is_system = models.BooleanField(default=False)
    permissions = models.ManyToManyField(Permission, through="RolePermission", related_name="roles")

    class Meta:
        db_table = "app_role"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_role_name_per_tenant")
        ]
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        if self.is_system and self.name != "SYSTEM_ADMIN":
            raise ValidationError({"name": "System roles must be named SYSTEM_ADMIN."})
        if self.pk and self.is_system and self.name != "SYSTEM_ADMIN":
            raise ValidationError({"name": "SYSTEM_ADMIN cannot be renamed."})

    def save(self, *args, **kwargs) -> None:
        if not self.code:
            self.code = self.name.lower().replace(" ", "_")
        super().save(*args, **kwargs)


class RolePermission(BaseModel):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="role_permissions")

    class Meta:
        db_table = "app_role_permission"
        constraints = [
            models.UniqueConstraint(fields=["role", "permission"], name="unique_role_permission_assignment")
        ]
        ordering = ["role__name", "permission__module", "permission__action"]

    def __str__(self) -> str:
        return f"{self.role.name} -> {self.permission.code}"


class UserRole(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="user_roles")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="user_roles")

    class Meta:
        db_table = "app_user_role"
        constraints = [
            models.UniqueConstraint(fields=["user", "role"], name="unique_user_role_assignment")
        ]
        ordering = ["user__username", "role__name"]

    def __str__(self) -> str:
        return f"{self.user.username} -> {self.role.name}"


class RefreshToken(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="refresh_tokens")
    jti = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    token_hash = models.CharField(max_length=255, db_index=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    replaced_by = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="replaced_tokens")
    is_blacklisted = models.BooleanField(default=False)
    device_id = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        db_table = "app_refresh_token"
        ordering = ["-created_at"]

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def revoke(self) -> None:
        self.revoked_at = timezone.now()
        self.is_blacklisted = True
        self.save(update_fields=["revoked_at", "is_blacklisted", "updated_at"])


class LoginHistory(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="login_histories")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    device = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=[("success", "Success"), ("failed", "Failed")], default="success")
    failure_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "app_login_history"
        ordering = ["-created_at"]


class FailedLoginAttempt(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="failed_login_attempts")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    attempt_count = models.PositiveIntegerField(default=1)
    locked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "app_failed_login_attempt"
        ordering = ["-created_at"]

    def lock(self, duration_minutes: int = 15) -> None:
        self.locked_until = timezone.now() + timezone.timedelta(minutes=duration_minutes)
        self.save(update_fields=["locked_until", "updated_at"])


class MFAMethod(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mfa_methods")
    method = models.CharField(max_length=20, choices=[("totp", "TOTP")], default="totp")
    secret = models.CharField(max_length=255)
    is_enabled = models.BooleanField(default=False)
    recovery_codes = models.JSONField(default=list, blank=True)
    last_verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "app_mfa_method"
        ordering = ["-created_at"]


class AuditLog(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs")
    action = models.CharField(max_length=100)
    resource_type = models.CharField(max_length=100, blank=True)
    resource_id = models.CharField(max_length=255, blank=True)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        db_table = "app_audit_log"
        ordering = ["-created_at"]
