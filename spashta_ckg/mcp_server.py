"""
Spashta MCP Server - Model Context Protocol tool interface for AI Coding Agents.
Powered by the official MCP Python SDK for robust, non-blocking cross-platform stdio transport.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Optional
from spashta_ckg.engine import CKG

# Log to stderr (safe for stdio MCP servers since stdout is reserved for JSON-RPC)
logger = logging.getLogger("spashta_mcp")

try:
    from mcp.server.mcpserver import MCPServer as _ServerBase
except ImportError:
    from mcp.server.fastmcp import FastMCP as _ServerBase

mcp = _ServerBase("spashta_ckg")

def _get_ckg(project_dir: str = ".") -> CKG:
    root = Path(project_dir).resolve() if project_dir and project_dir != "." else Path.cwd()
    try:
        return CKG.load(project_root=root)
    except FileNotFoundError:
        logger.warning(f"No Spashta CKG found at {root}. Explicit scan required.")
        raise RuntimeError(
            f"No Spashta CKG found at '{root}'. "
            f"Please run 'spashta_scan(project_dir=\"...\")' or CLI 'spashta_ckg scan -p \"...\"' first."
        )

@mcp.tool()
async def spashta_impact(symbol: str, depth: int = 3, project_dir: str = ".") -> str:
    """Calculate blast radius: what views, templates, styles, and functions depend on or call a given symbol before you edit or refactor it."""
    ckg = _get_ckg(project_dir)
    return json.dumps(ckg.impact(symbol, depth=depth), indent=2)

@mcp.tool()
async def spashta_routes(project_dir: str = ".") -> str:
    """List all full-stack routes and see how backend views, frontend templates, and HTMX triggers connect."""
    ckg = _get_ckg(project_dir)
    return json.dumps(ckg.routes(), indent=2)

@mcp.tool()
async def spashta_search(query: str, node_type: Optional[str] = None, project_dir: str = ".") -> str:
    """Search the Code Knowledge Graph for symbols, styles, routes, or components."""
    ckg = _get_ckg(project_dir)
    return json.dumps(ckg.search(query, node_type=node_type), indent=2)

@mcp.tool()
async def spashta_dead_code(language: Optional[str] = None, project_dir: str = ".") -> str:
    """Find unreferenced dead code across Python, JavaScript, and CSS with high precision."""
    ckg = _get_ckg(project_dir)
    return json.dumps(ckg.dead_code(language=language), indent=2)

@mcp.tool()
async def spashta_scan(project_dir: str = ".") -> str:
    """Scan or rebuild the full multi-language Code Knowledge Graph for a project."""
    root = Path(project_dir).resolve() if project_dir and project_dir != "." else Path.cwd()
    ckg = CKG.build(project_root=root)
    return json.dumps(ckg.stats(), indent=2)

@mcp.tool()
async def spashta_refresh(files: Optional[str] = None, project_dir: str = ".") -> str:
    """Fast incremental refresh: re-parse only changed or specified files (e.g. after code edits) in milliseconds."""
    root = Path(project_dir).resolve() if project_dir and project_dir != "." else Path.cwd()
    ckg = CKG.refresh(project_root=root, files=files)
    return json.dumps(ckg.stats(), indent=2)

def main():
    """Starts the official MCP server on stdio transport or displays help if invoked from CLI."""
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help", "help"):
        print("Spashta MCP Server (Stdio transport). Intended to be invoked by MCP clients.")
        print("Usage in mcp_config.json:")
        print('  { "mcpServers": { "spashta_ckg": { "command": "spashta_ckg_mcp", "args": [] } } }')
        return
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
