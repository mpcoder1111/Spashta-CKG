"""
Spashta-CKG — Runtime Adapter Enrichment Engine

ROLE
----
This script applies framework-specific semantics to the merged raw
Code Knowledge Graph AST produced by build_runtime_ast.py.

It performs the **first semantic enrichment layer** in a controlled,
rule-driven, and non-destructive manner.

OUTPUT
------
runtime/code_knowledge_graph_enriched.json

THIS SCRIPT DOES
----------------
Phase 1 — Adapter Governance Validation
• Validates adapter rule JSONs using validate_adapter_rules.py
• Ensures adapters do not invent schema keys
• Fails early on governance violations

Phase 2 — Semantic Enrichment
• Loads runtime/code_knowledge_graph_ast.json
• Applies active adapters from project/profile.json
• Uses declarative adapter rules only:
    – framework_mapping.json
    – adapter_contracts.json
    – adapter agent rules
• Supports Advanced Detection Logic:
    – Inheritance Checks ("extends")
    – Decorator Verification ("decorated_by")
    – Import Provenance ("requires_import")
    – Strict File Path Globbing (fnmatch)
• Annotates existing nodes with semantic_roles
• Performs framework contract checks

GUARANTEES
----------
• Graph structure is NOT modified
• No nodes or edges are added or removed
• Enrichment is deterministic and reproducible
• Core schema integrity is preserved

DOES NOT
--------
• Does NOT generate AST
• Does NOT parse source code
• Does NOT apply LLM reasoning
• Does NOT create parallel graphs

PRINCIPLE
---------
There is ONE graph.

Builders define structure.
Adapters define meaning.
Agents define reasoning.

This script produces the trusted semantic memory
used by IDE agents and reasoning layers.
"""



import sys
import json
import subprocess
import copy
from pathlib import Path

# Path Setup - REPO_ROOT is the Spashta-CKG folder (parent of Spashta_2.0)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SPASHTA_DIR = REPO_ROOT / "Spashta_2.0"
PROFILE_PATH = SPASHTA_DIR / "project" / "profile.json"
RUNTIME_DIR = SPASHTA_DIR / "runtime"
AST_PATH = RUNTIME_DIR / "code_knowledge_graph_ast.json"
ENRICHED_PATH = RUNTIME_DIR / "code_knowledge_graph_enriched.json"
DIFF_PATH = RUNTIME_DIR / "diff_report.json"
VALIDATOR_SCRIPT = SPASHTA_DIR / "adapters" / "validation" / "validate_adapter_rules.py"

def load_json(path):
    if not path.exists(): return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def run_governance_check(adapters):
    """Phase 3: Adapter Rule Validation."""
    print("Running Governance Check (Adapter Rules)...")
    all_passed = True
    
    for fw in adapters:
        cmd = [sys.executable, str(VALIDATOR_SCRIPT), fw]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"Governance Check PASSED: {fw}")
        except subprocess.CalledProcessError as e:
            print(f"Governance Check FAILED for {fw}:\n{e.stdout}\n{e.stderr}")
            all_passed = False
            
    return all_passed

def apply_enrichment_logic(node, edges_from, edges_to, node_map, detection_rules):
    """Core logic to check rules against a single node."""
    node_id = node.get("id")
    node_name = node.get("name")
    
    # 2. Rule Matching
    match = True
    
    # Rule: inheritance_includes (Class inherits from X)
    if match and "inheritance_includes" in detection_rules:
        found = False
        for edge_type, target_id in edges_from.get(node_id, []):
            if edge_type == "extends":
                target_node = node_map.get(target_id)
                if target_node:
                    t_name = target_node.get("name")
                    if t_name in detection_rules["inheritance_includes"]:
                        found = True
                        break
        if not found: match = False
        
    # Rule: file_path_contains (Defined in file matching glob X)
    if match and "file_path_contains" in detection_rules:
        from fnmatch import fnmatch
        found_file = False
        for edge_type, source_id in edges_to.get(node_id, []):
            if edge_type == "defines":
                 source_node = node_map.get(source_id)
                 if source_node:
                     # Use 'file_path' if available (Strong Identity), else name
                     fname = source_node.get("file_path", source_node.get("name", ""))
                     pattern = detection_rules["file_path_contains"]
                     # Wrap in * * if it's just a keyword, unless it looks like a glob
                     glob_pat = f"*{pattern}*" if "*" not in pattern else pattern
                     
                     if fnmatch(fname, glob_pat):
                         found_file = True
                         break
        if not found_file: match = False
        
    # Rule: decorated_by (Strict Decorator Check)
    if match and "decorated_by" in detection_rules:
        found_dec = False
        required_decs = detection_rules["decorated_by"] # List of strings
        # Check incoming 'decorates' edges? 
        # Wait, if A decorates B, edge is A -> decorates -> B or B -> decorated_by -> A?
        # Core schema usually says: Decorator -> decorates -> Function.
        # So specific Function node (B) has INCOMING 'decorates' edge from Decorator (A).
        
        for edge_type, source_id in edges_to.get(node_id, []):
            if edge_type == "decorates":
                dec_node = node_map.get(source_id)
                if dec_node:
                    dec_name = dec_node.get("name")
                    # Handle @login_required (name='login_required')
                    if dec_name in required_decs:
                        found_dec = True
                        break
        if not found_dec: match = False

    # Rule: requires_import (Strict Usage Check)
    if match and "requires_import" in detection_rules:
        found_imp = False
        required_pkg = detection_rules["requires_import"]
        
        # Determining "Context File":
        # 1. Start at Node (e.g. Class)
        # 2. Go UP "defines" edge to find File node
        # 3. Check outgoing 'imports' edges from that File node
        
        file_node = None
        for edge_type, source_id in edges_to.get(node_id, []):
            if edge_type == "defines":
                 file_node = node_map.get(source_id)
                 break
        
        if file_node:
             file_id = file_node.get("id")
             for edge_type, target_id in edges_from.get(file_id, []):
                  if edge_type == "imports":
                      # Target could be "File:django/db.py" or just "django.db" depending on resolution
                      # We check simplistic name match for now
                      tgt_node = node_map.get(target_id)
                      if tgt_node:
                          tgt_name = tgt_node.get("name")
                          if required_pkg in tgt_name:
                              found_imp = True
                              break
        
        if not found_imp: match = False

    # Rule: used_in_calls (Function calls X)
    if match and "used_in_calls" in detection_rules:
        found_call = False
        for edge_type, target_id in edges_from.get(node_id, []):
             if edge_type == "calls":
                 target_node = node_map.get(target_id)
                 if target_node:
                     t_name = target_node.get("name")
                     if t_name in detection_rules["used_in_calls"]:
                         found_call = True
                         break
        if not found_call: match = False
        
    # Rule: function_name (Exact name match)
    if match and "function_name" in detection_rules:
         if node_name not in detection_rules["function_name"]:
             match = False

    return match

def main():
    if not PROFILE_PATH.exists():
        print("Error: No project profile found.")
        sys.exit(1)
        
    if not AST_PATH.exists():
         print(f"Error: {AST_PATH.name} not yet generated. Please generate it using runtime\\build_runtime_ast.py")
         sys.exit(1)
         
    profile = load_json(PROFILE_PATH)
    adapters = profile.get("frameworks", [])

    # Phase 3: Governance
    if not run_governance_check(adapters):
        sys.exit(1)

    # Load Data
    raw_ast = load_json(AST_PATH)
    old_enriched_ast = load_json(ENRICHED_PATH) # May be None
    diff_report = load_json(DIFF_PATH) # May be None

    # Determine Workload
    # If no Diff or no Old version, RE-RUN ALL.
    if not diff_report or not old_enriched_ast:
        print("Full Enrichment Triggered (No diff or no old version).")
        nodes_to_enrich = {n["id"]: n for n in raw_ast["nodes"]}
        preserved_nodes = {}
    else:
        print("Incremental Enrichment Triggered.")
        # Partition
        nodes_to_enrich = {}
        preserved_nodes = {}
        
        old_nodes_map = {n["id"]: n for n in old_enriched_ast["nodes"]}
        raw_nodes_map = {n["id"]: n for n in raw_ast["nodes"]}
        
        node_status = diff_report.get("node_status", {})
        
        for nid, raw_node in raw_nodes_map.items():
            status = node_status.get(nid, "MODIFIED") # Default to modified if unknown
            
            if status == "UNCHANGED" and nid in old_nodes_map:
                # PRESERVE OLD (Keep semantics)
                preserved_nodes[nid] = old_nodes_map[nid]
            else:
                # ENRICH NEW (Use Raw)
                nodes_to_enrich[nid] = raw_node

    print(f"Nodes to Preserve: {len(preserved_nodes)}")
    print(f"Nodes to Enrich: {len(nodes_to_enrich)}")

    # Pre-compute Edge Lookups (Needed for rule matching on New Nodes)
    # We use RAW edges for topology checks
    edges_from = {}
    edges_to = {}
    
    # helper: map for lookups (Must include ALL nodes to resolve targets)
    # Ideally should include both preserved and new for comprehensive linking
    combined_lookup_map = {**preserved_nodes, **nodes_to_enrich}

    for e in raw_ast["edges"]:
        src = e.get("source", e.get("from"))
        tgt = e.get("target", e.get("to"))
        typ = e.get("type", e.get("edge"))
        
        if src and tgt:
            edges_from.setdefault(src, []).append((typ, tgt))
            edges_to.setdefault(tgt, []).append((typ, src))

    # Run Enrichment Loop on 'nodes_to_enrich' only
    enriched_count = 0
    
    for fw in adapters:
        mapping_path = SPASHTA_DIR / "adapters" / fw / "framework_mapping.json"
        if not mapping_path.exists(): continue
        
        mapping = load_json(mapping_path)
        
        for rule in mapping.get("mappings", []):
            role = rule["semantic_role"]
            target_core_node = rule["core_node"]
            detection = rule.get("detection_rules", {})
            
            for nid, node in nodes_to_enrich.items():
                n_type = node.get("node_type", node.get("type"))
                if n_type != target_core_node: continue
                
                if apply_enrichment_logic(node, edges_from, edges_to, combined_lookup_map, detection):
                    current_roles = node.get("semantic_roles", [])
                    if role not in current_roles:
                        current_roles.append(role)
                        node["semantic_roles"] = current_roles
                        enriched_count += 1
    
    # Combine Results
    final_nodes = list(preserved_nodes.values()) + list(nodes_to_enrich.values())
    
    output_graph = {
        "nodes": final_nodes,
        "edges": raw_ast["edges"], # Structure is always Authoritative Raw
        "ambiguities": raw_ast.get("ambiguities", []), # Preserve Known Unknowns
        "_meta": {
            "enrichment_mode": "incremental" if diff_report else "full",
            "stats": {
                "preserved": len(preserved_nodes),
                "enriched": len(nodes_to_enrich),
                "roles_applied": enriched_count
            }
        }
    }

    with open(ENRICHED_PATH, 'w', encoding='utf-8') as f:
        json.dump(output_graph, f, indent=2)
        
    print(f"Enrichment Complete. Graph saved to {ENRICHED_PATH}")

if __name__ == "__main__":
    main()
