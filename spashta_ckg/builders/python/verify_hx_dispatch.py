"""Self-contained runnable proof for GENERIC inline HX-Trigger dispatch (spec/fullstack-coupling-roadmap.md P3).

Runs the Python builder over builders/tests/data/hx_dispatch_dummy.py (single-file scan) and asserts:
  resp['HX-Trigger'] = 'rvRefresh'                     -> dispatches_event to Event 'rvRefresh'
  resp['HX-Trigger'] = 'saved, closeDialog'            -> two events 'saved' + 'closeDialog'
  resp['HX-Trigger'] = json.dumps({'showToast':..,'openDialog':..}) -> two events (the literal keys)
  resp['HX-Trigger'] = json.dumps(data)                -> NO edge, an unresolved_hx_trigger ambiguity

Run:  python builders/python/verify_hx_dispatch.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

BUILDER = Path(__file__).resolve().parent / "build_python_ast.py"
FIXTURE = BUILDER.parent.parent / "tests" / "data" / "hx_dispatch_dummy.py"


def _run() -> dict:
    out = Path(tempfile.mkdtemp(prefix="spashta_hx_")) / "frag.json"
    subprocess.run(
        [sys.executable, str(BUILDER), "--source-root", str(FIXTURE), "--out", str(out)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(out.read_text("utf-8"))


def main() -> int:
    frag = _run()
    id2name = {n["id"]: n.get("name") for n in frag["nodes"]}
    # (caller-function-name, event-name) pairs
    dispatched = set()
    for e in frag["edges"]:
        if e["edge"] != "dispatches_event":
            continue
        caller = id2name.get(e["from"], e["from"]).split("::")[-1]
        ev = id2name.get(e["to"], e["to"]).split("::")[-1]
        dispatched.add((caller, ev))
    ambig = [a for a in frag.get("ambiguities", []) if a["kind"] == "unresolved_hx_trigger"]

    checks = [
        ("bare string -> dispatches_event 'rvRefresh'", ("bare_event", "rvRefresh") in dispatched),
        ("comma-separated -> 'saved' + 'closeDialog'",
         ("comma_events", "saved") in dispatched and ("comma_events", "closeDialog") in dispatched),
        ("json.dumps(dict-literal) -> 'showToast' + 'openDialog'",
         ("json_events", "showToast") in dispatched and ("json_events", "openDialog") in dispatched),
        ("computed json.dumps(var) -> unresolved_hx_trigger ambiguity, no edge",
         len(ambig) >= 1 and ("computed_event", "showToast") not in dispatched),
    ]
    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
