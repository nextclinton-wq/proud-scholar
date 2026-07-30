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
from .models import Dashboard, Feature, FeatureAction, FeatureCategory, FeatureItem, MFAMethod, RoleFeature

from .permissions import FeaturePermission, IsSystemAdmin
from .serializers import (
    AssignFeatureSerializer,
    DashboardBannerRequestSerializer,
    DashboardCreateSerializer,
    DashboardQuickActionRequestSerializer,
    DashboardSerializer,
    DashboardStatisticCardRequestSerializer,
    DashboardUpdateSerializer,
    DashboardWidgetRequestSerializer,
    FeatureActionSerializer,
    FeatureCategorySerializer,
    FeatureItemSerializer,
    FeatureSerializer,
    LoginSerializer,
    LogoutSerializer,
    MFASetupSerializer,
    MFAVerifySerializer,
    RefreshTokenSerializer,
    RegisterSerializer,
    RoleFeatureAssignSerializer,
    RoleFeatureActionAssignSerializer,
    RoleFeatureSerializer,
)
from .services import AuthService, DashboardService, FeatureService

User = get_user_model()


def _build_mfa_login_payload(user):
    mfa = MFAMethod.objects.filter(user=user, is_deleted=False, is_enabled=True).first()
    user_info = {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "tenant": str(user.tenant) if user.tenant is not None else None,
    }
    if mfa:
        return (
            {
                "mfa_required": True,
                "user": user_info,
                "otp_instructions": "Check your phone for the 6-digit code in your authenticator app.",
            },
            "MFA verification required.",
        )
    return (
        {
            "mfa_setup_required": True,
            "user": user_info,
            "otp_instructions": "Scan the QR code with Google Authenticator or another authenticator app, then enter the 6-digit code shown on your phone.",
        },
        "MFA setup required.",
    )


class APIResponseMixin:
    def success_response(self, data: Any = None, message: str = "", status_code: int = status.HTTP_200_OK) -> Response:
        return Response({"success": True, "message": message, "data": data or {}, "errors": []}, status=status_code)

    def error_response(self, message: str, errors: list[str] | None = None, status_code: int = status.HTTP_400_BAD_REQUEST) -> Response:
        return Response({"success": False, "message": message, "data": {}, "errors": errors or []}, status=status_code)


class DashboardViewSet(APIResponseMixin, viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = None

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.service = DashboardService(request=request)

    def create(self, request, *args, **kwargs):
        serializer = DashboardCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = self.service.create_dashboard(request.user, serializer.validated_data)
            return self.success_response(result, "Dashboard created successfully.", status.HTTP_201_CREATED)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    def list(self, request, *args, **kwargs):
        try:
            result = self.service.list_dashboards(request.user)
            return self.success_response(result, "Dashboards retrieved successfully.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    def retrieve(self, request, *args, **kwargs):
        dashboard = Dashboard.objects.filter(id=kwargs.get("id"), is_deleted=False).first()
        if not dashboard:
            return self.error_response("Dashboard not found.", ["Dashboard not found."], status.HTTP_404_NOT_FOUND)
        try:
            result = self.service._serialize_dashboard(dashboard)
            return self.success_response(result, "Dashboard retrieved successfully.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        dashboard = Dashboard.objects.filter(id=kwargs.get("id"), is_deleted=False).first()
        if not dashboard:
            return self.error_response("Dashboard not found.", ["Dashboard not found."], status.HTTP_404_NOT_FOUND)
        serializer = DashboardUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = self.service.update_dashboard(request.user, dashboard, serializer.validated_data)
            return self.success_response(result, "Dashboard updated successfully.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        dashboard = Dashboard.objects.filter(id=kwargs.get("id"), is_deleted=False).first()
        if not dashboard:
            return self.error_response("Dashboard not found.", ["Dashboard not found."], status.HTTP_404_NOT_FOUND)
        try:
            result = self.service.delete_dashboard(request.user, dashboard)
            return self.success_response(result, "Dashboard deleted successfully.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="assign-feature")
    def assign_feature(self, request, id=None):
        dashboard = Dashboard.objects.filter(id=id, is_deleted=False).first()
        if not dashboard:
            return self.error_response("Dashboard not found.", ["Dashboard not found."], status.HTTP_404_NOT_FOUND)
        serializer = AssignFeatureSerializer(data=request.data)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = self.service.assign_feature(request.user, dashboard, serializer.validated_data)
            return self.success_response(result, "Feature assigned successfully.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="remove-feature")
    def remove_feature(self, request, id=None):
        dashboard = Dashboard.objects.filter(id=id, is_deleted=False).first()
        if not dashboard:
            return self.error_response("Dashboard not found.", ["Dashboard not found."], status.HTTP_404_NOT_FOUND)
        feature_id = request.data.get("feature_id")
        try:
            result = self.service.remove_feature(request.user, dashboard, feature_id)
            return self.success_response(result, "Feature removed successfully.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["get"], url_path="features")
    def features(self, request, id=None):
        dashboard = Dashboard.objects.filter(id=id, is_deleted=False).first()
        if not dashboard:
            return self.error_response("Dashboard not found.", ["Dashboard not found."], status.HTTP_404_NOT_FOUND)
        try:
            result = self.service.get_dashboard_features(request.user, dashboard)
            return self.success_response(result, "Dashboard features retrieved successfully.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"], url_path="menu")
    def menu(self, request):
        try:
            result = self.service.get_dashboard_menu(request.user)
            return self.success_response(result, "Dashboard menu retrieved successfully.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"], url_path="payload")
    def payload(self, request):
        try:
            result = self.service.get_dashboard_payload(request.user)
            return self.success_response(result, "Dashboard payload retrieved successfully.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"], url_path="widgets")
    def list_widgets(self, request):
        try:
            result = self.service.list_dashboard_widgets(request.user, request.query_params.get("dashboard_id"))
            return self.success_response(result, "Dashboard widgets retrieved successfully.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"], url_path="widgets")
    def create_widget(self, request):
        serializer = DashboardWidgetRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = self.service.create_dashboard_widget(request.user, serializer.validated_data)
            return self.success_response(result, "Dashboard widget created successfully.", status.HTTP_201_CREATED)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["put"], url_path=r"widgets/(?P<widget_id>[^/.]+)")
    def update_widget(self, request, widget_id=None):
        serializer = DashboardWidgetRequestSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = self.service.update_dashboard_widget(request.user, widget_id, serializer.validated_data)
            return self.success_response(result, "Dashboard widget updated successfully.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["delete"], url_path=r"widgets/(?P<widget_id>[^/.]+)")
    def delete_widget(self, request, widget_id=None):
        try:
            result = self.service.delete_dashboard_widget(request.user, widget_id)
            return self.success_response(result, "Dashboard widget deleted successfully.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"], url_path="actions")
    def list_quick_actions(self, request):
        try:
            result = self.service.list_dashboard_actions(request.user)
            return self.success_response(result, "Dashboard quick actions retrieved successfully.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"], url_path="actions")
    def create_quick_action(self, request):
        serializer = DashboardQuickActionRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = self.service.create_dashboard_quick_action(request.user, serializer.validated_data)
            return self.success_response(result, "Dashboard quick action created successfully.", status.HTTP_201_CREATED)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["put"], url_path=r"actions/(?P<action_id>[^/.]+)")
    def update_quick_action(self, request, action_id=None):
        serializer = DashboardQuickActionRequestSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = self.service.update_dashboard_quick_action(request.user, action_id, serializer.validated_data)
            return self.success_response(result, "Dashboard quick action updated successfully.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["delete"], url_path=r"actions/(?P<action_id>[^/.]+)")
    def delete_quick_action(self, request, action_id=None):
        try:
            result = self.service.delete_dashboard_quick_action(request.user, action_id)
            return self.success_response(result, "Dashboard quick action deleted successfully.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"], url_path="statistics")
    def list_statistics(self, request):
        try:
            result = self.service.list_dashboard_statistics(request.user)
            return self.success_response(result, "Dashboard statistic cards retrieved successfully.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"], url_path="statistics")
    def create_statistic_card(self, request):
        serializer = DashboardStatisticCardRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = self.service.create_dashboard_statistic_card(request.user, serializer.validated_data)
            return self.success_response(result, "Dashboard statistic card created successfully.", status.HTTP_201_CREATED)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["put"], url_path=r"statistics/(?P<card_id>[^/.]+)")
    def update_statistic_card(self, request, card_id=None):
        serializer = DashboardStatisticCardRequestSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = self.service.update_dashboard_statistic_card(request.user, card_id, serializer.validated_data)
            return self.success_response(result, "Dashboard statistic card updated successfully.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["delete"], url_path=r"statistics/(?P<card_id>[^/.]+)")
    def delete_statistic_card(self, request, card_id=None):
        try:
            result = self.service.delete_dashboard_statistic_card(request.user, card_id)
            return self.success_response(result, "Dashboard statistic card deleted successfully.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"], url_path="banners")
    def list_banners(self, request):
        try:
            result = self.service.list_dashboard_banners(request.user)
            return self.success_response(result, "Dashboard banners retrieved successfully.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"], url_path="banners")
    def create_banner(self, request):
        serializer = DashboardBannerRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = self.service.create_dashboard_banner(request.user, serializer.validated_data)
            return self.success_response(result, "Dashboard banner created successfully.", status.HTTP_201_CREATED)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["put"], url_path=r"banners/(?P<banner_id>[^/.]+)")
    def update_banner(self, request, banner_id=None):
        serializer = DashboardBannerRequestSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = self.service.update_dashboard_banner(request.user, banner_id, serializer.validated_data)
            return self.success_response(result, "Dashboard banner updated successfully.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["delete"], url_path=r"banners/(?P<banner_id>[^/.]+)")
    def delete_banner(self, request, banner_id=None):
        try:
            result = self.service.delete_dashboard_banner(request.user, banner_id)
            return self.success_response(result, "Dashboard banner deleted successfully.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"], url_path="by-url/(?P<slug>[^/.]+)")
    def by_url(self, request, slug=None):
        try:
            result = self.service.get_dashboard_by_url(request.user, slug)
            return self.success_response(result, "Dashboard retrieved successfully.", status.HTTP_200_OK)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)


class FeatureCategoryViewSet(APIResponseMixin, viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsSystemAdmin]
    serializer_class = FeatureCategorySerializer

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.service = FeatureService(request=request)

    def list(self, request, *args, **kwargs):
        try:
            categories = FeatureCategory.objects.filter(tenant=str(request.user.tenant), is_deleted=False)
            return self.success_response([self.service._serialize_category(category) for category in categories], "Feature categories retrieved successfully.")
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    def create(self, request, *args, **kwargs):
        serializer = FeatureCategorySerializer(data=request.data, context={"tenant": str(request.user.tenant)})
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = self.service.create_category(request.user, serializer.validated_data)
            return self.success_response(result, "Feature category created successfully.", status.HTTP_201_CREATED)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        category = FeatureCategory.objects.filter(id=kwargs.get("id"), tenant=str(request.user.tenant), is_deleted=False).first()
        if not category:
            return self.error_response("Feature category not found.", ["Feature category not found."], status.HTTP_404_NOT_FOUND)
        serializer = FeatureCategorySerializer(data=request.data, context={"tenant": str(request.user.tenant)}, partial=True)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = self.service.update_category(request.user, category, serializer.validated_data)
            return self.success_response(result, "Feature category updated successfully.")
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        category = FeatureCategory.objects.filter(id=kwargs.get("id"), tenant=str(request.user.tenant), is_deleted=False).first()
        if not category:
            return self.error_response("Feature category not found.", ["Feature category not found."], status.HTTP_404_NOT_FOUND)
        try:
            result = self.service.delete_category(request.user, category)
            return self.success_response(result, "Feature category deleted successfully.")
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)


class FeatureViewSet(APIResponseMixin, viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsSystemAdmin]
    serializer_class = FeatureSerializer

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.service = FeatureService(request=request)

    def list(self, request, *args, **kwargs):
        try:
            result = self.service.list_features(request.user)
            return self.success_response(result, "Features retrieved successfully.")
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    def create(self, request, *args, **kwargs):
        serializer = FeatureSerializer(data=request.data, context={"tenant": str(request.user.tenant)})
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = self.service.create_feature(request.user, serializer.validated_data)
            return self.success_response(result, "Feature created successfully.", status.HTTP_201_CREATED)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    def retrieve(self, request, *args, **kwargs):
        try:
            result = self.service.get_feature(request.user, kwargs.get("id"))
            return self.success_response(result, "Feature retrieved successfully.")
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        feature = Feature.objects.filter(id=kwargs.get("id"), tenant=str(request.user.tenant), is_deleted=False).first()
        if not feature:
            return self.error_response("Feature not found.", ["Feature not found."], status.HTTP_404_NOT_FOUND)
        serializer = FeatureSerializer(data=request.data, context={"tenant": str(request.user.tenant)}, partial=True)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = self.service.update_feature(request.user, feature, serializer.validated_data)
            return self.success_response(result, "Feature updated successfully.")
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        feature = Feature.objects.filter(id=kwargs.get("id"), tenant=str(request.user.tenant), is_deleted=False).first()
        if not feature:
            return self.error_response("Feature not found.", ["Feature not found."], status.HTTP_404_NOT_FOUND)
        try:
            result = self.service.delete_feature(request.user, feature)
            return self.success_response(result, "Feature deleted successfully.")
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["get"], url_path="items")
    def items(self, request, id=None):
        try:
            result = self.service.list_feature_items(request.user, id)
            return self.success_response(result, "Feature items retrieved successfully.")
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="items")
    def create_item(self, request, id=None):
        serializer = FeatureItemSerializer(data=request.data)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = self.service.create_feature_item(request.user, id, serializer.validated_data)
            return self.success_response(result, "Feature item created successfully.", status.HTTP_201_CREATED)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["get"], url_path="actions")
    def actions(self, request, id=None):
        try:
            result = self.service.list_feature_actions(request.user, id)
            return self.success_response(result, "Feature actions retrieved successfully.")
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="actions")
    def create_action(self, request, id=None):
        serializer = FeatureActionSerializer(data=request.data)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = self.service.create_feature_action(request.user, id, serializer.validated_data)
            return self.success_response(result, "Feature action created successfully.", status.HTTP_201_CREATED)
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)


class FeatureItemViewSet(APIResponseMixin, viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsSystemAdmin]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.service = FeatureService(request=request)

    def update(self, request, *args, **kwargs):
        item = FeatureItem.objects.filter(id=kwargs.get("id"), tenant=str(request.user.tenant), is_deleted=False).first()
        if not item:
            return self.error_response("Feature item not found.", ["Feature item not found."], status.HTTP_404_NOT_FOUND)
        serializer = FeatureItemSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            item.title = serializer.validated_data.get("title", item.title)
            item.route = serializer.validated_data.get("route", item.route)
            item.icon = serializer.validated_data.get("icon", item.icon)
            item.display_order = serializer.validated_data.get("display_order", item.display_order)
            item.badge = serializer.validated_data.get("badge", item.badge)
            item.opens_in_new_tab = serializer.validated_data.get("opens_in_new_tab", item.opens_in_new_tab)
            item.permission_code = serializer.validated_data.get("permission_code", item.permission_code)
            item.is_visible = serializer.validated_data.get("is_visible", item.is_visible)
            item.save(update_fields=["title", "route", "icon", "display_order", "badge", "opens_in_new_tab", "permission_code", "is_visible", "updated_at"])
            return self.success_response(self.service._serialize_feature_item(item), "Feature item updated successfully.")
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        item = FeatureItem.objects.filter(id=kwargs.get("id"), tenant=str(request.user.tenant), is_deleted=False).first()
        if not item:
            return self.error_response("Feature item not found.", ["Feature item not found."], status.HTTP_404_NOT_FOUND)
        item.soft_delete(user=request.user)
        return self.success_response({"deleted": True, "item_id": str(item.id)}, "Feature item deleted successfully.")


class FeatureActionViewSet(APIResponseMixin, viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsSystemAdmin]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.service = FeatureService(request=request)

    def update(self, request, *args, **kwargs):
        action = FeatureAction.objects.filter(id=kwargs.get("id"), tenant=str(request.user.tenant), is_deleted=False).first()
        if not action:
            return self.error_response("Feature action not found.", ["Feature action not found."], status.HTTP_404_NOT_FOUND)
        serializer = FeatureActionSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            action.name = serializer.validated_data.get("name", action.name)
            action.code = serializer.validated_data.get("code", action.code)
            action.http_method = serializer.validated_data.get("http_method", action.http_method)
            action.endpoint = serializer.validated_data.get("endpoint", action.endpoint)
            action.permission_code = serializer.validated_data.get("permission_code", action.permission_code)
            action.description = serializer.validated_data.get("description", action.description)
            action.is_active = serializer.validated_data.get("is_active", action.is_active)
            action.save(update_fields=["name", "code", "http_method", "endpoint", "permission_code", "description", "is_active", "updated_at"])
            return self.success_response(self.service._serialize_feature_action(action), "Feature action updated successfully.")
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        action = FeatureAction.objects.filter(id=kwargs.get("id"), tenant=str(request.user.tenant), is_deleted=False).first()
        if not action:
            return self.error_response("Feature action not found.", ["Feature action not found."], status.HTTP_404_NOT_FOUND)
        action.soft_delete(user=request.user)
        return self.success_response({"deleted": True, "action_id": str(action.id)}, "Feature action deleted successfully.")


class RoleFeatureViewSet(APIResponseMixin, viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsSystemAdmin]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.service = FeatureService(request=request)

    @action(detail=False, methods=["get"], url_path=r"(?P<role_id>[^/.]+)")
    def list_role_features(self, request, role_id=None):
        try:
            result = self.service.list_role_features(request.user, role_id)
            return self.success_response(result, "Role features retrieved successfully.")
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"], url_path=r"(?P<role_id>[^/.]+)")
    def assign(self, request, role_id=None):
        serializer = RoleFeatureAssignSerializer(data=request.data)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = self.service.assign_role_feature(request.user, role_id, serializer.validated_data)
            return self.success_response(result, "Role feature assigned successfully.")
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["delete"], url_path=r"(?P<role_id>[^/.]+)/(?P<feature_id>[^/.]+)")
    def remove(self, request, role_id=None, feature_id=None):
        try:
            result = self.service.remove_role_feature(request.user, role_id, feature_id)
            return self.success_response(result, "Role feature removed successfully.")
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"], url_path=r"(?P<role_id>[^/.]+)/actions")
    def assign_action(self, request, role_id=None):
        serializer = RoleFeatureActionAssignSerializer(data=request.data)
        if not serializer.is_valid():
            return self.error_response("Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            result = self.service.assign_role_action(request.user, role_id, serializer.validated_data)
            return self.success_response(result, "Role action assigned successfully.")
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"], url_path=r"(?P<role_id>[^/.]+)/actions")
    def list_actions(self, request, role_id=None):
        try:
            result = self.service.list_role_actions(request.user, role_id)
            return self.success_response(result, "Role actions retrieved successfully.")
        except Exception as exc:
            return self.error_response(str(exc), [str(exc)], status.HTTP_400_BAD_REQUEST)


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
