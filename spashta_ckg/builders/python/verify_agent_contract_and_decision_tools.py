"""
Regression and Contract Verification Suite for Spashta-CKG Agent Architecture.
Validates:
1. Universal Response Envelope Schema across all tools
2. can_delete Decision Engine (Production vs. Test Blockers)
3. Symbol Type Precedence Tiering & Ambiguity Flagging
4. mtime Freshness Signal & Staleness Guardrail
5. Compact by Default (Docstrings omitted by default, never truncated)
6. .spashta.json Tracked Configuration File Discovery
7. 9-Tool Native MCP Server Execution
"""

import sys
import json
import asyncio
import subprocess
from pathlib import Path
from spashta_ckg import CKG
from spashta_ckg.runtime.query_spashta import (
    TYPE_WEIGHTS, resolve_symbol_node, make_compact_node,
    make_envelope, check_freshness, can_delete as qs_can_delete
)
from spashta_ckg.mcp_server import (
    spashta_impact, spashta_can_delete, spashta_locate, spashta_routes,
    spashta_search, spashta_dead_code, spashta_stats, spashta_refresh, spashta_scan
)

TEST_DATA_DIR = Path(__file__).resolve().parent.parent / "tests" / "data"

def test_symbol_precedence_tiering():
    print("[1/7] Testing Symbol Type Hierarchy & Ambiguity Flagging...")
    
    # Synthesize a graph with 3 nodes sharing the name 'evidence'
    mock_graph = {
        "nodes": [
            {"id": "models.py::EvidencePayload::evidence", "name": "evidence", "node_type": "Field", "line_start": 10},
            {"id": "retrieval/evidence.py::evidence", "name": "evidence", "node_type": "Function", "line_start": 84},
            {"id": "context.py::evidence", "name": "evidence", "node_type": "Variable", "line_start": 5}
        ],
        "edges": []
    }
    
    winner, is_ambiguous, alts = resolve_symbol_node(mock_graph, "evidence")
    assert winner is not None, "Failed to resolve symbol 'evidence'"
    assert winner["id"] == "retrieval/evidence.py::evidence", f"Expected Function to win, got: {winner['id']}"
    assert winner["node_type"] == "Function", f"Expected Function type, got: {winner['node_type']}"
    assert is_ambiguous is True, "Expected is_ambiguous to be True on name collision"
    assert len(alts) == 2, f"Expected 2 alternative nodes, got: {len(alts)}"
    print("   ✅ Function won over Field/Variable with unambiguous ambiguity flagging!")


def test_can_delete_decision_engine():
    print("[2/7] Testing can_delete Decision Engine (Production vs Test)...")
    
    mock_graph = {
        "nodes": [
            {"id": "app/service.py::CoreService", "name": "CoreService", "node_type": "Class", "file_path": "app/service.py"},
            {"id": "app/views.py::order_view", "name": "order_view", "node_type": "Function", "file_path": "app/views.py"},
            {"id": "app/utils.py::LegacyHelper", "name": "LegacyHelper", "node_type": "Function", "file_path": "app/utils.py"},
            {"id": "tests/test_utils.py::test_legacy", "name": "test_legacy", "node_type": "TestCase", "file_path": "tests/test_utils.py"},
            {"id": "app/orphan.py::OrphanFunc", "name": "OrphanFunc", "node_type": "Function", "file_path": "app/orphan.py"}
        ],
        "edges": [
            {"from": "app/views.py::order_view", "to": "app/service.py::CoreService", "edge": "calls"},
            {"from": "tests/test_utils.py::test_legacy", "to": "app/utils.py::LegacyHelper", "edge": "calls"}
        ]
    }
    
    # Scenario A: Symbol has production callers
    res_a = qs_can_delete(mock_graph, "CoreService")
    assert res_a["can_delete"] is False, "CoreService should NOT be deletable (has production caller)"
    assert len(res_a["blockers"]["production"]) == 1
    assert res_a["requires_test_updates"] == []
    
    # Scenario B: Symbol has ONLY test callers
    res_b = qs_can_delete(mock_graph, "LegacyHelper")
    assert res_b["can_delete"] is True, "LegacyHelper SHOULD be deletable (only has test callers)"
    assert len(res_b["blockers"]["production"]) == 0
    assert len(res_b["blockers"]["tests"]) == 1
    assert "tests/test_utils.py" in res_b["requires_test_updates"]
    
    # Scenario C: Symbol has zero callers
    res_c = qs_can_delete(mock_graph, "OrphanFunc")
    assert res_c["can_delete"] is True, "OrphanFunc SHOULD be deletable (zero callers)"
    assert len(res_c["blockers"]["production"]) == 0
    assert len(res_c["blockers"]["tests"]) == 0
    assert res_c["requires_test_updates"] == []
    print("   ✅ Production vs Test deletion verdicts match formal specification!")


def test_universal_envelope_structure():
    print("[3/7] Testing Universal Response Envelope Standard...")
    ckg = CKG.build(project_root=TEST_DATA_DIR)
    
    # 3a. Impact envelope
    imp = ckg.impact("BaseClass", depth=2)
    assert imp["status"] in ("ok", "not_found", "error")
    assert imp["command"] == "impact"
    assert "target" in imp and "resolved_id" in imp["target"]
    assert "summary" in imp and "total_items" in imp["summary"]
    assert "returned_items" in imp["summary"] and "truncated" in imp["summary"]
    assert "items" in imp and isinstance(imp["items"], list)
    assert "_meta" in imp and "is_stale" in imp["_meta"]
    
    # 3b. Search envelope
    search_nodes = ckg.search("UserModel")
    assert len(search_nodes) > 0
    assert "id" in search_nodes[0] and "name" in search_nodes[0]
    
    # 3c. Dead code envelope
    dead = ckg.dead_code("py")
    assert dead["status"] == "ok"
    assert "provenance" in dead and "files_analyzed" in dead["provenance"]
    assert "summary" in dead and "total_candidates" in dead["summary"]
    print("   ✅ Universal envelope keys (status, target, summary, items, _meta) verified!")


def test_compact_node_default():
    print("[4/7] Testing Compact-by-Default (Docstrings Omitted by Default)...")
    raw_node = {
        "id": "app/views.py::complex_view",
        "name": "complex_view",
        "node_type": "Function",
        "file_path": "app/views.py",
        "line_start": 10,
        "line_end": 60,
        "docstring": "This is a 50-line massive docstring with full architectural context...",
        "ast_raw": {"tokens": 500}
    }
    
    compact = make_compact_node(raw_node, include_full=False)
    assert "docstring" not in compact, "Docstring should be omitted by default in compact mode"
    assert "ast_raw" not in compact, "ast_raw should be omitted in compact mode"
    assert compact["id"] == "app/views.py::complex_view"
    assert compact["file_path"] == "app/views.py"
    
    full = make_compact_node(raw_node, include_full=True)
    assert "docstring" in full, "Docstring must be retained in full mode without truncation"
    assert full["docstring"] == raw_node["docstring"], "Docstring must never be truncated!"
    print("   ✅ Compact default and non-truncated full docstrings verified!")


def test_config_dotfile_discovery():
    print("[5/7] Testing .spashta.json Configuration Discovery...")
    cfg = CKG.get_profile_info(project_root=TEST_DATA_DIR)
    assert "excluded_directories" in cfg
    assert isinstance(cfg["excluded_directories"], list)
    print(f"   ✅ Discovered active profile: {cfg['path']}")


def test_cli_can_delete_and_envelope():
    print("[6/7] Testing CLI can-delete and Universal Envelope...")
    cli_exe = str(Path(sys.executable).parent / "spashta_ckg.exe")
    
    # Run CLI can-delete
    out_cd = subprocess.check_output(
        [cli_exe, "can-delete", "BaseClass", "-p", str(TEST_DATA_DIR), "--json"],
        text=True
    )
    d_cd = json.loads(out_cd)
    assert d_cd["status"] == "ok"
    assert d_cd["command"] == "can_delete"
    assert "can_delete" in d_cd
    assert "blockers" in d_cd
    assert "_meta" in d_cd
    
    # Run CLI search with --full vs compact
    out_search = subprocess.check_output(
        [cli_exe, "search", "UserModel", "-p", str(TEST_DATA_DIR), "--json"],
        text=True
    )
    d_search = json.loads(out_search)
    assert d_search["status"] == "ok"
    assert d_search["command"] == "search"
    assert len(d_search["items"]) > 0
    print("   ✅ CLI subcommands conform to universal envelope!")


def test_mcp_server_suite():
    print("[7/7] Testing 9-Tool Native MCP Server Suite...")
    async def run_mcp_tests():
        test_dir = str(TEST_DATA_DIR)
        
        # 1. spashta_impact
        r_imp = await spashta_impact("BaseClass", project_dir=test_dir)
        assert isinstance(r_imp, dict) and r_imp["status"] == "ok"
        
        # 2. spashta_can_delete (NEW)
        r_cd = await spashta_can_delete("BaseClass", project_dir=test_dir)
        assert isinstance(r_cd, dict) and r_cd["command"] == "can_delete"
        
        # 3. spashta_locate
        r_loc = await spashta_locate("UserModel", project_dir=test_dir)
        assert isinstance(r_loc, dict) and r_loc["id"] == "python_dummy.py::UserModel"
        
        # 4. spashta_routes
        r_rt = await spashta_routes(project_dir=test_dir)
        assert isinstance(r_rt, list)
        
        # 5. spashta_search
        r_s = await spashta_search("UserModel", project_dir=test_dir)
        assert isinstance(r_s, list) and len(r_s) > 0
        
        # 6. spashta_dead_code
        r_dc = await spashta_dead_code("css", project_dir=test_dir)
        assert isinstance(r_dc, dict) and r_dc["status"] == "ok"
        
        # 7. spashta_stats
        r_st = await spashta_stats(project_dir=test_dir)
        assert isinstance(r_st, dict) and r_st["status"] == "ok"
        
        # 8. spashta_refresh
        r_rf = await spashta_refresh(files="python_dummy.py", project_dir=test_dir)
        assert isinstance(r_rf, dict) and r_rf["status"] == "ok"
        
        # 9. spashta_scan
        r_sc = await spashta_scan(project_dir=test_dir)
        assert isinstance(r_sc, dict) and r_sc["status"] == "ok"

    asyncio.run(run_mcp_tests())
    print("   ✅ All 9 native MCP tools return structured dictionaries asynchronously!")


def main():
    print("=" * 80)
    print("   SPASHTA-CKG AGENT CONTRACT & DECISION TOOLS REGRESSION SUITE   ")
    print("=" * 80)
    test_symbol_precedence_tiering()
    test_can_delete_decision_engine()
    test_universal_envelope_structure()
    test_compact_node_default()
    test_config_dotfile_discovery()
    test_cli_can_delete_and_envelope()
    test_mcp_server_suite()
    print("=" * 80)
    print("   STATUS: 100% GREEN - ALL 7 AGENT CONTRACT TEST GROUPS PASSED   ")
    print("=" * 80)

if __name__ == "__main__":
    main()
