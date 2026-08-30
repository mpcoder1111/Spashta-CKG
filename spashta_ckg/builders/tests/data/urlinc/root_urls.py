"""Fixture root URLconf (spec/fullstack-coupling-roadmap.md P2).

A literal include('sub_urls', namespace='subns') -> includes_urlconf (File->File) with namespace metadata.
A non-literal include(extra_patterns) -> an unresolved_include ambiguity (never a guessed edge).
"""

from django.urls import include, path

extra_patterns = []

urlpatterns = [
    path("app/", include("sub_urls", namespace="subns")),
    path("bare/", include("sub_urls")),
    path("dyn/", include(extra_patterns)),
]
