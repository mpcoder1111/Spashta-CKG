"""
Spashta MCP Server - Model Context Protocol tool interface for AI Coding Agents.
Powered by the official MCP Python SDK for robust, non-blocking cross-platform stdio transport.
"""

import json
from pathlib import Path
from typing import Optional
from spashta_ckg.engine import CKG

try:
    from mcp.server.mcpserver import MCPServer as _ServerBase
except ImportError:
    from mcp.server.fastmcp import FastMCP as _ServerBase

mcp = _ServerBase("spashta_ckg")

@mcp.tool()
def spashta_impact(symbol: str, depth: int = 3, project_dir: str = ".") -> str:
    """Calculate blast radius: what views, templates, styles, and functions depend on or call a given symbol before you edit or refactor it."""
    try:
        ckg = CKG.load(project_root=project_dir)
    except FileNotFoundError:
        ckg = CKG.build(project_root=project_dir)
    return json.dumps(ckg.impact(symbol, depth=depth), indent=2)

@mcp.tool()
def spashta_dead_code(language: Optional[str] = None, project_dir: str = ".") -> str:
    """Find unreferenced dead code across Python, JavaScript, and CSS with high precision."""
    try:
        ckg = CKG.load(project_root=project_dir)
    except FileNotFoundError:
        ckg = CKG.build(project_root=project_dir)
    return json.dumps(ckg.dead_code(language=language), indent=2)

@mcp.tool()
def spashta_routes(project_dir: str = ".") -> str:
    """List all full-stack routes and see how backend views, frontend templates, and HTMX triggers connect."""
    try:
        ckg = CKG.load(project_root=project_dir)
    except FileNotFoundError:
        ckg = CKG.build(project_root=project_dir)
    return json.dumps(ckg.routes(), indent=2)

@mcp.tool()
def spashta_search(query: str, node_type: Optional[str] = None, project_dir: str = ".") -> str:
    """Search the Code Knowledge Graph for symbols, styles, routes, or components."""
    try:
        ckg = CKG.load(project_root=project_dir)
    except FileNotFoundError:
        ckg = CKG.build(project_root=project_dir)
    return json.dumps(ckg.search(query, node_type=node_type), indent=2)

@mcp.tool()
def spashta_scan(project_dir: str = ".") -> str:
    """Scan or rebuild the full multi-language Code Knowledge Graph for a project."""
    ckg = CKG.build(project_root=project_dir)
    return json.dumps(ckg.stats(), indent=2)

def main():
    """Starts the official MCP server on stdio transport."""
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
