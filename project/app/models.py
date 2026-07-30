from __future__ import annotations

import uuid
from typing import Optional

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from .current_request import get_current_user


class TenantAwareManager(models.Manager):
    def for_tenant(self, tenant=None):
        if tenant is None:
            current_user = get_current_user()
            tenant = getattr(current_user, "tenant", None)
        if tenant is None:
            return self.none()
        return self.get_queryset().filter(tenant=str(tenant))

    def active(self):
        return self.get_queryset().filter(is_active=True, is_deleted=False)

    def inactive(self):
        return self.get_queryset().filter(is_active=False)


class ActiveManager(TenantAwareManager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True, is_deleted=False)


class InactiveManager(TenantAwareManager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=False)


class TenantAwareModel(models.Model):
    objects = TenantAwareManager()
    active_objects = ActiveManager()
    inactive_objects = InactiveManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        current_user = get_current_user()
        if getattr(self, "tenant", None) is None and current_user is not None:
            self.tenant = current_user.tenant
        if current_user is not None:
            if getattr(self, "created_by", None) is None:
                self.created_by = current_user
            self.updated_by = current_user
        super().save(*args, **kwargs)


class BaseModel(TenantAwareModel):
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


class FeatureCategory(BaseModel):
    name = models.CharField(max_length=100)
    code = models.SlugField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, default="circle")
    display_order = models.PositiveIntegerField(default=0)
    is_system = models.BooleanField(default=False)

    class Meta:
        db_table = "app_feature_category"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="unique_feature_category_code_per_tenant"),
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_feature_category_name_per_tenant"),
        ]
        ordering = ["display_order", "name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        if not self.code:
            self.code = slugify(self.name)
        super().save(*args, **kwargs)


class Feature(BaseModel):
    feature_category = models.ForeignKey(FeatureCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name="features")
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, blank=True)
    code = models.SlugField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, default="circle")
    route = models.CharField(max_length=255, blank=True)
    api_base_url = models.CharField(max_length=255, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    feature_type = models.CharField(
        max_length=20,
        choices=[
            ("MENU", "Menu"),
            ("PAGE", "Page"),
            ("ACTION", "Action"),
            ("REPORT", "Report"),
            ("DASHBOARD", "Dashboard"),
            ("WIDGET", "Widget"),
            ("API", "Api"),
        ],
        default="MENU",
    )
    category = models.CharField(max_length=100, blank=True)
    is_visible = models.BooleanField(default=True)
    is_assignable = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False)

    class Meta:
        db_table = "app_feature"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="unique_feature_code_per_tenant"),
            models.UniqueConstraint(fields=["tenant", "slug"], name="unique_feature_slug_per_tenant"),
        ]
        ordering = ["display_order", "name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            self.slug = slugify(self.name)
        if not self.code:
            self.code = self.slug
        super().save(*args, **kwargs)


class FeatureItem(BaseModel):
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name="feature_items")
    title = models.CharField(max_length=100)
    route = models.CharField(max_length=255, blank=True)
    icon = models.CharField(max_length=50, default="circle")
    display_order = models.PositiveIntegerField(default=0)
    parent_item = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")
    badge = models.CharField(max_length=50, blank=True)
    opens_in_new_tab = models.BooleanField(default=False)
    permission_code = models.CharField(max_length=100, blank=True)
    is_visible = models.BooleanField(default=True)

    class Meta:
        db_table = "app_feature_item"
        ordering = ["display_order", "title"]

    def __str__(self) -> str:
        return self.title


class FeatureAction(BaseModel):
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name="feature_actions")
    name = models.CharField(max_length=100)
    code = models.SlugField(max_length=100, blank=True)
    http_method = models.CharField(max_length=10, default="POST")
    endpoint = models.CharField(max_length=255, blank=True)
    permission_code = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "app_feature_action"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "feature", "code"], name="unique_feature_action_code_per_tenant_feature"),
        ]
        ordering = ["feature__name", "name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        if not self.code:
            self.code = slugify(self.name)
        super().save(*args, **kwargs)


class RoleFeature(BaseModel):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_features")
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name="role_features")
    enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "app_role_feature"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "role", "feature"], name="unique_role_feature_assignment_per_tenant")
        ]
        ordering = ["role__name", "feature__name"]

    def __str__(self) -> str:
        return f"{self.role.name} -> {self.feature.name}"


class RoleFeatureAction(BaseModel):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_feature_actions")
    feature_action = models.ForeignKey(FeatureAction, on_delete=models.CASCADE, related_name="role_feature_actions")
    enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "app_role_feature_action"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "role", "feature_action"], name="unique_role_feature_action_assignment_per_tenant")
        ]
        ordering = ["role__name", "feature_action__name"]

    def __str__(self) -> str:
        return f"{self.role.name} -> {self.feature_action.name}"


class Dashboard(BaseModel):
    role = models.OneToOneField(Role, on_delete=models.CASCADE, related_name="dashboard")
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, blank=True)
    url = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    logo = models.CharField(max_length=255, blank=True)
    theme = models.CharField(max_length=50, blank=True)
    home_route = models.CharField(max_length=255, blank=True)
    default_layout = models.CharField(max_length=100, blank=True)
    is_default = models.BooleanField(default=False)
    features = models.ManyToManyField(Feature, through="DashboardFeature", related_name="dashboards")

    class Meta:
        db_table = "app_dashboard"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "slug"], name="unique_dashboard_slug_per_tenant")
        ]
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            self.slug = slugify(self.name)
        if not self.url:
            self.url = f"/dashboard/{self.slug}/"
        super().save(*args, **kwargs)


class DashboardFeature(BaseModel):
    dashboard = models.ForeignKey(Dashboard, on_delete=models.CASCADE, related_name="dashboard_features")
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name="dashboard_features")

    class Meta:
        db_table = "app_dashboard_feature"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "dashboard", "feature"], name="unique_dashboard_feature_per_tenant")
        ]
        ordering = ["dashboard__name", "feature__name"]

    def __str__(self) -> str:
        return f"{self.dashboard.name} -> {self.feature.name}"


class DashboardWidget(BaseModel):
    dashboard = models.ForeignKey(Dashboard, on_delete=models.CASCADE, related_name="widgets")
    title = models.CharField(max_length=100)
    widget_type = models.CharField(max_length=100)
    feature = models.ForeignKey(Feature, null=True, blank=True, on_delete=models.SET_NULL, related_name="widgets")
    display_order = models.PositiveIntegerField(default=0)
    width = models.PositiveIntegerField(default=1)
    height = models.PositiveIntegerField(default=1)
    configuration = models.JSONField(default=dict, blank=True)
    is_visible = models.BooleanField(default=True)

    class Meta:
        db_table = "app_dashboard_widget"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "dashboard", "title"], name="unique_dashboard_widget_title_per_tenant")
        ]
        ordering = ["dashboard__name", "display_order", "title"]

    def __str__(self) -> str:
        return f"{self.dashboard.name} -> {self.title}"


class DashboardQuickAction(BaseModel):
    dashboard = models.ForeignKey(Dashboard, on_delete=models.CASCADE, related_name="quick_actions")
    feature_action = models.ForeignKey(FeatureAction, on_delete=models.CASCADE, related_name="quick_actions")
    display_order = models.PositiveIntegerField(default=0)
    icon = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=30, blank=True)

    class Meta:
        db_table = "app_dashboard_quick_action"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "dashboard", "feature_action"], name="unique_dashboard_quick_action_per_tenant")
        ]
        ordering = ["dashboard__name", "display_order"]

    def __str__(self) -> str:
        return f"{self.dashboard.name} -> {self.feature_action.name}"


class DashboardStatisticCard(BaseModel):
    dashboard = models.ForeignKey(Dashboard, on_delete=models.CASCADE, related_name="statistic_cards")
    title = models.CharField(max_length=100)
    feature = models.ForeignKey(Feature, null=True, blank=True, on_delete=models.SET_NULL, related_name="statistic_cards")
    api_endpoint = models.CharField(max_length=255, blank=True)
    icon = models.CharField(max_length=50, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    refresh_interval = models.PositiveIntegerField(default=60)

    class Meta:
        db_table = "app_dashboard_statistic_card"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "dashboard", "title"], name="unique_dashboard_statistic_card_title_per_tenant")
        ]
        ordering = ["dashboard__name", "display_order", "title"]

    def __str__(self) -> str:
        return f"{self.dashboard.name} -> {self.title}"


class DashboardBanner(BaseModel):
    dashboard = models.ForeignKey(Dashboard, on_delete=models.CASCADE, related_name="banners")
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    image = models.CharField(max_length=255, blank=True)
    button_text = models.CharField(max_length=100, blank=True)
    button_route = models.CharField(max_length=255, blank=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "app_dashboard_banner"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "dashboard", "title"], name="unique_dashboard_banner_title_per_tenant")
        ]
        ordering = ["dashboard__name", "display_order", "title"]

    def __str__(self) -> str:
        return f"{self.dashboard.name} -> {self.title}"


class DashboardRoute(BaseModel):
    dashboard = models.ForeignKey(Dashboard, on_delete=models.CASCADE, related_name="dashboard_routes")
    name = models.CharField(max_length=100)
    route = models.CharField(max_length=255)
    icon = models.CharField(max_length=50, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_visible = models.BooleanField(default=True)

    class Meta:
        db_table = "app_dashboard_route"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "dashboard", "route"], name="unique_dashboard_route_per_tenant")
        ]
        ordering = ["dashboard__name", "sort_order", "name"]

    def __str__(self) -> str:
        return f"{self.dashboard.name} -> {self.name}"


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
    device_name = models.CharField(max_length=255, blank=True, default="phone")
    authenticator_app = models.CharField(max_length=255, blank=True, default="Google Authenticator")

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
