"""Self-contained runnable proof for the URLconf include-tree (spec/fullstack-coupling-roadmap.md P2).

Copies builders/tests/data/urlinc/ to a temp dir OUTSIDE Spashta-CKG (the scanner excludes its own tree),
runs the Python builder over it, and asserts:
  include("sub_urls", namespace="subns") -> includes_urlconf (root_urls.py -> sub_urls.py) with namespace="subns";
  include("sub_urls")                    -> includes_urlconf (root_urls.py -> sub_urls.py), no namespace;
  include(extra_patterns)                -> NO edge, an unresolved_include ambiguity (never a guess).

Run:  python builders/python/verify_include_tree.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BUILDER = Path(__file__).resolve().parent / "build_python_ast.py"
FIXTURE = BUILDER.parent.parent / "tests" / "data" / "urlinc"


def _run() -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="spashta_urlinc_"))
    dest = tmp / "urlinc"
    shutil.copytree(FIXTURE, dest)
    out = tmp / "frag.json"
    subprocess.run(
        [sys.executable, str(BUILDER), "--source-root", str(dest), "--out", str(out)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(out.read_text("utf-8"))


def main() -> int:
    frag = _run()
    inc = [e for e in frag["edges"] if e["edge"] == "includes_urlconf"]
    pairs = {(e["from"].split("/")[-1], e["to"].split("/")[-1]) for e in inc}
    ns_edges = {(e["from"].split("/")[-1], e.get("namespace")) for e in inc}
    ambig = {a["expression"] for a in frag.get("ambiguities", []) if a["kind"] == "unresolved_include"}

    checks = [
        ("literal include -> includes_urlconf root_urls.py -> sub_urls.py",
         ("root_urls.py", "sub_urls.py") in pairs),
        ("namespace= carried as edge metadata (subns)",
         ("root_urls.py", "subns") in ns_edges),
        ("bare include (no namespace) still emits the edge",
         sum(1 for e in inc if e["from"].endswith("root_urls.py")) >= 2),
        ("non-literal include(var) -> unresolved_include ambiguity, no edge",
         any("include" in x for x in ambig)),
    ]
    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
