"""
Quick enrichment script for demo purposes.
"""
import json
from datetime import datetime
from pathlib import Path

RUNTIME_DIR = Path("runtime")
INPUT_PATH = RUNTIME_DIR / "code_knowledge_graph_enriched.json"
OUTPUT_PATH = RUNTIME_DIR / "code_knowledge_graph_enriched_by_Agent.json"

# Load graph
with open(INPUT_PATH, "r", encoding="utf-8") as f:
    graph = json.load(f)

now = datetime.now().isoformat()

# Define enrichments based on node analysis
enrichments = {
    "File:build_kg_ast_based.py": {
        "intent": "Core AST builder script that generates the Code Knowledge Graph from Python source code",
        "summary": "AST-based CKG generator",
        "complexity_score": 4,
        "domain_tags": ["code-analysis", "ast", "knowledge-graph", "meta-tooling"],
        "pure_logic": False,
        "side_effects": ["file_write"],
        "enriched_at_hash": "fe74d81cbcb33565ef0e186c26665986",
        "enriched_at": now
    },
    "build_kg_ast_based.py::calculate_file_hash": {
        "intent": "Computes MD5 hash of a file for change detection",
        "summary": "File hash calculator",
        "complexity_score": 1,
        "domain_tags": ["hashing", "change-detection"],
        "pure_logic": True,
        "side_effects": [],
        "enriched_at_hash": "fe74d81cbcb33565ef0e186c26665986",
        "enriched_at": now
    },
    "build_kg_ast_based.py::CodeAnalyzer": {
        "intent": "AST visitor that extracts code structure including imports, classes, functions",
        "summary": "AST code analyzer visitor",
        "complexity_score": 4,
        "domain_tags": ["ast-analysis", "code-parsing"],
        "pure_logic": True,
        "side_effects": [],
        "enriched_at_hash": "fe74d81cbcb33565ef0e186c26665986",
        "enriched_at": now
    },
    "build_kg_ast_based.py::main": {
        "intent": "Entry point that orchestrates CKG generation by scanning files and building the graph",
        "summary": "Main CKG orchestrator",
        "complexity_score": 3,
        "domain_tags": ["orchestration", "entry-point"],
        "pure_logic": False,
        "side_effects": ["file_write"],
        "enriched_at_hash": "fe74d81cbcb33565ef0e186c26665986",
        "enriched_at": now
    },
    "File:sample_project/app/models.py": {
        "intent": "Django data model definitions for the application",
        "summary": "Django models module",
        "complexity_score": 1,
        "domain_tags": ["data-model", "orm", "django"],
        "pure_logic": True,
        "side_effects": [],
        "enriched_at_hash": "7ea922ea096d8a6d259ef2c241cdf44f",
        "enriched_at": now
    },
    "sample_project/app/models.py::MyModel": {
        "intent": "Simple data model with a name field for demonstration purposes",
        "summary": "Demo data model",
        "complexity_score": 1,
        "domain_tags": ["data-model", "entity"],
        "pure_logic": True,
        "side_effects": [],
        "enriched_at_hash": "7ea922ea096d8a6d259ef2c241cdf44f",
        "enriched_at": now
    },
    "File:sample_project/app/views.py": {
        "intent": "Django views handling HTTP requests and rendering templates",
        "summary": "Django views module",
        "complexity_score": 2,
        "domain_tags": ["web-views", "http", "django"],
        "pure_logic": False,
        "side_effects": ["database_read"],
        "enriched_at_hash": "b7edc6bfc866cbb29351456360ca47e2",
        "enriched_at": now
    },
    "sample_project/app/views.py::home": {
        "intent": "Home page view that fetches all MyModel objects and renders them in a template",
        "summary": "Home page view",
        "complexity_score": 2,
        "domain_tags": ["web-view", "data-retrieval", "template-rendering"],
        "pure_logic": False,
        "side_effects": ["database_read"],
        "enriched_at_hash": "b7edc6bfc866cbb29351456360ca47e2",
        "enriched_at": now
    }
}

# Apply enrichments
for node in graph["nodes"]:
    node_id = node["id"]
    if node_id in enrichments:
        node["llm_enrichment"] = enrichments[node_id]

# Apply llm_resolution to ambiguities
for amb in graph.get("ambiguities", []):
    kind = amb.get("kind", "")
    
    if kind == "call_target_unknown" and "render" in amb.get("expression", ""):
        amb["llm_resolution"] = {
            "status": "resolved",
            "probable_target": "django.shortcuts.render",
            "confidence": 0.95,
            "reasoning": "render is imported from django.shortcuts at line 1"
        }
    elif kind == "import_module_unknown":
        amb["llm_resolution"] = {
            "status": "unresolved",
            "confidence": 0.0,
            "reasoning": "External Django framework module, not in local codebase"
        }
    elif kind in ["mapping_violation", "schema_violation"]:
        amb["llm_resolution"] = {
            "status": "unresolved",
            "confidence": 0.0,
            "reasoning": "Schema/mapping issue - requires builder configuration update"
        }

# Update meta
graph["_meta"]["level_2_enrichment"] = {
    "timestamp": now,
    "model": "gemini-2.0-flash",
    "nodes_enriched": len(enrichments),
    "ambiguities_processed": len(graph.get("ambiguities", []))
}

# Save
with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(graph, f, indent=2)

print(f"Enriched graph saved to {OUTPUT_PATH}")
print(f"Nodes enriched: {len(enrichments)}")
print(f"Ambiguities processed: {len(graph.get('ambiguities', []))}")
