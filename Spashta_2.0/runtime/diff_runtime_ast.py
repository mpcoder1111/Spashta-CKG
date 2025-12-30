"""
Spashta-CKG - Runtime AST Diff Generator
=========================================
Purpose:
    Detects incremental changes between the newly built Raw AST and the 
    previous Enriched AST to conform to the "Incremental Enrichment" protocol.

Logic:
    1.  Load New Raw AST (from build_runtime_ast.py).
    2.  Load Old Enriched AST (if exists).
    3.  Compare 'File' nodes using 'file_hash'.
    4.  Propagate File status to child nodes (Classes, Functions) via 'defines'/'contains' edges.
    5.  Handle Global/External nodes (not in any file).
    6.  Output 'diff_report.json' to classify every node as:
        - ADDED
        - MODIFIED
        - UNCHANGED
        - REMOVED

Usage:
    python runtime/diff_runtime_ast.py
"""

import json
import sys
import os
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Path Setup - REPO_ROOT is the Spashta-CKG folder (parent of Spashta_2.0)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SPASHTA_DIR = REPO_ROOT / "Spashta_2.0"
RUNTIME_DIR = SPASHTA_DIR / "runtime"
NEW_AST_PATH = RUNTIME_DIR / "code_knowledge_graph_ast.json"
OLD_AST_PATH = RUNTIME_DIR / "code_knowledge_graph_enriched.json"
DIFF_REPORT_PATH = RUNTIME_DIR / "diff_report.json"

def load_json(path):
    if not path.exists():
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Error loading {path}: {e}")
        return None

def build_containment_map(graph):
    """
    Returns a map: NodeID -> FileID
    Traverses 'defines', 'contains_class', 'contains_method', 'contains_member' edges.
    """
    parent_map = {} # Child -> Parent
    
    # Files are their own parents
    for n in graph.get("nodes", []):
         if n.get("node_type") == "File":
             parent_map[n["id"]] = n["id"]

    # Edges define hierarchy
    # We treat 'defines' as the primary ownership edge from File -> Thing
    # We treat 'contains_*' as ownership from Thing -> sub-Thing
    ownership_edges = {"defines", "contains_class", "contains_method", "contains_member", "contains_variable"}
    
    # Multi-pass propagation to handle depth
    # Or just build adjacency list and BFS from Files? BFS is safer.
    
    adj = {}
    for e in graph.get("edges", []):
        if e["type"] in ownership_edges:
            adj.setdefault(e["source"], []).append(e["target"])
            
    # BFS from Files
    queue = [n["id"] for n in graph.get("nodes", []) if n.get("node_type") == "File"]
    visited = set(queue)
    
    # Initialize map for root files
    node_to_file = {fid: fid for fid in queue}
    
    while queue:
        parent_id = queue.pop(0)
        root_file = node_to_file[parent_id]
        
        children = adj.get(parent_id, [])
        for child_id in children:
            if child_id not in visited:
                visited.add(child_id)
                node_to_file[child_id] = root_file
                queue.append(child_id)
                
    return node_to_file

def generate_diff():
    logging.info("Starting Incremental Diff Analysis...")
    
    new_ast = load_json(NEW_AST_PATH)
    if not new_ast:
        logging.error("New AST missing. Cannot diff.")
        sys.exit(1)
        
    old_ast = load_json(OLD_AST_PATH)
    
    report = {
        "status": "success",
        "file_status": {},
        "node_status": {},
        "stats": {"added": 0, "modified": 0, "unchanged": 0, "removed": 0}
    }

    # Case 0: First Run (No Old AST)
    if not old_ast:
        logging.info("No previous AST found. Marking ALL as ADDED.")
        for n in new_ast["nodes"]:
            report["node_status"][n["id"]] = "ADDED"
            report["stats"]["added"] += 1
            if n.get("node_type") == "File":
                report["file_status"][n["id"]] = "ADDED"
        
        with open(DIFF_REPORT_PATH, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
        return

    # Case 1: Incremental Run
    
    # 1. Map Files and Hashes
    # Normalization: Builders might use 'hash' or 'file_hash'. We accept both.
    new_files = {}
    for n in new_ast["nodes"]:
        if n.get("node_type") == "File":
            new_files[n["id"]] = n.get("file_hash") or n.get("hash")

    old_files = {}
    for n in old_ast["nodes"]:
        if n.get("node_type") == "File":
            old_files[n["id"]] = n.get("file_hash") or n.get("hash")
    
    # 2. Determine File Status
    all_files = set(new_files.keys()) | set(old_files.keys())
    
    for fid in all_files:
        if fid not in old_files:
            report["file_status"][fid] = "ADDED"
        elif fid not in new_files:
            report["file_status"][fid] = "REMOVED"
        else:
            n_hash = new_files[fid]
            o_hash = old_files[fid]
            
            # SAFEGUARD: If hash is missing, assume MODIFIED to force re-enrichment
            if n_hash is None or o_hash is None:
                report["file_status"][fid] = "MODIFIED"
                logging.warning(f"File {fid} missing hash. Forcing MODIFIED status.")
            elif n_hash != o_hash:
                report["file_status"][fid] = "MODIFIED"
            else:
                report["file_status"][fid] = "UNCHANGED"
            
    # 3. Map Nodes to Files
    new_node_to_file = build_containment_map(new_ast)
    old_node_to_file = build_containment_map(old_ast)
    
    new_nodes_map = {n["id"]: n for n in new_ast["nodes"]}
    old_nodes_map = {n["id"]: n for n in old_ast["nodes"]}
    
    all_node_ids = set(new_nodes_map.keys()) | set(old_nodes_map.keys())
    
    for nid in all_node_ids:
        # REMOVED
        if nid not in new_nodes_map:
            report["node_status"][nid] = "REMOVED"
            report["stats"]["removed"] += 1
            continue
            
        # ADDED
        if nid not in old_nodes_map:
            report["node_status"][nid] = "ADDED"
            report["stats"]["added"] += 1
            continue
            
        # EXISTING: Check Status
        # Optimization: If file hash is UNCHANGED, node is UNCHANGED.
        # Exception: Nodes not belonging to files (e.g. inferred inferred libraries) -> check structural equality.
        
        owner_file = new_node_to_file.get(nid)
        file_status = report["file_status"].get(owner_file) if owner_file else None
        
        if file_status == "UNCHANGED":
            report["node_status"][nid] = "UNCHANGED"
            report["stats"]["unchanged"] += 1
        elif file_status in ("ADDED", "MODIFIED"):
            # If file changed, we treat all its nodes as modified/re-evaluatable
            # We could do finer, deep-equal check, but safer to re-enrich.
            report["node_status"][nid] = "MODIFIED"
            report["stats"]["modified"] += 1
        else:
            # Orphan Node (No owner file, e.g. generic inferred node)
            # Compare pure structural dict (excluding mutable meta if any)
            # For strictness, if we can't tie it to a stable file, we check structural equality.
            
            n_new = new_nodes_map[nid]
            n_old = old_nodes_map[nid]
            
            # Simple check: if structure identical -> Unchanged
            # We exclude keys that might vary harmlessly, though builder is deterministic.
            if json.dumps(n_new, sort_keys=True) == json.dumps(n_old, sort_keys=True): # Structural match? 
                # Note: n_old has 'semantic_roles' and n_new doesn't.
                # We must compare ONLY common structural keys.
                # Actually, n_new is RAW. n_old is ENRICHED.
                # We cannot simple compare json dumps.
                
                # Logic: If raw structure (type, name, etc) is same, and parent is unknown/unchanged...
                # Actually, simplest safe policy: MODIFIED. Let enricher re-run adapter rules.
                # Adapter rules are cheap.
                report["node_status"][nid] = "MODIFIED"
                report["stats"]["modified"] += 1

    logging.info(f"Diff Complete. Stats: {report['stats']}")
    
    with open(DIFF_REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

if __name__ == "__main__":
    generate_diff()
