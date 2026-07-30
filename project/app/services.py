from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import string
import time
import uuid
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password, check_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import exceptions
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    AuditLog,
    Dashboard,
    DashboardFeature,
    DashboardWidget,
    DashboardQuickAction,
    DashboardStatisticCard,
    DashboardBanner,
    DashboardRoute,
    FailedLoginAttempt,
    Feature,
    FeatureAction,
    FeatureCategory,
    FeatureItem,
    LoginHistory,
    MFAMethod,
    Permission,
    RefreshToken as RefreshTokenModel,
    Role,
    RoleFeature,
    RoleFeatureAction,
    RolePermission,
    UserRole,
)

User = get_user_model()


class DashboardService:
    def __init__(self, request=None):
        self.request = request

    def create_dashboard(self, user: User, data: dict[str, Any]) -> dict[str, Any]:
        if not self._is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can create dashboards.")
        tenant = str(user.tenant or uuid.uuid4())
        role_name = data.get("role_name") or data.get("dashboard_name")
        role = Role.objects.filter(tenant=tenant, name=role_name, is_deleted=False).first()
        if role is None:
            role = Role.objects.create(
                tenant=tenant,
                name=role_name,
                code=(data.get("slug") or role_name).lower().replace(" ", "_"),
                description=data.get("description", ""),
                is_system=False,
                created_by=user,
            )
        dashboard = Dashboard.objects.filter(tenant=tenant, role=role, is_deleted=False).first()
        if dashboard is None:
            slug = data.get("slug") or self._slugify(role_name)
            dashboard = Dashboard.objects.create(
                tenant=tenant,
                role=role,
                name=role_name,
                slug=slug,
                url=f"/dashboard/{slug}/",
                description=data.get("description", ""),
                is_active=data.get("is_active", True),
                created_by=user,
            )
            self._create_default_dashboard_routes(dashboard, user)
            self._add_default_features(dashboard, user)
        self._log_audit(user=user, action="dashboard_create", details={"dashboard_id": str(dashboard.id), "role": role_name}, actor=user, request=self.request)
        return self._serialize_dashboard(dashboard)

    def update_dashboard(self, user: User, dashboard: Dashboard, data: dict[str, Any]) -> dict[str, Any]:
        if not self._is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can update dashboards.")
        if data.get("dashboard_name"):
            dashboard.name = data["dashboard_name"]
        if data.get("role_name"):
            role = dashboard.role
            role.name = data["role_name"]
            role.code = (data.get("slug") or data["role_name"]).lower().replace(" ", "_")
            role.save(update_fields=["name", "code", "updated_at"])
        if data.get("slug"):
            dashboard.slug = data["slug"]
            dashboard.url = f"/dashboard/{data['slug']}/"
        if data.get("description") is not None:
            dashboard.description = data["description"]
        if "is_active" in data:
            dashboard.is_active = data["is_active"]
        dashboard.save(update_fields=["name", "slug", "url", "description", "is_active", "updated_at"])
        self._log_audit(user=user, action="dashboard_update", details={"dashboard_id": str(dashboard.id)}, actor=user, request=self.request)
        return self._serialize_dashboard(dashboard)

    def delete_dashboard(self, user: User, dashboard: Dashboard) -> dict[str, Any]:
        if not self._is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can delete dashboards.")
        dashboard.is_active = False
        dashboard.is_deleted = True
        dashboard.deleted_at = timezone.now()
        dashboard.save(update_fields=["is_active", "is_deleted", "deleted_at", "updated_at"])
        self._log_audit(user=user, action="dashboard_delete", details={"dashboard_id": str(dashboard.id)}, actor=user, request=self.request)
        return {"deleted": True, "dashboard_id": str(dashboard.id)}

    def list_dashboards(self, user: User) -> list[dict[str, Any]]:
        if not self._is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can list dashboards.")
        dashboards = Dashboard.objects.filter(tenant=str(user.tenant), is_deleted=False).select_related("role")
        return [self._serialize_dashboard(d) for d in dashboards]

    def assign_feature(self, user: User, dashboard: Dashboard, data: dict[str, Any]) -> dict[str, Any]:
        if not self._is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can assign features.")
        feature = None
        if data.get("feature_id"):
            feature = Feature.objects.filter(id=data["feature_id"], tenant=str(user.tenant), is_deleted=False).first()
        elif data.get("feature_name") or data.get("feature_slug"):
            slug = data.get("feature_slug") or self._slugify(data.get("feature_name") or "")
            feature, _ = Feature.objects.get_or_create(
                tenant=str(user.tenant),
                slug=slug,
                defaults={
                    "name": data.get("feature_name") or slug.replace("-", " ").title(),
                    "icon": data.get("icon") or "circle",
                    "route": data.get("route") or f"/{slug}/",
                    "category": data.get("category") or "General",
                    "created_by": user,
                },
            )
        if not feature:
            raise exceptions.ValidationError("A valid feature is required.")
        DashboardFeature.objects.get_or_create(
            tenant=str(user.tenant),
            dashboard=dashboard,
            feature=feature,
            defaults={"created_by": user},
        )
        self._log_audit(user=user, action="dashboard_assign_feature", details={"dashboard_id": str(dashboard.id), "feature_id": str(feature.id)}, actor=user, request=self.request)
        return self._serialize_dashboard(dashboard)

    def remove_feature(self, user: User, dashboard: Dashboard, feature_id: str | None = None) -> dict[str, Any]:
        if not self._is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can remove features.")
        feature = Feature.objects.filter(id=feature_id, tenant=str(user.tenant), is_deleted=False).first() if feature_id else None
        if not feature:
            raise exceptions.ValidationError("Feature not found.")
        DashboardFeature.objects.filter(tenant=str(user.tenant), dashboard=dashboard, feature=feature).delete()
        self._log_audit(user=user, action="dashboard_remove_feature", details={"dashboard_id": str(dashboard.id), "feature_id": str(feature.id)}, actor=user, request=self.request)
        return self._serialize_dashboard(dashboard)

    def get_dashboard_features(self, user: User, dashboard: Dashboard) -> list[dict[str, Any]]:
        if not self._can_view_dashboard(user, dashboard):
            raise exceptions.PermissionDenied("You do not have access to this dashboard.")
        return [self._serialize_feature(f) for f in dashboard.features.filter(tenant=str(user.tenant), is_deleted=False).all()]

    def get_dashboard_by_url(self, user: User, slug: str) -> dict[str, Any]:
        dashboard = Dashboard.objects.filter(tenant=str(user.tenant), slug=slug, is_deleted=False).first()
        if not dashboard:
            raise exceptions.NotFound("Dashboard not found.")
        if not self._can_view_dashboard(user, dashboard):
            raise exceptions.PermissionDenied("You do not have access to this dashboard.")
        return self._serialize_dashboard(dashboard)

    def get_dashboard_menu(self, user: User) -> dict[str, Any]:
        if not user.is_authenticated:
            raise exceptions.AuthenticationFailed("Authentication required.")
        dashboard = self._get_user_dashboard(user) or self._create_fallback_dashboard(user)
        sidebar = self._build_sidebar(dashboard, dashboard.role)
        return {"menu": sidebar, "dashboard": self._serialize_dashboard(dashboard)}

    def get_dashboard_payload(self, user: User) -> dict[str, Any]:
        if not user.is_authenticated:
            raise exceptions.AuthenticationFailed("Authentication required.")

        dashboard = self._get_user_dashboard(user)
        if not dashboard:
            dashboard = self._create_fallback_dashboard(user)

        role = dashboard.role
        permissions = self._get_role_permissions(role)
        sidebar = self._build_sidebar(dashboard, role)
        widgets = self._serialize_widgets(self._get_dashboard_widgets(dashboard, role))
        actions = self._serialize_quick_actions(self._get_dashboard_quick_actions(dashboard, role))
        statistics = self._serialize_statistic_cards(self._get_dashboard_statistic_cards(dashboard, role))
        banners = self._serialize_banners(dashboard.banners.filter(tenant=str(user.tenant), is_deleted=False, is_visible=True).order_by("display_order", "title"))

        self._log_audit(user=user, action="dashboard_view", details={"dashboard_id": str(dashboard.id)}, actor=user, request=self.request)

        return {
            "dashboard": self._serialize_dashboard(dashboard),
            "sidebar": sidebar,
            "widgets": widgets,
            "quick_actions": actions,
            "statistics": statistics,
            "banners": banners,
            "current_user": {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "tenant": str(user.tenant) if user.tenant else None,
            },
            "role": {"id": str(role.id), "name": role.name, "code": role.code},
            "permissions": permissions,
            "theme": dashboard.theme,
            "school_branding": {"logo": dashboard.logo},
        }

    def list_dashboard_widgets(self, user: User, dashboard_id: str | None = None) -> list[dict[str, Any]]:
        if not self._is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can manage dashboard widgets.")
        dashboard = self._get_dashboard_by_id(user, dashboard_id)
        widgets = DashboardWidget.objects.filter(tenant=str(user.tenant), dashboard=dashboard, is_deleted=False, is_visible=True).order_by("display_order", "title")
        return self._serialize_widgets(widgets)

    def create_dashboard_widget(self, user: User, data: dict[str, Any]) -> dict[str, Any]:
        if not self._is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can create dashboard widgets.")
        dashboard = self._get_dashboard_by_id(user, data.get("dashboard_id"))
        feature = None
        if data.get("feature_id"):
            feature = Feature.objects.filter(id=data["feature_id"], tenant=str(user.tenant), is_deleted=False).first()
            if not feature:
                raise exceptions.NotFound("Feature not found.")
        widget, created = DashboardWidget.objects.get_or_create(
            tenant=str(user.tenant),
            dashboard=dashboard,
            title=data["title"],
            defaults={
                "widget_type": data["widget_type"],
                "feature": feature,
                "display_order": data.get("display_order", 0),
                "width": data.get("width", 1),
                "height": data.get("height", 1),
                "configuration": data.get("configuration", {}),
                "is_visible": data.get("is_visible", True),
                "created_by": user,
            },
        )
        if not created:
            raise exceptions.ValidationError("A widget with that title already exists on this dashboard.")
        self._log_audit(user=user, action="widget_added", details={"dashboard_id": str(dashboard.id), "widget_id": str(widget.id)}, actor=user, request=self.request)
        return self._serialize_widget(widget)

    def update_dashboard_widget(self, user: User, widget_id: str, data: dict[str, Any]) -> dict[str, Any]:
        if not self._is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can update dashboard widgets.")
        widget = DashboardWidget.objects.filter(id=widget_id, tenant=str(user.tenant), is_deleted=False).first()
        if not widget:
            raise exceptions.NotFound("Dashboard widget not found.")
        for key in ["title", "widget_type", "display_order", "width", "height", "configuration", "is_visible"]:
            if key in data:
                setattr(widget, key, data[key])
        if "feature_id" in data:
            feature = Feature.objects.filter(id=data["feature_id"], tenant=str(user.tenant), is_deleted=False).first()
            if not feature:
                raise exceptions.NotFound("Feature not found.")
            widget.feature = feature
        widget.save(update_fields=["title", "widget_type", "feature", "display_order", "width", "height", "configuration", "is_visible", "updated_at"])
        self._log_audit(user=user, action="widget_updated", details={"widget_id": str(widget.id)}, actor=user, request=self.request)
        return self._serialize_widget(widget)

    def delete_dashboard_widget(self, user: User, widget_id: str) -> dict[str, Any]:
        if not self._is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can delete dashboard widgets.")
        widget = DashboardWidget.objects.filter(id=widget_id, tenant=str(user.tenant), is_deleted=False).first()
        if not widget:
            raise exceptions.NotFound("Dashboard widget not found.")
        widget.soft_delete(user=user)
        self._log_audit(user=user, action="widget_removed", details={"widget_id": str(widget.id)}, actor=user, request=self.request)
        return {"removed": True, "widget_id": str(widget.id)}

    def create_dashboard_quick_action(self, user: User, data: dict[str, Any]) -> dict[str, Any]:
        if not self._is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can create dashboard quick actions.")
        dashboard = self._get_dashboard_by_id(user, data.get("dashboard_id"))
        action = FeatureAction.objects.filter(id=data["feature_action_id"], tenant=str(user.tenant), is_deleted=False).first()
        if not action:
            raise exceptions.NotFound("Feature action not found.")
        quick_action, created = DashboardQuickAction.objects.get_or_create(
            tenant=str(user.tenant),
            dashboard=dashboard,
            feature_action=action,
            defaults={
                "display_order": data.get("display_order", 0),
                "icon": data.get("icon", ""),
                "color": data.get("color", ""),
                "created_by": user,
            },
        )
        if not created:
            raise exceptions.ValidationError("This dashboard quick action is already registered.")
        self._log_audit(user=user, action="action_added", details={"dashboard_id": str(dashboard.id), "quick_action_id": str(quick_action.id)}, actor=user, request=self.request)
        return {
            "id": str(quick_action.id),
            "dashboard_id": str(dashboard.id),
            "feature_action_id": str(quick_action.feature_action_id),
            "display_order": quick_action.display_order,
            "icon": quick_action.icon,
            "color": quick_action.color,
        }

    def update_dashboard_quick_action(self, user: User, action_id: str, data: dict[str, Any]) -> dict[str, Any]:
        if not self._is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can update dashboard quick actions.")
        quick_action = DashboardQuickAction.objects.filter(id=action_id, tenant=str(user.tenant), is_deleted=False).first()
        if not quick_action:
            raise exceptions.NotFound("Dashboard quick action not found.")
        if data.get("display_order") is not None:
            quick_action.display_order = data["display_order"]
        if data.get("icon") is not None:
            quick_action.icon = data["icon"]
        if data.get("color") is not None:
            quick_action.color = data["color"]
        if data.get("feature_action_id") is not None:
            action = FeatureAction.objects.filter(id=data["feature_action_id"], tenant=str(user.tenant), is_deleted=False).first()
            if not action:
                raise exceptions.NotFound("Feature action not found.")
            quick_action.feature_action = action
        quick_action.save(update_fields=["feature_action", "display_order", "icon", "color", "updated_at"])
        self._log_audit(user=user, action="action_updated", details={"quick_action_id": str(quick_action.id)}, actor=user, request=self.request)
        return {
            "id": str(quick_action.id),
            "dashboard_id": str(quick_action.dashboard_id),
            "feature_action_id": str(quick_action.feature_action_id),
            "display_order": quick_action.display_order,
            "icon": quick_action.icon,
            "color": quick_action.color,
        }

    def delete_dashboard_quick_action(self, user: User, action_id: str) -> dict[str, Any]:
        if not self._is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can delete dashboard quick actions.")
        quick_action = DashboardQuickAction.objects.filter(id=action_id, tenant=str(user.tenant), is_deleted=False).first()
        if not quick_action:
            raise exceptions.NotFound("Dashboard quick action not found.")
        quick_action.soft_delete(user=user)
        self._log_audit(user=user, action="action_removed", details={"quick_action_id": str(quick_action.id)}, actor=user, request=self.request)
        return {"removed": True, "action_id": str(quick_action.id)}

    def create_dashboard_statistic_card(self, user: User, data: dict[str, Any]) -> dict[str, Any]:
        if not self._is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can create dashboard statistic cards.")
        dashboard = self._get_dashboard_by_id(user, data.get("dashboard_id"))
        feature = None
        if data.get("feature_id"):
            feature = Feature.objects.filter(id=data["feature_id"], tenant=str(user.tenant), is_deleted=False).first()
            if not feature:
                raise exceptions.NotFound("Feature not found.")
        card, created = DashboardStatisticCard.objects.get_or_create(
            tenant=str(user.tenant),
            dashboard=dashboard,
            title=data["title"],
            defaults={
                "feature": feature,
                "api_endpoint": data.get("api_endpoint", ""),
                "icon": data.get("icon", ""),
                "display_order": data.get("display_order", 0),
                "refresh_interval": data.get("refresh_interval", 60),
                "created_by": user,
            },
        )
        if not created:
            raise exceptions.ValidationError("A statistic card with that title already exists on this dashboard.")
        self._log_audit(user=user, action="statistics_card_added", details={"dashboard_id": str(dashboard.id), "card_id": str(card.id)}, actor=user, request=self.request)
        return self._serialize_statistic_cards([card])[0]

    def update_dashboard_statistic_card(self, user: User, card_id: str, data: dict[str, Any]) -> dict[str, Any]:
        if not self._is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can update dashboard statistic cards.")
        card = DashboardStatisticCard.objects.filter(id=card_id, tenant=str(user.tenant), is_deleted=False).first()
        if not card:
            raise exceptions.NotFound("Dashboard statistic card not found.")
        if data.get("title") is not None:
            card.title = data["title"]
        if data.get("feature_id") is not None:
            card.feature = Feature.objects.filter(id=data["feature_id"], tenant=str(user.tenant), is_deleted=False).first()
            if data.get("feature_id") and not card.feature:
                raise exceptions.NotFound("Feature not found.")
        if data.get("api_endpoint") is not None:
            card.api_endpoint = data["api_endpoint"]
        if data.get("icon") is not None:
            card.icon = data["icon"]
        if data.get("display_order") is not None:
            card.display_order = data["display_order"]
        if data.get("refresh_interval") is not None:
            card.refresh_interval = data["refresh_interval"]
        card.save(update_fields=["title", "feature", "api_endpoint", "icon", "display_order", "refresh_interval", "updated_at"])
        self._log_audit(user=user, action="statistics_card_updated", details={"card_id": str(card.id)}, actor=user, request=self.request)
        return self._serialize_statistic_cards([card])[0]

    def delete_dashboard_statistic_card(self, user: User, card_id: str) -> dict[str, Any]:
        if not self._is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can delete dashboard statistic cards.")
        card = DashboardStatisticCard.objects.filter(id=card_id, tenant=str(user.tenant), is_deleted=False).first()
        if not card:
            raise exceptions.NotFound("Dashboard statistic card not found.")
        card.soft_delete(user=user)
        self._log_audit(user=user, action="statistics_card_removed", details={"card_id": str(card.id)}, actor=user, request=self.request)
        return {"removed": True, "card_id": str(card.id)}

    def create_dashboard_banner(self, user: User, data: dict[str, Any]) -> dict[str, Any]:
        if not self._is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can create dashboard banners.")
        dashboard = self._get_dashboard_by_id(user, data.get("dashboard_id"))
        banner, created = DashboardBanner.objects.get_or_create(
            tenant=str(user.tenant),
            dashboard=dashboard,
            title=data["title"],
            defaults={
                "description": data.get("description", ""),
                "image": data.get("image", ""),
                "button_text": data.get("button_text", ""),
                "button_route": data.get("button_route", ""),
                "display_order": data.get("display_order", 0),
                "created_by": user,
            },
        )
        if not created:
            raise exceptions.ValidationError("A banner with that title already exists on this dashboard.")
        self._log_audit(user=user, action="banner_added", details={"dashboard_id": str(dashboard.id), "banner_id": str(banner.id)}, actor=user, request=self.request)
        return self._serialize_banners([banner])[0]

    def update_dashboard_banner(self, user: User, banner_id: str, data: dict[str, Any]) -> dict[str, Any]:
        if not self._is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can update dashboard banners.")
        banner = DashboardBanner.objects.filter(id=banner_id, tenant=str(user.tenant), is_deleted=False).first()
        if not banner:
            raise exceptions.NotFound("Dashboard banner not found.")
        if data.get("title") is not None:
            banner.title = data["title"]
        if data.get("description") is not None:
            banner.description = data["description"]
        if data.get("image") is not None:
            banner.image = data["image"]
        if data.get("button_text") is not None:
            banner.button_text = data["button_text"]
        if data.get("button_route") is not None:
            banner.button_route = data["button_route"]
        if data.get("display_order") is not None:
            banner.display_order = data["display_order"]
        banner.save(update_fields=["title", "description", "image", "button_text", "button_route", "display_order", "updated_at"])
        self._log_audit(user=user, action="banner_updated", details={"banner_id": str(banner.id)}, actor=user, request=self.request)
        return self._serialize_banners([banner])[0]

    def delete_dashboard_banner(self, user: User, banner_id: str) -> dict[str, Any]:
        if not self._is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can delete dashboard banners.")
        banner = DashboardBanner.objects.filter(id=banner_id, tenant=str(user.tenant), is_deleted=False).first()
        if not banner:
            raise exceptions.NotFound("Dashboard banner not found.")
        banner.soft_delete(user=user)
        self._log_audit(user=user, action="banner_removed", details={"banner_id": str(banner.id)}, actor=user, request=self.request)
        return {"removed": True, "banner_id": str(banner.id)}

    def list_dashboard_actions(self, user: User) -> list[dict[str, Any]]:
        dashboard = self._get_user_dashboard(user)
        if not dashboard:
            raise exceptions.NotFound("Dashboard not found.")
        actions = self._get_dashboard_quick_actions(dashboard, dashboard.role)
        return self._serialize_quick_actions(actions)

    def list_dashboard_statistics(self, user: User) -> list[dict[str, Any]]:
        dashboard = self._get_user_dashboard(user)
        if not dashboard:
            raise exceptions.NotFound("Dashboard not found.")
        statistics = self._get_dashboard_statistic_cards(dashboard, dashboard.role)
        return self._serialize_statistic_cards(statistics)

    def list_dashboard_banners(self, user: User) -> list[dict[str, Any]]:
        dashboard = self._get_user_dashboard(user)
        if not dashboard:
            raise exceptions.NotFound("Dashboard not found.")
        banners = dashboard.banners.filter(tenant=str(user.tenant), is_deleted=False, is_visible=True).order_by("display_order", "title")
        return self._serialize_banners(banners)

    def register_dashboard_widget(self, user: User, dashboard: Dashboard, data: dict[str, Any]) -> DashboardWidget:
        return self.create_dashboard_widget(user, {**data, "dashboard_id": str(dashboard.id)})

    def register_dashboard_action(self, user: User, dashboard: Dashboard, feature_action: FeatureAction, display_order: int = 0, icon: str = "", color: str = "") -> DashboardQuickAction:
        action, created = DashboardQuickAction.objects.get_or_create(
            tenant=str(user.tenant),
            dashboard=dashboard,
            feature_action=feature_action,
            defaults={
                "display_order": display_order,
                "icon": icon,
                "color": color,
                "created_by": user,
            },
        )
        if not created:
            raise exceptions.ValidationError("This dashboard action is already registered.")
        self._log_audit(user=user, action="action_added", details={"dashboard_id": str(dashboard.id), "feature_action_id": str(feature_action.id)}, actor=user, request=self.request)
        return action

    def register_dashboard_card(self, user: User, dashboard: Dashboard, data: dict[str, Any]) -> DashboardStatisticCard:
        card, created = DashboardStatisticCard.objects.get_or_create(
            tenant=str(user.tenant),
            dashboard=dashboard,
            title=data["title"],
            defaults={
                "feature": Feature.objects.filter(id=data.get("feature_id"), tenant=str(user.tenant), is_deleted=False).first() if data.get("feature_id") else None,
                "api_endpoint": data.get("api_endpoint", ""),
                "icon": data.get("icon", ""),
                "display_order": data.get("display_order", 0),
                "refresh_interval": data.get("refresh_interval", 60),
                "created_by": user,
            },
        )
        if not created:
            raise exceptions.ValidationError("A statistic card with that title already exists on this dashboard.")
        self._log_audit(user=user, action="statistics_card_added", details={"dashboard_id": str(dashboard.id), "card_id": str(card.id)}, actor=user, request=self.request)
        return card

    def register_dashboard_banner(self, user: User, dashboard: Dashboard, data: dict[str, Any]) -> DashboardBanner:
        banner, created = DashboardBanner.objects.get_or_create(
            tenant=str(user.tenant),
            dashboard=dashboard,
            title=data["title"],
            defaults={
                "description": data.get("description", ""),
                "image": data.get("image", ""),
                "button_text": data.get("button_text", ""),
                "button_route": data.get("button_route", ""),
                "display_order": data.get("display_order", 0),
                "created_by": user,
            },
        )
        if not created:
            raise exceptions.ValidationError("A banner with that title already exists on this dashboard.")
        self._log_audit(user=user, action="banner_added", details={"dashboard_id": str(dashboard.id), "banner_id": str(banner.id)}, actor=user, request=self.request)
        return banner

    def _build_sidebar(self, dashboard: Dashboard, role: Role) -> list[dict[str, Any]]:
        tenant = str(dashboard.tenant)
        role_features = Feature.objects.filter(
            tenant=tenant,
            role_features__role=role,
            is_deleted=False,
            is_visible=True,
        )
        dashboard_features = dashboard.features.filter(tenant=tenant, is_deleted=False, is_visible=True)
        assigned_features = (role_features | dashboard_features).distinct().select_related("feature_category").order_by("feature_category__display_order", "display_order", "name")

        categories: dict[str, list[dict[str, Any]]] = {}
        for feature in assigned_features:
            category_name = feature.feature_category.name if feature.feature_category else "General"
            categories.setdefault(category_name, [])

            feature_items = feature.feature_items.filter(tenant=tenant, is_deleted=False, is_visible=True).order_by("display_order", "title")
            if feature_items.exists():
                for item in feature_items:
                    categories[category_name].append(
                        {
                            "id": str(item.id),
                            "feature_id": str(feature.id),
                            "title": item.title,
                            "route": item.route or feature.route or f"/{feature.slug}/",
                            "icon": item.icon,
                            "badge": item.badge,
                            "opens_in_new_tab": item.opens_in_new_tab,
                        }
                    )
            else:
                categories[category_name].append(
                    {
                        "id": str(feature.id),
                        "title": feature.name,
                        "route": feature.route or f"/{feature.slug}/",
                        "icon": feature.icon,
                    }
                )

        return [
            {"category": category_name, "items": items}
            for category_name, items in sorted(categories.items(), key=lambda item: item[0])
        ]

    def _get_user_dashboard(self, user: User) -> Dashboard | None:
        role = UserRole.objects.filter(user=user, tenant=str(user.tenant), is_deleted=False).order_by("-created_at").first()
        if role:
            return Dashboard.objects.filter(role=role.role, tenant=str(user.tenant), is_deleted=False).first()
        if self._is_system_admin(user):
            return Dashboard.objects.filter(tenant=str(user.tenant), is_deleted=False).order_by("-created_at").first()
        return None

    def _get_dashboard_by_id(self, user: User, dashboard_id: str | None) -> Dashboard:
        if not dashboard_id:
            raise exceptions.ValidationError("Dashboard id is required.")
        dashboard = Dashboard.objects.filter(id=dashboard_id, tenant=str(user.tenant), is_deleted=False).first()
        if not dashboard:
            raise exceptions.NotFound("Dashboard not found.")
        return dashboard

    def _get_dashboard_widgets(self, dashboard: Dashboard, role: Role) -> list[DashboardWidget]:
        tenant = str(dashboard.tenant)
        assigned_feature_ids = Feature.objects.filter(
            tenant=tenant,
            role_features__role=role,
            is_deleted=False,
            is_visible=True,
        ).values_list("id", flat=True)
        return DashboardWidget.objects.filter(
            tenant=tenant,
            dashboard=dashboard,
            feature_id__in=assigned_feature_ids,
            is_deleted=False,
            is_visible=True,
        ).order_by("display_order", "title")

    def _get_dashboard_quick_actions(self, dashboard: Dashboard, role: Role) -> list[DashboardQuickAction]:
        tenant = str(dashboard.tenant)
        assigned_action_ids = RoleFeatureAction.objects.filter(
            tenant=tenant,
            role=role,
            is_deleted=False,
        ).values_list("feature_action_id", flat=True)
        return DashboardQuickAction.objects.filter(
            tenant=tenant,
            dashboard=dashboard,
            feature_action_id__in=assigned_action_ids,
            is_deleted=False,
        ).order_by("display_order")

    def _get_dashboard_statistic_cards(self, dashboard: Dashboard, role: Role) -> list[DashboardStatisticCard]:
        tenant = str(dashboard.tenant)
        assigned_feature_ids = Feature.objects.filter(
            tenant=tenant,
            role_features__role=role,
            is_deleted=False,
            is_visible=True,
        ).values_list("id", flat=True)
        return DashboardStatisticCard.objects.filter(
            tenant=tenant,
            dashboard=dashboard,
            is_deleted=False,
        ).filter(models.Q(feature__isnull=True) | models.Q(feature_id__in=assigned_feature_ids)).order_by("display_order", "title")

    def _serialize_widgets(self, widgets: list[DashboardWidget]) -> list[dict[str, Any]]:
        return [self._serialize_widget(widget) for widget in widgets]

    def _serialize_widget(self, widget: DashboardWidget) -> dict[str, Any]:
        return {
            "id": str(widget.id),
            "title": widget.title,
            "widget_type": widget.widget_type,
            "feature_id": str(widget.feature_id) if widget.feature_id else None,
            "display_order": widget.display_order,
            "width": widget.width,
            "height": widget.height,
            "configuration": widget.configuration,
            "is_visible": widget.is_visible,
        }

    def _serialize_quick_actions(self, actions: list[DashboardQuickAction]) -> list[dict[str, Any]]:
        return [
            {
                "id": str(action.id),
                "feature_action_id": str(action.feature_action_id),
                "name": action.feature_action.name,
                "icon": action.icon,
                "color": action.color,
                "display_order": action.display_order,
            }
            for action in actions
        ]

    def _serialize_statistic_cards(self, cards: list[DashboardStatisticCard]) -> list[dict[str, Any]]:
        return [
            {
                "id": str(card.id),
                "title": card.title,
                "feature_id": str(card.feature_id) if card.feature_id else None,
                "api_endpoint": card.api_endpoint,
                "icon": card.icon,
                "display_order": card.display_order,
                "refresh_interval": card.refresh_interval,
            }
            for card in cards
        ]

    def _serialize_banners(self, banners: list[DashboardBanner]) -> list[dict[str, Any]]:
        return [
            {
                "id": str(banner.id),
                "title": banner.title,
                "description": banner.description,
                "image": banner.image,
                "button_text": banner.button_text,
                "button_route": banner.button_route,
                "display_order": banner.display_order,
            }
            for banner in banners
        ]

    def _get_role_permissions(self, role: Role) -> dict[str, Any]:
        feature_codes = list(
            Feature.objects.filter(
                tenant=str(role.tenant),
                role_features__role=role,
                is_deleted=False,
                is_visible=True,
            ).values_list("code", flat=True).distinct()
        )
        action_codes = list(
            FeatureAction.objects.filter(
                tenant=str(role.tenant),
                role_feature_actions__role=role,
                is_deleted=False,
            ).values_list("code", flat=True).distinct()
        )
        return {"features": feature_codes, "actions": action_codes}

    def _ensure_dashboard_for_role(self, role: Role, user: User | None = None) -> Dashboard:
        dashboard, created = Dashboard.objects.get_or_create(
            tenant=str(role.tenant),
            role=role,
            defaults={
                "name": role.name,
                "slug": role.code or self._slugify(role.name),
                "url": f"/dashboard/{role.code or self._slugify(role.name)}/",
                "description": f"{role.name} dashboard",
                "is_active": True,
                "created_by": user,
            },
        )
        if created:
            self._create_default_dashboard_routes(dashboard, user)
            self._add_default_features(dashboard, user)
        return dashboard

    def _create_fallback_dashboard(self, user: User) -> Dashboard:
        tenant = str(user.tenant or uuid.uuid4())
        role_assignment = UserRole.objects.filter(user=user, tenant=tenant, is_deleted=False).order_by("-created_at").first()
        if role_assignment:
            return self._ensure_dashboard_for_role(role_assignment.role, user)
        role, _ = Role.objects.get_or_create(
            tenant=tenant,
            name="Default",
            defaults={"code": "default", "description": "Default dashboard role", "created_by": user},
        )
        return self._ensure_dashboard_for_role(role, user)

    def _get_user_dashboard(self, user: User) -> Dashboard | None:
        role = UserRole.objects.filter(user=user, tenant=str(user.tenant), is_deleted=False).order_by("-created_at").first()
        if role:
            return Dashboard.objects.filter(role=role.role, tenant=str(user.tenant), is_deleted=False).first()
        if self._is_system_admin(user):
            return Dashboard.objects.filter(tenant=str(user.tenant), is_deleted=False).order_by("-created_at").first()
        return None

    def _can_view_dashboard(self, user: User, dashboard: Dashboard) -> bool:
        if self._is_system_admin(user):
            return True
        return bool(UserRole.objects.filter(user=user, role=dashboard.role, tenant=str(user.tenant), is_deleted=False).exists())

    def _create_default_dashboard_routes(self, dashboard: Dashboard, user: User | None) -> None:
        defaults = [
            ("User Profile", "/profile", "person"),
            ("Change Password", "/change-password", "key"),
            ("Notifications", "/notifications", "bell"),
            ("Logout", "/logout", "box-arrow-right"),
        ]
        tenant = str(dashboard.tenant)
        created_by = user if user is not None else dashboard.created_by
        for index, (name, route, icon) in enumerate(defaults, start=1):
            DashboardRoute.objects.get_or_create(
                tenant=tenant,
                dashboard=dashboard,
                route=route,
                defaults={"name": name, "icon": icon, "sort_order": index, "created_by": created_by},
            )

    def _add_default_features(self, dashboard: Dashboard, user: User | None) -> None:
        defaults = [
            ("User Profile", "user-profile", "/profile", "person"),
            ("Change Password", "change-password", "/change-password", "key"),
            ("Notifications", "notifications", "/notifications", "bell"),
            ("Logout", "logout", "/logout", "box-arrow-right"),
        ]
        tenant = str(dashboard.tenant)
        created_by = user if user is not None else dashboard.created_by
        for name, slug, route, icon in defaults:
            feature, _ = Feature.objects.get_or_create(
                tenant=tenant,
                slug=slug,
                defaults={"name": name, "icon": icon, "route": route, "category": "Core", "created_by": created_by},
            )
            DashboardFeature.objects.get_or_create(tenant=tenant, dashboard=dashboard, feature=feature, defaults={"created_by": created_by})

    def _serialize_dashboard(self, dashboard: Dashboard) -> dict[str, Any]:
        return {
            "id": str(dashboard.id),
            "name": dashboard.name,
            "slug": dashboard.slug,
            "url": dashboard.url,
            "description": dashboard.description,
            "is_active": dashboard.is_active,
            "role": {"id": str(dashboard.role.id), "name": dashboard.role.name, "code": dashboard.role.code},
            "features": [self._serialize_feature(feature) for feature in dashboard.features.filter(tenant=str(dashboard.tenant), is_deleted=False).all()],
        }

    def _serialize_feature(self, feature: Feature) -> dict[str, Any]:
        return {"id": str(feature.id), "name": feature.name, "slug": feature.slug, "icon": feature.icon, "route": feature.route, "category": feature.category}

    def _slugify(self, value: str) -> str:
        return slugify(value or "dashboard")

    def _is_system_admin(self, user: User) -> bool:
        return bool(user.is_superuser or user.username == "SYSTEM_ADMIN")

    def _log_audit(self, user: User | None, action: str, details: dict[str, Any] | None = None, actor: User | None = None, request=None) -> None:
        AuditLog.objects.create(
            user=user,
            tenant=str(user.tenant) if user and getattr(user, "tenant", None) else None,
            action=action,
            details=details or {},
            ip_address=self.request.META.get("REMOTE_ADDR") if self.request else None,
            user_agent=self.request.META.get("HTTP_USER_AGENT", "") if self.request else "",
            created_by=actor,
        )


class FeatureService:
    def __init__(self, request=None):
        self.request = request

    def _tenant(self, user: User | None) -> str:
        return str(user.tenant) if user and getattr(user, "tenant", None) else str(uuid.uuid4())

    def is_system_admin(self, user: User) -> bool:
        return bool(user.is_superuser or user.username == "SYSTEM_ADMIN")

    def create_category(self, user: User, data: dict[str, Any]) -> dict[str, Any]:
        if not self.is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can create feature categories.")
        tenant = self._tenant(user)
        category = FeatureCategory.objects.create(
            tenant=tenant,
            name=data["name"],
            code=data.get("code") or slugify(data["name"]),
            description=data.get("description", ""),
            icon=data.get("icon", "circle"),
            display_order=data.get("display_order", 0),
            is_system=data.get("is_system", False),
            created_by=user,
        )
        self._log_audit(user=user, action="feature_category_create", details={"category_id": str(category.id)}, actor=user, request=self.request)
        return self._serialize_category(category)

    def update_category(self, user: User, category: FeatureCategory, data: dict[str, Any]) -> dict[str, Any]:
        if not self.is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can update feature categories.")
        if data.get("name"):
            category.name = data["name"]
        if data.get("code"):
            category.code = data["code"]
        if data.get("description") is not None:
            category.description = data["description"]
        if data.get("icon") is not None:
            category.icon = data["icon"]
        if "display_order" in data:
            category.display_order = data["display_order"]
        if "is_active" in data:
            category.is_active = data["is_active"]
        category.save(update_fields=["name", "code", "description", "icon", "display_order", "is_active", "updated_at"])
        self._log_audit(user=user, action="feature_category_update", details={"category_id": str(category.id)}, actor=user, request=self.request)
        return self._serialize_category(category)

    def delete_category(self, user: User, category: FeatureCategory) -> dict[str, Any]:
        if not self.is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can delete feature categories.")
        if category.features.filter(is_deleted=False).exists():
            raise exceptions.ValidationError("Cannot delete a category that still has features.")
        category.soft_delete(user=user)
        self._log_audit(user=user, action="feature_category_delete", details={"category_id": str(category.id)}, actor=user, request=self.request)
        return {"deleted": True, "category_id": str(category.id)}

    def create_feature(self, user: User, data: dict[str, Any]) -> dict[str, Any]:
        if not self.is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can create features.")
        tenant = self._tenant(user)
        category = None
        feature_category_id = data.get("feature_category_id")
        if feature_category_id:
            category = FeatureCategory.objects.filter(id=feature_category_id, tenant=tenant, is_deleted=False).first()
        if not category and data.get("feature_category"):
            category = FeatureCategory.objects.filter(tenant=tenant, code=data["feature_category"], is_deleted=False).first()
        if not category and data.get("feature_category_id") is None and data.get("feature_category") is None:
            category = None
        feature = Feature.objects.create(
            tenant=tenant,
            feature_category=category,
            name=data["name"],
            slug=data.get("slug") or slugify(data["name"]),
            code=data.get("code") or slugify(data["name"]),
            description=data.get("description", ""),
            icon=data.get("icon", "circle"),
            route=data.get("route", ""),
            api_base_url=data.get("api_base_url", ""),
            display_order=data.get("display_order", 0),
            feature_type=data.get("feature_type", "MENU"),
            category=category.name if category else data.get("category", ""),
            is_visible=data.get("is_visible", True),
            is_assignable=data.get("is_assignable", True),
            is_system=data.get("is_system", False),
            created_by=user,
        )
        self._log_audit(user=user, action="feature_create", details={"feature_id": str(feature.id)}, actor=user, request=self.request)
        return self._serialize_feature(feature)

    def update_feature(self, user: User, feature: Feature, data: dict[str, Any]) -> dict[str, Any]:
        if not self.is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can update features.")
        if data.get("name"):
            feature.name = data["name"]
        if data.get("slug"):
            feature.slug = data["slug"]
        if data.get("code"):
            feature.code = data["code"]
        if data.get("description") is not None:
            feature.description = data["description"]
        if data.get("icon") is not None:
            feature.icon = data["icon"]
        if data.get("route") is not None:
            feature.route = data["route"]
        if data.get("api_base_url") is not None:
            feature.api_base_url = data["api_base_url"]
        if "display_order" in data:
            feature.display_order = data["display_order"]
        if data.get("feature_type"):
            feature.feature_type = data["feature_type"]
        if data.get("category") is not None:
            feature.category = data["category"]
        if "is_visible" in data:
            feature.is_visible = data["is_visible"]
        if "is_assignable" in data:
            feature.is_assignable = data["is_assignable"]
        if "is_active" in data:
            feature.is_active = data["is_active"]
        feature.save(update_fields=["name", "slug", "code", "description", "icon", "route", "api_base_url", "display_order", "feature_type", "category", "is_visible", "is_assignable", "is_active", "updated_at"])
        self._log_audit(user=user, action="feature_update", details={"feature_id": str(feature.id)}, actor=user, request=self.request)
        return self._serialize_feature(feature)

    def delete_feature(self, user: User, feature: Feature) -> dict[str, Any]:
        if not self.is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can delete features.")
        if feature.role_features.filter(is_deleted=False).exists() or feature.dashboard_features.filter(is_deleted=False).exists():
            raise exceptions.ValidationError("Cannot delete a feature that is in use.")
        if feature.is_system:
            raise exceptions.ValidationError("Cannot delete system features.")
        feature.soft_delete(user=user)
        self._log_audit(user=user, action="feature_delete", details={"feature_id": str(feature.id)}, actor=user, request=self.request)
        return {"deleted": True, "feature_id": str(feature.id)}

    def list_features(self, user: User) -> list[dict[str, Any]]:
        tenant = self._tenant(user)
        features = Feature.objects.filter(tenant=tenant, is_deleted=False).select_related("feature_category")
        return [self._serialize_feature(f) for f in features]

    def get_feature(self, user: User, feature_id: str) -> dict[str, Any]:
        tenant = self._tenant(user)
        feature = Feature.objects.filter(id=feature_id, tenant=tenant, is_deleted=False).first()
        if not feature:
            raise exceptions.NotFound("Feature not found.")
        return self._serialize_feature(feature)

    def create_feature_item(self, user: User, feature_id: str, data: dict[str, Any]) -> dict[str, Any]:
        if not self.is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can create feature items.")
        feature = Feature.objects.filter(id=feature_id, tenant=self._tenant(user), is_deleted=False).first()
        if not feature:
            raise exceptions.NotFound("Feature not found.")
        item = FeatureItem.objects.create(
            tenant=self._tenant(user),
            feature=feature,
            title=data["title"],
            route=data.get("route", ""),
            icon=data.get("icon", "circle"),
            display_order=data.get("display_order", 0),
            parent_item=None,
            badge=data.get("badge", ""),
            opens_in_new_tab=data.get("opens_in_new_tab", False),
            permission_code=data.get("permission_code", ""),
            is_visible=data.get("is_visible", True),
            created_by=user,
        )
        self._log_audit(user=user, action="feature_item_create", details={"feature_id": str(feature.id), "item_id": str(item.id)}, actor=user, request=self.request)
        return self._serialize_feature_item(item)

    def list_feature_items(self, user: User, feature_id: str) -> list[dict[str, Any]]:
        tenant = self._tenant(user)
        feature = Feature.objects.filter(id=feature_id, tenant=tenant, is_deleted=False).first()
        if not feature:
            raise exceptions.NotFound("Feature not found.")
        return [self._serialize_feature_item(i) for i in feature.feature_items.filter(tenant=tenant, is_deleted=False).order_by("display_order", "title")]

    def create_feature_action(self, user: User, feature_id: str, data: dict[str, Any]) -> dict[str, Any]:
        if not self.is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can create feature actions.")
        feature = Feature.objects.filter(id=feature_id, tenant=self._tenant(user), is_deleted=False).first()
        if not feature:
            raise exceptions.NotFound("Feature not found.")
        action = FeatureAction.objects.create(
            tenant=self._tenant(user),
            feature=feature,
            name=data["name"],
            code=data.get("code") or slugify(data["name"]),
            http_method=data.get("http_method", "POST"),
            endpoint=data.get("endpoint", ""),
            permission_code=data.get("permission_code", ""),
            description=data.get("description", ""),
            created_by=user,
        )
        self._log_audit(user=user, action="feature_action_create", details={"feature_id": str(feature.id), "action_id": str(action.id)}, actor=user, request=self.request)
        return self._serialize_feature_action(action)

    def list_feature_actions(self, user: User, feature_id: str) -> list[dict[str, Any]]:
        tenant = self._tenant(user)
        feature = Feature.objects.filter(id=feature_id, tenant=tenant, is_deleted=False).first()
        if not feature:
            raise exceptions.NotFound("Feature not found.")
        return [self._serialize_feature_action(a) for a in feature.feature_actions.filter(tenant=tenant, is_deleted=False).order_by("name")]

    def assign_role_feature(self, user: User, role_id: str, data: dict[str, Any]) -> dict[str, Any]:
        if not self.is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can assign features to roles.")
        role = Role.objects.filter(id=role_id, tenant=self._tenant(user), is_deleted=False).first()
        if not role:
            raise exceptions.NotFound("Role not found.")
        feature = Feature.objects.filter(id=data["feature_id"], tenant=self._tenant(user), is_deleted=False).first()
        if not feature:
            raise exceptions.NotFound("Feature not found.")
        assignment, _ = RoleFeature.objects.get_or_create(tenant=self._tenant(user), role=role, feature=feature, defaults={"created_by": user, "enabled": True})
        self._log_audit(user=user, action="role_feature_assign", details={"role_id": str(role.id), "feature_id": str(feature.id)}, actor=user, request=self.request)
        return self._serialize_role_feature(assignment)

    def remove_role_feature(self, user: User, role_id: str, feature_id: str) -> dict[str, Any]:
        if not self.is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can remove features from roles.")
        role = Role.objects.filter(id=role_id, tenant=self._tenant(user), is_deleted=False).first()
        if not role:
            raise exceptions.NotFound("Role not found.")
        assignment = RoleFeature.objects.filter(tenant=self._tenant(user), role=role, feature_id=feature_id, is_deleted=False).first()
        if not assignment:
            raise exceptions.NotFound("Role feature assignment not found.")
        assignment.soft_delete(user=user)
        self._log_audit(user=user, action="role_feature_remove", details={"role_id": str(role.id), "feature_id": feature_id}, actor=user, request=self.request)
        return {"removed": True, "role_id": str(role.id), "feature_id": feature_id}

    def list_role_features(self, user: User, role_id: str) -> list[dict[str, Any]]:
        role = Role.objects.filter(id=role_id, tenant=self._tenant(user), is_deleted=False).first()
        if not role:
            raise exceptions.NotFound("Role not found.")
        return [self._serialize_role_feature(item) for item in role.role_features.filter(tenant=self._tenant(user), is_deleted=False)]

    def assign_role_action(self, user: User, role_id: str, data: dict[str, Any]) -> dict[str, Any]:
        if not self.is_system_admin(user):
            raise exceptions.PermissionDenied("Only system administrators can assign actions to roles.")
        role = Role.objects.filter(id=role_id, tenant=self._tenant(user), is_deleted=False).first()
        if not role:
            raise exceptions.NotFound("Role not found.")
        action = FeatureAction.objects.filter(id=data["action_id"], tenant=self._tenant(user), is_deleted=False).first()
        if not action:
            raise exceptions.NotFound("Feature action not found.")
        assignment, _ = RoleFeatureAction.objects.get_or_create(tenant=self._tenant(user), role=role, feature_action=action, defaults={"created_by": user, "enabled": True})
        self._log_audit(user=user, action="role_action_assign", details={"role_id": str(role.id), "action_id": str(action.id)}, actor=user, request=self.request)
        return self._serialize_role_action(assignment)

    def list_role_actions(self, user: User, role_id: str) -> list[dict[str, Any]]:
        role = Role.objects.filter(id=role_id, tenant=self._tenant(user), is_deleted=False).first()
        if not role:
            raise exceptions.NotFound("Role not found.")
        return [self._serialize_role_action(item) for item in role.role_feature_actions.filter(tenant=self._tenant(user), is_deleted=False)]

    def register_feature(self, user: User, name: str, code: str, feature_type: str = "MENU", route: str = "", category_name: str | None = None, menu_title: str | None = None, menu_route: str | None = None) -> dict[str, Any]:
        category = None
        if category_name:
            category, _ = FeatureCategory.objects.get_or_create(tenant=self._tenant(user), code=slugify(category_name), defaults={"name": category_name, "created_by": user, "is_system": True})
        feature = Feature.objects.create(
            tenant=self._tenant(user),
            feature_category=category,
            name=name,
            slug=slugify(code),
            code=code,
            description=f"Auto-registered feature: {name}",
            icon="circle",
            route=route,
            display_order=0,
            feature_type=feature_type,
            category=category_name or "General",
            is_visible=True,
            is_assignable=True,
            is_system=True,
            created_by=user,
        )
        feature_item = None
        if menu_title or menu_route:
            feature_item = FeatureItem.objects.create(
                tenant=self._tenant(user),
                feature=feature,
                title=menu_title or name,
                route=menu_route or route,
                icon="circle",
                display_order=0,
                created_by=user,
            )
        self._log_audit(user=user, action="feature_register", details={"feature_id": str(feature.id)}, actor=user, request=self.request)
        return {"feature": feature, "feature_item": feature_item}

    def build_dashboard_payload(self, user: User) -> dict[str, Any]:
        tenant = self._tenant(user)
        role = UserRole.objects.filter(user=user, tenant=tenant, is_deleted=False).order_by("-created_at").first()
        assigned_features = Feature.objects.filter(
            tenant=tenant,
            role_features__role=role.role if role else None,
            is_deleted=False,
            is_visible=True,
        ).distinct() if role else Feature.objects.none()
        categories = {}
        for feature in assigned_features.order_by("feature_category__display_order", "display_order", "name"):
            category_name = feature.feature_category.name if feature.feature_category else "General"
            categories.setdefault(category_name, []).append(
                {
                    "title": feature.name,
                    "route": feature.route or f"/{feature.slug}/",
                    "icon": feature.icon,
                }
            )
        sidebar = [{"category": name, "items": items} for name, items in sorted(categories.items(), key=lambda item: item[0])]
        return {"dashboard": {"title": "Dynamic Dashboard", "logo": "", "sidebar": sidebar}}

    def _serialize_category(self, category: FeatureCategory) -> dict[str, Any]:
        return {"id": str(category.id), "name": category.name, "code": category.code, "description": category.description, "icon": category.icon, "display_order": category.display_order, "is_system": category.is_system, "is_active": category.is_active}

    def _serialize_feature(self, feature: Feature) -> dict[str, Any]:
        return {"id": str(feature.id), "feature_category_id": str(feature.feature_category.id) if feature.feature_category else None, "name": feature.name, "slug": feature.slug, "code": feature.code, "description": feature.description, "icon": feature.icon, "route": feature.route, "api_base_url": feature.api_base_url, "display_order": feature.display_order, "feature_type": feature.feature_type, "category": feature.category, "is_visible": feature.is_visible, "is_assignable": feature.is_assignable, "is_system": feature.is_system, "is_active": feature.is_active}

    def _serialize_feature_item(self, item: FeatureItem) -> dict[str, Any]:
        return {"id": str(item.id), "feature_id": str(item.feature_id), "title": item.title, "route": item.route, "icon": item.icon, "display_order": item.display_order, "parent_item_id": str(item.parent_item_id) if item.parent_item_id else None, "badge": item.badge, "opens_in_new_tab": item.opens_in_new_tab, "permission_code": item.permission_code, "is_visible": item.is_visible, "is_active": item.is_active}

    def _serialize_feature_action(self, action: FeatureAction) -> dict[str, Any]:
        return {"id": str(action.id), "feature_id": str(action.feature_id), "name": action.name, "code": action.code, "http_method": action.http_method, "endpoint": action.endpoint, "permission_code": action.permission_code, "description": action.description, "is_active": action.is_active}

    def _serialize_role_feature(self, assignment: RoleFeature) -> dict[str, Any]:
        return {"id": str(assignment.id), "role_id": str(assignment.role_id), "feature_id": str(assignment.feature_id), "enabled": assignment.enabled}

    def _serialize_role_action(self, assignment: RoleFeatureAction) -> dict[str, Any]:
        return {"id": str(assignment.id), "role_id": str(assignment.role_id), "action_id": str(assignment.feature_action_id), "enabled": assignment.enabled}

    def _log_audit(self, user: User | None, action: str, details: dict[str, Any] | None = None, actor: User | None = None, request=None) -> None:
        AuditLog.objects.create(
            user=user,
            tenant=str(user.tenant) if user and getattr(user, "tenant", None) else None,
            action=action,
            details=details or {},
            ip_address=self.request.META.get("REMOTE_ADDR") if self.request else None,
            user_agent=self.request.META.get("HTTP_USER_AGENT", "") if self.request else "",
            created_by=actor,
        )


class AuthService:
    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_MINUTES = 15

    def __init__(self, request=None):
        self.request = request

    def register_user(self, data: dict[str, Any], actor: User | None = None) -> dict[str, Any]:
        tenant = data.get("tenant") or str(uuid.uuid4())
        user = User.objects.create(
            username=data["username"],
            email=data["email"],
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            tenant=str(tenant),
            is_active=True,
            password=make_password(data["password"]),
        )
        user.set_password(data["password"])
        user.password_history = [self._hash_password(data["password"])]
        user.save(update_fields=["password", "password_history"])

        system_role = self._ensure_system_admin_role(user.tenant, actor=user)
        roles = self._resolve_roles(data.get("role_names", []), user.tenant, actor=user)
        if system_role:
            roles = [system_role] + roles
        for role in roles:
            UserRole.objects.create(user=user, role=role, tenant=str(user.tenant), created_by=actor)

        self._log_audit(user=user, action="registration", details={"tenant": str(user.tenant), "roles": [r.name for r in roles]}, actor=actor)
        return self._issue_tokens(user, actor=actor)

    def login_user(self, data: dict[str, Any], request=None) -> dict[str, Any]:
        username = data.get("username")
        email = data.get("email")
        user = self._get_user_for_login(username=username, email=email)
        if user is None:
            raise exceptions.AuthenticationFailed("Invalid credentials.")
        if not user.is_active or user.is_deleted:
            raise exceptions.AuthenticationFailed("Account is inactive.")
        if self._is_account_locked(user):
            raise exceptions.AuthenticationFailed("Account is locked.")
        if not check_password(data["password"], user.password):
            self._record_failed_login(user, request)
            raise exceptions.AuthenticationFailed("Invalid credentials.")
        self._clear_failed_attempts(user)
        self._create_login_history(user, request, status="success")
        self._log_audit(user=user, action="login", details={"status": "success"}, actor=user, request=request)
        return self._issue_tokens(user, actor=user, request=request)

    def logout_user(self, refresh_token_value: str, user: User, request=None) -> dict[str, Any]:
        token_model = self._get_valid_refresh_token(refresh_token_value, user=user)
        token_model.revoke()
        self._log_audit(user=user, action="logout", details={"token_jti": str(token_model.jti)}, actor=user, request=request)
        return {"message": "Logged out successfully."}

    def refresh_token(self, refresh_token_value: str, user: User | None = None, request=None) -> dict[str, Any]:
        token_model = RefreshTokenModel.objects.filter(token_hash=self._hash_token(refresh_token_value), is_deleted=False).first()
        if not token_model or token_model.is_blacklisted or token_model.is_expired or token_model.revoked_at:
            raise exceptions.AuthenticationFailed("Invalid refresh token.")
        if user and token_model.user_id != user.pk:
            raise exceptions.AuthenticationFailed("Invalid refresh token.")
        rotated = self._rotate_refresh_token(token_model, request=request)
        self._log_audit(user=token_model.user, action="refresh_token", details={"token_jti": str(token_model.jti)}, actor=token_model.user, request=request)
        return {"access": rotated["access"], "refresh": rotated["refresh"]}

    def setup_mfa(self, user: User, password: str, device_name: str | None = None) -> dict[str, Any]:
        if not check_password(password, user.password):
            raise exceptions.AuthenticationFailed("Invalid credentials.")
        method, created = MFAMethod.objects.get_or_create(user=user, tenant=str(user.tenant), defaults={"secret": self._generate_secret(), "created_by": user})
        if not created:
            method.secret = self._generate_secret()
        method.is_enabled = True
        method.recovery_codes = self._generate_recovery_codes()
        method.save(update_fields=["secret", "is_enabled", "recovery_codes", "updated_at"])
        self._log_audit(user=user, action="mfa_enable", details={"device_name": device_name or "default"}, actor=user)
        return {"secret": method.secret, "recovery_codes": method.recovery_codes, "otpauth_url": self._build_otpauth_url(user, method.secret)}

    def verify_mfa(self, user: User, code: str, request=None) -> dict[str, Any]:
        method = MFAMethod.objects.filter(user=user, is_deleted=False).first()
        if not method or not self._verify_totp(code, method.secret):
            raise exceptions.ValidationError("Invalid MFA code.")
        method.last_verified_at = timezone.now()
        method.save(update_fields=["last_verified_at", "updated_at"])
        self._log_audit(user=user, action="mfa_verify", details={"status": "success"}, actor=user, request=request)
        return self._issue_tokens(user, actor=user, request=request)

    def get_user_features(self, user: User) -> list[str]:
        roles = Role.objects.filter(user_roles__user=user, tenant=str(user.tenant), is_active=True, is_deleted=False)
        permissions = Permission.objects.filter(role_permissions__role__in=roles, tenant=str(user.tenant), is_active=True, is_deleted=False).distinct()
        return [p.code for p in permissions]

    def get_user_modules(self, user: User) -> list[str]:
        features = self.get_user_features(user)
        modules = sorted({feature.split(".")[0] for feature in features})
        return modules

    def _ensure_system_admin_role(self, tenant: str | None, actor: User | None = None) -> Role | None:
        tenant_key = str(tenant or uuid.uuid4())
        role, created = Role.objects.get_or_create(
            tenant=tenant_key,
            name="SYSTEM_ADMIN",
            defaults={"is_system": True, "is_active": True, "description": "System administrator role", "created_by": actor},
        )
        return role

    def _resolve_roles(self, role_names: list[str], tenant: str | None, actor: User | None = None) -> list[Role]:
        roles: list[Role] = []
        for name in role_names:
            role = Role.objects.filter(tenant=str(tenant), name=name, is_deleted=False).first()
            if role:
                roles.append(role)
        return roles

    def _issue_tokens(self, user: User, actor: User | None = None, request=None) -> dict[str, Any]:
        refresh = RefreshToken.for_user(user)
        token_value = str(refresh)
        refresh_model = RefreshTokenModel.objects.create(
            user=user,
            tenant=str(user.tenant),
            token_hash=self._hash_token(token_value),
            expires_at=timezone.now() + timedelta(days=7),
            device_id=self._device_id_from_request(request),
            ip_address=self._ip_address_from_request(request),
            user_agent=self._user_agent_from_request(request),
            created_by=actor,
        )
        access = str(RefreshToken.for_user(user).access_token)
        return {
            "access": access,
            "refresh": token_value,
            "refresh_token_id": str(refresh_model.jti),
            "user": {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "tenant": str(user.tenant),
            },
        }

    def _rotate_refresh_token(self, token_model: RefreshTokenModel, request=None) -> dict[str, Any]:
        token_model.is_blacklisted = True
        token_model.revoked_at = timezone.now()
        token_model.save(update_fields=["is_blacklisted", "revoked_at", "updated_at"])
        new_refresh = RefreshToken.for_user(token_model.user)
        new_value = str(new_refresh)
        new_model = RefreshTokenModel.objects.create(
            user=token_model.user,
            tenant=str(token_model.user.tenant),
            token_hash=self._hash_token(new_value),
            expires_at=timezone.now() + timedelta(days=7),
            replaced_by=token_model,
            device_id=self._device_id_from_request(request),
            ip_address=self._ip_address_from_request(request),
            user_agent=self._user_agent_from_request(request),
            created_by=token_model.user,
        )
        access = str(new_refresh.access_token)
        return {"access": access, "refresh": new_value, "refresh_token_id": str(new_model.jti)}

    def _get_valid_refresh_token(self, refresh_token_value: str, user: User | None = None) -> RefreshTokenModel:
        token_hash = self._hash_token(refresh_token_value)
        token_model = RefreshTokenModel.objects.filter(token_hash=token_hash, is_deleted=False).first()
        if not token_model:
            raise exceptions.AuthenticationFailed("Invalid refresh token.")
        if token_model.is_blacklisted or token_model.is_expired or token_model.revoked_at:
            raise exceptions.AuthenticationFailed("Invalid refresh token.")
        if user and token_model.user_id != user.pk:
            raise exceptions.AuthenticationFailed("Invalid refresh token.")
        return token_model

    def _create_login_history(self, user: User, request=None, status: str = "success", failure_reason: str = "") -> None:
        LoginHistory.objects.create(
            user=user,
            tenant=str(user.tenant),
            ip_address=self._ip_address_from_request(request),
            user_agent=self._user_agent_from_request(request),
            device=self._device_id_from_request(request),
            status=status,
            failure_reason=failure_reason,
            created_by=user,
        )

    def _record_failed_login(self, user: User, request=None) -> None:
        attempt, created = FailedLoginAttempt.objects.get_or_create(user=user, tenant=str(user.tenant), defaults={"created_by": user})
        attempt.attempt_count += 1
        if attempt.attempt_count >= self.MAX_FAILED_ATTEMPTS:
            attempt.lock(self.LOCKOUT_MINUTES)
        attempt.save(update_fields=["attempt_count", "locked_until", "updated_at"])
        self._create_login_history(user, request, status="failed", failure_reason="Invalid credentials")
        self._log_audit(user=user, action="login", details={"status": "failed"}, actor=user, request=request)

    def _is_account_locked(self, user: User) -> bool:
        attempt = FailedLoginAttempt.objects.filter(user=user, is_deleted=False).order_by("-created_at").first()
        if not attempt:
            return False
        if attempt.locked_until and timezone.now() < attempt.locked_until:
            return True
        return False

    def _clear_failed_attempts(self, user: User) -> None:
        FailedLoginAttempt.objects.filter(user=user, is_deleted=False).update(is_deleted=True, is_active=False, updated_at=timezone.now())

    def _get_user_for_login(self, username: str | None = None, email: str | None = None) -> User | None:
        if email:
            return User.objects.filter(email=email, is_deleted=False).first()
        if username:
            return User.objects.filter(username=username, is_deleted=False).first()
        return None

    def _hash_password(self, password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _generate_secret(self) -> str:
        return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")

    def _generate_recovery_codes(self) -> list[str]:
        return ["".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8)) for _ in range(8)]

    def _build_otpauth_url(self, user: User, secret: str) -> str:
        return f"otpauth://totp/ProudScholar:{user.email}?secret={secret}&issuer=ProudScholar"

    def _generate_totp(self, secret: str, timestamp: int | None = None) -> str:
        normalized_secret = (secret or "").strip().upper()
        if not normalized_secret:
            return "000000"
        padding = "=" * ((8 - len(normalized_secret) % 8) % 8)
        try:
            key = base64.b32decode(normalized_secret + padding, casefold=True)
        except Exception:
            key = normalized_secret.encode("utf-8")

        current = timestamp if timestamp is not None else int(time.time() // 30)
        msg = struct.pack(">Q", current)
        digest = hmac.new(key, msg, hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        binary = struct.unpack(">I", digest[offset: offset + 4])[0] & 0x7FFFFFFF
        return f"{binary % 10**6:06d}"

    def _verify_totp(self, code: str, secret: str) -> bool:
        if not code or len(code) != 6:
            return False
        try:
            int(code)
        except ValueError:
            return False

        current = int(time.time() // 30)
        for offset in range(-1, 2):
            if self._generate_totp(secret, current + offset) == code:
                return True
        return False

    def _ip_address_from_request(self, request=None) -> str | None:
        if not request:
            return None
        return request.META.get("REMOTE_ADDR")

    def _user_agent_from_request(self, request=None) -> str:
        if not request:
            return ""
        return request.META.get("HTTP_USER_AGENT", "")

    def _device_id_from_request(self, request=None) -> str:
        if not request:
            return ""
        return request.META.get("HTTP_X_DEVICE_ID", "")

    def _log_audit(self, user: User | None, action: str, details: dict[str, Any] | None = None, actor: User | None = None, request=None) -> None:
        AuditLog.objects.create(
            user=user,
            tenant=str(user.tenant) if user and getattr(user, "tenant", None) else None,
            action=action,
            details=details or {},
            ip_address=self._ip_address_from_request(request),
            user_agent=self._user_agent_from_request(request),
            created_by=actor,
        )
