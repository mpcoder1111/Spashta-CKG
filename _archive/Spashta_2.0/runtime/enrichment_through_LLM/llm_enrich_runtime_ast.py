"""
Spashta 2.0 – Level-2 LLM Semantic Enrichment Helper Script

PURPOSE
-------
This script is a HELPER for the LLM enrichment process.
It provides utilities for identifying pending files, validation, and statistics.

The actual enrichment is performed by the IDE Agent (LLM), NOT this script.

COMMANDS
--------
--list-pending   : Compare hashes, output files needing enrichment
--validate       : Validate Agent's output JSON
--stats          : Show enrichment statistics

OUTPUT FILES
------------
LLM_working_files/files_to_enrich.json   : List of files pending enrichment
LLM_working_files/enrichment_stats.json  : Statistics about enrichment progress

USAGE
-----
# Step 1: Agent runs this to get pending files
python llm_enrich_runtime_ast.py --list-pending

# Step 2: Agent processes files from files_to_enrich.json

# Step 3: Validate output (optional)
python llm_enrich_runtime_ast.py --validate
"""

import json
import sys
import argparse
import datetime
from pathlib import Path

# Path Configuration
SCRIPT_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = SCRIPT_DIR.parent  # runtime/
WORKING_DIR = SCRIPT_DIR / "LLM_working_files"

# Input files
L1_ENRICHED_PATH = RUNTIME_DIR / "code_knowledge_graph_enriched.json"
L2_ENRICHED_PATH = RUNTIME_DIR / "code_knowledge_graph_enriched_by_Agent.json"

# Output files (to working folder)
FILES_TO_ENRICH_PATH = WORKING_DIR / "files_to_enrich.json"
ENRICHMENT_STATS_PATH = WORKING_DIR / "enrichment_stats.json"


def load_json(path):
    """Load JSON file, return None if not exists."""
    if not path.exists():
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(path, data):
    """Save data to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def get_file_nodes(graph):
    """Extract File nodes from graph."""
    return [n for n in graph.get("nodes", []) if n.get("node_type") == "File"]


def list_pending_files(mode="incremental"):
    """
    Compare hashes between L1 and L2 graphs.
    Output list of files that need enrichment.
    """
    print("Analyzing files for pending enrichment...")
    
    # Load L1 enriched graph (source of truth for current state)
    l1_graph = load_json(L1_ENRICHED_PATH)
    if not l1_graph:
        print(f"Error: {L1_ENRICHED_PATH} not found.")
        sys.exit(1)
    
    # Load L2 enriched graph (previous enrichment, may not exist)
    l2_graph = load_json(L2_ENRICHED_PATH)
    
    # Get all File nodes from L1
    l1_file_nodes = get_file_nodes(l1_graph)
    
    # Build lookup for L2 nodes (if exists)
    l2_node_map = {}
    if l2_graph:
        for node in l2_graph.get("nodes", []):
            l2_node_map[node.get("id")] = node
    
    # Analyze each file
    files_to_enrich = []
    files_skipped = []
    
    for file_node in l1_file_nodes:
        file_id = file_node.get("id")
        current_hash = file_node.get("hash")
        file_path = file_node.get("file_path", file_node.get("name"))
        
        # Check if L2 has this file
        l2_node = l2_node_map.get(file_id)
        
        needs_enrichment = False
        reason = ""
        
        if mode == "full":
            # Full mode: enrich all files
            needs_enrichment = True
            reason = "full_mode"
        elif not l2_node:
            # File not in L2 graph: new file
            needs_enrichment = True
            reason = "new_file"
        elif "llm_enrichment" not in l2_node:
            # File exists but no enrichment
            needs_enrichment = True
            reason = "not_enriched"
        else:
            # Check hash comparison
            enriched_at_hash = l2_node.get("llm_enrichment", {}).get("enriched_at_hash")
            if enriched_at_hash != current_hash:
                needs_enrichment = True
                reason = "hash_changed"
            else:
                reason = "unchanged"
        
        file_info = {
            "id": file_id,
            "file_path": file_path,
            "current_hash": current_hash
        }
        
        if needs_enrichment:
            file_info["reason"] = reason
            files_to_enrich.append(file_info)
        else:
            file_info["reason"] = reason
            files_skipped.append(file_info)
    
    # Prepare output
    output = {
        "_generated_at": datetime.datetime.now().isoformat(),
        "_mode": mode,
        "_summary": {
            "total_files": len(l1_file_nodes),
            "pending_enrichment": len(files_to_enrich),
            "skipped": len(files_skipped)
        },
        "files_to_enrich": files_to_enrich,
        "files_skipped": files_skipped
    }
    
    # Save output
    save_json(FILES_TO_ENRICH_PATH, output)
    
    # Print summary
    print(f"\nSummary:")
    print(f"  Total files: {len(l1_file_nodes)}")
    print(f"  Pending enrichment: {len(files_to_enrich)}")
    print(f"  Skipped (unchanged): {len(files_skipped)}")
    print(f"\nOutput saved to: {FILES_TO_ENRICH_PATH}")
    
    return output


def show_stats():
    """Show enrichment statistics."""
    print("Calculating enrichment statistics...")
    
    l1_graph = load_json(L1_ENRICHED_PATH)
    l2_graph = load_json(L2_ENRICHED_PATH)
    
    if not l1_graph:
        print(f"Error: {L1_ENRICHED_PATH} not found.")
        sys.exit(1)
    
    total_nodes = len(l1_graph.get("nodes", []))
    total_ambiguities = len(l1_graph.get("ambiguities", []))
    
    nodes_enriched = 0
    ambiguities_resolved = 0
    ambiguities_unresolved = 0
    
    if l2_graph:
        for node in l2_graph.get("nodes", []):
            if "llm_enrichment" in node:
                nodes_enriched += 1
        
        for amb in l2_graph.get("ambiguities", []):
            if "llm_resolution" in amb:
                if amb["llm_resolution"].get("status") == "resolved":
                    ambiguities_resolved += 1
                else:
                    ambiguities_unresolved += 1
    
    stats = {
        "_generated_at": datetime.datetime.now().isoformat(),
        "nodes": {
            "total": total_nodes,
            "enriched": nodes_enriched,
            "pending": total_nodes - nodes_enriched,
            "coverage_percent": round(nodes_enriched / total_nodes * 100, 1) if total_nodes > 0 else 0
        },
        "ambiguities": {
            "total": total_ambiguities,
            "resolved": ambiguities_resolved,
            "unresolved": ambiguities_unresolved,
            "not_processed": total_ambiguities - ambiguities_resolved - ambiguities_unresolved
        }
    }
    
    save_json(ENRICHMENT_STATS_PATH, stats)
    
    print(f"\nEnrichment Statistics:")
    print(f"  Nodes: {nodes_enriched}/{total_nodes} ({stats['nodes']['coverage_percent']}%)")
    print(f"  Ambiguities: {ambiguities_resolved} resolved, {ambiguities_unresolved} unresolved")
    print(f"\nStats saved to: {ENRICHMENT_STATS_PATH}")
    
    return stats


def validate_output():
    """Validate the Agent's output JSON."""
    print("Validating LLM enrichment output...")
    
    l2_graph = load_json(L2_ENRICHED_PATH)
    
    if not l2_graph:
        print(f"Error: {L2_ENRICHED_PATH} not found. Nothing to validate.")
        sys.exit(1)
    
    errors = []
    warnings = []
    
    # Check required sections
    if "nodes" not in l2_graph:
        errors.append("Missing 'nodes' array")
    if "edges" not in l2_graph:
        errors.append("Missing 'edges' array")
    
    # Check nodes
    for node in l2_graph.get("nodes", []):
        node_id = node.get("id", "UNKNOWN")
        
        # Check if llm_enrichment is properly structured
        if "llm_enrichment" in node:
            enr = node["llm_enrichment"]
            if "intent" not in enr:
                warnings.append(f"Node {node_id}: missing 'intent' in llm_enrichment")
            if "summary" not in enr:
                warnings.append(f"Node {node_id}: missing 'summary' in llm_enrichment")
    
    # Check ambiguities
    for i, amb in enumerate(l2_graph.get("ambiguities", [])):
        if "llm_resolution" in amb:
            res = amb["llm_resolution"]
            if "status" not in res:
                errors.append(f"Ambiguity {i}: missing 'status' in llm_resolution")
            if res.get("status") == "resolved" and "probable_target" not in res:
                errors.append(f"Ambiguity {i}: status is 'resolved' but missing 'probable_target'")
    
    # Print results
    print(f"\nValidation Results:")
    print(f"  Errors: {len(errors)}")
    print(f"  Warnings: {len(warnings)}")
    
    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  ❌ {e}")
    
    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  ⚠️ {w}")
    
    if not errors and not warnings:
        print("\n✅ Validation passed. Output is valid.")
    
    return {"errors": errors, "warnings": warnings}


def main():
    parser = argparse.ArgumentParser(
        description="LLM Enrichment Helper Script for Spashta-CKG"
    )
    parser.add_argument(
        "--list-pending",
        action="store_true",
        help="Compare hashes and list files needing enrichment"
    )
    parser.add_argument(
        "--mode",
        choices=["incremental", "full"],
        default="incremental",
        help="Mode: 'incremental' (default) or 'full'"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show enrichment statistics"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate Agent's output JSON"
    )
    
    args = parser.parse_args()
    
    if args.list_pending:
        list_pending_files(mode=args.mode)
    elif args.stats:
        show_stats()
    elif args.validate:
        validate_output()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
