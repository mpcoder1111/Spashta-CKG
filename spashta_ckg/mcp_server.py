"""
Spashta MCP Server - Model Context Protocol tool interface for AI Coding Agents.
"""

import sys
import json
from pathlib import Path
from spashta_ckg.engine import CKG

TOOLS = [
    {
        "name": "spashta_impact",
        "description": "Calculate blast radius: what views, templates, styles, and functions depend on or call a given symbol before you edit or refactor it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": { "type": "string", "description": "Name of function, class, style class, or model" },
                "depth": { "type": "integer", "description": "Max traversal depth (default: 3)", "default": 3 },
                "project_dir": { "type": "string", "description": "Path to project root (default: current directory)" }
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "spashta_dead_code",
        "description": "Find unreferenced dead code across Python, JavaScript, and CSS with high precision.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "language": { "type": "string", "enum": ["css", "js", "py"], "description": "Filter by language" },
                "project_dir": { "type": "string", "description": "Path to project root (default: current directory)" }
            }
        }
    },
    {
        "name": "spashta_routes",
        "description": "List all full-stack routes and see how backend views, frontend templates, and HTMX triggers connect.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": { "type": "string", "description": "Path to project root (default: current directory)" }
            }
        }
    },
    {
        "name": "spashta_search",
        "description": "Search the Code Knowledge Graph for symbols, styles, routes, or components.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": { "type": "string", "description": "Search query" },
                "node_type": { "type": "string", "description": "Filter by node type (e.g. Function, Route, StyleClass)" },
                "project_dir": { "type": "string", "description": "Path to project root" }
            },
            "required": ["query"]
        }
    },
    {
        "name": "spashta_scan",
        "description": "Scan or rebuild the full multi-language Code Knowledge Graph for a project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": { "type": "string", "description": "Path to project root" }
            }
        }
    }
]

def handle_request(req):
    method = req.get("method")
    msg_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": { "tools": {} },
                "serverInfo": { "name": "spashta-mcp", "version": "3.0.0" }
            }
        }

    elif method == "notifications/initialized":
        return None

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": { "tools": TOOLS }
        }

    elif method == "tools/call":
        params = req.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})
        project_dir = args.get("project_dir") or "."

        try:
            if tool_name == "spashta_scan":
                ckg = CKG.build(project_root=project_dir)
                res_content = json.dumps(ckg.stats(), indent=2)
            else:
                try:
                    ckg = CKG.load(project_root=project_dir)
                except FileNotFoundError:
                    ckg = CKG.build(project_root=project_dir)

                if tool_name == "spashta_impact":
                    res = ckg.impact(args["symbol"], depth=args.get("depth", 3))
                    res_content = json.dumps(res, indent=2)

                elif tool_name == "spashta_dead_code":
                    res = ckg.dead_code(language=args.get("language"))
                    res_content = json.dumps(res, indent=2)

                elif tool_name == "spashta_routes":
                    res = ckg.routes()
                    res_content = json.dumps(res, indent=2)

                elif tool_name == "spashta_search":
                    res = ckg.search(args["query"], node_type=args.get("node_type"))
                    res_content = json.dumps(res, indent=2)

                else:
                    return {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": { "code": -32601, "message": f"Unknown tool: {tool_name}" }
                    }

            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{ "type": "text", "text": res_content }]
                }
            }

        except Exception as ex:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": { "code": -32000, "message": str(ex) }
            }

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": { "code": -32601, "message": f"Method not found: {method}" }
    }

def main():
    """Stdio JSON-RPC server loop."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = handle_request(req)
            if resp:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
        except Exception:
            pass

if __name__ == "__main__":
    main()
