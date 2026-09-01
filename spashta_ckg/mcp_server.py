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

try:
    from mcp.types import CallToolResult, TextContent
except ImportError:
    CallToolResult, TextContent = None, None

mcp = _ServerBase("spashta_ckg")

class SpashtaMCPResult(CallToolResult):
    """
    Subclass of CallToolResult providing transparent dictionary access for Python callers
    while delivering both formatted text content and native structuredContent to MCP clients.
    """
    def __getitem__(self, item):
        if self.structured_content and isinstance(self.structured_content, dict):
            return self.structured_content[item]
        raise KeyError(item)

    def get(self, item, default=None):
        if self.structured_content and isinstance(self.structured_content, dict):
            return self.structured_content.get(item, default)
        return default

    def __contains__(self, item):
        return self.structured_content is not None and item in self.structured_content

    def keys(self):
        return self.structured_content.keys() if isinstance(self.structured_content, dict) else [].keys()

    def values(self):
        return self.structured_content.values() if isinstance(self.structured_content, dict) else [].values()

    def items(self):
        return self.structured_content.items() if isinstance(self.structured_content, dict) else [].items()


def _to_mcp_result(data):
    """Wraps result into SpashtaMCPResult supporting structuredContent and TextContent."""
    if CallToolResult is not None and TextContent is not None:
        structured = data if isinstance(data, dict) else {"items": data}
        return SpashtaMCPResult(
            content=[TextContent(type="text", text=json.dumps(data, indent=2))],
            structured_content=structured
        )
    return data


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
async def spashta_impact(symbol: str, depth: int = 3, project_dir: str = ".") -> SpashtaMCPResult:
    """Calculate blast radius: what views, templates, styles, and functions depend on or call a given symbol before you edit or refactor it."""
    ckg = _get_ckg(project_dir)
    return _to_mcp_result(ckg.impact(symbol, depth=depth))

@mcp.tool()
async def spashta_dependencies(symbol: str, depth: int = 3, project_dir: str = ".") -> SpashtaMCPResult:
    """Inspect downstream outgoing dependencies: see what functions, models, templates, and packages a symbol calls or uses before refactoring or moving it."""
    ckg = _get_ckg(project_dir)
    return _to_mcp_result(ckg.dependencies(symbol, depth=depth))

@mcp.tool()
async def spashta_can_delete(symbol: str, depth: int = 3, summary_only: bool = False, project_dir: str = ".") -> SpashtaMCPResult:
    """Evaluate whether a symbol can be safely deleted without breaking working code. Distinguishes production blockers from test-only blockers. Use summary_only=True to receive compact blocker file lists and save tokens."""
    ckg = _get_ckg(project_dir)
    return _to_mcp_result(ckg.can_delete(symbol, depth=depth, summary_only=summary_only))

@mcp.tool()
async def spashta_routes(project_dir: str = ".") -> SpashtaMCPResult:
    """List all full-stack routes and see how backend views, frontend templates, and HTMX triggers connect."""
    ckg = _get_ckg(project_dir)
    return _to_mcp_result(ckg.routes())

@mcp.tool()
async def spashta_search(query: str, node_type: Optional[str] = None, project_dir: str = ".") -> SpashtaMCPResult:
    """Search the Code Knowledge Graph for symbols, styles, routes, or components with compact output by default."""
    ckg = _get_ckg(project_dir)
    return _to_mcp_result(ckg.search(query, node_type=node_type))

@mcp.tool()
async def spashta_dead_code(language: Optional[str] = None, project_dir: str = ".") -> SpashtaMCPResult:
    """Find unreferenced dead code across Python, JavaScript, and CSS with audit provenance."""
    ckg = _get_ckg(project_dir)
    return _to_mcp_result(ckg.dead_code(language=language))

@mcp.tool()
async def spashta_scan(project_dir: str = ".") -> SpashtaMCPResult:
    """Scan or rebuild the full multi-language Code Knowledge Graph for a project."""
    root = Path(project_dir).resolve() if project_dir and project_dir != "." else Path.cwd()
    ckg = CKG.build(project_root=root)
    return _to_mcp_result(ckg.stats())

@mcp.tool()
async def spashta_locate(symbol: str, project_dir: str = ".") -> SpashtaMCPResult:
    """Locate the exact file path, start line, and end line of a function, class, route, or template symbol in universal envelope schema with ambiguity detection."""
    ckg = _get_ckg(project_dir)
    return _to_mcp_result(ckg.locate(symbol))

@mcp.tool()
async def spashta_stats(project_dir: str = ".") -> SpashtaMCPResult:
    """Get high-level summary statistics, node breakdowns, edge types, and semantic role counts for the Code Knowledge Graph."""
    ckg = _get_ckg(project_dir)
    return _to_mcp_result(ckg.stats())

@mcp.tool()
async def spashta_refresh(files: Optional[str] = None, project_dir: str = ".") -> SpashtaMCPResult:
    """Fast incremental refresh: re-parse only changed or specified files (e.g. after code edits) in milliseconds."""
    root = Path(project_dir).resolve() if project_dir and project_dir != "." else Path.cwd()
    ckg = CKG.refresh(project_root=root, files=files)
    return _to_mcp_result(ckg.stats())

def main():
    """Starts the official MCP server on stdio transport or displays help if invoked from CLI."""
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help", "help"):
        print("""Spashta MCP Server (Stdio Transport) - Agent-Native Code Knowledge Graph Intelligence
Protocol: Model Context Protocol (MCP) over Stdio JSON-RPC
Version: 3.2.8

Dual Delivery Output Format:
  All tools return SpashtaMCPResult supporting dual-delivery:
  1. content: Formatted JSON text (backward-compatible with text-based MCP clients like Claude Code)
  2. structured_content: Native decoded dictionary for modern structuredContent-aware MCP clients (0 decoding)

10 Native Zero-Click MCP Tools:
  1. spashta_impact(symbol: str, depth: int = 3, project_dir: str = ".")
     Upstream blast radius: who calls or depends on this symbol before you edit it.
     Returns: Universal envelope with caller nodes and discriminating spread.

  2. spashta_dependencies(symbol: str, depth: int = 3, project_dir: str = ".")
     Downstream outgoing dependencies: what a symbol calls, imports, or uses before refactoring.
     Returns: Universal envelope with outgoing dependencies and relation types.

  3. spashta_can_delete(symbol: str, depth: int = 3, summary_only: bool = False, project_dir: str = ".")
     High-level safe deletion decision engine: evaluates if a symbol can be safely deleted.
     Distinguishes production blockers (unsafe) from test-only blockers (safe + requires test updates).
     Set summary_only=True for compact blocker file lists (~350 bytes) instead of heavy AST nodes.
     Returns: { "can_delete": bool, "blockers": {...}, "requires_test_updates": [...] }

  4. spashta_locate(symbol: str, project_dir: str = ".")
     Pinpoint exact file path, start line, and end line of a function, class, route, or template.
     Breaks exact-name ties via type weighting (Functions > Models > Fields).
     Returns: Universal envelope with target coordinates and ambiguity flags.

  5. spashta_search(query: str, node_type: Optional[str] = None, project_dir: str = ".")
     Search indexed symbols, classes, routes, or components.
     Compact by default (docstrings omitted to save context tokens).
     Returns: List of matching symbol entries.

  6. spashta_routes(project_dir: str = ".")
     Full-stack routes connecting backend views, templates, and HTMX triggers.
     Returns: List of URL route mappings with connected frontend/backend nodes.

  7. spashta_dead_code(language: Optional[str] = None, project_dir: str = ".")
     Dynamic-syntax safe audit for unreferenced dead code across Python, JS, and CSS.
     Returns: Universal envelope with dead items, breakdown, and audit provenance.

  8. spashta_stats(project_dir: str = ".")
     High-level graph health: total nodes, edges, language breakdowns, and semantic roles.
     Returns: Graph summary metrics and freshness status.

  9. spashta_refresh(files: Optional[str] = None, project_dir: str = ".")
     Sub-50ms incremental synchronization: re-parses only modified or specified files.
     Returns: Updated graph summary statistics.

  10. spashta_scan(project_dir: str = ".")
      Initial repository scan: auto-detects languages/frameworks and builds CKG cache.
      Returns: Complete graph statistics.

IDE Configuration (mcp_config.json):
  {
    "mcpServers": {
      "spashta_ckg": {
        "command": "spashta_ckg_mcp",
        "args": []
      }
    }
  }""")
        return
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
