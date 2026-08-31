"""
Deterministic Verifier: Incremental Graph Integrity & Edge Retention (Spashta 3.2.4)
Ensures that targeted --file refreshes, plain auto-detect refreshes, and add/delete cycles
preserve 100% exact node and edge counts without dropping caller links.
"""

import sys
import shutil
from pathlib import Path
from spashta_ckg import CKG

def test_incremental_edge_retention():
    test_dir = Path(__file__).resolve().parent.parent / "tests" / "data"
    spashta_dir = test_dir / ".spashta"
    if spashta_dir.exists():
        shutil.rmtree(spashta_dir, ignore_errors=True)

    # 1. Ground Truth Full Scan
    ckg_scan = CKG.build(project_root=test_dir)
    n_scan = len(ckg_scan.nodes)
    e_scan = len(ckg_scan.edges)
    assert n_scan > 0 and e_scan > 0, "Initial scan produced empty graph"

    # 2. Targeted Refresh on Unchanged Python File
    ckg_ref_py = CKG.refresh(project_root=test_dir, files=["python_dummy.py"])
    assert len(ckg_ref_py.nodes) == n_scan, f"Node count changed on targeted Python refresh: {len(ckg_ref_py.nodes)} vs {n_scan}"
    assert len(ckg_ref_py.edges) == e_scan, f"CRITICAL: Edge loss on targeted Python refresh: {len(ckg_ref_py.edges)} vs {e_scan}"

    # 3. Repeated Targeted Refresh (Idempotence)
    ckg_ref_py2 = CKG.refresh(project_root=test_dir, files=["python_dummy.py"])
    assert len(ckg_ref_py2.nodes) == n_scan and len(ckg_ref_py2.edges) == e_scan

    # 4. Targeted Refresh on Unchanged JS File
    ckg_ref_js = CKG.refresh(project_root=test_dir, files=["js_dummy.js"])
    assert len(ckg_ref_js.nodes) == n_scan, f"Node count changed on targeted JS refresh: {len(ckg_ref_js.nodes)} vs {n_scan}"
    assert len(ckg_ref_js.edges) == e_scan, f"CRITICAL: Edge loss on targeted JS refresh: {len(ckg_ref_js.edges)} vs {e_scan}"

    # 5. Plain Auto-Detect Refresh (No Changes)
    ckg_ref_plain = CKG.refresh(project_root=test_dir)
    assert len(ckg_ref_plain.nodes) == n_scan, f"Node count changed on plain refresh: {len(ckg_ref_plain.nodes)} vs {n_scan}"
    assert len(ckg_ref_plain.edges) == e_scan, f"CRITICAL: Edge loss on plain refresh: {len(ckg_ref_plain.edges)} vs {e_scan}"

    # 6. Add File -> Incremental Refresh -> Delete File -> Incremental Refresh
    dummy_file = test_dir / "_temp_retention_dummy.py"
    dummy_file.write_text("from python_dummy import variable_ops\ndef temp_caller():\n    variable_ops()\n", encoding="utf-8")
    try:
        ckg_added = CKG.refresh(project_root=test_dir)
        assert len(ckg_added.nodes) > n_scan, f"Expected node increase on add, got {len(ckg_added.nodes)} vs {n_scan}"
        assert len(ckg_added.edges) > e_scan, f"Expected edge increase on add, got {len(ckg_added.edges)} vs {e_scan}"
    finally:
        dummy_file.unlink(missing_ok=True)

    ckg_restored = CKG.refresh(project_root=test_dir)
    assert len(ckg_restored.nodes) == n_scan, f"Node restoration mismatch: {len(ckg_restored.nodes)} vs {n_scan}"
    assert len(ckg_restored.edges) == e_scan, f"Edge restoration mismatch: {len(ckg_restored.edges)} vs {e_scan}"

    print(f"PASSED: All incremental edge retention invariants verified on {n_scan} nodes & {e_scan} edges.")

if __name__ == "__main__":
    test_incremental_edge_retention()
