from __future__ import annotations

import uuid
from typing import Any

from django.contrib.auth import password_validation
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

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
