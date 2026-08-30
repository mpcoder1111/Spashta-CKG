"""Fixture sub URLconf included by root_urls.py (spec/fullstack-coupling-roadmap.md P2)."""

from django.urls import path


def my_view(request):
    return None


app_name = "sub"

urlpatterns = [
    path("x/", my_view, name="x"),
]
