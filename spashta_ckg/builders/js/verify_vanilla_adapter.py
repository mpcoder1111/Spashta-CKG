"""Self-contained proof for the Vanilla-JS ADAPTER (spec/js-support.md Phase 2).

Builds the JS fragment for the dummy, then applies the REAL enrichment engine logic
(runtime.enrich_runtime_ast.apply_enrichment_logic) with adapters/vanilla/framework_mapping.json,
and asserts the event functions receive the `Signal` semantic role — exactly how the HTMX adapter
tags Templates as Component. Reuses the engine (no re-implementation).

Run:  python builders/js/verify_vanilla_adapter.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

BUILDER_DIR = Path(__file__).resolve().parent
SPASHTA_DIR = BUILDER_DIR.parent.parent
BUILDER = BUILDER_DIR / "build_js_ast.py"
FIXTURE = BUILDER_DIR.parent / "tests" / "data" / "js_dummy.js"
ADAPTER = SPASHTA_DIR / "adapters" / "vanilla" / "framework_mapping.json"

sys.path.insert(0, str(SPASHTA_DIR / "runtime"))
from enrich_runtime_ast import apply_enrichment_logic  # the real engine logic


def _fragment() -> dict:
    out = Path(tempfile.gettempdir()) / "spashta_vanilla_fragment.json"
    subprocess.run(
        [sys.executable, str(BUILDER), "--source-root", str(FIXTURE), "--out", str(out)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(out.read_text("utf-8"))


def main() -> int:
    frag = _fragment()
    nodes = frag["nodes"]
    node_map = {n["id"]: n for n in nodes}
    edges_from: dict = {}
    edges_to: dict = {}
    for e in frag["edges"]:
        edges_from.setdefault(e["from"], []).append((e["edge"], e["to"]))
        edges_to.setdefault(e["to"], []).append((e["edge"], e["from"]))

    adapter = json.loads(ADAPTER.read_text("utf-8"))
    for rule in adapter["mappings"]:
        role = rule["semantic_role"]
        detection = rule.get("detection_rules", {})
        for node in nodes:
            if node.get("node_type") != rule["core_node"]:
                continue
            if apply_enrichment_logic(node, edges_from, edges_to, node_map, detection):
                node.setdefault("semantic_roles", [])
                if role not in node["semantic_roles"]:
                    node["semantic_roles"].append(role)

    signals = {n["name"] for n in nodes if "Signal" in n.get("semantic_roles", [])}
    non_event = {n["name"] for n in nodes
                 if n["node_type"] == "Function" and "Signal" not in n.get("semantic_roles", [])}

    checks = [
        ("init tagged Signal (registers a listener)", "init" in signals),
        ("fireRefresh tagged Signal (dispatches)", "fireRefresh" in signals),
        ("non-event fn 'helper' NOT tagged Signal", "helper" in non_event),
        ("non-event fn 'run' NOT tagged Signal", "run" in non_event),
    ]
    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    print("  signals:", sorted(signals))
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
