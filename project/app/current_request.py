from __future__ import annotations

import threading
from typing import Optional

from django.http import HttpRequest
from django.contrib.auth import get_user_model

_thread_locals = threading.local()


def set_current_request(request: HttpRequest) -> None:
    _thread_locals.request = request


def get_current_request() -> Optional[HttpRequest]:
    return getattr(_thread_locals, "request", None)


def clear_current_request() -> None:
    if hasattr(_thread_locals, "request"):
        del _thread_locals.request


def get_current_user():
    request = get_current_request()
    if request is None:
        return None
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return user
