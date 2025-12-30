"""
Spashta-CKG — Builder Output Schema Validator

PURPOSE
-------
This script validates that a Builder's output AST conforms strictly to the
Spashta Core Software Schema defined in:

    core/software_schema/nodes.json
    core/software_schema/edges.json

It acts as the final structural gate before an AST is trusted by Adapters
and Agents.

WHAT THIS SCRIPT VALIDATES
--------------------------
1. Every emitted Node has:
   - A valid identifier (id or name)
   - A valid node type defined in nodes.json

2. Every emitted Edge has:
   - A valid edge type defined in edges.json
   - A valid source node and target node present in the AST

3. Every (source_type → edge_type → target_type) triple:
   - Is explicitly allowed by the Core edges schema

4. The AST structure is internally consistent:
   - No orphaned edges
   - No unknown node or edge types
   - No malformed records

WHAT THIS SCRIPT IS
-------------------
• A schema conformance validator for Builder output
• Framework-agnostic (Python / HTML / JS / CSS)
• Language-agnostic
• Deterministic and machine-verifiable
• Safe to use in CI and Agent pipelines

WHAT THIS SCRIPT IS NOT
-----------------------
• NOT a mapping coverage checker
  (see check_*_mapping_coverage.py)
• NOT a semantic or behavioral validator
• NOT a Builder runner
• NOT an Adapter or Agent

It validates *structure only*, never meaning.

WHY THIS EXISTS
---------------
Agents and Adapters trust the AST blindly.
If an AST violates Core schema, downstream reasoning becomes unsafe.

This validator ensures:
    "Only schema-valid ASTs are allowed to proceed."

USAGE
-----
Validate an AST and print the report:
    python validate_builder_output.py test_output_ast.json

Validate and write a report to a file:
    python validate_builder_output.py test_output_ast.json --out report.json

DESIGN PRINCIPLE
----------------
When validation fails:
• The validator is NOT weakened
• Builders are NOT patched silently
• Core schema is reviewed deliberately if a universal relationship is missing

This script prevents ontology drift and enforces structural correctness.
"""


import sys
import json
from pathlib import Path
from typing import Dict, List, Any

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
SCHEMA_DIR = BASE_DIR / "core" / "software_schema"

def load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def validate_ast(ast_path: str, output_file: str = None):
    ast_path = Path(ast_path)
    if not ast_path.exists():
        print(f"Error: AST file not found: {ast_path}")
        sys.exit(1)
        
    print(f"Validating AST: {ast_path.name}")
    
    # Load Schema
    try:
        nodes_schema = load_json(SCHEMA_DIR / "nodes.json")
        raw_edges_schema = load_json(SCHEMA_DIR / "edges.json")
        
        # Flatten Edges Schema (Handle distinct categories like 'direct_structural', 'reference_symbolic')
        edges_schema = {}
        for category, rules in raw_edges_schema.items():
            if category == "_meta": 
                continue
            if isinstance(rules, dict):
                edges_schema.update(rules)
                
    except Exception as e:
        print(f"Error loading Core Schema: {e}")
        sys.exit(1)
        
    # Load AST
    try:
        ast_data = load_json(ast_path)
    except Exception as e:
        print(f"Error loading AST: {e}")
        sys.exit(1)

    nodes = ast_data.get("nodes", [])
    edges = ast_data.get("edges", [])
    
    report = {
        "file": ast_path.name,
        "status": "pass",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "ambiguity_count": len(ast_data.get("ambiguities", [])),
        "schema_errors": [],
        "schema_warnings": []
    }
    
    # Map Node ID -> Type
    node_id_map = {}
    valid_node_types = set(nodes_schema.keys())
    
    # 1. Validate Nodes
    for n in nodes:
        # Support aliases for flexibility
        nid = n.get("id") or n.get("name")
        ntype = n.get("type") or n.get("node_type")
        
        if not nid:
             report["schema_errors"].append({"issue": "Missing Node ID", "node": n})
             continue
             
        if not ntype:
             report["schema_errors"].append({"issue": "Missing Node Type", "node": n})
             continue
             
        node_id_map[nid] = ntype
        
        if ntype not in valid_node_types:
            report["schema_errors"].append({
                "issue": "Invalid Node Type", 
                "value": ntype, 
                "id": nid,
                "detail": "Type not defined in nodes.json"
            })
            
    # 2. Validate Edges
    valid_edge_types = set(edges_schema.keys())
    
    for e in edges:
        e_type = e.get("edge")
        src = e.get("from")
        dst = e.get("to")
        
        if not e_type or not src or not dst:
            report["schema_errors"].append({"issue": "Malformed Edge", "edge": e})
            continue
            
        if e_type not in valid_edge_types:
             report["schema_errors"].append({
                "issue": "Invalid Edge Type",
                "value": e_type,
                "from": src,
                "to": dst,
                "detail": "Edge type not defined in edges.json"
            })
             continue
             
        # 3. Validate Semantic Constraints (Triples)
        src_type = node_id_map.get(src)
        dst_type = node_id_map.get(dst)
        
        if not src_type:
            # Maybe node missing from AST?
            report["schema_errors"].append({"issue": "Orphaned Edge Source", "edge": e, "detail": f"Node {src} not found in AST nodes"})
            continue
            
        if not dst_type:
            report["schema_errors"].append({"issue": "Orphaned Edge Target", "edge": e, "detail": f"Node {dst} not found in AST nodes"})
            continue
            
        # Check Allowed Relationships
        edge_def = edges_schema[e_type]
        allowed_from = set(edge_def.get("from", []))
        allowed_to = set(edge_def.get("to", []))
        
        if src_type not in allowed_from:
             report["schema_errors"].append({
                 "issue": "Invalid Edge Relationship (Source)",
                 "edge_type": e_type,
                 "from_type": src_type,
                 "to_type": dst_type,
                 "allowed": list(allowed_from),
                 "detail": f"Edge '{e_type}' cannot originate from '{src_type}'"
             })
             
        if dst_type not in allowed_to:
             report["schema_errors"].append({
                 "issue": "Invalid Edge Relationship (Target)",
                 "edge_type": e_type,
                 "from_type": src_type,
                 "to_type": dst_type,
                 "allowed": list(allowed_to),
                 "detail": f"Edge '{e_type}' cannot point to '{dst_type}'"
             })

    # 4. Validate Ambiguities (The "Unknowns" must be structured)
    ambiguities = ast_data.get("ambiguities", [])
    required_ambiguity_fields = ["id", "kind", "reason", "confidence"]
    
    for amb in ambiguities:
        # Check Fields
        missing_fields = [f for f in required_ambiguity_fields if f not in amb]
        if missing_fields:
            report["schema_errors"].append({
                "issue": "Malformed Ambiguity Ticket", 
                "missing": missing_fields, 
                "record": amb
            })
            continue
            
        # Check Confidence Enum (Basic Check)
        if amb["confidence"] not in ["unresolved", "heuristic", "structural_violation"]:
            report["schema_warnings"].append({
                "issue": "Non-Standard Ambiguity Confidence",
                "value": amb["confidence"],
                "id": amb["id"]
            })

    # Final Status
    if report["schema_errors"]:
        report["status"] = "fail"

    # Output
    report_json = json.dumps(report, indent=2)
    if output_file:
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(report_json)
            print(f"Validation report saved to: {output_file}")
        except Exception as e:
            print(f"Error writing report: {e}")
            print(report_json)
    else:
        print(report_json)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_builder_output.py <path_to_ast.json> [--out <report.json>]")
        sys.exit(1)
        
    ast_file = sys.argv[1]
    out_file = None
    if len(sys.argv) >= 4 and sys.argv[2] == "--out":
        out_file = sys.argv[3]
        
    validate_ast(ast_file, out_file)
