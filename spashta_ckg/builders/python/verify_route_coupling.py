"""Self-contained runnable proof for frontend->Django route coupling (spec/frontend-route-coupling.md US-1).

Runs the Python builder on builders/tests/data/route_app/ and the HTML builder on
builders/tests/data/route_template.html, asserting the deterministic contract: a
path(..., view, name='x') with a module app_name registers a Route('app:x') that resolves_to the
view; a dynamic name is an ambiguity; a template's hx-get="{% url 'app:x' %}" emits calls_api onto
the SAME bare-named Route('app:x') (joined BY NAME); a dynamic {% url var %} stays a placeholder.

Run:  python builders/python/verify_route_coupling.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

PY_BUILDER = Path(__file__).resolve().parent / "build_python_ast.py"
HTML_BUILDER = PY_BUILDER.parent.parent / "html" / "build_html_ast.py"
DATA = PY_BUILDER.parent.parent / "tests" / "data"
APP = DATA / "route_urls_dummy.py"  # single file (builders/tests/ is a scan-excluded dir)
TEMPLATE = DATA / "route_template.html"


def _run(builder: Path, src: Path) -> dict:
    out = Path(tempfile.gettempdir()) / f"spashta_route_{builder.stem}.json"
    subprocess.run(
        [sys.executable, str(builder), "--source-root", str(src), "--out", str(out)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(out.read_text("utf-8"))


def _pairs(frag: dict, etype: str) -> set:
    by = {n["id"]: n["name"] for n in frag["nodes"]}
    return {
        (by.get(e["from"], e["from"]), by.get(e["to"], e["to"]))
        for e in frag["edges"]
        if e["edge"] == etype
    }


def main() -> int:
    py = _run(PY_BUILDER, APP)
    html = _run(HTML_BUILDER, TEMPLATE)

    py_routes = {n["name"] for n in py["nodes"] if n["node_type"] == "Route"}
    resolves = _pairs(py, "resolves_to")  # (route_name, view_name)
    py_amb = {a["kind"] for a in py["ambiguities"]}
    html_routes = {n["name"] for n in html["nodes"] if n["node_type"] == "Route"}
    calls_api = _pairs(html, "calls_api")  # (template, route_name)

    checks = [
        ("Route 'shop:list' registered from urls.py", "shop:list" in py_routes),
        ("Route 'shop:detail' registered", "shop:detail" in py_routes),
        ("shop:list resolves_to view product_list", ("shop:list", "product_list") in resolves),
        ("shop:detail resolves_to product_detail", ("shop:detail", "product_detail") in resolves),
        ("CBV: shop:cbv resolves_to the ProductView class (.as_view() unwrapped)",
         ("shop:cbv", "ProductView") in resolves),
        ("dynamic name= is an unresolved_route ambiguity (not a guessed route)", "unresolved_route" in py_amb),
        ("HTML {% url 'shop:list' %} -> bare Route 'shop:list'", "shop:list" in html_routes),
        ("template calls_api -> Route 'shop:list' (joins the Python route by name)",
         any(r == "shop:list" for _, r in calls_api)),
        ("dynamic {% url var %} NOT resolved to a route named 'dyn_name'", "dyn_name" not in html_routes),
    ]
    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
