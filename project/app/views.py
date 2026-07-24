from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from rest_framework import exceptions, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.views.generic import TemplateView
import json
from django.contrib.auth.hashers import check_password
from .models import MFAMethod

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


def _build_mfa_login_payload(user):
    if not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
        return None

    mfa = MFAMethod.objects.filter(user=user, is_deleted=False, is_enabled=True).first()
    user_info = {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "tenant": str(user.tenant) if user.tenant is not None else None,
    }
    if mfa:
        return ({"mfa_required": True, "user": user_info}, "MFA verification required.")
    return ({"mfa_setup_required": True, "user": user_info}, "MFA setup required.")


class APIResponseMixin:
    def success_response(self, data: Any = None, message: str = "", status_code: int = status.HTTP_200_OK) -> Response:
        return Response({"success": True, "message": message, "data": data or {}, "errors": []}, status=status_code)

    def error_response(self, message: str, errors: list[str] | None = None, status_code: int = status.HTTP_400_BAD_REQUEST) -> Response:
        return Response({"success": False, "message": message, "data": {}, "errors": errors or []}, status=status_code)


class AuthViewSet(APIResponseMixin, viewsets.ViewSet):
    permission_classes = [AllowAny]
    serializer_class = None

    def initial(self, request, *args, **kwargs):
        """Perform per-request initialization and attach the service with request context."""
        super().initial(request, *args, **kwargs)
        self.service = AuthService(request=request)

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

        service = AuthService(request=request)
        username = serializer.validated_data.get("username")
        email = serializer.validated_data.get("email")
        user = service._get_user_for_login(username=username, email=email)
        if user is None:
            return self.error_response("Invalid credentials.", ["Invalid credentials."], status.HTTP_401_UNAUTHORIZED)
        if not user.is_active or getattr(user, "is_deleted", False):
            return self.error_response("Account is inactive.", ["Account is inactive."], status.HTTP_401_UNAUTHORIZED)
        if not check_password(serializer.validated_data["password"], user.password):
            try:
                service._record_failed_login(user, request)
            except Exception:
                pass
            return self.error_response("Invalid credentials.", ["Invalid credentials."], status.HTTP_401_UNAUTHORIZED)

        mfa_payload = _build_mfa_login_payload(user)
        if mfa_payload:
            payload, message = mfa_payload
            return self.success_response(payload, message)

        try:
            result = service.login_user(serializer.validated_data, request=request)
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

    def _get_mfa_user(self, request, validated_data):
        if request.user.is_authenticated and getattr(request.user, "is_active", False) and not getattr(request.user, "is_deleted", False):
            return request.user
        username = validated_data.get("username")
        email = validated_data.get("email")
        user = AuthService(request=request)._get_user_for_login(username=username, email=email)
        if user is None or not user.is_active or getattr(user, "is_deleted", False):
            raise exceptions.AuthenticationFailed("Invalid credentials.")
        return user

    @action(detail=False, methods=["post"], url_path="mfa/setup")
    def mfa_setup(self, request):
        serializer = MFASetupSerializer(data=request.data)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            user = self._get_mfa_user(request, serializer.validated_data)
            result = AuthService(request=request).setup_mfa(user, serializer.validated_data["password"], serializer.validated_data.get("device_name"))
            return self.success_response(result, "MFA setup complete.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"], url_path="mfa/verify")
    def mfa_verify(self, request):
        serializer = MFAVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            user = self._get_mfa_user(request, serializer.validated_data)
            result = AuthService(request=request).verify_mfa(user, serializer.validated_data["code"], request=request)
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


@csrf_exempt
def signin_view(request):
    """Support POSTs sent to /signin/ (legacy pages) and render the welcome template on GET.

    POST: accept JSON or form-encoded body, validate with LoginSerializer, and call AuthService.login_user.
    This endpoint is csrf_exempt to support legacy form posts that don't include the token.
    """
    if request.method == "GET":
        return TemplateView.as_view(template_name='welcome.html')(request)

    if request.method == "POST":
        try:
            if request.content_type and 'application/json' in request.content_type:
                payload = json.loads(request.body.decode('utf-8') or '{}')
            else:
                payload = request.POST.dict()
        except Exception:
            payload = {}

        serializer = LoginSerializer(data=payload)
        if not serializer.is_valid():
            return JsonResponse({"success": False, "message": "Validation failed.", "data": {}, "errors": serializer.errors}, status=400)
        # Validate credentials first so we can enforce MFA for admin users
        service = AuthService(request=request)
        username = serializer.validated_data.get("username")
        email = serializer.validated_data.get("email")
        user = service._get_user_for_login(username=username, email=email)
        if user is None:
            return JsonResponse({"success": False, "message": "Invalid credentials.", "data": {}, "errors": ["Invalid credentials."]}, status=401)
        if not user.is_active or getattr(user, "is_deleted", False):
            return JsonResponse({"success": False, "message": "Account is inactive.", "data": {}, "errors": ["Account is inactive."]}, status=401)
        if not check_password(serializer.validated_data["password"], user.password):
            try:
                service._record_failed_login(user, request)
            except Exception:
                pass
            return JsonResponse({"success": False, "message": "Invalid credentials.", "data": {}, "errors": ["Invalid credentials."]}, status=401)

        mfa_payload = _build_mfa_login_payload(user)
        if mfa_payload:
            payload, message = mfa_payload
            return JsonResponse({"success": True, "message": message, "data": payload, "errors": []}, status=200)

        try:
            result = service.login_user(serializer.validated_data, request=request)
            return JsonResponse({"success": True, "message": "Login successful.", "data": result, "errors": []}, status=200)
        except Exception as exc:
            return JsonResponse({"success": False, "message": str(exc), "data": {}, "errors": [str(exc)]}, status=401)

    return JsonResponse({"success": False, "message": "Method not allowed.", "data": {}, "errors": []}, status=405)
