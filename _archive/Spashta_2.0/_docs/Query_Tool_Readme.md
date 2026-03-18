# Query Spashta — AI Agent's Gateway to Code Knowledge

This document provides complete documentation for `query_spashta.py`, the CLI tool that AI Agents use to query the Code Knowledge Graph.

*Last Updated: 2025-12-30*

---

## Overview

`query_spashta.py` is the **primary interface** for AI Agents to access the Code Knowledge Graph (CKG). Instead of reading every file, agents can query structured information about the codebase.

| Aspect | Details |
|--------|---------|
| **Location** | `runtime/query_spashta.py` |
| **Input** | `runtime/code_knowledge_graph_enriched.json` (preferred) or `code_knowledge_graph_ast.json` (fallback) |
| **Output** | Human-readable text or JSON (use `--json` for agents) |

> **Key Benefit:** Agents query facts, not guess structure.

---

## Quick Reference

| Command | Purpose | Example |
|---------|---------|---------|
| `search` | Find nodes by name/attributes | `search "login" --type Function` |
| `locate` | Get file path + line numbers | `locate "app/views.py::login"` |
| `read` | View actual source code | `read "app/views.py::login"` |
| `details` | Full node metadata | `details "app/views.py::login"` |
| `impact` | Who depends on this? | `impact "app/models.py::User" --depth 3` |
| `dependencies` | What does this use? | `dependencies "app/views.py::login"` |
| `call-graph` | Function call chains (Python) | `call-graph "app/views.py::search_page"` |
| `stats` | Graph statistics | `stats` |
| `list-files` | All indexed files | `list-files` |

**Always use `--json` for AI agent consumption:**
```bash
python query_spashta.py search "auth" --json
```

---

## Commands in Detail

### 1. `search` — Find Nodes

Find nodes by name, ID, or attributes.

**Syntax:**
```bash
python query_spashta.py search "<query>" [--type <node_type>] [--json]
```

**Search Modes:**

| Mode | Syntax | Example | Finds |
|------|--------|---------|-------|
| **Name/ID** | `"text"` | `"login"` | Nodes containing "login" |
| **By Type** | `--type X` | `--type Function` | Only Functions |
| **By Decorator** | `"decorator:X"` | `"decorator:login_required"` | Python with @login_required |
| **By HTML Tag** | `"tag:X"` | `"tag:form"` | `<form>` elements |
| **By CSS Selector** | `"pseudo_state:X"` | `"pseudo_state:hover"` | `:hover` selectors |

**Examples:**
```bash
# Find all functions named "auth"
python query_spashta.py search "auth" --type Function --json

# Find all Python functions with @login_required decorator
python query_spashta.py search "decorator:login_required" --json

# Find all HTML form elements
python query_spashta.py search "tag:form" --json

# Find all CSS :hover selectors
python query_spashta.py search "pseudo_state:hover" --json
```

**Output:**
```json
[
  {
    "id": "app/views.py::login",
    "node_type": "Function",
    "name": "login",
    "file_path": "app/views.py",
    "line_start": 45
  }
]
```

---

### 2. `locate` — Get Exact Location

Get file path and line numbers for a node.

**Syntax:**
```bash
python query_spashta.py locate "<node_id>" [--json]
```

**Example:**
```bash
python query_spashta.py locate "app/views.py::login" --json
```

**Output:**
```json
{
  "id": "app/views.py::login",
  "file": "app/views.py",
  "line_start": 45,
  "line_end": 67,
  "docstring": "Handle user login with authentication."
}
```

---

### 3. `read` — View Source Code

Read the actual source code for a node.

**Syntax:**
```bash
python query_spashta.py read "<node_id>" [--json]
```

**Example:**
```bash
python query_spashta.py read "app/views.py::login" --json
```

**Output:**
```json
{
  "content": "def login(request):\n    \"\"\"Handle user login.\"\"\"\n    if request.method == 'POST':\n        ...",
  "mode": "snippet",
  "lines": "45-67"
}
```

**Modes:**
- `snippet` — Just the function/class code (uses `line_start` to `line_end`)
- `full_file` — Entire file (when line numbers not available)

---

### 4. `details` — Full Node Metadata

Get complete node information including all attributes.

**Syntax:**
```bash
python query_spashta.py details "<node_id>" [--json]
```

**Example:**
```bash
python query_spashta.py details "app/views.py::login" --json
```

**Output:**
```json
{
  "id": "app/views.py::login",
  "node_type": "Function",
  "name": "login",
  "file_path": "app/views.py",
  "line_start": 45,
  "line_end": 67,
  "docstring": "Handle user login with authentication.",
  "semantic_role": "View",
  "signature": {
    "decorators": ["@login_required"],
    "parameters": ["request"]
  }
}
```

---

### 5. `impact` — Who Depends on This?

Analyze what code depends on a given node (incoming edges).

**Use Case:** "If I change this, what might break?"

**Syntax:**
```bash
python query_spashta.py impact "<node_id>" [--depth N] [--json]
```

**Example:**
```bash
python query_spashta.py impact "app/models.py::User" --depth 3 --json
```

**Output:**
```json
{
  "app/views.py::profile": {
    "relation": "imports",
    "depth": 1,
    "node_type": "Function"
  },
  "app/serializers.py::UserSerializer": {
    "relation": "imports",
    "depth": 1,
    "node_type": "Class"
  }
}
```

---

### 6. `dependencies` — What Does This Use?

Analyze what a node depends on (outgoing edges).

**Use Case:** "What do I need to understand to work on this?"

**Syntax:**
```bash
python query_spashta.py dependencies "<node_id>" [--depth N] [--json]
```

**Example:**
```bash
python query_spashta.py dependencies "app/views.py::login" --json
```

**Output:**
```json
{
  "app/models.py::User": {
    "relation": "imports",
    "depth": 1,
    "node_type": "Class"
  },
  "app/services.py::AuthService": {
    "relation": "calls",
    "depth": 1,
    "node_type": "Class"
  }
}
```

---

### 7. `call-graph` — Function Call Relationships

**⚠️ PYTHON ONLY** — Analyze function call chains.

**Use Case:** "If I change LLMService.generate(), what will break?"

**Syntax:**
```bash
python query_spashta.py call-graph "<node_id>" [--json]
```

**Example:**
```bash
python query_spashta.py call-graph "app/views.py::search_page" --json
```

**Output:**
```json
{
  "node_id": "app/views.py::search_page",
  "calls": [
    {
      "target": "app/services.py::SearchService.search",
      "target_name": "search",
      "target_type": "Method",
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
  "summary": {
    "outgoing_count": 1,
    "incoming_count": 1
  }
}
```

**Limitation:**
- Only tracks **internal calls** (your code → your code)
- External library calls (`json.load`, `os.path`) are NOT tracked
- Unresolved dynamic calls are logged as ambiguities

---

### 8. `stats` — Graph Statistics

Display node count, edge count, and metadata.

**Syntax:**
```bash
python query_spashta.py stats [--json]
```

**Output:**
```json
{
  "total_nodes": 1234,
  "total_edges": 5678,
  "node_types": {
    "File": 45,
    "Function": 234,
    "Class": 56,
    "Method": 189
  }
}
```

---

### 9. `list-files` — All Indexed Files

Get a list of all files indexed in the CKG.

**Syntax:**
```bash
python query_spashta.py list-files [--json]
```

**Output:**
```json
[
  "app/views.py",
  "app/models.py",
  "app/services.py",
  "templates/base.html",
  "static/css/style.css"
]
```

---

## Language-Specific Notes

| Command | Python | HTML | CSS | Notes |
|---------|--------|------|-----|-------|
| `search` | ✅ | ✅ | ✅ | Works for all node types |
| `locate` | ✅ | ✅ | ✅ | Requires `line_start` attribute |
| `read` | ✅ | ✅ | ✅ | Requires `file_path` attribute |
| `details` | ✅ | ✅ | ✅ | Works for all nodes |
| `impact` | ✅ | ✅ | ✅ | All relationship types |
| `dependencies` | ✅ | ✅ | ✅ | All relationship types |
| `call-graph` | ✅ | ❌ | ❌ | **Python only** — function calls |
| `stats` | ✅ | ✅ | ✅ | Global statistics |
| `list-files` | ✅ | ✅ | ✅ | All indexed files |

**For HTML/CSS Relationships:**
- Use `dependencies` to see what a Template uses (API calls, styles)
- Use `impact` to see what uses a StyleClass

---

## Node ID Format

Node IDs follow a consistent pattern:

| Node Type | ID Format | Example |
|-----------|-----------|---------|
| **File** | `File:<path>` | `File:app/views.py` |
| **Function** | `<file>::<name>` | `app/views.py::login` |
| **Class** | `<file>::<name>` | `app/models.py::User` |
| **Method** | `<file>::<class>.<method>` | `app/models.py::User.save` |
| **Template** | `Template:<path>` | `Template:app/templates/home.html` |
| **StyleClass** | `StyleClass:<selector>` | `StyleClass:.button` |

---

## Tips for AI Agents

### 1. Always Use `--json`
```bash
python query_spashta.py search "login" --json
```
JSON output is machine-readable and parseable.

### 2. Search → Locate → Read Workflow
```bash
# Step 1: Find the function
python query_spashta.py search "handle_payment" --type Function --json

# Step 2: Get its location
python query_spashta.py locate "app/payments.py::handle_payment" --json

# Step 3: Read the code
python query_spashta.py read "app/payments.py::handle_payment" --json
```

### 3. Impact Analysis Before Changes
```bash
# Before modifying User model, check what depends on it
python query_spashta.py impact "app/models.py::User" --depth 3 --json
```

### 4. Use Call-Graph for Refactoring
```bash
# Before renaming a function, see who calls it
python query_spashta.py call-graph "app/services.py::validate_order" --json
```

---

## Common Use Cases

| Use Case | Command |
|----------|---------|
| "Find all views" | `search "view" --type Function --json` |
| "What does login() do?" | `details "app/views.py::login" --json` |
| "Show me the code" | `read "app/views.py::login" --json` |
| "What calls this function?" | `call-graph "app/views.py::login" --json` |
| "What breaks if I change User?" | `impact "app/models.py::User" --depth 3 --json` |
| "What does this template use?" | `dependencies "Template:app/templates/home.html" --json` |
| "List all project files" | `list-files --json` |

---

## Error Handling

| Error | Meaning | Solution |
|-------|---------|----------|
| `Node not found` | Node ID doesn't exist | Use `search` first to find correct ID |
| `File not found` | Source file missing | Check `profile.json` project_root |
| `CKG not found` | No graph generated | Run `build_runtime_ast.py` first |

---

## Related Documentation

| Document | Content |
|----------|---------|
| `Runtime_Readme.md` | Execution flow and enrichment |
| `Codes_Info_Readme.md` | All runtime scripts |
| `Spashta2.0_Universal_Architecture_Readme.md` | Full architecture reference |

---

*Query Tool for Spashta-CKG — Enabling AI Agents to Query, Not Guess*
