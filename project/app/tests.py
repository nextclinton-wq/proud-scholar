from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


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
