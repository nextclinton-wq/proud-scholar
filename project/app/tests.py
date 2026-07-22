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
