"""
================================================================================
Spashta CKG Query Tool - AI Agent's Gateway to Code Knowledge
================================================================================

ABOUT SPASHTA-CKG
-----------------
Spashta-CKG is a Code Knowledge Graph designed for AI Agents.
It provides structured, queryable information about a codebase without
requiring the agent to read every file.

RUNTIME ARTIFACTS
-----------------
1. `runtime/code_knowledge_graph_ast.json`     - Structural Skeleton (Raw AST)
2. `runtime/code_knowledge_graph_enriched.json` - Semantic Intelligence (Preferred)

This tool queries the ENRICHED graph by default.

AVAILABLE COMMANDS
------------------
| Command       | Purpose                                        |
|---------------|------------------------------------------------|
| search        | Find nodes by name, ID, or attributes          |
| locate        | Get file path and line numbers for a node      |
| read          | Read actual source code of a node              |
| details       | Get full JSON object of a node                 |
| impact        | Who depends on this? (with layer labels)       |
| dependencies  | What does this use? (Outgoing edges)           |
| call-graph    | Function call relationships (caller/callee)    |
| consumers     | ALL ORM usage sites for a model (graph+grep)   |
| stats         | Graph statistics (node/edge/type counts)       |
| list-files    | List all indexed source files (--app filter)   |
| scope-check   | Verify analysis coverage before implementing   |

USAGE EXAMPLES
--------------
# Find all functions named "auth"
python query_spashta.py search "auth" --type Function --json

# Get exact location of a function
python query_spashta.py locate "app/views.py::login" --json

# Read the source code of a function
python query_spashta.py read "app/views.py::login" --json

# See what a function calls and who calls it
python query_spashta.py call-graph "app/views.py::search_page" --json

# Find all functions with @login_required decorator
python query_spashta.py search "decorator:login_required" --json

# Impact analysis: what breaks if I change User model?
python query_spashta.py impact "app/models.py::User" --depth 3 --json

OUTPUT FORMAT
-------------
Use --json flag for machine-readable JSON output (recommended for agents).
Without --json, output is human-readable text.

LANGUAGE-SPECIFIC NOTES
-----------------------
| Command       | Python | HTML/CSS | Notes                                    |
|---------------|--------|----------|------------------------------------------|
| search        | ✓      | ✓        | Works for all node types                 |
| locate        | ✓      | ✓        | Works for all nodes with line_start      |
| read          | ✓      | ✓        | Works for all nodes with file_path       |
| details       | ✓      | ✓        | Works for all nodes                      |
| impact        | ✓      | ✓        | ALL relationships (imports, defines...)  |
| dependencies  | ✓      | ✓        | ALL relationships (imports, calls_api...)| 
| call-graph    | ✓      | ✗        | PYTHON ONLY - function/method calls      |
| stats         | ✓      | ✓        | Global statistics                        |
| list-files    | ✓      | ✓        | All indexed files                        |

FOR HTML/CSS RELATIONSHIPS:
  - Use `dependencies` to see what a Template uses (API calls, styles)
  - Use `impact` to see what uses a StyleClass

EXAMPLES:
  # Python: See what function login() calls
  query_spashta.py call-graph "app/views.py::login" --json
  
  # HTML: See what home.html depends on (API calls, CSS)
  query_spashta.py dependencies "Template:sample_project/app/templates/home.html" --json
  
  # CSS: See what uses .button class
  query_spashta.py impact "StyleClass:.button" --json

================================================================================
"""

import json
import argparse
import sys
import io
from pathlib import Path

# Windows encoding safety: force UTF-8 stdout to prevent cp1252 crashes
# on Unicode characters in node names, docstrings, and status symbols.
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# =============================================================================
# CONFIGURATION & CONSTANTS
# =============================================================================

# Path Setup - REPO_ROOT is the Spashta-CKG folder
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SPASHTA_DIR = REPO_ROOT / "Spashta_2.1"
CKG_PATH = SPASHTA_DIR / "runtime" / "code_knowledge_graph_enriched.json"
PROFILE_PATH = SPASHTA_DIR / "project" / "profile.json"


def get_real_project_root():
    """
    Resolves the actual source code root directory.
    
    Reads profile.json to determine where the user's source code lives.
    This is important for the 'read' command to find actual files on disk.
    
    Returns:
        Path: Absolute path to the project's source code root.
    """
    default_root = REPO_ROOT
    
    if PROFILE_PATH.exists():
        try:
            with open(PROFILE_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                raw_root = data.get("project_root")
                if raw_root:
                    path = Path(raw_root)
                    if path.is_absolute():
                        return path
                    else:
                        return (REPO_ROOT / path).resolve()
        except Exception:
            pass
            
    return default_root


PROJECT_ROOT = get_real_project_root()


# =============================================================================
# CONSUMERS (grep+graph hybrid)
# =============================================================================

# ORM patterns that indicate model usage (universal across Django, SQLAlchemy, etc.)
ORM_PATTERNS = [
    ".objects.create(",
    ".objects.get_or_create(",
    ".objects.update_or_create(",
    ".objects.filter(",
    ".objects.get(",
    ".objects.all(",
    ".objects.exclude(",
    ".objects.bulk_create(",
    ".objects.update(",
    ".objects.delete(",
    ".objects.values(",
    ".objects.count(",
    ".objects.exists(",
    ".objects.first(",
    ".objects.last(",
    ".objects.aggregate(",
    ".objects.annotate(",
    ".objects.select_related(",
    ".objects.prefetch_related(",
    # SQLAlchemy patterns
    ".query(",
    "session.add(",
    "session.query(",
]


def find_consumers(model_name, graph):
    """
    Find all files that use a model via ORM patterns (grep) + graph impact.

    Hybrid approach:
    - Graph step: run impact to find files connected by edges
    - Grep step: scan project .py files for ORM method calls on the model name
    - Merge: union of both, classified by architectural layer

    Args:
        model_name: Simple model class name (e.g., "TabularFile", "User")
        graph: Loaded CKG

    Returns:
        dict with graph_results, grep_results, merged consumers by layer
    """
    import re

    # --- Graph step: find node and run impact ---
    graph_files = {}
    model_node_id = None
    for node in graph.get("nodes", []):
        if node.get("name") == model_name and node.get("node_type") in ("Class", "DataModel"):
            model_node_id = node["id"]
            break

    if model_node_id:
        impact_results = trace_deps(graph, model_node_id, "incoming", depth=2)
        for node_id, info in impact_results.items():
            # Extract file path
            fpath = node_id.split("::")[0] if "::" in node_id else node_id
            fpath = fpath.replace("File:", "")
            if fpath.endswith(".py"):
                graph_files[fpath] = {
                    "relation": info.get("relation"),
                    "depth": info.get("depth"),
                    "layer": info.get("layer", classify_layer(fpath)),
                    "source": "graph"
                }

    # --- Grep step: scan .py files for ORM patterns ---
    grep_files = {}
    if PROJECT_ROOT.exists():
        exclude_dirs = {".venv", "__pycache__", "venv", ".git", "node_modules",
                        "Spashta-CKG", ".agent", "testing", "migrations"}

        for py_file in PROJECT_ROOT.rglob("*.py"):
            # Skip excluded dirs
            if any(ex in py_file.parts for ex in exclude_dirs):
                continue
            try:
                content = py_file.read_text("utf-8", errors="replace")
            except Exception:
                continue

            # Search for model name + ORM patterns
            matches = []
            for i, line in enumerate(content.split("\n"), 1):
                for pattern in ORM_PATTERNS:
                    full_pattern = model_name + pattern
                    if full_pattern in line:
                        matches.append({
                            "line": i,
                            "pattern": pattern.strip("("),
                            "code": line.strip()[:100]
                        })

            if matches:
                rel_path = str(py_file.relative_to(PROJECT_ROOT)).replace("\\", "/")
                grep_files[rel_path] = {
                    "matches": matches,
                    "match_count": len(matches),
                    "layer": classify_layer(rel_path),
                    "source": "grep"
                }

    # --- Merge: union of both ---
    all_files = set(graph_files.keys()) | set(grep_files.keys())
    consumers_by_layer = {}

    for fpath in sorted(all_files):
        layer = classify_layer(fpath)
        in_graph = fpath in graph_files
        in_grep = fpath in grep_files

        entry = {
            "file": fpath,
            "layer": layer,
            "found_by": "both" if (in_graph and in_grep) else ("graph" if in_graph else "grep"),
        }
        if in_grep:
            entry["orm_calls"] = grep_files[fpath]["matches"]
        if in_graph:
            entry["relation"] = graph_files[fpath].get("relation")

        consumers_by_layer.setdefault(layer, []).append(entry)

    # Summary
    graph_only = [f for f in all_files if f in graph_files and f not in grep_files]
    grep_only = [f for f in all_files if f in grep_files and f not in graph_files]
    both = [f for f in all_files if f in graph_files and f in grep_files]

    return {
        "model": model_name,
        "model_node_id": model_node_id,
        "consumers": consumers_by_layer,
        "summary": {
            "total_files": len(all_files),
            "graph_only": len(graph_only),
            "grep_only": len(grep_only),
            "both": len(both),
        },
        "grep_only_files": sorted(grep_only),
        "graph_only_files": sorted(graph_only),
    }


# =============================================================================
# GRAPH LOADING
# =============================================================================

def load_graph():
    """
    Loads the Code Knowledge Graph from disk.
    
    Prefers the enriched graph (with semantic roles).
    Falls back to raw AST graph if enriched not found.
    
    Returns:
        dict: The loaded CKG with nodes, edges, and metadata.
    """
    if not CKG_PATH.exists():
        fallback = SPASHTA_DIR / "runtime" / "code_knowledge_graph_ast.json"
        if fallback.exists():
            with open(fallback, 'r', encoding='utf-8') as f:
                return json.load(f)
        print(f"Error: CKG not found at {CKG_PATH}", file=sys.stderr)
        sys.exit(1)
    with open(CKG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


# =============================================================================
# SEARCH FUNCTIONALITY
# =============================================================================

def smart_search(graph, query, type_filter=None, app_filter=None):
    """
    Performs intelligent search across CKG nodes.

    Supports:
    - Simple text search: Matches against node name and ID
    - Attribute search:   Use "key:value" syntax (e.g., "decorator:login")
    - Type filtering:     Use --type to filter by node type
    - App filtering:      Use --app to filter by app/directory

    Args:
        graph: The loaded CKG
        query: Search query string
        type_filter: Optional node type filter (e.g., "Function", "Class")
        app_filter: Optional app/directory prefix filter (e.g., "core_utils")

    Returns:
        list: Matching nodes (max 50 results)
    """
    results = []

    # Check for attribute search syntax "key:value"
    attr_filter = None
    if ":" in query and "::" not in query:
        parts = query.split(":", 1)
        attr_filter = (parts[0].lower(), parts[1].lower())

    query_lower = query.lower()

    for node in graph.get("nodes", []):
        # 1. Type Filter
        if type_filter and node.get("node_type", "").lower() != type_filter.lower():
            continue

        # 1b. App Filter
        if app_filter:
            node_path = node.get("file_path") or node.get("id", "")
            if not node_path.startswith(app_filter + "/") and not node_path.startswith(app_filter + "\\"):
                # Also check if id contains the app prefix (for scoped IDs)
                node_id = node.get("id", "")
                if not node_id.startswith(app_filter + "/") and not node_id.startswith(app_filter + "\\"):
                    continue
            
        # 2. Attribute Filter (Advanced)
        if attr_filter:
            k, v = attr_filter
            match = False
            
            # Check 'attributes' dict (HTML/CSS context)
            if "attributes" in node and node["attributes"]:
                if str(node["attributes"].get(k, "")).lower() == v:
                    match = True
            
            # Check 'signature' decorators (Python)
            if k in ("decorator", "@"):
                sig = node.get("signature", {})
                if sig:
                    for dec in sig.get("decorators", []):
                        if v in dec.lower():
                            match = True
                            break

            # Check direct properties
            if str(node.get(k, "")).lower() == v:
                match = True
                
            if not match:
                continue

        # 3. Name/ID Match (if not purely attribute search)
        else:
            name = node.get("name", "").lower()
            nid = node.get("id", "").lower()
            if query_lower not in name and query_lower not in nid:
                continue
            
        results.append(node)

    # Sort results by exact match relevance
    def match_rank(n):
        nid = n.get("id", "")
        nname = n.get("name", "")
        ntype = n.get("node_type", "")
        # Primary rank
        if nid == query: base = 0
        elif nname == query: base = 1
        elif nid.endswith(f"::{query}"): base = 2
        elif nid.lower() == query_lower: base = 3
        elif nname.lower() == query_lower: base = 4
        elif nid.lower().endswith(f"::{query_lower}"): base = 5
        else: base = 6
        # Secondary tiering (higher weight -> lower sorting index)
        type_w = TYPE_WEIGHTS.get(ntype, 10)
        return (base, -type_w)

    results.sort(key=match_rank)
    return results[:50]


def make_compact_node(n, include_full=False):
    """Formats a node for agent consumption. Omit heavy docstrings by default (never truncate)."""
    if include_full:
        return n
    fpath = n.get("file_path") or (n.get("id", "").split("::")[0] if "::" in n.get("id", "") else None)
    if fpath and fpath.startswith("File:"):
        fpath = fpath[5:]
    return {
        "id": n.get("id"),
        "name": n.get("name"),
        "node_type": n.get("node_type"),
        "file_path": fpath,
        "line_start": n.get("line_start"),
        "line_end": n.get("line_end"),
        "semantic_roles": n.get("semantic_roles", [])
    }


# =============================================================================
# SYMBOL TYPE PRECEDENCE & AMBIGUITY HIERARCHY
# =============================================================================

TYPE_WEIGHTS = {
    # Tier 1: Executable Core Constructs & Callables (Highest precedence)
    "Function": 100,
    "Method": 100,
    "AsyncFunction": 100,
    "Class": 95,
    "View": 95,
    "Route": 90,
    # Tier 2: Structural File-Level Containers
    "Module": 80,
    "File": 80,
    "Package": 80,
    "Template": 75,
    "Stylesheet": 75,
    # Tier 3: Domain Models & Adapter Abstractions
    "DataModel": 65,
    "Form": 60,
    "Signal": 60,
    "Component": 60,
    # Tier 4: Leaf-Level Properties & Variables
    "Field": 40,
    "Property": 40,
    "Variable": 35,
    "Parameter": 30,
    # Tier 5: Styling Selectors
    "StyleClass": 20,
    "StyleID": 20,
    "Keyframes": 20
}


def resolve_symbol_node(graph, node_id, node_type_filter=None):
    """
    Finds matching nodes for query with type weighting and ambiguity detection.
    
    Returns:
        tuple: (primary_node, is_ambiguous, alternatives_list)
    """
    nodes = graph.get("nodes", [])
    if not node_id:
        return None, False, []

    # 1. Exact ID match (unambiguous)
    for n in nodes:
        if n.get("id") == node_id:
            return n, False, []

    # 2. Auto-detect: if node_id looks like a file path, try with File: prefix
    if "::" not in node_id and not node_id.startswith("File:"):
        file_extensions = (".py", ".html", ".css", ".js", ".json", ".yaml", ".yml", ".txt", ".md")
        if any(node_id.endswith(ext) for ext in file_extensions):
            prefixed = f"File:{node_id}"
            for n in nodes:
                if n.get("id") == prefixed:
                    return n, False, []

    # 3. Exact match by symbol name
    exact_matches = [n for n in nodes if n.get("name") == node_id]
    if node_type_filter:
        exact_matches = [n for n in exact_matches if n.get("node_type") == node_type_filter]

    if exact_matches:
        exact_matches.sort(key=lambda n: TYPE_WEIGHTS.get(n.get("node_type"), 10), reverse=True)
        winner = exact_matches[0]
        alts = [
            {
                "id": n.get("id"),
                "name": n.get("name"),
                "node_type": n.get("node_type"),
                "file_path": n.get("file_path") or (n.get("id", "").split("::")[0] if "::" in n.get("id", "") else None),
                "line_start": n.get("line_start")
            }
            for n in exact_matches[1:]
        ]
        return winner, len(exact_matches) > 1, alts

    # 4. Suffix match by ::symbol
    suffix_matches = [n for n in nodes if n.get("id", "").endswith(f"::{node_id}")]
    if suffix_matches:
        suffix_matches.sort(key=lambda n: TYPE_WEIGHTS.get(n.get("node_type"), 10), reverse=True)
        winner = suffix_matches[0]
        alts = [
            {
                "id": n.get("id"),
                "name": n.get("name"),
                "node_type": n.get("node_type"),
                "file_path": n.get("file_path") or (n.get("id", "").split("::")[0] if "::" in n.get("id", "") else None),
                "line_start": n.get("line_start")
            }
            for n in suffix_matches[1:]
        ]
        return winner, len(suffix_matches) > 1, alts

    # 5. Case-insensitive symbol name
    node_id_lower = node_id.lower()
    case_name_matches = [n for n in nodes if (n.get("name") or "").lower() == node_id_lower]
    if case_name_matches:
        case_name_matches.sort(key=lambda n: TYPE_WEIGHTS.get(n.get("node_type"), 10), reverse=True)
        winner = case_name_matches[0]
        alts = [
            {
                "id": n.get("id"),
                "name": n.get("name"),
                "node_type": n.get("node_type"),
                "file_path": n.get("file_path") or (n.get("id", "").split("::")[0] if "::" in n.get("id", "") else None),
                "line_start": n.get("line_start")
            }
            for n in case_name_matches[1:]
        ]
        return winner, len(case_name_matches) > 1, alts

    # 6. Case-insensitive suffix match
    case_suffix_matches = [n for n in nodes if (n.get("id") or "").lower().endswith(f"::{node_id_lower}")]
    if case_suffix_matches:
        case_suffix_matches.sort(key=lambda n: TYPE_WEIGHTS.get(n.get("node_type"), 10), reverse=True)
        winner = case_suffix_matches[0]
        alts = [
            {
                "id": n.get("id"),
                "name": n.get("name"),
                "node_type": n.get("node_type"),
                "file_path": n.get("file_path") or (n.get("id", "").split("::")[0] if "::" in n.get("id", "") else None),
                "line_start": n.get("line_start")
            }
            for n in case_suffix_matches[1:]
        ]
        return winner, len(case_suffix_matches) > 1, alts

    return None, False, []


def check_freshness(project_root=None):
    """
    Inspects scan_meta.json to determine if any tracked source files have been modified or deleted.
    Executes in ~1-2ms without loading ASTs.
    """
    root = Path(project_root).resolve() if project_root else PROJECT_ROOT
    meta_candidates = [
        root / ".spashta" / "scan_meta.json",
        root / "runtime" / "scan_meta.json"
    ]
    meta_path = next((p for p in meta_candidates if p.exists()), None)
    
    stale_files = []
    graph_built_at = None
    
    if meta_path:
        try:
            from datetime import datetime, timezone
            st_mtime = meta_path.stat().st_mtime
            graph_built_at = datetime.fromtimestamp(st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                scan_meta = json.load(f)
            for rel_path, entry in scan_meta.items():
                if isinstance(entry, dict) and "mtime" in entry:
                    fpath = root / rel_path
                    if fpath.exists():
                        cur_mtime = fpath.stat().st_mtime
                        if cur_mtime > entry["mtime"] + 0.001:
                            stale_files.append(rel_path)
                    else:
                        stale_files.append(rel_path)
        except Exception:
            pass
    elif (root / ".spashta" / "code_knowledge_graph_enriched.json").exists():
        try:
            from datetime import datetime, timezone
            st_mtime = (root / ".spashta" / "code_knowledge_graph_enriched.json").stat().st_mtime
            graph_built_at = datetime.fromtimestamp(st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass

    return {
        "version": "3.2.8",
        "graph_built_at": graph_built_at,
        "is_stale": len(stale_files) > 0,
        "staleness_check": "mtime-manifest",
        "stale_files_count": len(stale_files),
        "stale_files": sorted(stale_files)
    }


def make_envelope(
    command,
    status="ok",
    target=None,
    items=None,
    summary=None,
    ambiguous=False,
    alternatives=None,
    provenance=None,
    error=None,
    suggestions=None,
    project_root=None,
    extra=None
):
    """
    Builds the standardized universal response envelope for all Spashta queries.
    Status is strictly one of: 'ok', 'not_found', 'error'.
    """
    if items is None:
        items = []
    if alternatives is None:
        alternatives = []
    if summary is None:
        summary = {}

    if "total_items" not in summary:
        summary["total_items"] = len(items)
    if "returned_items" not in summary:
        summary["returned_items"] = len(items)
    if "truncated" not in summary:
        summary["truncated"] = summary["returned_items"] < summary["total_items"]

    freshness = check_freshness(project_root)

    env = {
        "status": status,
        "command": command,
        "target": target or {},
        "ambiguous": ambiguous,
        "alternatives": alternatives,
        "summary": summary,
        "items": items,
        "_meta": freshness
    }

    if provenance:
        env["provenance"] = provenance
    elif provenance is None and extra and "provenance" in extra:
        env["provenance"] = extra["provenance"]

    if error:
        env["error"] = error
    if suggestions:
        env["suggestions"] = suggestions
    if extra:
        for k, v in extra.items():
            if k != "provenance":
                env[k] = v

    return env


# =============================================================================
# NODE/EDGE UTILITIES
# =============================================================================

def get_node(graph, node_id):
    """
    Retrieves a specific node by its ID, symbol name, or file path.
    Supports exact ID match, file paths, bare symbol names, and scoped identifiers.

    Args:
        graph: The loaded CKG
        node_id: Exact node ID, symbol name, or file path

    Returns:
        dict or None: The node object, or None if not found.
    """
    winner, _, _ = resolve_symbol_node(graph, node_id)
    return winner


# Cross-emitter placeholder node types: Spashta emits ONE placeholder per emitter, joined BY NAME
# (js-support §0d) — e.g. a url-name 'app:x' is a Route in urls.py (resolves_to the view) AND a Route
# in each template that hx-get's it (calls_api); a custom event is a JS Event AND an HTMX-listener
# Event. So impact/dependencies on such a node must UNION all same-(type,name) siblings.
_PLACEHOLDER_TYPES = {"Route", "Event", "StyleClass", "StyleID"}


def _template_logical(node):
    """A Template's logical name (Django-search-path relative), so a physical Template
    (`Template:app/templates/app/x.html`) and a render() placeholder (`…::Template::app/x.html`)
    map to the SAME key `app/x.html`."""
    import re as _re
    s = (node.get("name") or node.get("id") or "").replace("Template:", "")
    return _re.split(r"(?:^|/)templates/", s)[-1].lstrip("/")


def resolve_impact_start_ids(graph, node_id):
    """Return the node id(s) impact/dependencies should walk. For a placeholder type (Route/Event/
    StyleClass) — or a bare name that matches one — return EVERY same-(type,name) sibling so the
    cross-emitter coupling (e.g. a route's view + the templates that call it) resolves from one query.
    A **Template** joins by its logical (search-path-relative) name, so the render() placeholder and the
    physical HTML Template unite (view→template ↔ template→view). A normal node resolves to its exact id."""
    nodes = graph.get("nodes", [])
    exact = get_node(graph, node_id)
    if exact and exact.get("node_type") == "Template":
        key = _template_logical(exact)
        return [n["id"] for n in nodes
                if n.get("node_type") == "Template" and _template_logical(n) == key] or [exact["id"]]
    if exact and exact.get("node_type") in _PLACEHOLDER_TYPES:
        t, nm = exact["node_type"], exact.get("name")
        return [n["id"] for n in nodes if n.get("node_type") == t and n.get("name") == nm]
    if exact:
        return [exact["id"]]
    sibs = [n["id"] for n in nodes
            if n.get("node_type") in _PLACEHOLDER_TYPES and n.get("name") == node_id]
    return sibs or [node_id]


def node_not_found_response(graph, node_id):
    """
    Returns an error response with suggestions when a node ID is not found.
    Searches for nodes whose name or ID contains the query as a substring.
    """
    query = node_id.lower()
    # Extract just the name part if scoped ID
    name_part = node_id.split("::")[-1].lower() if "::" in node_id else query

    suggestions = []
    for node in graph.get("nodes", []):
        nid = node.get("id", "").lower()
        name = node.get("name", "").lower()
        if name_part in name or name_part in nid:
            suggestions.append({"id": node["id"], "node_type": node.get("node_type", "")})
            if len(suggestions) >= 5:
                break

    result = {"error": f"Node not found: {node_id}"}
    if suggestions:
        result["suggestions"] = suggestions
        result["hint"] = "Try one of the suggested IDs above."
    else:
        result["hint"] = f"No similar nodes found. Use: search \"{name_part}\" --json"
    return result


def get_edges_list(graph):
    """Returns the edges array from the graph."""
    return graph.get("edges", [])


# Framework/runtime-injected class prefixes (dead-code-accuracy P2): classes a framework ADDS at runtime,
# never present in source, so they always look "dead". Extensible — add your stack's runtime classes here.
_FRAMEWORK_CLASS_PREFIXES = ("htmx-",)  # htmx-request / htmx-added / htmx-settling / htmx-swapping / htmx-indicator


def _dynamic_class_text(graph):
    """All `dynamic_class_unresolved` ambiguity text joined — a dead class whose name appears here is applied
    via a computed/templated attribute (`class="x-{{ v }}"` / a `{% if %}` the tokenizer couldn't split), so
    it is NOT dead. dead-code-accuracy P2."""
    return " ".join(a.get("expression", "") for a in graph.get("ambiguities", [])
                    if a.get("kind") == "dynamic_class_unresolved")


def _node_type(node):
    """Node type, tolerant of the `node_type`/`type` key variation across graph versions."""
    return node.get("node_type") or node.get("type")


def _css_index(graph):
    """Build the CSS lookup once: defines / uses_style / queries_dom / uses_animation grouped by the
    STYLE NODE NAME (the placeholder-per-emitter model unifies by name). Returns dicts keyed by name."""
    nodes = graph.get("nodes", [])
    id2 = {n["id"]: n for n in nodes}
    from collections import defaultdict
    defines = defaultdict(set)      # class/keyframes name -> set(defining stylesheet ids)
    style_users = defaultdict(set)  # class name -> set(user file ids)  [uses_style + queries_dom]
    anim_users = defaultdict(set)   # keyframes name -> set(user stylesheet ids)  [uses_animation]
    kf_hashes = defaultdict(set)    # body_hash -> set(keyframes names)
    for n in nodes:
        if _node_type(n) == "Keyframes" and n.get("body_hash"):
            kf_hashes[n["body_hash"]].add(n.get("name"))
    for e in graph.get("edges", []):
        src, dst, kind = get_edge_endpoints(e)
        tgt = id2.get(dst)
        if not tgt:
            continue
        tt, name = _node_type(tgt), tgt.get("name")
        if kind == "defines" and tt in ("StyleClass", "Keyframes"):
            defines[(tt, name)].add(src)
        elif kind in ("uses_style", "queries_dom") and tt == "StyleClass":
            style_users[name].add(src.split("::")[0])
        elif kind == "uses_animation" and tt == "Keyframes":
            anim_users[name].add(src.split("::")[0])
    return defines, style_users, anim_users, kf_hashes


def get_edge_endpoints(edge):
    """
    Extracts source, target, and type from an edge.
    
    Handles key variations in edge schema:
    - source/target vs from/to
    - type vs relation_type vs edge
    
    Returns:
        tuple: (source_id, target_id, edge_type)
    """
    src = edge.get("source") or edge.get("from")
    dst = edge.get("target") or edge.get("to")
    kind = edge.get("type") or edge.get("relation_type") or edge.get("edge")
    return src, dst, kind


# =============================================================================
# LAYER CLASSIFICATION
# =============================================================================

# Standard architectural layers — file path patterns (universal for Django/FastAPI/Rails)
LAYER_PATTERNS = [
    ("test",               lambda p: "test_" in p or "/tests/" in p or "/tests." in p),
    ("migration",          lambda p: "migrations/" in p),
    ("admin",              lambda p: "admin.py" in p),
    ("serializer",         lambda p: "serializer" in p),
    ("view",               lambda p: "views.py" in p or "_views" in p or "views/" in p),
    ("service",            lambda p: "services/" in p or "service.py" in p),
    ("management_command", lambda p: "management/commands" in p),
    ("model",              lambda p: "models.py" in p or "models/" in p),
    ("adapter",            lambda p: "adapters/" in p or "adapter.py" in p),
    ("url_config",         lambda p: "urls.py" in p),
    ("template",           lambda p: "templates/" in p),
]


def classify_layer(file_path: str) -> str:
    """Classify a file into an architectural layer by path pattern."""
    p = file_path.lower()
    for layer_name, matcher in LAYER_PATTERNS:
        if matcher(p):
            return layer_name
    return "other"


def build_layer_coverage(impact_results: dict) -> dict:
    """
    Build layer coverage summary from impact results.

    Returns:
        {
            "layer_coverage": {"model": true, "view": false, ...},
            "missing_layers": ["view", "admin"],
            "warning": "..." (if view or service layer missing)
        }
    """
    expected_layers = {"model", "service", "view", "admin", "serializer", "test"}
    found_layers = set()

    for node_id, info in impact_results.items():
        path = node_id.lower()
        layer = classify_layer(path)
        if layer != "other":
            found_layers.add(layer)

    coverage = {layer: (layer in found_layers) for layer in sorted(expected_layers)}
    missing = sorted(expected_layers - found_layers)

    result = {
        "layer_coverage": coverage,
        "missing_layers": missing,
    }

    # Add warning if critical layers are missing
    if "view" in missing:
        result["warning"] = ("No VIEW files in impact results. "
                             "If this model uses lazy imports in views, they will not appear. "
                             "Consider running a grep-based search for ORM patterns.")
    elif "service" in missing:
        result["warning"] = ("No SERVICE files in impact results. "
                             "Check if services use lazy imports or indirect access.")

    return result


# =============================================================================
# DEPENDENCY TRACING
# =============================================================================

def trace_deps(graph, start_id, direction, depth, current_depth=0, visited=None):
    """
    Recursively traces dependencies in the graph.
    
    Args:
        graph: The loaded CKG
        start_id: Starting node ID
        direction: "outgoing" (what does this use?) or "incoming" (who uses this?)
        depth: Maximum recursion depth
        current_depth: Current recursion level (internal)
        visited: Set of visited nodes (internal, prevents cycles)
    
    Returns:
        dict: Map of related node IDs to their relationship info
    
    Example Output:
        {
            "app/models.py::User": {
                "relation": "imports",
                "depth": 1,
                "node_type": "Class"
            }
        }
    """
    if visited is None:
        visited = set()
    if current_depth >= depth:
        return {}

    results = {}
    edges = get_edges_list(graph)

    # Expand a PLACEHOLDER start (Route/Event/StyleClass) to its by-name siblings and follow ALL their
    # edges as ONE logical node — the cross-emitter join (js-support §0d). Applied at EVERY hop (via the
    # recursion below), so a multi-hop traversal crosses the placeholder boundary: e.g. a view -> its
    # urls.py Route -> (the template-side Route siblings of the same url-name) -> the templates that
    # hx-get it. A non-placeholder node expands to just itself (unchanged behaviour).
    for sid in resolve_impact_start_ids(graph, start_id):
        if sid in visited:
            continue
        visited.add(sid)
        for edge in edges:
            src, dst, kind = get_edge_endpoints(edge)

            neighbor = None
            if direction == "outgoing" and src == sid:
                neighbor = dst
            elif direction == "incoming" and dst == sid:
                neighbor = src

            if neighbor and neighbor not in results:
                node_obj = get_node(graph, neighbor)
                results[neighbor] = {
                    "relation": kind,
                    "depth": current_depth + 1,
                    "node_type": node_obj.get("node_type") if node_obj else "Unknown",
                    "layer": classify_layer(neighbor)
                }
                # Recurse (the neighbor is placeholder-expanded inside its own trace_deps call).
                results.update(trace_deps(graph, neighbor, direction, depth, current_depth + 1, visited))

    return results


# =============================================================================
# CALL GRAPH ANALYSIS
# =============================================================================

def get_call_graph(graph, node_id):
    """
    Analyzes function call relationships for a given node.
    
    This is a KEY FEATURE for impact analysis. Shows:
    - OUTGOING: What functions does this function call?
    - INCOMING: What functions call this function?
    
    Each call includes the line number where the call occurs.
    
    Args:
        graph: The loaded CKG
        node_id: Function or Method node ID
    
    Returns:
        dict: {
            "node_id": "...",
            "calls": [...],      # What this function calls
            "called_by": [...],  # What calls this function
            "summary": {...}     # Counts
        }
    
    Example:
        get_call_graph(graph, "app/views.py::search_page")
        
        Returns:
        {
            "node_id": "app/views.py::search_page",
            "calls": [
                {
                    "target": "app/services.py::SearchService",
                    "target_name": "SearchService",
                    "target_type": "Class",
                    "call_line": 45
                }
            ],
            "called_by": [
                {
                    "caller": "app/urls.py",
                    "caller_name": "urls.py",
                    "caller_type": "File",
                    "call_line": 12
                }
            ],
            "summary": {"outgoing_count": 1, "incoming_count": 1}
        }
    """
    # Resolve bare symbol or prefix to canonical node ID
    target_node = get_node(graph, node_id)
    if target_node:
        node_id = target_node.get("id", node_id)

    edges = get_edges_list(graph)
    
    # Outgoing: What does this function call?
    outgoing_calls = []
    for edge in edges:
        src, dst, kind = get_edge_endpoints(edge)
        if src == node_id and kind == "calls":
            target_node = get_node(graph, dst)
            outgoing_calls.append({
                "target": dst,
                "target_name": target_node.get("name") if target_node else dst.split("::")[-1],
                "target_type": target_node.get("node_type") if target_node else "Unknown",
                "call_line": edge.get("call_line")
            })
    
    # Incoming: What calls this function?
    incoming_calls = []
    for edge in edges:
        src, dst, kind = get_edge_endpoints(edge)
        if dst == node_id and kind == "calls":
            caller_node = get_node(graph, src)
            incoming_calls.append({
                "caller": src,
                "caller_name": caller_node.get("name") if caller_node else src.split("::")[-1],
                "caller_type": caller_node.get("node_type") if caller_node else "Unknown",
                "call_line": edge.get("call_line")
            })
    
    return {
        "node_id": node_id,
        "calls": outgoing_calls,
        "called_by": incoming_calls,
        "summary": {
            "outgoing_count": len(outgoing_calls),
            "incoming_count": len(incoming_calls)
        }
    }


# =============================================================================
# CODE READING
# =============================================================================

def read_content(graph, node_id):
    """
    Reads the actual source code for a node from disk.
    
    Uses line_start and line_end metadata to extract just the relevant
    code snippet, not the entire file.
    
    Args:
        graph: The loaded CKG
        node_id: Node ID (e.g., "app/views.py::login")
    
    Returns:
        dict: {
            "content": "def login(request): ...",
            "mode": "snippet" or "full_file",
            "lines": "45-67"
        }
        OR
        {"error": "..."}
    """
    node = get_node(graph, node_id)
    if not node:
        return {"error": "Node not found"}
    
    file_path = node.get("file_path")
    
    # Infer file path from ID if missing
    if not file_path and "::" in node["id"]:
        file_path = node["id"].split("::")[0]
        if file_path.startswith("File:"):
            file_path = file_path[5:]

    if not file_path:
        return {"error": "No file path for node"}
    
    # Strict path resolution from graph project root or PROJECT_ROOT
    root = Path(graph.get("_meta", {}).get("project_root", PROJECT_ROOT))
    target_path = root / file_path if not Path(file_path).is_absolute() else Path(file_path)
    if not target_path.exists() and (PROJECT_ROOT / file_path).exists():
        target_path = PROJECT_ROOT / file_path
    if not target_path.exists() and Path(file_path).exists():
        target_path = Path(file_path)
    
    if not target_path.exists():
        return {"error": f"File not found at: {target_path}"}
         
    try:
        with open(target_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        start = node.get("line_start")
        end = node.get("line_end")
        
        if start is None:
            return {"content": "".join(lines), "mode": "full_file"}
            
        start_idx = max(0, start - 1)
        if start_idx >= len(lines):
            return {"error": f"Line start {start} out of bounds ({len(lines)} lines)"}
             
        end_idx = end if end else len(lines)
        
        snippet = "".join(lines[start_idx:end_idx])
        return {"content": snippet, "mode": "snippet", "lines": f"{start}-{end}"}
        
    except Exception as e:
        return {"error": str(e)}


def _get_suggestions(graph, query, max_suggestions=5):
    """Finds near-match suggestions for a missing symbol."""
    suggestions = []
    q_lower = (query or "").lower()
    for n in graph.get("nodes", []):
        name = (n.get("name") or "").lower()
        nid = (n.get("id") or "").lower()
        if q_lower in name or q_lower in nid:
            suggestions.append(n.get("id"))
            if len(suggestions) >= max_suggestions:
                break
    return suggestions


def node_not_found_response(graph, node_id, command=None, project_root=None):
    """
    Returns standardized universal error envelope when a node is not found in the graph.
    """
    return make_envelope(
        command=command or "query",
        status="not_found",
        target={"query": node_id},
        error=f"Node not found: {node_id}",
        suggestions=_get_suggestions(graph, node_id),
        project_root=project_root
    )


# =============================================================================
# HIGH-LEVEL DECISION TOOL (can_delete)
# =============================================================================

def can_delete(graph, symbol, depth=3, project_root=None, summary_only=False):
    """
    Evaluates whether a symbol can be safely deleted without breaking working code.
    
    Separates production callers from test callers:
    - Production callers present -> can_delete: false
    - Test callers only -> can_delete: true with requires_test_updates: [tests/test_x.py]
    - Zero callers -> can_delete: true with requires_test_updates: []
    
    Args:
        graph: Loaded CKG
        symbol: Target symbol name or node ID
        depth: Traversal depth for callers
        project_root: Optional project root path
        summary_only: If True, omits verbose items list and returns concise blocker files
        
    Returns:
        dict: Standardized universal envelope with can_delete boolean verdict,
              blockers breakdown, and test update requirements.
    """
    target_node, is_ambiguous, alts = resolve_symbol_node(graph, symbol)
    if not target_node:
        return make_envelope(
            command="can_delete",
            status="not_found",
            target={"query": symbol},
            error=f"Node not found: {symbol}",
            suggestions=_get_suggestions(graph, symbol),
            project_root=project_root,
            extra={
                "can_delete": False,
                "blockers": {"production": [], "tests": []},
                "requires_test_updates": []
            }
        )

    target_id = target_node.get("id")
    impact_results = trace_deps(graph, target_id, "incoming", depth)

    prod_blockers = []
    test_blockers = []
    test_files = set()

    for nid, info in impact_results.items():
        node_obj = get_node(graph, nid)
        fpath = info.get("file_path") or (node_obj.get("file_path") if node_obj else None) or (nid.split("::")[0] if "::" in nid else "")
        if fpath.startswith("File:"):
            fpath = fpath[5:]
        
        caller_name = info.get("name") or (node_obj.get("name") if node_obj else nid.split("::")[-1])
        ntype = info.get("node_type") or (node_obj.get("node_type") if node_obj else "Unknown")
        line_start = info.get("line_start") or (node_obj.get("line_start") if node_obj else None)

        blocker_entry = {
            "id": nid,
            "name": caller_name,
            "node_type": ntype,
            "file_path": fpath,
            "line_start": line_start,
            "relation": info.get("edge_type", "calls")
        }

        # Classify test caller vs production caller
        norm_fpath = fpath.replace("\\", "/").lower()
        is_test = (
            "/tests/" in norm_fpath or
            norm_fpath.startswith("tests/") or
            "test_" in norm_fpath or
            "_test.py" in norm_fpath or
            "_tests.py" in norm_fpath or
            norm_fpath.endswith("tests.py") or
            ntype == "TestCase" or
            "test_case" in (node_obj.get("semantic_roles", []) if node_obj else [])
        )

        if is_test:
            test_blockers.append(blocker_entry)
            if fpath:
                test_files.add(fpath)
        else:
            prod_blockers.append(blocker_entry)

    can_del = len(prod_blockers) == 0
    req_tests = sorted(list(test_files)) if can_del and len(test_blockers) > 0 else []

    target_info = {
        "query": symbol,
        "resolved_id": target_id,
        "name": target_node.get("name"),
        "node_type": target_node.get("node_type"),
        "file_path": target_node.get("file_path") or (target_id.split("::")[0] if "::" in target_id else None),
        "line_start": target_node.get("line_start")
    }

    if summary_only:
        items_payload = []
        summary = {
            "total_blockers": len(prod_blockers) + len(test_blockers),
            "production_blockers": len(prod_blockers),
            "test_blockers": len(test_blockers),
            "returned_items": 0,
            "truncated": False,
            "summary_only": True
        }
        blockers_payload = {
            "production": sorted(list({b["file_path"] for b in prod_blockers if b.get("file_path")})),
            "tests": sorted(list({b["file_path"] for b in test_blockers if b.get("file_path")}))
        }
    else:
        items_payload = prod_blockers + test_blockers
        summary = {
            "total_blockers": len(prod_blockers) + len(test_blockers),
            "production_blockers": len(prod_blockers),
            "test_blockers": len(test_blockers),
            "returned_items": len(prod_blockers) + len(test_blockers),
            "truncated": False,
            "summary_only": False
        }
        blockers_payload = {
            "production": prod_blockers,
            "tests": test_blockers
        }

    return make_envelope(
        command="can_delete",
        status="ok",
        target=target_info,
        items=items_payload,
        summary=summary,
        ambiguous=is_ambiguous,
        alternatives=alts,
        project_root=project_root,
        extra={
            "can_delete": can_del,
            "blockers": blockers_payload,
            "requires_test_updates": req_tests
        }
    )


# =============================================================================
# OUTPUT FORMATTING
# =============================================================================

# Context-aware hints: shown after each command's JSON output to remind
# agents what other Spashta commands are available for the logical next step.
COMMAND_HINTS = {
    "search": "Next: use 'locate' to confirm a node, 'read' to see code, or 'impact' to check blast radius before editing.",
    "locate": "Next: use 'read' to see the actual code, or 'dependencies' to map internal structure.",
    "read": "Next: use 'impact' on this node BEFORE making changes. Run 'consumers' if modifying a model class.",
    "details": "Tip: signature.args and signature.decorators are available. Use 'impact' to see who depends on this.",
    "impact": "Tip: check 'missing_layers' — if view/service layer is absent, run 'consumers' for complete coverage.",
    "dependencies": "Next: use 'read' on specific methods (not full class). Use 'impact' before editing.",
    "call-graph": "Tip: 'impact' gives broader results than call-graph. Use 'consumers' for model usage sites.",
    "consumers": "This shows ALL ORM usage. Check 'grep_only_files' — those are blind spots not in the graph.",
    "stats": "Tip: use 'search --app <name>' to explore a specific app. Run 'impact' before any code changes.",
    "list-files": "Tip: use 'search --app <name> --type Class' to find classes in a specific app.",
    "scope-check": "If verdict is INCOMPLETE, analyze the unanalyzed files before implementing.",
}


def output(data, as_json=False):
    """
    Formats and prints output.

    Args:
        data: Data to output (dict, list, or string)
        as_json: If True, output pure JSON (for agents). If False, human-readable.
    """
    if as_json:
        print(json.dumps(data, indent=2))
    else:
        if isinstance(data, list):
            print(f"Found {len(data)} items:")
            for item in data:
                if isinstance(item, dict):
                    item_id = item.get('id') or item.get('name') or str(item)
                    item_type = f" ({item.get('node_type')})" if item.get('node_type') else ""
                    print(f"  - {item_id}{item_type}")
                else:
                    print(f"  - {item}")
        elif isinstance(data, dict):
            if "content" in data:
                print(f"--- Code ({data.get('mode')}) ---")
                print(data["content"])
                print("-----------------------------")
            else:
                print(json.dumps(data, indent=2))
        else:
            print(data)


# =============================================================================
# CLI ARGUMENT PARSING
# =============================================================================

def parse_args():
    """
    Parses command-line arguments.
    
    All commands support --json flag for machine-readable output.
    """
    # Parent parser for common args
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("--json", action="store_true", 
                               help="Output pure JSON (recommended for AI agents)")

    # Main parser with detailed description
    description = """
================================================================================
SPASHTA CKG QUERY TOOL - AI Agent's Gateway to Code Knowledge
================================================================================

Query the Code Knowledge Graph to understand codebase structure, dependencies,
and relationships without reading every file.

QUICK START:
  search     - Find code by name or attributes
  locate     - Get file path and line numbers
  read       - View actual source code
  call-graph - See function call relationships
  impact     - Who depends on this?

EXAMPLES:
  query_spashta.py search "login" --json
  query_spashta.py call-graph "app/views.py::login" --json
  query_spashta.py impact "app/models.py::User" --depth 3 --json
================================================================================
    """
    
    parser = argparse.ArgumentParser(
        description=description, 
        formatter_class=argparse.RawTextHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # -------------------------------------------------------------------------
    # SEARCH Command
    # -------------------------------------------------------------------------
    p_search = subparsers.add_parser(
        "search", 
        parents=[parent_parser], 
        help="Find nodes by name, ID, or attributes",
        description="""
Find nodes in the CKG using text search or attribute filters.

SEARCH SYNTAX:
  query_spashta.py search "login"                    # Name/ID contains "login"
  query_spashta.py search "auth" --type Function     # Only functions
  query_spashta.py search "decorator:login_required" # By decorator
  query_spashta.py search "tag:form"                 # HTML elements by tag
  query_spashta.py search "pseudo_state:hover"       # CSS pseudo-selectors
        """
    )
    p_search.add_argument("query", help="Search query (text or key:value)")
    p_search.add_argument("--type", help="Filter by node type (Function, Class, Field, Constant, TestCase, etc.)")
    p_search.add_argument("--app", help="Filter by app/directory prefix (e.g., core_utils)")
    
    # -------------------------------------------------------------------------
    # LOCATE Command
    # -------------------------------------------------------------------------
    p_locate = subparsers.add_parser(
        "locate", 
        parents=[parent_parser], 
        help="Get file path and line numbers for a node",
        description="""
Get the exact location of a code element.

Returns file path, line_start, line_end, and docstring (if available).

EXAMPLE:
  query_spashta.py locate "app/views.py::login" --json
        """
    )
    p_locate.add_argument("node_id", help="Exact node ID (e.g., app/views.py::login)")
    
    # -------------------------------------------------------------------------
    # READ Command
    # -------------------------------------------------------------------------
    p_read = subparsers.add_parser(
        "read", 
        parents=[parent_parser], 
        help="Read actual source code of a node",
        description="""
Read the source code for a specific function, class, or other node.

Uses line_start/line_end to extract just the relevant code snippet.

EXAMPLE:
  query_spashta.py read "app/views.py::login" --json
        """
    )
    p_read.add_argument("node_id", help="Exact node ID")

    # -------------------------------------------------------------------------
    # DETAILS Command
    # -------------------------------------------------------------------------
    p_details = subparsers.add_parser(
        "details", 
        parents=[parent_parser], 
        help="Get full JSON object of a node",
        description="""
Get complete node metadata including all attributes.

EXAMPLE:
  query_spashta.py details "app/views.py::login" --json
        """
    )
    p_details.add_argument("node_id", help="Exact node ID")
    
    # -------------------------------------------------------------------------
    # IMPACT Command
    # -------------------------------------------------------------------------
    p_impact = subparsers.add_parser(
        "impact", 
        parents=[parent_parser], 
        help="Who depends on this? (Incoming edges)",
        description="""
Analyze what code depends on a given node.

USE CASE: "If I change this, what might break?"

EXAMPLE:
  query_spashta.py impact "app/models.py::User" --depth 3 --json
        """
    )
    p_impact.add_argument("node_id", help="Node to analyze")
    p_impact.add_argument("--depth", type=int, default=2, 
                          help="How many levels deep to trace (default: 2)")
    
    # -------------------------------------------------------------------------
    # DEPENDENCIES Command
    # -------------------------------------------------------------------------
    p_deps = subparsers.add_parser(
        "dependencies", 
        parents=[parent_parser], 
        help="What does this use? (Outgoing edges)",
        description="""
Analyze what a node depends on (imports, calls, etc.).

USE CASE: "What do I need to understand to work on this?"

EXAMPLE:
  query_spashta.py dependencies "app/views.py::login" --json
        """
    )
    p_deps.add_argument("node_id", help="Node to analyze")
    p_deps.add_argument("--depth", type=int, default=1, 
                        help="How many levels deep to trace (default: 1)")
    
    # -------------------------------------------------------------------------
    # CALL-GRAPH Command
    # -------------------------------------------------------------------------
    p_callgraph = subparsers.add_parser(
        "call-graph", 
        parents=[parent_parser], 
        help="[PYTHON ONLY] Show function call relationships",
        description="""
[PYTHON ONLY] Analyze function call chains for a Python function or method.

NOTE: This command only works for Python code. For HTML/CSS relationships,
      use the 'dependencies' or 'impact' commands instead.

Shows:
  - CALLS: What functions does this function call?
  - CALLED_BY: What functions call this function?
  - CALL_LINE: Exact line number where each call occurs

USE CASE: "If I change LLMService.generate(), what will break?"

EXAMPLE:
  query_spashta.py call-graph "app/views.py::search_page" --json

OUTPUT:
  {
    "node_id": "app/views.py::search_page",
    "calls": [
      {"target": "...", "target_name": "...", "call_line": 45}
    ],
    "called_by": [
      {"caller": "...", "caller_name": "...", "call_line": 12}
    ]
  }

LIMITATION:
  Only tracks INTERNAL calls (your code -> your code).
  External library calls (json.load, os.path, etc.) are NOT tracked
  because they are not part of the scanned codebase.
  Unresolved calls are logged as ambiguities, not in call-graph.
        """
    )
    p_callgraph.add_argument("node_id", 
                             help="Function or Method ID (e.g., app/views.py::search)")
    
    # -------------------------------------------------------------------------
    # STATS Command
    # -------------------------------------------------------------------------
    subparsers.add_parser(
        "stats", 
        parents=[parent_parser], 
        help="Show graph statistics",
        description="Display node count, edge count, and metadata."
    )
    
    # -------------------------------------------------------------------------
    # LIST-FILES Command
    # -------------------------------------------------------------------------
    p_listfiles = subparsers.add_parser(
        "list-files",
        parents=[parent_parser],
        help="List all indexed source files",
        description="Get a list of all files that have been indexed in the CKG.\nUse --app to filter by app/directory."
    )
    p_listfiles.add_argument("--app", help="Filter files by app/directory prefix (e.g., core_utils, notebook_ai)")

    # -------------------------------------------------------------------------
    # SCOPE-CHECK Command
    # -------------------------------------------------------------------------
    p_scope = subparsers.add_parser(
        "scope-check",
        parents=[parent_parser],
        help="Verify analysis coverage — find files you missed",
        description="""
Self-audit: compare your analyzed files against full impact results.
Returns files in impact that you did NOT analyze (production files only).

USE CASE: Before implementing, confirm you haven't missed any consumer.

EXAMPLE:
  query_spashta.py scope-check "models.py::TabularFile" \\
      --analyzed "tabular_service.py,document_service.py,ui_views.py" --json
        """
    )
    p_scope.add_argument("node_id", help="Node to check impact for")
    p_scope.add_argument("--analyzed", required=True,
                         help="Comma-separated list of files you have already analyzed")
    p_scope.add_argument("--depth", type=int, default=2,
                         help="Impact depth (default: 2)")

    # -------------------------------------------------------------------------
    # CONSUMERS Command
    # -------------------------------------------------------------------------
    p_consumers = subparsers.add_parser(
        "consumers",
        parents=[parent_parser],
        help="Find ALL files that use a model (graph + grep hybrid)",
        description="""
Find every file that uses a model class via ORM patterns.

Combines two approaches:
  1. Graph: impact analysis (follows import/call edges)
  2. Grep: scans .py files for .objects.create(), .filter(), etc.

Files found by grep but NOT by graph indicate lazy imports or dynamic usage.

EXAMPLE:
  query_spashta.py consumers "User" --json
  query_spashta.py consumers "TabularFile" --json
        """
    )
    p_consumers.add_argument("model_name", help="Model class name (e.g., User, TabularFile)")

    # -------------------------------------------------------------------------
    # CSS coverage commands (css-coverage-roadmap P3)
    # -------------------------------------------------------------------------
    p_deadcss = subparsers.add_parser(
        "dead-css", parents=[parent_parser],
        help="CSS classes / @keyframes defined but never used",
        description="A StyleClass with a `defines` edge but NO `uses_style` (markup) / `queries_dom` (JS)\n"
                    "inbound, or a Keyframes with no `uses_animation` inbound. CANDIDATES — a class may be\n"
                    "applied dynamically; confirm before deleting.\n\nEXAMPLE:\n  query_spashta.py dead-css --json")
    p_deadcss.add_argument("--kind", choices=["class", "keyframes", "all"], default="all",
                           help="Which definitions to check (default: all)")

    p_clsuse = subparsers.add_parser(
        "class-usage", parents=[parent_parser],
        help="Every user of a CSS class (templates + JS) and where it's defined",
        description="All `uses_style` (templates) + `queries_dom` (JS) users of a class, plus the "
                    "stylesheet(s) that `defines` it.\n\nEXAMPLE:\n  query_spashta.py class-usage fp-bulk-busy-btn --json")
    p_clsuse.add_argument("name", help="CSS class name WITHOUT the leading dot (e.g. fp-bulk-busy-btn)")

    subparsers.add_parser(
        "dup-styles", parents=[parent_parser],
        help="CSS classes defined in >1 stylesheet / @keyframes with an identical body",
        description="A StyleClass defined by more than one stylesheet, and Keyframes sharing a body_hash\n"
                    "(byte-identical animations). CANDIDATES for consolidation.\n\nEXAMPLE:\n  query_spashta.py dup-styles --json")

    return parser.parse_args()


# =============================================================================
# MAIN COMMAND DISPATCHER
# =============================================================================

def main():
    """Main entry point. Dispatches to appropriate command handler."""
    args = parse_args()
    
    if not args.command:
        print("No command specified. Use --help for usage information.")
        sys.exit(1)

    graph = load_graph()
    
    # -------------------------------------------------------------------------
    # Command Handlers
    # -------------------------------------------------------------------------
    
    if args.command == "search":
        res = smart_search(graph, args.query, args.type, getattr(args, "app", None))
        if args.json:
            total_nodes = len(graph.get("nodes", []))
            output({
                "results": res,
                "metadata": {
                    "total_matches": len(res),
                    "total_searched": total_nodes,
                    "query": args.query,
                    "type_filter": args.type,
                    "app_filter": getattr(args, "app", None),
                }
            }, True)
        else:
            output(res, False)
        
    elif args.command == "locate":
        node = get_node(graph, args.node_id)
        if node:
            file_path = node.get("file_path")
            if not file_path and "::" in node.get("id", ""):
                file_path = node["id"].split("::")[0]
                if file_path.startswith("File:"):
                    file_path = file_path[5:]
            if not file_path:
                file_path = node.get("name", "N/A")
            loc = {
                "id": node["id"],
                "file": file_path,
                "line_start": node.get("line_start"),
                "line_end": node.get("line_end"),
                "node_type": node.get("node_type"),
                "docstring": node.get("docstring")
            }
            output(loc, args.json)
        else:
            output(node_not_found_response(graph, args.node_id), args.json)
            
    elif args.command == "read":
        res = read_content(graph, args.node_id)
        output(res, args.json)

    elif args.command == "details":
        node = get_node(graph, args.node_id)
        output(node if node else node_not_found_response(graph, args.node_id), args.json)
        
    elif args.command == "impact":
        res = trace_deps(graph, args.node_id, "incoming", args.depth)  # placeholder-aware (by-name)
        if args.json:
            # Add layer coverage summary to JSON output
            coverage = build_layer_coverage(res)
            output({"results": res, **coverage}, True)
        else:
            output(res, False)

    elif args.command == "dependencies":
        res = trace_deps(graph, args.node_id, "outgoing", args.depth)  # placeholder-aware (by-name)
        output(res, args.json)
        
    elif args.command == "call-graph":
        res = get_call_graph(graph, args.node_id)
        output(res, args.json)
         
    elif args.command == "stats":
        from collections import Counter
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        node_types = Counter(n.get("node_type", "Unknown") for n in nodes)
        edge_types = Counter()
        for e in edges:
            _, _, kind = get_edge_endpoints(e)
            edge_types[kind or "Unknown"] += 1
        # Count semantic roles
        role_counts = Counter()
        for n in nodes:
            for r in n.get("semantic_roles", []):
                role_counts[r] += 1
        stats = {
            "nodes": len(nodes),
            "edges": len(edges),
            "ambiguities": len(graph.get("ambiguities", [])),
            "node_types": dict(node_types.most_common()),
            "edge_types": dict(edge_types.most_common()),
            "semantic_roles": dict(role_counts.most_common()) if role_counts else {},
            "meta": graph.get("_meta", {})
        }
        output(stats, args.json)
    
    elif args.command == "list-files":
        all_files = sorted({n.get("file_path") for n in graph.get("nodes", []) if n.get("file_path")})
        app_filter = getattr(args, "app", None)
        if app_filter:
            all_files = [f for f in all_files if f.startswith(app_filter + "/") or f.startswith(app_filter + "\\")]
        if args.json:
            # Group by app for JSON output
            from collections import defaultdict
            grouped = defaultdict(list)
            for f in all_files:
                app = f.split("/")[0] if "/" in f else "root"
                grouped[app].append(f)
            output({"total": len(all_files), "files_by_app": dict(grouped)}, True)
        else:
            output(all_files, False)

    elif args.command == "scope-check":
        # Run impact, then compare against analyzed list
        impact_results = trace_deps(graph, args.node_id, "incoming", args.depth)
        analyzed_list = [f.strip() for f in args.analyzed.split(",") if f.strip()]

        # Get all production files from impact (exclude tests)
        production_files = {}
        for node_id, info in impact_results.items():
            layer = info.get("layer", classify_layer(node_id))
            if layer != "test":
                production_files[node_id] = {**info, "layer": layer}

        # Check which production files are NOT in analyzed list
        unanalyzed = {}
        for node_id, info in production_files.items():
            # Match by substring — analyzed list may have short names
            covered = any(a in node_id for a in analyzed_list)
            if not covered:
                unanalyzed[node_id] = info

        total_prod = len(production_files)
        analyzed_count = total_prod - len(unanalyzed)
        coverage_pct = round(analyzed_count / total_prod * 100) if total_prod > 0 else 100

        verdict = "COMPLETE" if not unanalyzed else f"INCOMPLETE — {len(unanalyzed)} production file(s) not analyzed"

        result = {
            "target": args.node_id,
            "analyzed": analyzed_list,
            "total_production_files": total_prod,
            "analyzed_count": analyzed_count,
            "coverage_percent": coverage_pct,
            "verdict": verdict,
        }
        if unanalyzed:
            result["unanalyzed_production"] = unanalyzed
        output(result, args.json)

    elif args.command == "consumers":
        res = find_consumers(args.model_name, graph)
        output(res, args.json)

    elif args.command == "dead-css":
        defines, style_users, anim_users, _ = _css_index(graph)
        dyn_text = _dynamic_class_text(graph)
        # Partition unused classes (dead-code-accuracy P2): framework-injected / dynamically-referenced /
        # provably dead. Only the last is a real deletion candidate.
        dead_classes, dynamic_classes, framework_classes, dead_kf = [], [], [], []
        for (tt, name), srcs in defines.items():
            if tt == "Keyframes":
                if args.kind in ("keyframes", "all") and name not in anim_users:
                    dead_kf.append(name)
                continue
            if args.kind not in ("class", "all") or name in style_users:
                continue
            # Variable-modifier awareness (dead-code-accuracy P4): a BEM modifier filled by a variable —
            # class="x x--{{ status }}" — never emits the literal `x--archived`, but its base appears as
            # `x--{{`/`x--{%` in a dynamic ambiguity. So a dead `x--suffix` whose base is dynamically
            # modified is applied at runtime, not dead.
            base = name.rsplit("--", 1)[0] if "--" in name else None
            var_modifier = bool(base) and (base + "--{{" in dyn_text or base + "--{%" in dyn_text)
            if any(name.startswith(p) for p in _FRAMEWORK_CLASS_PREFIXES):
                framework_classes.append(name)          # runtime-injected — never dead
            elif name in dyn_text or var_modifier:
                dynamic_classes.append(name)             # applied via a computed/templated attribute
            else:
                dead_classes.append(name)                # provably unused — the real candidate
        res = {"note": "`dead_classes` = provably unused (still CANDIDATES — a class built entirely in Python "
                       "or used only in an inline <script> can't be seen; confirm before deleting). "
                       "`dynamically_referenced` + `framework` are NOT dead.",
               "dead_classes": sorted(dead_classes),
               "dynamically_referenced": sorted(dynamic_classes),
               "framework": sorted(framework_classes),
               "dead_keyframes": sorted(dead_kf),
               "counts": {"classes": len(dead_classes), "dynamically_referenced": len(dynamic_classes),
                          "framework": len(framework_classes), "keyframes": len(dead_kf)}}
        output(res, args.json)

    elif args.command == "class-usage":
        defines, style_users, _, _ = _css_index(graph)
        name = args.name.lstrip(".")
        res = {"class": name,
               "defined_in": sorted(defines.get(("StyleClass", name), [])),
               "used_by": sorted(style_users.get(name, [])),
               "used": bool(style_users.get(name))}
        output(res, args.json)

    elif args.command == "dup-styles":
        defines, _, _, kf_hashes = _css_index(graph)
        dup_classes = {name: sorted(srcs) for (tt, name), srcs in defines.items()
                       if tt == "StyleClass" and len(srcs) > 1}
        identical_kf = [sorted(names) for names in kf_hashes.values() if len(names) > 1]
        res = {"note": "CANDIDATES — a class in >1 file may be an intentional media-query/theme override.",
               "classes_defined_in_multiple_files": dict(sorted(dup_classes.items())),
               "identical_keyframes": identical_kf,
               "counts": {"dup_classes": len(dup_classes), "identical_keyframe_groups": len(identical_kf)}}
        output(res, args.json)

    # --- Contextual hint (JSON mode only, printed to stderr so it doesn't break JSON parsing) ---
    if args.json and args.command in COMMAND_HINTS:
        import sys as _sys
        print(f"\n[Spashta] {COMMAND_HINTS[args.command]}", file=_sys.stderr)


if __name__ == "__main__":
    main()
