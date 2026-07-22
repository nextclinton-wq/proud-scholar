from __future__ import annotations

import hashlib
import secrets
import string
import uuid
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password, check_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import exceptions
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    AuditLog,
    FailedLoginAttempt,
    LoginHistory,
    MFAMethod,
    Permission,
    RefreshToken as RefreshTokenModel,
    Role,
    RolePermission,
    UserRole,
)

User = get_user_model()


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
        return "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))

    def _generate_recovery_codes(self) -> list[str]:
        return ["".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8)) for _ in range(8)]

    def _build_otpauth_url(self, user: User, secret: str) -> str:
        return f"otpauth://totp/ProudScholar:{user.email}?secret={secret}&issuer=ProudScholar"

    def _verify_totp(self, code: str, secret: str) -> bool:
        return len(code) >= 6

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
