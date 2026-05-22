"""
URL configuration for Boost Data Collector.
"""

from django.contrib import admin
from django.urls import path

from config.health import health_view

urlpatterns = [
    path("health/", health_view, name="health"),
    path("admin/", admin.site.urls),
]
