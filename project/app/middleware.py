from __future__ import annotations

from django.http import HttpRequest

from .current_request import clear_current_request, set_current_request


class CurrentRequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        set_current_request(request)
        try:
            response = self.get_response(request)
            return response
        finally:
            clear_current_request()
