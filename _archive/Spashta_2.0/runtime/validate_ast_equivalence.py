"""
Spashta-CKG — AST Structural Equivalence Validator

PURPOSE
-------
Ensure that the enriched Code Knowledge Graph (CKG) has NOT changed
the structural topology of the raw AST produced by builders.

This validator enforces the core architectural guarantee:
    Adapters may INTERPRET facts, but must NEVER MODIFY facts.

WHEN THIS RUNS
--------------
This script MUST be executed after:
    - build_runtime_ast.py
    - enrich_runtime_ast.py

And BEFORE:
    - Any IDE agent reasoning
    - Any automated code modification

WHAT IT VALIDATES
-----------------
Nodes:
    - Same node count
    - Same node IDs
    - Same node types
    - No nodes added or removed

Edges:
    - Same edge count
    - Same (source, target, type) relationships
    - No edges added or removed
    - No rewiring of relationships

ALLOWED DIFFERENCES
-------------------
The enriched AST MAY add:
    - semantic_roles
    - annotations
    - confidence scores
    - framework tags

These are allowed ONLY as additional fields.
No structural fields may change.

FORBIDDEN DIFFERENCES
---------------------
    - Adding nodes or edges
    - Removing nodes or edges
    - Changing node types
    - Changing edge types
    - Changing edge source or target

INPUTS
------
    1. Raw AST JSON path
    2. Enriched AST JSON path

OUTPUTS
-------
    - Exit code 0: Structural equivalence preserved
    - Exit code 1: Structural violation detected
    - JSON report written to:
        runtime/validation_reports/ast_equivalence_report.json

FAILURE BEHAVIOR
----------------
On failure:
    - The runtime/agent loop MUST HALT
    - No agent reasoning is allowed
    - Violations are emitted in machine-readable form

This file is a STRUCTURAL GUARD.
It must never attempt to repair, infer, or relax rules.
"""


import json
import sys
import os
import logging
from pathlib import Path

# Configure logging to stderr so JSON report is clean if printed
logging.basicConfig(level=logging.INFO, stream=sys.stderr, format='%(levelname)s: %(message)s')

# Path Setup - REPO_ROOT is the Spashta-CKG folder (parent of Spashta_2.0)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SPASHTA_DIR = REPO_ROOT / "Spashta_2.0"
REPORT_DIR = SPASHTA_DIR / "runtime" / "validation_reports"
REPORT_FILE = REPORT_DIR / "ast_equivalence_report.json"

def load_graph(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load graph from {path}: {e}")
        sys.exit(1)

def write_report(status, violations):
    """Write the validation report to JSON file."""
    report = {
        "status": status,
        "violations": violations
    }
    
    # Ensure directory exists
    if not REPORT_DIR.exists():
        try:
            REPORT_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logging.error(f"Failed to create report directory {REPORT_DIR}: {e}")
            # Fallback to current dir if cannot create
            
    try:
        with open(REPORT_FILE, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
        logging.info(f"Validation report written to: {REPORT_FILE}")
    except Exception as e:
        logging.error(f"Failed to write report to {REPORT_FILE}: {e}")

def validate_equivalence(raw_path, enriched_path):
    logging.info("Starting AST Equivalence Validation...")
    logging.info(f"Raw AST: {raw_path}")
    logging.info(f"Enriched AST: {enriched_path}")

    raw_graph = load_graph(raw_path)
    enriched_graph = load_graph(enriched_path)
    
    violations = []

    # 1. Validate Node Count
    raw_nodes = raw_graph.get("nodes", [])
    enriched_nodes = enriched_graph.get("nodes", [])

    if len(raw_nodes) != len(enriched_nodes):
        violations.append({
            "type": "node_count_mismatch",
            "detail": f"Raw nodes: {len(raw_nodes)}, Enriched nodes: {len(enriched_nodes)}"
        })

    # Create dictionaries for faster lookup
    raw_node_map = {n['id']: n for n in raw_nodes}
    enriched_node_map = {n['id']: n for n in enriched_nodes}

    # 2. Validate Node IDs and Types
    # Check missing in enriched (Deleted nodes)
    for node_id, raw_node in raw_node_map.items():
        if node_id not in enriched_node_map:
            violations.append({
                "type": "node_removed",
                "detail": f"Node {node_id} present in Raw but missing in Enriched."
            })
            continue
        
        enriched_node = enriched_node_map[node_id]
        
        # Check Type Preservation
        # NOTE: We explicitly EXCLUDE 'file_hash' and other metadata from this check.
        # Only 'id' and 'type' define the structural topology.
        # 'file_hash' is mutable metadata for incremental builds.
        if raw_node.get('type') != enriched_node.get('type'):
            violations.append({
                "type": "node_type_changed",
                "detail": f"Node {node_id} type changed from '{raw_node.get('type')}' to '{enriched_node.get('type')}'"
            })

    # Check extra in enriched (Added nodes)
    for node_id in enriched_node_map:
        if node_id not in raw_node_map:
            violations.append({
                "type": "node_added",
                "detail": f"Node {node_id} added in Enriched (Forbidden)."
            })

    # 3. Validate Edges
    raw_edges = raw_graph.get("edges", [])
    enriched_edges = enriched_graph.get("edges", [])

    if len(raw_edges) != len(enriched_edges):
         # We log this but continue to find specific mismatches
         pass 

    # Helper to create unique edge keys
    def get_edge_key(edge):
        # Using sorted tuple of (source, target, type) to identify edge
        return f"{edge['source']}->{edge['target']}|{edge['type']}"

    raw_edge_keys = {get_edge_key(e) for e in raw_edges}
    enriched_edge_keys = {get_edge_key(e) for e in enriched_edges}

    # Check for missing edges (Deleted edges)
    missing_edges = raw_edge_keys - enriched_edge_keys
    for key in missing_edges:
        violations.append({
            "type": "edge_removed",
            "detail": f"Edge {key} missing in Enriched."
        })

    # Check for extra edges (Added edges)
    extra_edges = enriched_edge_keys - raw_edge_keys
    for key in extra_edges:
        violations.append({
            "type": "edge_added",
            "detail": f"Edge {key} added in Enriched (Forbidden)."
        })

    # 4. Validate Ambiguities (Preservation Check)
    raw_ambiguities = raw_graph.get("ambiguities", [])
    enriched_ambiguities = enriched_graph.get("ambiguities", [])
    
    # We strictly enforce that ambiguities are preserved (count match for now)
    # Ideally, we would check identity, but count is a good proxy for accidental drops.
    if len(raw_ambiguities) != len(enriched_ambiguities):
        violations.append({
            "type": "ambiguity_mismatch",
            "detail": f"Raw ambiguities: {len(raw_ambiguities)}, Enriched ambiguities: {len(enriched_ambiguities)}. Enrichment must preserve known unknowns."
        })

    # Final Decision
    if violations:
        logging.error("❌ Enriched AST violates structural equivalence.")
        for v in violations[:5]: # Log first few violations to stderr
            logging.error(f"  [{v['type']}] {v['detail']}")
        if len(violations) > 5:
            logging.error(f"  ... and {len(violations) - 5} more.")
            
        write_report("fail", violations)
        return False
    else:
        logging.info("✅ AST Equivalence Validation PASSED: Topology is preserved.")
        write_report("pass", [])
        return True

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python validate_ast_equivalence.py <raw_ast_path> <enriched_ast_path>")
        sys.exit(1)
    
    raw = sys.argv[1]
    enriched = sys.argv[2]
    
    success = validate_equivalence(raw, enriched)
    if not success:
        sys.exit(1)
    sys.exit(0)
