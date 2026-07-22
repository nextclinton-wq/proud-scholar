from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from .permissions import FeaturePermission, IsSystemAdmin
from .serializers import (
    LoginSerializer,
    LogoutSerializer,
    MFASetupSerializer,
    MFAVerifySerializer,
    RefreshTokenSerializer,
    RegisterSerializer,
)
from .services import AuthService

User = get_user_model()


class APIResponseMixin:
    def success_response(self, data: Any = None, message: str = "", status_code: int = status.HTTP_200_OK) -> Response:
        return Response({"success": True, "message": message, "data": data or {}, "errors": []}, status=status_code)

    def error_response(self, message: str, errors: list[str] | None = None, status_code: int = status.HTTP_400_BAD_REQUEST) -> Response:
        return Response({"success": False, "message": message, "data": {}, "errors": errors or []}, status=status_code)


class AuthViewSet(APIResponseMixin, viewsets.ViewSet):
    permission_classes = [AllowAny]
    serializer_class = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.service = AuthService(request=self.request)

    def create(self, request, *args, **kwargs):
        return self.register(request)

    def register(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = AuthService(request=request).register_user(serializer.validated_data, actor=request.user if request.user.is_authenticated else None)
            return self.success_response(result, "User registered successfully.", status.HTTP_201_CREATED)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"], url_path="login")
    def login(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = AuthService(request=request).login_user(serializer.validated_data, request=request)
            return self.success_response(result, "Login successful.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_401_UNAUTHORIZED)

    @action(detail=False, methods=["post"], url_path="logout")
    def logout(self, request):
        serializer = LogoutSerializer(data=request.data)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = AuthService(request=request).logout_user(serializer.validated_data["refresh_token"], request.user, request=request)
            return self.success_response(result, "Logout successful.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"], url_path="refresh-token")
    def refresh_token(self, request):
        serializer = RefreshTokenSerializer(data=request.data)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = AuthService(request=request).refresh_token(serializer.validated_data["refresh_token"], request.user if request.user.is_authenticated else None, request=request)
            return self.success_response(result, "Token refreshed successfully.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_401_UNAUTHORIZED)

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated], url_path="mfa/setup")
    def mfa_setup(self, request):
        serializer = MFASetupSerializer(data=request.data)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = AuthService(request=request).setup_mfa(request.user, serializer.validated_data["password"], serializer.validated_data.get("device_name"))
            return self.success_response(result, "MFA setup complete.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated], url_path="mfa/verify")
    def mfa_verify(self, request):
        serializer = MFAVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = AuthService(request=request).verify_mfa(request.user, serializer.validated_data["code"], request=request)
            return self.success_response(result, "MFA verified successfully.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated], url_path="me")
    def me(self, request):
        return self.success_response({"id": str(request.user.id), "username": request.user.username, "email": request.user.email, "tenant": str(request.user.tenant)}, "Profile loaded.", status.HTTP_200_OK)

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated, FeaturePermission], url_path="features")
    def features(self, request):
        features = AuthService().get_user_features(request.user)
        return self.success_response({"features": features, "modules": AuthService().get_user_modules(request.user)}, "Features retrieved.", status.HTTP_200_OK)
