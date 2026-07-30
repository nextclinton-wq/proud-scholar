import base64
import hashlib
import hmac
import struct
import time

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import RequestFactory
from rest_framework import status
from rest_framework.test import APITestCase

from app.current_request import clear_current_request, set_current_request
from app.models import Dashboard, Feature, FeatureAction, FeatureCategory, FeatureItem, Role, RoleFeature, RoleFeatureAction, UserRole

User = get_user_model()


class DashboardAPITests(APITestCase):
    def setUp(self):
        self.system_admin = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="AdminPass123!",
            tenant="11111111-1111-1111-1111-111111111111",
        )
        self.regular_user = User.objects.create_user(
            username="teacher",
            email="teacher@example.com",
            password="TeacherPass123!",
            tenant="11111111-1111-1111-1111-111111111111",
        )
        self.client.force_authenticate(user=self.system_admin)
        self.create_url = reverse("dashboard-list")

    def test_system_admin_can_create_dashboard_with_default_features(self):
        response = self.client.post(
            self.create_url,
            {"dashboard_name": "Head Teacher", "role_name": "Head Teacher", "description": "Head teacher workspace"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        self.assertIn("Head Teacher", response.data["data"]["name"])
        self.assertGreaterEqual(len(response.data["data"]["features"]), 4)

    def test_assign_feature_updates_dashboard_menu(self):
        dashboard_response = self.client.post(
            self.create_url,
            {"dashboard_name": "Finance Manager", "role_name": "Finance Manager"},
            format="json",
        )
        dashboard_id = dashboard_response.data["data"]["id"]
        self.client.post(
            reverse("dashboard-assign-feature", args=[dashboard_id]),
            {"feature_name": "Students", "icon": "users", "route": "/students"},
            format="json",
        )
        menu_response = self.client.get(reverse("dashboard-menu"), format="json")
        self.assertEqual(menu_response.status_code, status.HTTP_200_OK)
        self.assertTrue(menu_response.data["success"])

    def test_regular_user_can_retrieve_menu_without_dashboard_assignment(self):
        regular_user = User.objects.create_user(
            username="teacher2",
            email="teacher2@example.com",
            password="TeacherPass123!",
            tenant="11111111-1111-1111-1111-111111111111",
        )
        self.client.force_authenticate(user=regular_user)

        response = self.client.get(reverse("dashboard-menu"), format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertIn("menu", response.data["data"])
        self.assertGreaterEqual(len(response.data["data"]["menu"]), 1)


class TenantAwareModelTests(APITestCase):
    def test_tenant_aware_manager_filters_by_tenant(self):
        factory = RequestFactory()
        tenant_id = "33333333-3333-3333-3333-333333333333"
        user = User.objects.create_user(
            username="tenant_user",
            email="tenant_user@example.com",
            password="TenantPass123!",
            tenant=tenant_id,
        )
        request = factory.get("/")
        request.user = user
        set_current_request(request)

        feature = Feature.objects.create(
            name="Tenant Feature",
            code="tenant_feature",
            feature_type="MENU",
            route="/tenant-feature/",
        )
        Feature.objects.create(
            tenant="44444444-4444-4444-4444-444444444444",
            name="Other Tenant Feature",
            code="other_tenant_feature",
            feature_type="MENU",
            route="/other-tenant-feature/",
        )

        tenant_features = Feature.objects.for_tenant()
        self.assertEqual(tenant_features.count(), 1)
        self.assertEqual(tenant_features.first().id, feature.id)

        clear_current_request()

    def test_active_and_inactive_manager_filters(self):
        tenant_id = "55555555-5555-5555-5555-555555555555"
        active_feature = Feature.objects.create(
            tenant=tenant_id,
            name="Active Feature",
            code="active_feature",
            feature_type="MENU",
            route="/active-feature/",
            is_active=True,
        )
        inactive_feature = Feature.objects.create(
            tenant=tenant_id,
            name="Inactive Feature",
            code="inactive_feature",
            feature_type="MENU",
            route="/inactive-feature/",
            is_active=False,
        )

        active_features = Feature.active_objects.for_tenant(tenant_id)
        self.assertIn(active_feature, list(active_features))
        self.assertNotIn(inactive_feature, list(active_features))

        inactive_features = Feature.inactive_objects.for_tenant(tenant_id)
        self.assertIn(inactive_feature, list(inactive_features))
        self.assertNotIn(active_feature, list(inactive_features))


class FeatureFrameworkAPITests(APITestCase):
    def setUp(self):
        self.system_admin = User.objects.create_superuser(
            username="featureadmin",
            email="featureadmin@example.com",
            password="FeaturePass123!",
            tenant="22222222-2222-2222-2222-222222222222",
        )
        self.regular_user = User.objects.create_user(
            username="featureuser",
            email="featureuser@example.com",
            password="FeaturePass123!",
            tenant="22222222-2222-2222-2222-222222222222",
        )
        self.client.force_authenticate(user=self.system_admin)
        self.features_url = reverse("feature-list")
        self.categories_url = reverse("feature-category-list")
        self.roles_url = reverse("role-feature-list", kwargs={"role_id": "00000000-0000-0000-0000-000000000000"})

    def test_system_admin_can_create_category_and_feature(self):
        category_response = self.client.post(
            self.categories_url,
            {"name": "Academic", "code": "academic", "description": "Academic features", "icon": "school"},
            format="json",
        )
        self.assertEqual(category_response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(category_response.data["success"])

        feature_response = self.client.post(
            self.features_url,
            {"name": "Students", "code": "students", "feature_type": "MENU", "feature_category_id": category_response.data["data"]["id"], "route": "/students"},
            format="json",
        )
        self.assertEqual(feature_response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(feature_response.data["success"])
        self.assertEqual(feature_response.data["data"]["code"], "students")

    def test_regular_user_cannot_create_feature(self):
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.post(
            self.features_url,
            {"name": "Finance", "code": "finance", "feature_type": "MENU"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_role_feature_assignment_and_dashboard_generation(self):
        role = self.system_admin.user_roles.create(role=Role.objects.create(tenant=str(self.system_admin.tenant), name="Academic Lead", code="academic_lead", created_by=self.system_admin), tenant=str(self.system_admin.tenant), created_by=self.system_admin)
        feature = Feature.objects.create(tenant=str(self.system_admin.tenant), name="Students", code="students", feature_type="MENU", route="/students", created_by=self.system_admin)
        FeatureItem.objects.create(tenant=str(self.system_admin.tenant), feature=feature, title="Students", route="/students", icon="people", display_order=1, created_by=self.system_admin)

        assign_response = self.client.post(
            reverse("role-feature-list", kwargs={"role_id": role.role.id}),
            {"feature_id": str(feature.id)},
            format="json",
        )
        self.assertEqual(assign_response.status_code, status.HTTP_200_OK)
        self.assertTrue(assign_response.data["success"])

        dashboard_response = self.client.get(reverse("dashboard-menu"), format="json")
        self.assertEqual(dashboard_response.status_code, status.HTTP_200_OK)
        self.assertTrue(dashboard_response.data["success"])

    def test_register_feature_helper_creates_feature_and_menu(self):
        from app.services import FeatureService

        service = FeatureService(request=None)
        result = service.register_feature(
            user=self.system_admin,
            name="Attendance",
            code="attendance",
            feature_type="MENU",
            route="/attendance",
            category_name="Academic",
            menu_title="Attendance",
            menu_route="/attendance",
        )
        self.assertTrue(result["feature"].is_active)
        self.assertTrue(result["feature_item"].is_active)


class AuthAPITests(APITestCase):
    def setUp(self):
        self.register_url = reverse("auth-register")
        self.login_url = reverse("auth-login")
        self.logout_url = reverse("auth-logout")
        self.refresh_url = reverse("auth-refresh-token")
        self.mfa_setup_url = reverse("auth-mfa-setup")
        self.mfa_verify_url = reverse("auth-mfa-verify")

    def test_register_and_login_flow(self):
        response = self.client.post(
            self.register_url,
            {
                "username": "alice",
                "email": "alice@example.com",
                "password": "StrongPass123!",
                "password_confirm": "StrongPass123!",
                "tenant": "11111111-1111-1111-1111-111111111111",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])

        login_response = self.client.post(
            self.login_url,
            {"username": "alice", "password": "StrongPass123!"},
            format="json",
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)

    def test_logout_requires_refresh_token(self):
        response = self.client.post(self.logout_url, {"refresh_token": "invalid"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_superuser_mfa_setup_accepts_pending_user(self):
        superuser = User.objects.create_superuser(
            username="clinton",
            email="clinton@example.com",
            password="Clints256",
            tenant="60cbeaea-7f9f-41df-afbf-369058ac445b",
        )

        response = self.client.post(
            self.mfa_setup_url,
            {"username": "clinton", "password": "Clints256", "device_name": "Google Authenticator"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertIn("secret", response.data["data"])
        self.assertIn("otpauth_url", response.data["data"])

    def test_superuser_login_then_mfa_setup_flow(self):
        superuser = User.objects.create_superuser(
            username="clinton",
            email="clinton@example.com",
            password="Clints256",
            tenant="60cbeaea-7f9f-41df-afbf-369058ac445b",
        )

        login_response = self.client.post(
            self.login_url,
            {"username": "clinton", "password": "Clints256"},
            format="json",
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertTrue(login_response.data["success"])
        self.assertIn("mfa_setup_required", login_response.data["data"])
        self.assertTrue(login_response.data["data"]["mfa_setup_required"])
        self.assertIn("user", login_response.data["data"])

        setup_response = self.client.post(
            self.mfa_setup_url,
            {
                "username": login_response.data["data"]["user"]["username"],
                "password": "Clints256",
                "device_name": "Google Authenticator",
            },
            format="json",
        )
        self.assertEqual(setup_response.status_code, status.HTTP_200_OK)
        self.assertTrue(setup_response.data["success"])
        self.assertIn("secret", setup_response.data["data"])
        self.assertIn("otpauth_url", setup_response.data["data"])

    def test_superuser_mfa_verify_accepts_pending_user(self):
        superuser = User.objects.create_superuser(
            username="clinton",
            email="clinton@example.com",
            password="Clints256",
            tenant="60cbeaea-7f9f-41df-afbf-369058ac445b",
        )
        from app.models import MFAMethod
        MFAMethod.objects.create(user=superuser, tenant=str(superuser.tenant), secret="SECRET123456", is_enabled=True)

        response = self.client.post(
            self.mfa_verify_url,
            {"username": "clinton", "code": "123456"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertIn("access", response.data["data"])
        self.assertIn("refresh", response.data["data"])

    def test_superuser_login_requires_mfa_setup(self):
        superuser = User.objects.create_superuser(
            username="clinton",
            email="clinton@example.com",
            password="Clints256",
            tenant="60cbeaea-7f9f-41df-afbf-369058ac445b",
        )
        self.assertTrue(superuser.is_superuser)

        login_response = self.client.post(
            self.login_url,
            {"username": "clinton", "password": "Clints256"},
            format="json",
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertTrue(login_response.data["success"])
        self.assertIn("mfa_setup_required", login_response.data["data"])
        self.assertTrue(login_response.data["data"]["mfa_setup_required"])

    def test_mfa_verify_accepts_real_totp_and_rejects_invalid_code(self):
        superuser = User.objects.create_superuser(
            username="totpuser",
            email="totp@example.com",
            password="StrongPass123!",
            tenant="69b0f36a-2c4a-4af4-8c9f-760b4cb9d95c",
        )

        setup_response = self.client.post(
            self.mfa_setup_url,
            {"username": "totpuser", "password": "StrongPass123!", "device_name": "Pixel 8"},
            format="json",
        )
        self.assertEqual(setup_response.status_code, status.HTTP_200_OK)
        secret = setup_response.data["data"]["secret"]

        def generate_totp(secret_value: str, current_time: int | None = None) -> str:
            normalized_secret = secret_value.strip().upper()
            padding = "=" * ((8 - len(normalized_secret) % 8) % 8)
            key = base64.b32decode(normalized_secret + padding, casefold=True)
            timestamp = current_time if current_time is not None else int(time.time() // 30)
            msg = struct.pack(">Q", timestamp)
            digest = hmac.new(key, msg, hashlib.sha1).digest()
            offset = digest[-1] & 0x0F
            binary = struct.unpack(">I", digest[offset: offset + 4])[0] & 0x7FFFFFFF
            otp = binary % 10**6
            return f"{otp:06d}"

        valid_code = generate_totp(secret)
        invalid_code = str((int(valid_code) + 1) % 1000000).zfill(6)

        valid_response = self.client.post(self.mfa_verify_url, {"username": "totpuser", "code": valid_code}, format="json")
        self.assertEqual(valid_response.status_code, status.HTTP_200_OK)
        self.assertTrue(valid_response.data["success"])

        invalid_response = self.client.post(self.mfa_verify_url, {"username": "totpuser", "code": invalid_code}, format="json")
        self.assertEqual(invalid_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(invalid_response.data["success"])
