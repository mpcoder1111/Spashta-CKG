"""Self-contained runnable proof for the Django/HTMX call couplings (spec/django-htmx-coupling.md).

Runs the Python builder on builders/tests/data/django_coupling_dummy.py and asserts, each deterministic:
- A: render(request, 'shop/list.html') → a renders_template edge to a Template('shop/list.html').
- B: reverse('shop:detail') / redirect('shop:list') → a calls_api edge to the Route (registered from
     the path(..., name=...) in the same file).
- C: an HX-Trigger helper call _append_hx_trigger(resp, 'rvRefresh', …) → a dispatches_event to
     Event('rvRefresh') (joins the JS listener by name at merge).

Run:  python builders/python/verify_django_htmx_coupling.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

BUILDER = Path(__file__).resolve().parent / "build_python_ast.py"
FIXTURE = BUILDER.parent.parent / "tests" / "data" / "django_coupling_dummy.py"


def _run() -> dict:
    out = Path(tempfile.gettempdir()) / "spashta_django_coupling.json"
    subprocess.run(
        [sys.executable, str(BUILDER), "--source-root", str(FIXTURE), "--out", str(out)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(out.read_text("utf-8"))


def main() -> int:
    frag = _run()
    by = {n["id"]: n for n in frag["nodes"]}

    def pairs(etype: str) -> set:
        return {(by.get(e["from"], {}).get("name", e["from"]), by.get(e["to"], {}).get("name", e["to"]))
                for e in frag["edges"] if e["edge"] == etype}

    renders = pairs("renders_template")
    calls_api = pairs("calls_api")
    dispatches = pairs("dispatches_event")

    checks = [
        ("A: product_list renders_template 'shop/list.html'",
         ("product_list", "shop/list.html") in renders),
        ("B: product_list calls_api Route 'shop:detail' (reverse)",
         ("product_list", "shop:detail") in calls_api),
        ("B: product_detail calls_api Route 'shop:list' (redirect)",
         ("product_detail", "shop:list") in calls_api),
        ("C: product_detail dispatches_event 'rvRefresh' (HX-Trigger helper)",
         ("product_detail", "rvRefresh") in dispatches),
    ]
    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
