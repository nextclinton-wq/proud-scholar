"""
URL configuration for project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic.base import RedirectView
from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from app.views import signin_view

urlpatterns = [
    path('', TemplateView.as_view(template_name='welcome.html'), name='welcome'),
    # Accept both /signin and /signin/ so POSTs from older pages don't 404
    path('signin/', signin_view, name='signin'),
    path('admin/auth/user/', RedirectView.as_view(url='/admin/app/user/', permanent=False), name='legacy-admin-user'),
    re_path(r'^admin/auth/user/(?P<path>.*)$', RedirectView.as_view(url='/admin/app/user/%(path)s', permanent=False)),
    path('admin/', admin.site.urls),
    path('api/v1/', include('app.urls')),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]
