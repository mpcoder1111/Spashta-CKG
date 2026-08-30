# Fixture — spec/django-htmx-coupling.md. Self-contained (view + urls + helper in one file) so a
# single-file builder run resolves everything (builders/tests/ is a scan-excluded dir).
from django.urls import path
from django.shortcuts import render, redirect, reverse


def _append_hx_trigger(response, event, payload):  # mimics our HX-Trigger helper
    return response


app_name = "shop"


def product_list(request):
    reverse("shop:detail")                       # B: reverse -> Route(shop:detail)
    return render(request, "shop/list.html", {})  # A: render -> Template('shop/list.html')


def product_detail(request, pk):
    _append_hx_trigger(None, "rvRefresh", {})     # C: HX-Trigger helper -> Event(rvRefresh)
    return redirect("shop:list")                  # B: redirect -> Route(shop:list)


urlpatterns = [
    path("", product_list, name="list"),
    path("<int:pk>/", product_detail, name="detail"),
]
