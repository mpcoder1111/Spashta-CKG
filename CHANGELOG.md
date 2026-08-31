# Changelog

All notable changes to Spashta-CKG will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [3.2.2] - 2026-08-31

**Spashta-CKG 3.2.2 — High-Speed Incremental Graph Refresh & Sub-50ms Edit Synchronization**

Added fast incremental change detection and partial graph refresh across the Python API (`CKG.refresh()`), Terminal CLI (`spashta_ckg refresh`, `spashta_ckg scan --incremental`), and native MCP Server (`spashta_refresh`).

### Added
- **Fast Incremental Refresh Engine (`CKG.refresh()`)**: Automatically detects modified, added, or deleted files using MD5 content hashing and only re-parses changed files/languages, updating `.spashta/` graph memory in ~20–50ms.
- **Targeted File Refresh**: Support for refreshing specific files directly via `--file` (e.g. `spashta_ckg refresh --file app/views.py` or `spashta_refresh(files="app/views.py")`).
- **New CLI Subcommand (`spashta_ckg refresh`) & Flag (`--incremental`)**: Fast CLI workflow to keep CKG cache in sync during active coding without doing full project scans.
- **Native MCP Tool (`spashta_refresh`)**: Allows AI agents to instantly re-synchronize graph memory after modifying files with zero user clicks.
- **Agent Skill & Governance Protocol Update**: Updated 4-phase closed loop with post-edit incremental refresh guidelines.

---

## [3.2.1] - 2026-08-30

**Spashta-CKG 3.2.1 — FastMCP Asynchronous Performance & Fail-Fast Reliability Patch**

Maintenance patch resolving background MCP daemon hangs, eliminating runaway full-disk scan fallbacks, and adding instant CLI `--help` handling.

### Fixed
- **CLI `-h` / `--help` Daemon Interception**: Added command-line argument handling in `spashta_ckg_mcp` so `--help` prints usage instructions and exits immediately in 0.05s instead of hanging on stdin.
- **Eliminated Runaway Disk Scan Fallbacks**: Removed the automatic `CKG.build()` fallback inside query MCP tools (`spashta_impact`, `spashta_routes`, `spashta_search`, `spashta_dead_code`). If no graph exists in the target directory, it now fails fast in 0.001s with an explicit prompt to run `spashta_scan`, preventing background processes from scanning the entire filesystem.
- **Asynchronous Tool Handlers (`async def`)**: Defined all FastMCP tools asynchronously to ensure the stdio transport event loop is never blocked by disk I/O.

---

## [3.2.0] - 2026-08-30

**Spashta-CKG 3.2 — Official Model Context Protocol (MCP) SDK Upgrade & Cross-Platform Transport**

Enterprise-grade MCP server upgrade integrating Anthropic's official `mcp` Python SDK for robust, non-blocking asynchronous stdio communication across all major AI coding environments.

### Added
- **Official Model Context Protocol (MCP) SDK Upgrade**: Migrated `spashta_ckg_mcp` to the official Python `mcp` SDK (`MCPServer` / `FastMCP`) with asynchronous stdio transport, eliminating Windows pipe buffer blocks and stream deadlocks across Antigravity, Cursor, Claude Desktop, and VS Code.
- **Cross-Version MCP Compatibility**: Seamless dual-support for both `mcp>=2.0.0` (`MCPServer`) and `mcp<2.0.0` (`FastMCP`).
- **Comprehensive Native MCP Tool Suite**: Native IDE execution for `spashta_impact`, `spashta_routes`, `spashta_search`, `spashta_dead_code`, and `spashta_scan` with zero-click silent execution.
- **Enhanced MCP Configuration Guides**: Clear setup documentation for global environments and project-level `.venv` paths on Windows, Linux, and macOS.

---

## [3.1.0] - 2026-08-30

**Spashta-CKG 3.1 — Zero-Config Multi-Language Engine & Streamlined Directory Exclusions**

Streamlined developer and agent experience with zero-config auto-discovery for all languages and frameworks, plus interactive directory exclusion management via `init` and `config`.

### Added
- **Interactive Project Initialization (`spashta_ckg init`)**: One-step project setup generating a clean `profile.json` with tailored directory exclusions (`--exclude`).
- **Configuration Management (`spashta_ckg config`)**: View active project settings (`spashta_ckg config`) or append exclusions (`spashta_ckg config --add-exclude "misc,legacy"`) directly from CLI.
- **Zero-Config Language & Framework Auto-Detection**: Removed redundant manual language and framework declarations. Spashta automatically indexes all present files across Python, JavaScript, HTML, and CSS, and dynamically applies Django, FastAPI, HTMX, and Vanilla JS semantic rules.
- **Simplified `profile.json` Schema**: Focused strictly on directory exclusions (`"exclude": ["..."]`), with full backwards-compatibility for legacy profiles.
- **Ad-Hoc Scan Exclusions**: Added `--exclude` flag to `spashta_ckg scan` for one-shot folder exclusions.

---

## [3.0.0] - 2026-08-30

**Spashta-CKG 3.0 — Full-Stack Code Knowledge Graph & MCP Server**

Major update packaging Spashta into an installable Python library (`spashta_ckg`), a 17-command interactive CLI, and a native Model Context Protocol (MCP) server (`spashta_ckg_mcp`).

### Added
- **Installable Package & CLI (`spashta_ckg`)**: Installable via `pip install git+https://github.com/mpcoder1111/Spashta-CKG.git` with 19 unified CLI commands (`init`, `config`, `scan`, `impact`, `dependencies`, `dead-code`, `dead-css`, `routes`, `call-graph`, `search`, `locate`, `read`, `details`, `consumers`, `scope-check`, `class-usage`, `dup-styles`, `list-files`, `stats`).
- **Project Configuration & Initialization (`init` / `config`)**: Automated project setup detecting languages and sensible exclusions, plus runtime scan overrides via `--exclude`, `--languages`, and `--frameworks`.
- **Native MCP Server (`spashta_ckg_mcp`)**: Fast JSON-RPC stdio MCP server giving AI Agents in Cursor, Antigravity, Claude Desktop, and VS Code native zero-click tool execution (`spashta_impact`, `spashta_dead_code`, `spashta_routes`, `spashta_search`, `spashta_scan`).
- **Full JavaScript Support (Tree-Sitter)**: New `build_js_ast.py` builder with tree-sitter AST parser, Vanilla JS framework adapter, DOM queries (`queries_dom`), `classList` mutations (`uses_style`), event listeners (`listens_to`, `dispatches_event`), and callback reference resolution (`calls`).
- **Full-Stack Django Route Couplings**: Resolves URLconf `path()` / `include()` hierarchies (`includes_urlconf`), links template `{% url %}` tags to Route nodes (`resolves_to`), and maps view API calls (`calls_api`).
- **HTMX Cross-Language Couplings**: Maps Python `HX-Trigger` response headers (`dispatches_event`), HTMX `hx-trigger="... from:body"` listeners (`listens_to`), Out-of-Band swaps (`oob_swaps`), and Form/Signal model extraction (`uses_model`).
- **Template Hierarchy Modeling**: Captures Django template tags `{% include %}` (`includes_template`) and `{% extends %}` (`extends_template`).
- **CSS Coverage & Keyframes**: New `Keyframes` node type, `@keyframes` extraction with `uses_animation` / `defines` edges, and fixed compound selector lookaheads (`.a.b`, `.parent > .child`).
- **Dead-Code Accuracy Engine**: Eliminates ~35% false positives in dead-CSS / dead-JS auditing by tracking dynamic class usages across HTML attributes, inline scripts, and template contexts.
- **Programmatic Python API**: `from spashta_ckg import CKG` for direct programmatic graph queries and pipeline integrations.

---

## [2.1.0] - 2026-03-18

**Spashta-CKG 2.1 — Deeper Awareness, Fewer Blind Spots**

Same 5-layer architecture as 2.0. All changes are additive — zero breaking changes. 76 changes total.

### Added

- **3 new Core node types:** `Field` (ORM fields), `Constant` (UPPER_CASE values), `TestCase` (test containers)
- **3 new Core edge types:** `has_field` (Class → Field), `references` (FK between models), `listens_to` (event/signal subscription)
- **Python builder:** ORM field detection, constant detection, TestCase classification, FK reference edges, self/super method resolution, lazy import tracking (`lazy: true` metadata)
- **Django adapter:** 4 new roles (ManagementCommand, URLConf, AppConfig, Migration) — total 13 roles
- **FastAPI adapter:** 2 new roles (EventHandler, Middleware) — total 7 roles
- **HTMX adapter:** Component and Fragment detection now working (was dead code in 2.0)
- **Enrichment engine:** 3 new detection rules (`arg_names_include`, `decorators`, `has_outgoing_edge`) — total 9 rules
- **Query tool:** `scope-check` command, `consumers` command (grep+graph hybrid), `--app` filter on search/list-files, layer classification in impact output, search result metadata
- **Adapter validator:** Detection rule key validation (catches typos), warning vs error separation
- **Integrity check:** `Integrity_Check_Spashta2.1.txt` with 7-step verification sequence
- **Agent hints:** Contextual `[Spashta]` hints on stderr after every JSON command — 11 command-specific next-step suggestions to guide agents toward complete analysis

### Fixed

- **Enrichment engine:** `arg_names_include` and `decorators` rules were declared in adapter mappings but never implemented — View functions and Signal handlers were invisible (dead code)
- **Enrichment engine:** `file_path_contains` didn't work for File/Template nodes (only checked parent via defines edge, not the node itself)
- **HTMX adapter:** `contains_attributes` rule was never implemented — replaced with working `has_outgoing_edge`
- **AST equivalence validator:** `node_type` vs `type` key mismatch, edge key format, hardcoded path
- **Diff engine:** Missing `has_field`/`contains_field` in ownership edges, edge key format
- **Query tool:** `locate` didn't resolve file path from node ID/name; auto File: prefix detection; Windows Unicode crash (auto UTF-8 stdout)
- **Adapter validator:** Custom semantic roles incorrectly treated as errors (now warnings)
- **Execution protocol:** Wrong command names in post_completion (`list-functions`, `search-callers` etc. didn't exist)
- **All runtime scripts:** Hardcoded `Spashta_2.0` paths → `Spashta_2.1` (6 files)
- **All _docs:** Stale `Spashta_2.0` references in 7 documentation files
- **Query Tool Readme:** Wrong command table from v1.x syntax replaced with actual 2.1 commands
- **Core schema (critical):** `imports.from` only allowed File/Module/Stylesheet — Function and Method were missing. This caused the schema enforcer to silently reject ALL function-scoped (lazy) import edges. 311 edges recovered after fix. `impact` now finds view consumers that use lazy imports.

### Changed

- **Core schema:** `imports.from` expanded (+Function, +Method for lazy imports), `defines.to` expanded (+Variable, Constant, Field, TestCase), `contains_member.to` expanded (+Field, Constant), `Enum`/`Decorator` languages expanded
- **Python language mapping:** v1.5 → v1.6 (8 new node mappings, 9 new edge mappings)
- **Builder rules:** v1.2 → v1.3 (4 new policy sections: classification, call resolution, import scope, string reference)
- **Profile:** Relative project_root (`..`), added `core_schema_version: 1.4`
- **Session log schema:** Added `diff_runtime_ast` step
- **Agent prompt:** v3 → v4, all 2.1 features documented, TRAP 4 (Unicode) simplified

### Metrics

| Metric | 2.0 | 2.1 |
|--------|-----|-----|
| Core node types | 33 | 38 |
| Core edge types | 19 | 22 |
| Detection rules | 4 (2 dead) | 9 (all working) |
| Django adapter roles | 9 | 13 |
| FastAPI adapter roles | 5 (2 dead) | 7 (2 dead documented) |
| HTMX adapter roles | 2 (both dead) | 2 (both working) |
| Query commands | 9 | 11 (+scope-check, +consumers) |
| Lazy import edges | 0 (schema rejected) | 311 (Function→imports now allowed) |
| Semantic roles (single app test) | ~0 | 77 |
| Enrichment (full project) | 100 (all "Component") | 300 (specific roles) |
| Total edges (full project) | ~15,700 | 16,053 (+311 lazy imports) |

> 📖 Full detail: `Spashta_2.1/Readme_updations_done_in_2.1.md`

---

## [2.0.0] - 2025-12-30

**Spashta-CKG 2.0 — Complete Architectural Redesign**

This is the first public release of Spashta-CKG with a production-ready architecture designed for AI-assisted coding at scale.

### 🎯 What is Spashta-CKG?

A **Code Knowledge Graph** tool that gives AI Agents deterministic, structured knowledge about codebases — eliminating guesswork and hallucinations.

### ✨ Key Features

- **AST-Based Parsing** — Extracts structure from Python, HTML, and CSS using native language tools
- **Line Numbers & Docstrings** — Exact locations and documentation for every code element
- **Import & Call Tracking** — Who imports whom, what calls what
- **Semantic Enrichment** — Framework-aware understanding (Django, FastAPI, HTMX)
- **Query Tool** — CLI for AI agents to query the graph without reading files
- **Incremental Updates** — Only re-process changed files

### 🏗️ Architecture Highlights

| Layer | Purpose |
|-------|---------|
| **Core** | Universal software schema (nodes.json, edges.json) |
| **Builders** | Language observers (Python, HTML, CSS) |
| **Adapters** | Framework interpreters (Django, FastAPI, HTMX) |
| **Runtime** | Execution engine (build → enrich → validate) |
| **Project** | Per-project configuration (profile.json) |

### 📊 Enrichment Levels

| Level | Description |
|-------|-------------|
| **L1** | Rule-based adapter enrichment (fast, deterministic) |
| **L2** | LLM-based enrichment (deep, business context) |

### 🔧 Supported Technologies

**Languages:**
- ✅ Python
- ✅ HTML
- ✅ CSS

**Frameworks:**
- ✅ Django
- ✅ FastAPI
- ✅ HTMX

### 📚 Documentation

Complete documentation suite included in `_docs/`:
- Architecture reference
- Builder & adapter guides
- Query tool reference
- Contributor guidelines

---

## [1.0.0] - Pre-2.0

Initial prototype. Superseded by 2.0 architecture.

---

*Spashta-CKG — Deterministic Architectural Memory for Agentic Coding*
