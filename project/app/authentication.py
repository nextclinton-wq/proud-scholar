from __future__ import annotations

from rest_framework_simplejwt.authentication import JWTAuthentication


class CustomJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        auth = super().authenticate(request)
        if auth is None:
            return None
        user, token = auth
        user.feature_cache = []
        return user, token
