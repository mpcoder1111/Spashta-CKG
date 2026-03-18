# Spashta-CKG Adapters - Complete Reference

> **"Adapters add framework meaning to structural facts."**

This document consolidates all adapter documentation for Spashta-CKG.

---

## Table of Contents

1. [Role in Architecture](#1-role-in-architecture)
2. [How Adapters Work](#2-how-adapters-work)
3. [Framework Mapping](#3-framework-mapping)
4. [Django Adapter](#4-django-adapter)
5. [FastAPI Adapter](#5-fastapi-adapter)
6. [HTMX Adapter](#6-htmx-adapter)
7. [Creating New Adapters](#7-creating-new-adapters)
8. [Anti-Patterns](#8-anti-patterns)

---

## 1. Role in Architecture

Adapters are the **Semantic Layer**. They explain *Framework Meaning* on top of *Language Structure*.

**Adapters are NOT runtime modules.** They are declarative mapping layers.

```
┌─────────────────────────────────────────────────────────────┐
│                    AI AGENT (Consumer)                      │
├─────────────────────────────────────────────────────────────┤
│                    ADAPTERS (Semantic)                      │
│   Django │ FastAPI │ HTMX │ (extensible)                    │
├─────────────────────────────────────────────────────────────┤
│                    BUILDERS (Structural)                    │
│   Python │ HTML │ CSS │ (extensible)                        │
├─────────────────────────────────────────────────────────────┤
│                    CORE SCHEMA (Universal)                  │
│   nodes.json │ edges.json                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. How Adapters Work

| User | Role | How They Use Adapters |
|------|------|----------------------|
| **Runtime** | Primary User | Applies `framework_mapping.json` to enrich CKG |
| **AI Agent** | Consumer | Reads semantic roles from enriched CKG |
| **Coder** | Author | Creates/modifies `framework_mapping.json` |

### The Core File: `framework_mapping.json`

Each adapter contains a single mapping file that defines:
- **Detection rules**: How to identify framework constructs (decorators, inheritance, function calls)
- **Semantic roles**: What role a node plays in the framework (View, DataModel, Template, etc.)

---

## 3. Framework Mapping

### How It Works

The `framework_mapping.json` file maps **structural patterns** to **semantic roles**.

**Example (Django):**
```json
{
  "Function": {
    "semantic_role": "View",
    "detection": {
      "has_argument": "request",
      "calls": ["render", "redirect", "HttpResponse"]
    }
  },
  "Class": {
    "semantic_role": "DataModel",
    "detection": {
      "inherits": "models.Model"
    }
  }
}
```

### What This Means:
- A `Function` with a `request` argument that calls `render()` → labeled as **View**
- A `Class` inheriting from `models.Model` → labeled as **DataModel**

---

## 4. Django Adapter

**Location**: `adapters/django/framework_mapping.json`

### Design Philosophy
> **"Django follows strict MVT (Model-View-Template) separation. This adapter identifies each layer."**

### Semantic Mappings

| Django Construct | Core Node | Semantic Role | Detection |
|------------------|-----------|---------------|-----------|
| Function-Based View | `Function` | `View` | Has `request` arg + calls `render()` |
| Class-Based View | `Class` | `View` | Inherits from `View`, `TemplateView`, etc. |
| Model | `Class` | `DataModel` | Inherits from `models.Model` |
| Template | `File` | `Template` | `.html` file in `templates/` directory |
| Form | `Class` | `FormHandler` | Inherits from `forms.Form` or `ModelForm` |
| Admin | `Class` | `AdminConfig` | Inherits from `admin.ModelAdmin` |

### Status
- [x] Framework Mapping complete

---

## 5. FastAPI Adapter

**Location**: `adapters/fastapi/framework_mapping.json`

### Design Philosophy
> **"FastAPI relies on Types (Pydantic) and Path Operations. We distinguish Schema (Contract) from Logic (View)."**

### Semantic Mappings

| FastAPI Construct | Core Node | Semantic Role | Detection |
|-------------------|-----------|---------------|-----------|
| Path Operation | `Function` | `View` | Decorated with `@app.get`, `@app.post`, etc. |
| Pydantic Model | `Class` | `APIContract` | Inherits from `BaseModel` |
| SQLModel | `Class` | `DataModel` | Inherits from `SQLModel` |
| Dependency | `Function` | `Dependency` | Used in `Depends(...)` |

### Status
- [x] Framework Mapping complete

---

## 6. HTMX Adapter

**Location**: `adapters/htmx/framework_mapping.json`

### Design Philosophy
> **"HTMX is a UI interaction protocol. It describes intent (Trigger → Request → Swap) declaratively within templates."**

### What This Adapter Does
- Identifies templates with HTMX attributes (`hx-get`, `hx-post`, `hx-target`, etc.)
- Adds `HTMXInteraction` semantic role to templates
- Does NOT execute or simulate HTMX behavior

### Semantic Mappings

| HTMX Construct | Core Node | Semantic Role | Detection |
|----------------|-----------|---------------|-----------|
| Template with hx-get | `Template` | `HTMXInteraction` | Contains `hx-get` attribute |
| Template with hx-post | `Template` | `HTMXInteraction` | Contains `hx-post` attribute |
| Template with hx-target | `Template` | `HTMXInteraction` | Contains `hx-target` attribute |

### Status
- [x] Framework Mapping complete

---

## 7. Creating New Adapters

### Step 1: Create Framework Directory

```
adapters/
└── your_framework/
    └── framework_mapping.json
```

### Step 2: Define Semantic Mappings

Create `framework_mapping.json` with this structure:

```json
{
  "_meta": {
    "framework": "your_framework",
    "version": "1.0",
    "description": "Semantic mappings for Your Framework"
  },
  "mappings": [
    {
      "node_type": "Function",
      "semantic_role": "Controller",
      "detection": {
        "decorated_by": ["@route", "@get", "@post"],
        "has_argument": "request"
      }
    },
    {
      "node_type": "Class",
      "semantic_role": "DataModel",
      "detection": {
        "inherits": ["BaseModel", "Entity"]
      }
    }
  ]
}
```

### Step 3: Register in Profile

Add your framework to `project/profile.json`:

```json
{
  "frameworks": ["your_framework"]
}
```

### Detection Rules Available

| Rule | Description | Example |
|------|-------------|---------|
| `decorated_by` | Function has specific decorators | `["@app.get", "@route"]` |
| `inherits` | Class inherits from specific base | `"models.Model"` |
| `has_argument` | Function has specific argument | `"request"` |
| `calls` | Function calls specific methods | `["render", "redirect"]` |
| `file_pattern` | File matches pattern | `"**/views.py"` |
| `contains_attribute` | Template has attribute | `"hx-get"` |

---

## 8. Anti-Patterns

### DO NOT:
- ❌ Parse Python or HTML in adapters (Builders do that)
- ❌ Mutate the core graph structure (only add semantic metadata)
- ❌ Invent new Node Types (use Semantic Roles instead)
- ❌ Add execution logic (adapters are declarative)

### DO:
- ✅ Map framework patterns to semantic roles
- ✅ Use detection rules based on structural patterns
- ✅ Keep mappings simple and deterministic
- ✅ Document your detection logic

---

## Directory Structure (Simplified)

```
adapters/
├── django/
│   └── framework_mapping.json    # Django semantic mappings
│
├── fastapi/
│   └── framework_mapping.json    # FastAPI semantic mappings
│
└── htmx/
    └── framework_mapping.json    # HTMX semantic mappings
```

---

*Last Updated: 2025-12-30*
