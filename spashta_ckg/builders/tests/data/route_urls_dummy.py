# Fixture urls — spec/frontend-route-coupling.md US-1. Self-contained (views + urlpatterns in one
# file) so the single-file builder run resolves the view in-registry (builders/tests/ is a scan-
# excluded dir, so a multi-file dir won't scan).
from django.urls import path


def product_list(request):
    return None


def product_detail(request, pk):
    return None


class ProductView:  # a class-based view (CBV)
    pass


app_name = "shop"

_dynamic_name = "computed"

urlpatterns = [
    path("", product_list, name="list"),                  # literal name + resolvable FBV
    path("<int:pk>/", product_detail, name="detail"),     # second route
    path("cbv/", ProductView.as_view(), name="cbv"),      # CBV -> resolves to the class
    path("x/", product_list, name=_dynamic_name),         # dynamic name -> unresolved_route ambiguity
]
