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
| impact        | Who depends on this? (Incoming edges)          |
| dependencies  | What does this use? (Outgoing edges)           |
| call-graph    | Function call relationships (caller/callee)    |
| stats         | Graph statistics (node/edge counts)            |
| list-files    | List all indexed source files                  |

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
from pathlib import Path

# =============================================================================
# CONFIGURATION & CONSTANTS
# =============================================================================

# Path Setup - REPO_ROOT is the Spashta-CKG folder (parent of Spashta_2.0)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SPASHTA_DIR = REPO_ROOT / "Spashta_2.0"
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

def smart_search(graph, query, type_filter=None):
    """
    Performs intelligent search across CKG nodes.
    
    Supports:
    - Simple text search: Matches against node name and ID
    - Attribute search:   Use "key:value" syntax (e.g., "decorator:login")
    - Type filtering:     Use --type to filter by node type
    
    Args:
        graph: The loaded CKG
        query: Search query string
        type_filter: Optional node type filter (e.g., "Function", "Class")
    
    Returns:
        list: Matching nodes (max 50 results)
    
    Examples:
        smart_search(graph, "auth")                    # Name/ID contains "auth"
        smart_search(graph, "decorator:login")         # Has @login decorator
        smart_search(graph, "tag:form")                # HTML tag is "form"
        smart_search(graph, "pseudo_state:hover")      # CSS :hover selector
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
            
    return results[:50]


# =============================================================================
# NODE/EDGE UTILITIES
# =============================================================================

def get_node(graph, node_id):
    """
    Retrieves a specific node by its ID.
    
    Args:
        graph: The loaded CKG
        node_id: Exact node ID (e.g., "app/views.py::login")
    
    Returns:
        dict or None: The node object, or None if not found.
    """
    for node in graph.get("nodes", []):
        if node["id"] == node_id:
            return node
    return None


def get_edges_list(graph):
    """Returns the edges array from the graph."""
    return graph.get("edges", [])


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
    if start_id in visited or current_depth >= depth:
        return {}
    
    visited.add(start_id)
    results = {}
    edges = get_edges_list(graph)
    
    for edge in edges:
        src, dst, kind = get_edge_endpoints(edge)
        
        neighbor = None
        if direction == "outgoing" and src == start_id:
            neighbor = dst
        elif direction == "incoming" and dst == start_id:
            neighbor = src
            
        if neighbor and neighbor not in results:
            node_obj = get_node(graph, neighbor)
            results[neighbor] = {
                "relation": kind,
                "depth": current_depth + 1,
                "node_type": node_obj.get("node_type") if node_obj else "Unknown"
            }
            # Recurse
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
    
    # Strict path resolution from PROJECT_ROOT (as defined in profile.json)
    target_path = PROJECT_ROOT / file_path
    
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


# =============================================================================
# OUTPUT FORMATTING
# =============================================================================

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
                print(f"  - {item.get('id')} ({item.get('node_type')})")
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
    p_search.add_argument("--type", help="Filter by node type (Function, Class, etc.)")
    
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
    subparsers.add_parser(
        "list-files", 
        parents=[parent_parser], 
        help="List all indexed source files",
        description="Get a list of all files that have been indexed in the CKG."
    )

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
        res = smart_search(graph, args.query, args.type)
        output(res, args.json)
        
    elif args.command == "locate":
        node = get_node(graph, args.node_id)
        if node:
            loc = {
                "id": node["id"],
                "file": node.get("file_path", "N/A"),
                "line_start": node.get("line_start"),
                "line_end": node.get("line_end"),
                "docstring": node.get("docstring")
            }
            output(loc, args.json)
        else:
            output({"error": "Node not found"}, args.json)
            
    elif args.command == "read":
        res = read_content(graph, args.node_id)
        output(res, args.json)

    elif args.command == "details":
        node = get_node(graph, args.node_id)
        output(node if node else {"error": "Node not found"}, args.json)
        
    elif args.command == "impact":
        res = trace_deps(graph, args.node_id, "incoming", args.depth)
        output(res, args.json)

    elif args.command == "dependencies":
        res = trace_deps(graph, args.node_id, "outgoing", args.depth)
        output(res, args.json)
        
    elif args.command == "call-graph":
        res = get_call_graph(graph, args.node_id)
        output(res, args.json)
         
    elif args.command == "stats":
        stats = {
            "nodes": len(graph.get("nodes", [])),
            "edges": len(graph.get("edges", [])),
            "meta": graph.get("_meta", {})
        }
        output(stats, args.json)
    
    elif args.command == "list-files":
        files = sorted({n.get("file_path") for n in graph.get("nodes", []) if n.get("file_path")})
        output(files, args.json)


if __name__ == "__main__":
    main()
