
import json
import logging
import datetime
from pathlib import Path

# Setup
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SPASHTA_DIR = REPO_ROOT / "Spashta_2.0"
RUNTIME_DIR = SPASHTA_DIR / "runtime"
INPUT_PATH = RUNTIME_DIR / "code_knowledge_graph_enriched.json"
OUTPUT_PATH = RUNTIME_DIR / "code_knowledge_graph_enriched_by_Agent.json"

# Mock LLM Output for Demo Files
# Format: NodeID -> Enrichment Dict
ENRICHMENT_DATA = {
    # MODELS
    "Class:DemoModel": {
        "intent": "Defines the core data structure for the demo application",
        "summary": "Primary domain model for demonstration",
        "complexity_score": 1,
        "domain_tags": ["data-model", "demo-core"],
        "pure_logic": True,
        "side_effects": []
    },
    "Method:DemoModel::get_display_name": {
        "intent": "Formats the model name for UI display",
        "summary": "Display name formatter",
        "complexity_score": 1,
        "domain_tags": ["ui-helper"],
        "pure_logic": True,
        "side_effects": []
    },
    
    # VIEWS
    "Function:home_demo": {
        "intent": "Handles the main landing page request and context loading",
        "summary": "Main dashboard view",
        "complexity_score": 2,
        "domain_tags": ["view", "navigation"],
        "pure_logic": False,
        "side_effects": ["database_read", "template_render"]
    },
    "Function:api_items_demo": {
        "intent": "API endpoint serving partial HTML for HTMX dynamic loading",
        "summary": "HTMX items endpoint",
        "complexity_score": 2,
        "domain_tags": ["api", "htmx", "dynamic-ui"],
        "pure_logic": False,
        "side_effects": ["database_read", "template_render"]
    },
    
    # JAVASCRIPT
    "Function:initDemo": {
        "intent": "Initializes frontend components on page load",
        "summary": "Frontend initializer",
        "complexity_score": 1,
        "domain_tags": ["frontend", "lifecycle"],
        "pure_logic": False,
        "side_effects": ["console_log"]
    },
    
    # SPASHTA QUERY TOOL (Example of Self-Documentation)
    "File:Spashta_2.0/runtime/query_spashta.py": {
        "intent": "CLI Entry point for querying the Code Knowledge Graph",
        "summary": "Main Query Tool CLI",
        "complexity_score": 4,
        "domain_tags": ["cli", "tooling", "interface"],
        "pure_logic": False,
        "side_effects": ["file_io", "stdout"]
    }
}

def main():
    if not INPUT_PATH.exists():
        logging.error(f"Input CKG not found: {INPUT_PATH}")
        return

    logging.info(f"Loading CKG from {INPUT_PATH}")
    with open(INPUT_PATH, 'r', encoding='utf-8') as f:
        graph = json.load(f)

    enriched_count = 0
    
    # Apply Enrichment
    for node in graph.get("nodes", []):
        nid = node.get("id")
        
        # Check by ID match
        # (Simplified matching: if key is IN the ID, apply it. Not robust but good for demo script)
        
        applied = False
        for key, enrichment in ENRICHMENT_DATA.items():
            # Exact ID match or simple heuristic
            if key == nid or (key.split(":")[-1] in nid and node.get("name") == key.split(":")[-1].split("::")[-1]):
                 # Basic heuristic matching for demo script simplicity
                 # Real agent would match exact IDs
                 node["llm_enrichment"] = {
                     **enrichment,
                     "enriched_at": datetime.datetime.now().isoformat(),
                     "enriched_at_hash": node.get("hash") or "unknown"
                 }
                 enriched_count += 1
                 applied = True
                 break
        
        # Generic fallback for all _demo files if not specifically targeted above
        if not applied and "_demo" in node.get("file_path", ""):
             node["llm_enrichment"] = {
                 "intent": f"Demo component: {node.get('name')}",
                 "summary": "Auto-generated demo description",
                 "complexity_score": 1,
                 "domain_tags": ["demo-generic"],
                 "enriched_at": datetime.datetime.now().isoformat(),
                 "enriched_at_hash": node.get("hash") or "unknown"
             }
             enriched_count += 1

    logging.info(f"Enriched {enriched_count} nodes.")

    # Save
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(graph, f, indent=2)
    
    logging.info(f"Saved Enriched Graph to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
