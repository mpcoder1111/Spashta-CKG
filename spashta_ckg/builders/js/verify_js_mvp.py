"""Self-contained runnable proof for build_js_ast.py (MVP — spec/js-support.md US-1).

Runs the JS builder on builders/tests/data/js_dummy.js and asserts the deterministic
contract: the expected Function defs, the resolved `calls` edges, and that an external
callee (document.getElementById) is an ambiguity, NOT a guessed edge.

Run:  python builders/js/verify_js_mvp.py
Requires: pip install tree-sitter tree-sitter-javascript
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

BUILDER_DIR = Path(__file__).resolve().parent
BUILDER = BUILDER_DIR / "build_js_ast.py"
FIXTURE = BUILDER_DIR.parent / "tests" / "data" / "js_dummy.js"


def _run() -> dict:
    out = Path(tempfile.gettempdir()) / "spashta_js_mvp_fragment.json"
    subprocess.run(
        [sys.executable, str(BUILDER), "--source-root", str(FIXTURE), "--out", str(out)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(out.read_text("utf-8"))


def main() -> int:
    frag = _run()
    names = {n["name"] for n in frag["nodes"] if n["node_type"] == "Function"}
    events = {n["name"] for n in frag["nodes"] if n["node_type"] == "Event"}
    by_id = {n["id"]: n["name"] for n in frag["nodes"]}

    def pairs(edge_type: str) -> set:
        return {(by_id.get(e["from"], e["from"]), by_id.get(e["to"], e["to"]))
                for e in frag["edges"] if e["edge"] == edge_type}

    calls = pairs("calls")
    listens = pairs("registers_event_handler")
    dispatches = pairs("dispatches_event")
    dom = pairs("queries_dom")
    style_classes = {n["name"] for n in frag["nodes"] if n["node_type"] == "StyleClass"}
    style_ids = {n["name"] for n in frag["nodes"] if n["node_type"] == "StyleID"}
    ambig = {a["expression"] for a in frag["ambiguities"]}

    checks = [
        ("defs found", {"window.app.greet", "window.app.warn", "helper", "run"} <= names),
        ("warn -> greet", ("window.app.warn", "window.app.greet") in calls),
        ("run -> helper", ("run", "helper") in calls),
        ("run -> window.app.greet", ("run", "window.app.greet") in calls),
        ("external callee is an ambiguity (not an edge)", "console.log" in ambig),
        # Phase 2 — event coupling through one shared Event node
        ("Event node 'app:refresh'", "app:refresh" in events),
        ("listener registers_event_handler -> app:refresh",
         any(t == "app:refresh" for _, t in listens)),
        ("fireRefresh dispatches_event -> app:refresh",
         ("fireRefresh", "app:refresh") in dispatches),
        # Phase 2 — DOM queries -> StyleClass/StyleID placeholders (join to CSS by name)
        ("StyleID node 'main-panel'", "main-panel" in style_ids),
        ("StyleClass node 'widget'", "widget" in style_classes),
        ("paint queries_dom -> main-panel", ("paint", "main-panel") in dom),
        ("paint queries_dom -> widget", ("paint", "widget") in dom),
        ("compound selector '.a .b' is an ambiguity (not an edge)", ".a .b" in ambig),
    ]
    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
