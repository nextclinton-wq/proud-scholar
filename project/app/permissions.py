from __future__ import annotations

from rest_framework.permissions import BasePermission


class FeaturePermission(BasePermission):
    """Allow access when the user has the required feature."""

    required_feature = None

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        if not self.required_feature:
            return True
        user_features = getattr(request.user, "feature_cache", None) or []
        return self.required_feature in user_features


class IsSystemAdmin(BasePermission):
    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.is_superuser or request.user.username == "SYSTEM_ADMIN"
