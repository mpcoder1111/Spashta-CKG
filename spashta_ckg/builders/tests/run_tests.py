"""
Spashta-CKG – Unified Builder Test Runner

PHILOSOPHY & DESIGN INTENT:
---------------------------
Reference: `docs/spashta_ckg_mapping_philosophy_contributor_reference.md`

1. **Mappings Declare**: `css_language_mapping.json` is a dictionary of meanings. It declares "If X exists, it means Y". It contains POSITIVE FACTS ONLY.
2. **Builders Enforce**: `build_css_ast.py` decides truth. It checks if X actually exists/is valid. If not, it emits an Ambiguity Ticket instead of the Edge.
3. **Tests Verify**: This script verifies that the Builder honored the Contract.

CONFIGURATION:
--------------
This script is **Configuration-Driven**. All paths (builder script, mapping file, dummy code location) and options are defined in:
`run_tests_config.json`

This makes the runner generic and reusable. To change test targets, update the JSON config, not this script.

WORKFLOW:
---------
1. **JOB 1: BUILD (The Enforcer)**
   Executes `build_css_ast.py` on `dummy_css_code.css` to generate real AST data.
   The builder attempts to prove every structural fact declared in the mapping.

2. **JOB 2: VALIDATE (The Contract & Coverage Verifier)**
   This step has a **Dual Purpose**:
   
   A. **Verify Test Completeness**: 
      Checks if `dummy_css_code.css` actually contains examples for EVERY rule in the Mapping. If the dummy code is missing a case, this step fails, prompting you to improve the test data.
      
   B. **Verify Builder Compliance**:
      Checks if the Builder correctly processed those examples by producing either:
      *   **Ideal Outcome**: The expected Node/Edge (Success)
      *   **Strict Fallback**: The mandated Ambiguity Ticket (Contract Success)

   If NEITHER occurs, the test FAILS.
"""

import sys
import subprocess
import json
from pathlib import Path
import argparse

DEFAULT_CONFIG = "run_tests_config.json"

def load_config():
    """Reads the JSON config file to get paths and settings."""
    parser = argparse.ArgumentParser(description="Spashta-CKG Unified Test Runner")
    parser.add_argument("--config", default=None, help="Path to config JSON")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    
    if args.config:
        # If absolute, use as is. If relative, resolve relative to CWD (User's Terminal)
        # OR relative to base_dir? Usually CWD is safer for CLI args.
        config_path = Path(args.config).resolve()
        # IMPORTANT: Base dir for resolving OTHER paths inside config should be the config's folder
        base_dir = config_path.parent
    else:
        config_path = base_dir / DEFAULT_CONFIG

    if not config_path.exists():
        print(f"CRITICAL: Config file not found at {config_path}")
        sys.exit(1)
        
    print(f">>> Log: Loaded Configuration from {config_path.name}")
    return json.loads(config_path.read_text("utf-8")), base_dir

def run_builder(config, base_dir):
    """
    JOB 1: AST Building
    -------------------
    Simulates a CLI run of the builder to create test artifacts.

    [Source Code]                   [Builder Script]                  [Output Artifact]
    `dummy_css_code.css`   ----->   `build_css_ast.py`    ----->      `test_output_ast.json`
    (Implicitly Scanned)            (Executed via Subprocess)          (Freshly Generated)
    """
    paths = config["paths"]
    builder_script = (base_dir / paths["builder_script"]).resolve()
    project_root = (base_dir / paths["project_root_relative"]).resolve()
    output_file = (base_dir / config["output"]["filename"]).resolve()

    print(f">>> [Job 1] Running Builder ({builder_script.name})...")
    
    if not builder_script.exists():
        print(f"ERROR: Builder script not found: {builder_script}")
        return {"success": False, "error": "Script not found"}

    if config["output"].get("clean_before_run", False) and output_file.exists():
        output_file.unlink()

    cmd = [
        sys.executable,
        str(builder_script),
        "--source-root", str(project_root),
        "--out", str(output_file)
    ]
    
    print(f"DEBUG: Executing Command: {cmd}")

    try:
        res = subprocess.run(cmd, check=True, capture_output=True, text=True) 
        print("    -> Builder Execution Successful.")
        print("    [Builder Output Start]")
        print(res.stdout)
        print("    [Builder Output End]")
        return {"success": True, "output_file": output_file}
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Builder Execution Failed! (Exit Code: {e.returncode})")
        print(e.stderr)
        return {"success": False, "error": e.stderr}

def verify_mapping_coverage(config, base_dir):
    """
    JOB 2: Contract Verification
    ----------------------------
    Verifies that the Builder honored the Mapping Contract.

    [Mapping]                           [Builder Output]
    "If X, imply Y"                     "Assertion of Y" OR "Ambiguity of Y"
           |                                     |
           |        +-------------------+        |
           +------> | CONTRACT VERIFIER | <------+
                    +-------------------+
    
    **Logic:**
    1. EXTRACT Requirements from `css_language_mapping.json`.
    2. EXTRACT Facts from `test_output_ast.json`.
    3. CHECK COMPLIANCE: 
       - Structural Match: Exact Node/Edge found (Ideal).
       - Contract Match: Strict Ambiguity found in place of missing Edge (Strict Fallback).
    
    Any Mapping Declaration that produces NEITHER is a violation.
    """
    print(f">>> [Job 2] Verifying Mapping Coverage...")
    
    # 1. Load Mapping
    mapping_path = (base_dir / config["paths"]["mapping_file"]).resolve()
    if not mapping_path.exists():
        return {"success": False, "error": "Mapping file missing"}
    
    try:
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"success": False, "error": f"Invalid Mapping JSON: {e}"}

    # 2. Extract Expectations
    expected_edges = set()
    expected_nodes = set()
    expected_nodes.add(mapping.get("file_node_type", "File"))
    
    # Strategy A: Regex Patterns (CSS/JS)
    patterns = mapping.get("patterns", {})
    if patterns:
        for name, rule in patterns.items():
            if "emit_edge" in rule: expected_edges.add(rule["emit_edge"])
            if "defines_edge" in rule: expected_edges.add(rule["defines_edge"])
            if "emit_node" in rule: expected_nodes.add(rule["emit_node"])
            if "target_node_type" in rule: expected_nodes.add(rule["target_node_type"])

    # Strategy B: Manual Expectations (Python/AST)
    # If mapping doesn't have regex patterns, we rely on the Config to tell us what to check.
    else:
        manual_exp = config.get("manual_expectations", {})
        expected_edges.update(manual_exp.get("edges", []))
        expected_nodes.update(manual_exp.get("nodes", []))

    # 3. Load Actual Output
    output_file = (base_dir / config["output"]["filename"]).resolve()
    if not output_file.exists():
        return {"success": False, "error": "Output file missing"}
        
    try:
        output = json.loads(output_file.read_text(encoding="utf-8"))
    except Exception:
        return {"success": False, "error": "Output is not valid JSON"}

    actual_nodes = set(n["node_type"] for n in output.get("nodes", []))
    actual_edges = set(e["edge"] for e in output.get("edges", []))
    actual_ambiguities = set(a["kind"] for a in output.get("ambiguities", []))

    # 4. Compare
    missing_nodes = expected_nodes - actual_nodes
    missing_edges = expected_edges - actual_edges
    
    strict_pass_edges = set()
    
    # ----------------------------------------------------
    # CONTRACT EXPECTATIONS (Dynamic from Config)
    # This section encodes the Builder's documented fallback behavior.
    # It asserts that: Unproven Edge X -> 'ambiguity_ticket_Y'.
    # ----------------------------------------------------
    contract_equivalences = config.get("contract_equivalences", {})
    rules = contract_equivalences.get("rules", [])
    
    for rule in rules:
        req_edge = rule.get("required_edge")
        acceptable_ambiguity = rule.get("accepted_ambiguity")
        
        if req_edge in missing_edges and acceptable_ambiguity in actual_ambiguities:
            strict_pass_edges.add(req_edge)
            missing_edges.remove(req_edge)
    # ----------------------------------------------------

    success = (len(missing_nodes) == 0 and len(missing_edges) == 0)

    return {
        "success": success,
        "missing_nodes": list(missing_nodes),
        "missing_edges": list(missing_edges),
        "strict_pass_edges": list(strict_pass_edges),
        "stats": {
            "nodes_found": len(actual_nodes),
            "nodes_expected": len(expected_nodes),
            "edges_found": len(actual_edges) + len(strict_pass_edges),
            "edges_expected": len(expected_edges),
            "node_count": len(output.get("nodes", [])),
            "edge_count": len(output.get("edges", []))
        }
    }

def main():
    config, base_dir = load_config()
    
    # 1. Run Builder
    print("\n------------------------------------------------------------")
    build_res = run_builder(config, base_dir)
    if not build_res["success"]:
        print(f"\n❌ CRITICAL FAILURE: Builder Crashed.\nError: {build_res['error']}")
        sys.exit(1)
    
    # 2. Run Validator
    print("------------------------------------------------------------")
    val_res = verify_mapping_coverage(config, base_dir)
    print("------------------------------------------------------------\n")

    # 3. Display Report
    print("=== TEST REPORT ===")
    print(f"Generated File: {build_res['output_file'].name}")
    print(f"AST Content: {val_res['stats']['node_count']} Nodes, {val_res['stats']['edge_count']} Edges")
    
    print("\n[Mapping Rule Verification]")
    print(f"Nodes Covered: {val_res['stats']['nodes_found']}/{val_res['stats']['nodes_expected']}")
    
    # Edges
    print(f"Edges Covered: {val_res['stats']['edges_found']}/{val_res['stats']['edges_expected']}")
    
    if val_res["strict_pass_edges"]:
        print(f"  -> Contract Expectations Matched (Ambiguity Fallback): {val_res['strict_pass_edges']}")
    
    # [Interpretation Guide]
    print("\n[Interpretation Guide]")
    if val_res["success"]:
        input_file = config.get("paths", {}).get("project_root_relative", "input_file")
        print(f"PASS: System is Healthy. '{input_file}' covers all rules, and Builder correctly enforced the contract.")
    else:
        print("FAIL: Mapping Rules Not Covered. Two hypotheses exist:")
        input_file = config.get("paths", {}).get("project_root_relative", "input_file")
        print(f"   1. [Test Data Gap]: '{input_file}' is missing an example for this rule. (Verify this first)")
        print("   2. [Builder Bug]: The example exists, but the Builder failed to capture it.")

    if not val_res["success"]:
        print("\n------------------------------------------------------------")
        print(">>> FINAL RESULT: FAIL")
        print("------------------------------------------------------------")
        if val_res["missing_nodes"]: print(f"Missing Nodes: {val_res['missing_nodes']}")
        if val_res["missing_edges"]: print(f"Missing Edges: {val_res['missing_edges']}")
        sys.exit(1)
    else:
        print("\n>>> FINAL RESULT: PASS")
        sys.exit(0)

if __name__ == "__main__":
    main()
