"""Self-contained runnable proof for Django form->model binding + signal receivers (roadmap P4).

Runs the Python builder over builders/tests/data/forms_signals_dummy.py (single-file scan) and asserts:
  class WidgetForm(forms.ModelForm): Meta.model = Widget      -> uses_model  (WidgetForm -> Widget)
  @receiver(post_save, sender=Widget) def on_widget_saved     -> listens_to  (on_widget_saved -> Signal 'post_save')

NOTE: the Forms Portal itself uses NO ModelForm and NO Django signals (HTMX + service functions instead),
so this phase is a GENERIC Spashta contribution proven at the fixture level — there are no portal instances
to light up. Additive + config-gated: a project without these patterns is byte-identical.

Run:  python builders/python/verify_forms_signals.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

BUILDER = Path(__file__).resolve().parent / "build_python_ast.py"
FIXTURE = BUILDER.parent.parent / "tests" / "data" / "forms_signals_dummy.py"


def _run() -> dict:
    out = Path(tempfile.mkdtemp(prefix="spashta_fs_")) / "frag.json"
    subprocess.run(
        [sys.executable, str(BUILDER), "--source-root", str(FIXTURE), "--out", str(out)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(out.read_text("utf-8"))


def main() -> int:
    frag = _run()
    id2name = {n["id"]: n.get("name") for n in frag["nodes"]}

    def pairs(etype: str) -> set:
        out = set()
        for e in frag["edges"]:
            if e["edge"] != etype:
                continue
            src = id2name.get(e["from"], e["from"]).split("::")[-1]
            dst = id2name.get(e["to"], e["to"]).split("::")[-1]
            out.add((src, dst))
        return out

    uses = pairs("uses_model")
    listens = pairs("listens_to")

    checks = [
        ("ModelForm Meta.model -> uses_model (WidgetForm -> Widget)", ("WidgetForm", "Widget") in uses),
        ("@receiver(post_save) -> listens_to (on_widget_saved -> post_save)",
         ("on_widget_saved", "post_save") in listens),
    ]
    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
