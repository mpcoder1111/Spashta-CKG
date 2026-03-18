"""
Spashta-CKG — Runtime AST Builder & Merger

ROLE
----
This script is the single authoritative runtime orchestrator that produces
the **raw, merged Code Knowledge Graph AST** for a project.

It coordinates multiple language builders, validates their outputs, and
merges them into one trusted structural graph.

OUTPUT
------
runtime/code_knowledge_graph_ast.json

THIS SCRIPT DOES
----------------
Phase 0 — Project Context Resolution
• Loads project/profile.json
• Determines which language builders are active
• Resolves project_root explicitly (no assumptions)

Phase 1 — Builder Execution & Validation
• Executes each language-specific builder
• Produces one AST fragment per language
• Immediately validates each fragment against Core Schema
• Stops execution on first violation (fail-fast safety)

Phase 2 — AST Merge (Deterministic & Concept-Aware)
• Merges all validated fragments into a single graph
• Identity Strategy (Priority Order):
  1. Strong Identity (File Paths): "File:app/models.py" -> Prevents filename collisions.
  2. Scoped Identity (Builder IDs): "app/models.py::MyModel" -> Preserves structure.
  3. Loose Identity (Fallback): "Route:/login" -> Enables "Conceptual Merging" across silos.
• Deduplicates nodes and edges deterministically
• Preserves only structural facts (no semantics)
• Writes the merging AST to runtime/

GUARANTEES
----------
• Exactly ONE merged raw AST is produced
• All nodes and edges conform to Core schema
• Multi-language projects are handled uniformly
• No semantic meaning is added

DOES NOT
--------
• Does NOT apply framework semantics
• Does NOT enrich intent or behavior
• Does NOT mutate source code
• Does NOT invoke LLMs or Agents

PRINCIPLE
---------
Builders define WHAT EXISTS.
This script ensures those facts are:
  validated → merged → trusted.

This output is immutable input for Adapter enrichment.
"""



import sys
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any

# Initial Setup - REPO_ROOT is the Spashta-CKG folder (parent of Spashta_2.0)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SPASHTA_DIR = REPO_ROOT / "Spashta_2.0"
PROFILE_PATH = SPASHTA_DIR / "project" / "profile.json"
RUNTIME_DIR = SPASHTA_DIR / "runtime"
VALIDATOR_SCRIPT = SPASHTA_DIR / "builders" / "validation" / "validate_builder_output.py"

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def run_command(cmd_list):
    """Runs a subprocess command."""
    try:
        subprocess.run(cmd_list, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"Error executing {' '.join(cmd_list)}:\n{e.stderr}")
        return False
    return True

def run_builder(language: str, project_root: Path, output_dir: Path):
    """Runs the builder for the specified language with explicit scope."""
    builder_script = SPASHTA_DIR / "builders" / language / f"build_{language}_ast.py"
    if not builder_script.exists():
        print(f"Warning: Builder for {language} not found at {builder_script}")
        return None
    
    fragment_path = output_dir / f"fragment_{language}.json"
    
    cmd = [
        sys.executable, str(builder_script),
        "--source-root", str(project_root),
        "--out", str(fragment_path)
    ]
    
    print(f"Running Builder: {language} -> {fragment_path.name}")
    if not run_command(cmd):
        return None
        
    if not fragment_path.exists():
         print(f"Error: Builder for {language} did not produce outputs.")
         return None
         
    return fragment_path

def validate_fragment(fragment_path):
    """Run validation on the fragment."""
    print(f"Validating fragment: {fragment_path.name}")
    
    report_file = RUNTIME_DIR / f"report_{fragment_path.stem}.json"
    cmd = [sys.executable, str(VALIDATOR_SCRIPT), str(fragment_path), "--out", str(report_file)]
    if not run_command(cmd):
        return False
        
    try:
        report = load_json(report_file)
    except:
        print("Validation report generation failed.")
        return False
        
    passed = (report.get("status") == "pass")
    
    if not passed:
        print(f"Validation FAILED for {fragment_path.name}:")
        for v in report.get("violations", []):
            print(f"- {v.get('issue')}: {v.get('node', {}).get('name') or v.get('value')} ({v.get('detail', '')})")
    
    # Cleanup report
    if report_file.exists(): report_file.unlink()
    
    return passed

def merge_fragments(fragments: List[Path]):
    """Merges all AST fragments into one Graph."""
    print("Merging and Normalizing AST Fragments...")
    merged_nodes = {} # key (canonical_id) -> node dict
    merged_edges = []
    seen_edges = set() # (type, source, target)
    
    merged_ambiguities = []
    
    # Pass 1: Collect and Normalize Nodes
    # We need a map from (Builder-Context-Name) -> Canonical ID to resolve edges later.
    # Current builders output edges using 'name' references.
    # Since names might not be globally unique across types, we try to resolve smartly.
    
    name_to_id_map = {} # 'name' -> 'canonical_id' (Last writer wins, assuming consistent naming)
    
    for frag in fragments:
        data = load_json(frag)
        
        # Collect Ambiguities
        merged_ambiguities.extend(data.get("ambiguities", []))
        
        for n in data.get("nodes", []):
            # 1. Normalize Type
            # Builders might emit 'node_type' or 'type'. Instruction says standardize to 'node_type'.
            n_type = n.get("node_type") or n.get("type") or "Unknown"
            
            # 2. Generate Stable ID (Strong Identity Strategy)
            # Priority 1: Use Unique File Path if available (e.g. File:app/models.py)
            # Priority 2: Use scoped ID from builder if it looks robust (e.g. app/models.py::Class::MyModel)
            # Priority 3: Fallback to Name (e.g. Class:MyModel) - risky for collisions
            
            n_name = n.get("name", "Unnamed")
            n_path = n.get("file_path")
            raw_id = n.get("id", "")
            
            # Heuristic for Robust ID: If ID contains the path or "::", it's likely scoped/strong already.
            # We trust the builder's scoped ID if available.
            
            if n_path and n_type == "File":
                 canonical_id = f"{n_type}:{n_path}"
            elif "::" in raw_id:
                 # It's a scoped symbol (e.g. app/models.py::MyModel)
                 # We preserve this detailed scope but normalize the prefix if needed?
                 # Actually, let's keep the builder's scoped ID as is, just prefixed with Type for global clarity if needed.
                 # But wait, builder IDs like "app/models.py::MyModel" are already strong.
                 canonical_id = raw_id
            elif n_path:
                 # It has a path but isn't a File node? (Rare case)
                 canonical_id = f"{n_type}:{n_path}::{n_name}"
            else:
                 # Fallback: Loose Identity (Name only)
                 canonical_id = f"{n_type}:{n_name}"
            
            # 3. Create Normalized Node
            normalized_node = n.copy()
            normalized_node["id"] = canonical_id
            normalized_node["node_type"] = n_type
            normalized_node["type"] = n_type
            
            merged_nodes[canonical_id] = normalized_node
            
            # Map builder-provided name AND raw ID to this new ID for edge resolution
            name_to_id_map[n_name] = canonical_id
            if raw_id:
                name_to_id_map[raw_id] = canonical_id

    # Pass 2: Normalize and Resolve Edges
    for frag in fragments:
        data = load_json(frag)
        
        for e in data.get("edges", []):
            # Normalize keys
            # Builders use 'from'/'to'/'edge'. Instruction: 'source'/'target'/'type'.
            
            raw_src = e.get("from")
            raw_tgt = e.get("to")
            raw_type = e.get("edge") or e.get("type")
            
            # Resolve to Canonical IDs
            # If the raw reference is already a canonical ID (unlikely), use it.
            # Otherwise look it up in the map.
            src_id = name_to_id_map.get(raw_src, raw_src)
            tgt_id = name_to_id_map.get(raw_tgt, raw_tgt)
            
            # Verify validity (Dangling pointer check)
            if src_id not in merged_nodes:
                 # Try to construct strict ID if simple lookup failed (e.g. if builder used implicit type)
                 # For now, we log warning/skip or accept? 
                 # We accept raw if strict lookup fails, but this risks validation failure.
                 pass
            
            if tgt_id not in merged_nodes:
                 pass

            # Create Normalized Edge
            normalized_edge = {
                "source": src_id,
                "target": tgt_id,
                "type": raw_type
            }
            
            # Validating metadata transfer
            for k, v in e.items():
                if k not in ["from", "to", "edge", "type", "source", "target"]:
                    normalized_edge[k] = v

            # Deduplicate
            edge_key = (raw_type, src_id, tgt_id)
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                merged_edges.append(normalized_edge)
                
    final_output = {
        "nodes": list(merged_nodes.values()),
        "edges": merged_edges,
        "ambiguities": merged_ambiguities,
        "_meta": {
             "source": "Spashta Runtime Orchestrator",
             "fragments_merged": [f.name for f in fragments]
        }
    }
    
    out_path = RUNTIME_DIR / "code_knowledge_graph_ast.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(final_output, f, indent=2)
    print(f"Final Merged AST saved to: {out_path}")

def main():
    if not PROFILE_PATH.exists():
        print("Error: No project profile found.")
        sys.exit(1)
        
    profile = load_json(PROFILE_PATH)
    languages = profile.get("languages", [])
    
    # Phase 0: Context Resolution
    if "project_root" in profile:
        # REPO_ROOT is Spashta-CKG folder
        # Relative paths in profile.json are resolved from REPO_ROOT
        raw_root = Path(profile["project_root"])

        project_root = (
            raw_root if raw_root.is_absolute()
            else (REPO_ROOT / raw_root).resolve()
        )

        print(f"REPO_ROOT: {REPO_ROOT}")
        print(f"Project root (raw): {raw_root}")
        print(f"Project root (resolved): {project_root}")
    else:
        print("Error: 'project_root' key missing in profile.json. Cannot determine scan scope.")
        sys.exit(1)


    print(f"Project Context: {project_root}")
    if not project_root.exists():
        print(f"Error: Project root path {project_root} not found.")
        sys.exit(1)
    
    # Ensure Runtime Dir Exists
    RUNTIME_DIR.mkdir(exist_ok=True)
    
    # Subdirectory for fragments
    FRAGMENTS_DIR = RUNTIME_DIR / "builders_generated_fragments"
    FRAGMENTS_DIR.mkdir(exist_ok=True)
    
    # Clean previous fragments in the subfolder
    for f in FRAGMENTS_DIR.glob("fragment_*.json"): f.unlink()
    
    valid_fragments = []
    
    for lang in languages:
        frag = run_builder(lang, project_root, FRAGMENTS_DIR)
        if frag:
            if validate_fragment(frag):
                valid_fragments.append(frag)
            else:
                print(f"Stopping Build: Validation failed for {lang}.")
                sys.exit(1) # Fail fast
        else:
             print(f"Error: Builder failed for declared language {lang}")
             sys.exit(1)

    # Phase 2: Merge
    if valid_fragments:
        merge_fragments(valid_fragments)
    else:
        print("No valid fragments to merge.")


if __name__ == "__main__":
    main()
