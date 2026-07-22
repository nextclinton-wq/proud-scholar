from django.urls import path

from .views import AuthViewSet

urlpatterns = [
    path("auth/register", AuthViewSet.as_view({"post": "register"}), name="auth-register"),
    path("auth/login", AuthViewSet.as_view({"post": "login"}), name="auth-login"),
    path("auth/logout", AuthViewSet.as_view({"post": "logout"}), name="auth-logout"),
    path("auth/refresh-token", AuthViewSet.as_view({"post": "refresh_token"}), name="auth-refresh-token"),
    path("auth/mfa/setup", AuthViewSet.as_view({"post": "mfa_setup"}), name="auth-mfa-setup"),
    path("auth/mfa/verify", AuthViewSet.as_view({"post": "mfa_verify"}), name="auth-mfa-verify"),
    path("auth/me", AuthViewSet.as_view({"get": "me"}), name="auth-me"),
    path("auth/features", AuthViewSet.as_view({"get": "features"}), name="auth-features"),
]
