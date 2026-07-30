from __future__ import annotations

import uuid
from typing import Any

from django.contrib.auth import password_validation
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import DashboardBanner, DashboardQuickAction, DashboardStatisticCard, DashboardWidget, Feature, FeatureAction, FeatureCategory, FeatureItem, Role, RoleFeature

User = get_user_model()


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    tenant = serializers.UUIDField(required=False, allow_null=True)
    role_names = serializers.ListField(child=serializers.CharField(), required=False, allow_empty=True)

    def validate_username(self, value: str) -> str:
        if User.objects.filter(username=value, is_deleted=False).exists():
            raise serializers.ValidationError("A user with that username already exists.")
        return value

    def validate_email(self, value: str) -> str:
        if User.objects.filter(email=value, is_deleted=False).exists():
            raise serializers.ValidationError("A user with that email already exists.")
        return value

    def validate_password(self, value: str) -> str:
        try:
            password_validation.validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        password = attrs.get("password")
        password_confirm = attrs.get("password_confirm")
        if password and password_confirm and password != password_confirm:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        username = attrs.get("username")
        email = attrs.get("email")
        password = attrs.get("password")
        if not username and not email:
            raise serializers.ValidationError({"username": "Either username or email is required."})
        if username and email:
            raise serializers.ValidationError({"username": "Provide either username or email, not both."})
        if not password:
            raise serializers.ValidationError({"password": "This field is required."})
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()


class RefreshTokenSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()


class MFASetupSerializer(serializers.Serializer):
    username = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True)
    device_name = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        username = attrs.get("username")
        email = attrs.get("email")
        if not username and not email:
            raise serializers.ValidationError({"username": "Either username or email is required."})
        return attrs


class MFAVerifySerializer(serializers.Serializer):
    username = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    code = serializers.CharField(max_length=10)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        username = attrs.get("username")
        email = attrs.get("email")
        if not username and not email:
            raise serializers.ValidationError({"username": "Either username or email is required."})
        return attrs


class PermissionSerializer(serializers.Serializer):
    module = serializers.CharField(max_length=100)
    action = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True)


class RoleCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True)
    code = serializers.CharField(max_length=100, required=False, allow_blank=True)


class RolePermissionSerializer(serializers.Serializer):
    permission_ids = serializers.ListField(child=serializers.UUIDField(), required=True)


class UserRoleSerializer(serializers.Serializer):
    role_ids = serializers.ListField(child=serializers.UUIDField(), required=True)


class DashboardCreateSerializer(serializers.Serializer):
    dashboard_name = serializers.CharField(max_length=100)
    role_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    slug = serializers.CharField(max_length=100, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False, default=True)


class DashboardUpdateSerializer(serializers.Serializer):
    dashboard_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    role_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    slug = serializers.CharField(max_length=100, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)


class AssignFeatureSerializer(serializers.Serializer):
    feature_id = serializers.UUIDField(required=False, allow_null=True)
    feature_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    feature_slug = serializers.CharField(max_length=100, required=False, allow_blank=True)
    icon = serializers.CharField(max_length=50, required=False, allow_blank=True)
    route = serializers.CharField(max_length=255, required=False, allow_blank=True)
    category = serializers.CharField(max_length=100, required=False, allow_blank=True)


class FeatureCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = FeatureCategory
        fields = ["id", "name", "code", "description", "icon", "display_order", "is_system", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_code(self, value: str) -> str:
        tenant = self.context.get("tenant")
        if FeatureCategory.objects.filter(tenant=tenant, code=value, is_deleted=False).exists():
            raise serializers.ValidationError("Feature category code already exists.")
        return value


class FeatureSerializer(serializers.ModelSerializer):
    feature_category_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Feature
        fields = ["id", "feature_category", "feature_category_id", "name", "slug", "code", "description", "icon", "route", "api_base_url", "display_order", "feature_type", "category", "is_visible", "is_assignable", "is_system", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at", "feature_category"]

    def validate_code(self, value: str) -> str:
        tenant = self.context.get("tenant")
        if Feature.objects.filter(tenant=tenant, code=value, is_deleted=False).exists():
            raise serializers.ValidationError("Feature code already exists.")
        return value

    def validate_route(self, value: str) -> str:
        tenant = self.context.get("tenant")
        if value and Feature.objects.filter(tenant=tenant, route=value, is_deleted=False).exists():
            raise serializers.ValidationError("Feature route already exists.")
        return value

    def create(self, validated_data):
        feature_category_id = validated_data.pop("feature_category_id", None)
        if feature_category_id:
            category = FeatureCategory.objects.filter(id=feature_category_id, is_deleted=False).first()
            if category:
                validated_data["feature_category"] = category
        return super().create(validated_data)


class FeatureItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeatureItem
        fields = ["id", "feature", "title", "route", "icon", "display_order", "parent_item", "badge", "opens_in_new_tab", "permission_code", "is_visible", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class FeatureActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeatureAction
        fields = ["id", "feature", "name", "code", "http_method", "endpoint", "permission_code", "description", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "name", "code", "description", "is_system", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "is_system", "created_at", "updated_at"]


class DashboardWidgetRequestSerializer(serializers.Serializer):
    dashboard_id = serializers.UUIDField(required=True)
    title = serializers.CharField(max_length=100)
    widget_type = serializers.CharField(max_length=100)
    feature_id = serializers.UUIDField(required=False, allow_null=True)
    display_order = serializers.IntegerField(required=False, default=0)
    width = serializers.IntegerField(required=False, default=1)
    height = serializers.IntegerField(required=False, default=1)
    configuration = serializers.JSONField(required=False, default=dict)
    is_visible = serializers.BooleanField(required=False, default=True)


class DashboardQuickActionRequestSerializer(serializers.Serializer):
    dashboard_id = serializers.UUIDField(required=True)
    feature_action_id = serializers.UUIDField(required=True)
    display_order = serializers.IntegerField(required=False, default=0)
    icon = serializers.CharField(max_length=50, required=False, allow_blank=True)
    color = serializers.CharField(max_length=30, required=False, allow_blank=True)


class DashboardStatisticCardRequestSerializer(serializers.Serializer):
    dashboard_id = serializers.UUIDField(required=True)
    title = serializers.CharField(max_length=100)
    feature_id = serializers.UUIDField(required=False, allow_null=True)
    api_endpoint = serializers.CharField(max_length=255, required=False, allow_blank=True)
    icon = serializers.CharField(max_length=50, required=False, allow_blank=True)
    display_order = serializers.IntegerField(required=False, default=0)
    refresh_interval = serializers.IntegerField(required=False, default=60)


class DashboardBannerRequestSerializer(serializers.Serializer):
    dashboard_id = serializers.UUIDField(required=True)
    title = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True)
    image = serializers.CharField(required=False, allow_blank=True)
    button_text = serializers.CharField(required=False, allow_blank=True)
    button_route = serializers.CharField(required=False, allow_blank=True)
    display_order = serializers.IntegerField(required=False, default=0)


class DashboardWidgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardWidget
        fields = ["id", "dashboard", "title", "widget_type", "feature", "display_order", "width", "height", "configuration", "is_visible", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class DashboardQuickActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardQuickAction
        fields = ["id", "dashboard", "feature_action", "display_order", "icon", "color", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class DashboardStatisticCardSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardStatisticCard
        fields = ["id", "dashboard", "title", "feature", "api_endpoint", "icon", "display_order", "refresh_interval", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class DashboardBannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardBanner
        fields = ["id", "dashboard", "title", "description", "image", "button_text", "button_route", "display_order", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class RoleFeatureAssignSerializer(serializers.Serializer):
    feature_id = serializers.UUIDField()


class RoleFeatureActionAssignSerializer(serializers.Serializer):
    action_id = serializers.UUIDField()


class RoleFeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoleFeature
        fields = ["id", "role", "feature", "enabled", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class DashboardSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    slug = serializers.CharField(read_only=True)
    url = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    role = serializers.DictField(read_only=True)
    features = serializers.ListField(read_only=True)
