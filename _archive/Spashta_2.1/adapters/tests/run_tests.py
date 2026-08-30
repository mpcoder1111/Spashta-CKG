import sys
import json
import argparse
import subprocess
from pathlib import Path

# Setup paths
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def run_test():
    parser = argparse.ArgumentParser(description="Spashta-CKG Adapter Test Runner")
    parser.add_argument("--config", required=True, help="Path to test config JSON")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    if not config_path.exists():
        print(f"Error: Config file not found at {config_path}")
        sys.exit(1)
    
    config = load_json(config_path)
    base_dir = config_path.parent

    print(f"--- Running Adapter Test: {config.get('name', 'Unnamed')} ---")

    # 1. Load Adapter Mapping
    mapping_rel_path = config["paths"]["mapping_file"]
    adapter_mapping_file = (base_dir / mapping_rel_path).resolve()
    
    if not adapter_mapping_file.exists():
        print(f"Error: Mapping file not found at {adapter_mapping_file}")
        sys.exit(1)

    adapter_mapping = load_json(adapter_mapping_file)
    
    # 2. Build AST via Subprocess
    dummy_files_Rel = config["paths"]["dummy_files"]
    dummy_dir = (base_dir / config["paths"]["dummy_dir"]).resolve()
    
    # Dynamic Builder Selection
    builder_rel_path = config["paths"].get("builder_script", "builders/python/build_python_ast.py")
    builder_script = PROJECT_ROOT / builder_rel_path
    
    if not builder_script.exists():
        print(f"Error: Builder script not found at {builder_script}")
        sys.exit(1)

    temp_output = CURRENT_DIR / "temp_test_ast.json"

    cmd = [
        sys.executable, str(builder_script),
        "--source-root", str(dummy_dir),
        "--out", str(temp_output)
    ]
    
    print(f"Building AST for directory: {dummy_dir.name}...")
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"Builder failed:\n{e.stderr}")
        sys.exit(1)

    # 3. Load Generated AST
    if not temp_output.exists():
        print("Error: Builder did not produce output file.")
        sys.exit(1)
        
    ast_data = load_json(temp_output)
    ast_nodes = ast_data.get("nodes", [])
    ast_edges = ast_data.get("edges", [])
    ast_ambiguities = ast_data.get("ambiguities", [])
    
    # Index nodes for name lookup
    node_map = {n["id"]: n for n in ast_nodes}

    # Helpers
    def get_edge_targets(source_id, edge_types):
        return [e["to"] for e in ast_edges if e["from"] == source_id and e["edge"] in edge_types]
        
    def get_edge_sources(target_id, edge_types):
        return [e["from"] for e in ast_edges if e["to"] == target_id and e["edge"] in edge_types]

    # 4. Verify Detection Rules
    print("\n--- Verifying Adapter Detection Rules ---")
    
    mappings = adapter_mapping.get("mappings", [])
    detected_nodes = {} # role -> list of node names

    for rule in mappings:
        role = rule["semantic_role"]
        core_node_type = rule["core_node"]
        detection = rule.get("detection_rules", {})

        for node in ast_nodes:
            if node.get("node_type") != core_node_type:
                continue
            
            match = True
            node_id = node.get("id")
            node_name = node.get("name")
            
            # Rule A: Inheritance
            # Strategy: Look for "extends" edges. If target is unresolved, look at Ambiguities.
            if "inheritance_includes" in detection:
                req_bases = detection["inheritance_includes"]
                
                # 1. Check Proven Edges
                try_bases = []
                target_ids = get_edge_targets(node_id, ["extends", "inherits_from"])
                for tid in target_ids:
                    if tid in node_map:
                         try_bases.append(node_map[tid]["name"])
                    else:
                         try_bases.append(tid) # fall back to ID string
                
                # 2. Check Unproven Ambiguities
                for amb in ast_ambiguities:
                    if amb["source_scope"] == node_id and amb["kind"] == "inheritance_target_unproven":
                         try_bases.append(str(amb.get("expression", "")))
                
                base_found = False
                for req in req_bases:
                    req_parts = req.split(".")
                    for base in try_bases:
                        # Exact match or substring match
                        if req in base: 
                            base_found = True
                            break
                        # Heuristic: Check if all parts of dot-path are in the AST dump string
                        # e.g. req="models.Model" in "Attribute(value=Name(id='models'), attr='Model')"
                        if len(req_parts) > 1 and all(part in base for part in req_parts):
                            base_found = True
                            break
                    if base_found: break
                
                if not base_found:
                    match = False

            # Rule B: File Path
            if match and "file_path_contains" in detection:
                req_path = detection["file_path_contains"]
                # Look for 'defines' edge coming TO this node
                definers = get_edge_sources(node_id, ["defines", "defines_class", "defines_function"])
                path_found = False
                for def_id in definers:
                    # def_id handles file path usually
                    if req_path in def_id:
                        path_found = True
                        break
                if not path_found:
                    match = False

            # Rule C: Function Name
            if match and "function_name" in detection:
                if node_name not in detection["function_name"]:
                    match = False
                    
            # Rule D: Decorators
            if match and "decorated_by" in detection:
                req_decos = detection["decorated_by"]
                decos = get_edge_sources(node_id, ["decorates"]) 
                
                # Check ambiguities "decorator_unknown"
                for amb in ast_ambiguities:
                    if amb["source_scope"] == node_id and amb["kind"] == "decorator_unknown":
                        decos.append(str(amb.get("expression", "")))

                deco_found = False
                for req in req_decos:
                    req_parts = req.split(".")
                    for d in decos:
                        if req in d:
                            deco_found = True
                            break
                        # Heuristic: Check all parts
                        if len(req_parts) > 1 and all(part in d for part in req_parts):
                            deco_found = True
                            break
                    if deco_found: break
                if not deco_found:
                    match = False
            
            # Rule F: Assigned Value (Variable assigned specific class/function)
            if match and "assigned_value" in detection:
                req_values = detection["assigned_value"]
                # Look for 'writes_to' edge target? No, 'writes_to' is Parent -> Variable.
                # We need to know what the variable was assigned TO. 
                # Strict Builder doesn't track RHS of assignment as a 'value' property on Variable node.
                # However, it might emit 'calls' from the Scope to the Class constructor?
                # Actually, Strict Builder for Assign:
                # visit_Assign -> registers Variable. 
                # It does NOT emit an edge for the RHS expression unless it's a Call?
                # Wait, visit_Call emits 'calls' from SCOPE to Target.
                # If Scope is the File, we see File calls APIRouter.
                # We don't see Variable = APIRouter. The link is lost in Strict Builder Pass 2!
                
                # EXCEPT: If we look at Ambiguities or source code? 
                # Or maybe we rely on 'calls' occurring in the same scope?
                # But 'Router' is a Variable node. The builder has no link between Variable and the Call that created it.
                # This is a GAP in the Strict Builder v1.
                
                # WORKAROUND for Test Runner:
                # Inspect the source code line? No.
                # 
                # Let's assume for now that if a Variable exists and we can't prove it, we skip this rule or fail?
                # Actually, `check_fastapi_mapping_coverage.py` likely didn't implement this either?
                # For `assigned_value` to work, the builder needs to emit `assigned_from` edge or similar. 
                # Since it doesn't, we cannot test this rule strictly yet. 
                # I will comment this out or implement a dummy pass if `node_name` matches typical router names? NO.
                
                # Real Fix: We can't verify 'assigned_value' with current builder. 
                # I will mark it as skipped or unimplemented.
                match = False # Conservative: If we can't verify, we don't match.
            
            # Rule E: Used In Calls (Function calls X)
            if match and "used_in_calls" in detection:
                req_calls = detection["used_in_calls"]
                # Node CALLS Target
                outgoing_targets = get_edge_targets(node_id, ["calls", "function_call"])
                
                calls_to_check = []
                for tid in outgoing_targets:
                     if tid in node_map: calls_to_check.append(node_map[tid]["name"])
                     else: calls_to_check.append(tid)
                     
                # Check ambiguities "call_target_unknown"
                for amb in ast_ambiguities:
                    if amb["source_scope"] == node_id and amb["kind"] == "call_target_unknown":
                        calls_to_check.append(str(amb.get("expression", "")))
                
                call_found = False
                for req in req_calls:
                     for callee in calls_to_check:
                         if req in callee:
                             call_found = True
                             break
                     if call_found: break
                if not call_found:
                    match = False
                    
            if match:
                detected_nodes.setdefault(role, []).append(node_name)
                print(f"  [MATCH] Node '{node_name}' identified as {role}")

    # 5. Verify against Expectations
    print("\n--- Test Results ---")
    expectations = config.get("expectations", {})
    expected_roles = expectations.get("roles_present", [])
    
    all_passed = True
    for expected_role in expected_roles:
        if expected_role in detected_nodes and detected_nodes[expected_role]:
            print(f"✅ Role '{expected_role}': Found instances {detected_nodes[expected_role]}")
        else:
            print(f"❌ Role '{expected_role}': NOT FOUND")
            all_passed = False
            
    if all_passed:
        print("\n>>> FINAL RESULT: PASS")
        sys.exit(0)
    else:
        print("\n>>> FINAL RESULT: FAIL")
        sys.exit(1)

if __name__ == "__main__":
    run_test()
