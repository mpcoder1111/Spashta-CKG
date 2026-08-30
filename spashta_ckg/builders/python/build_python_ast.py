"""
Spashta-CKG – Python AST Builder (Strict Implementation)

AUTHORITATIVE CONTRACT: `builders/python/builder_python_instructions.json`

## Overview
This script captures the **Objective Truth** of the codebase structure. It parses Python code to generate a Knowledge Graph (Nodes & Edges) strictly based on what is statically proven.

## Data Flow & Formats
1. [Codebase] -> [AST Parser] -> [StructureWalker] -> [Registry]
2. [Registry] + [Schema] -> [RelationWalker] -> [Edges]
3. Output: code_knowledge_graph_ast.json (Nodes, Edges, Ambiguities, Meta)

## Strict Compliance & Implemented Controls
This builder strictly validates against the Spashta Core Schema, addressing previous gaps:

1.  **No Hardcoded Schema**:
    - All Node/Edge types are dynamically loaded from `core/software_schema/nodes.json` and `edges.json`.
    - Logical AST names are mapped via `python_language_mapping.json` (e.g., `inherits_from` -> `extends`).

2.  **Schema Enforcement Gates**:
    - Every edge emission is gated by `SchemaEnforcer.is_allowed(src, dst)`.
    - Violations generate `schema_violation` ambiguities instead of invalid edges.

3.  **Strict Variable Provenance**:
    - Variables are only emitted if strictly defined by AST assignments (Store context).
    - `writes_to` edges are validated against schema rules (Function -> Variable).

4.  **Import & Call Assertiveness**:
    - No "ghost" targets. If an import or call target is not found in the scanned Registry, it is an Ambiguity, not a Node.
    - Resolves relative imports and attribute chains to proven IDs only.

5.  **Standardized Confidence**:
    - All nodes use `analysis_confidence="structural"` (no "proven" drift).

6.  **Metadata**:
    - Output includes `_meta` with builder version, schema version, and timestamp.
"""

import ast
import json
import hashlib
import sys
import uuid
import argparse
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Any, Union

# ---------------------------------------------------------
# CONSTANTS & CONFIG
# ---------------------------------------------------------


# PATHS RELATIVE TO THIS SCRIPT
BUILDER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BUILDER_DIR.parent.parent

INSTRUCTIONS_PATH = BUILDER_DIR / "builder_python_instructions_for_builder_code_development.json"
MAPPING_PATH = BUILDER_DIR / "python_language_mapping.json"
CORE_EDGES_PATH = PROJECT_ROOT / "core/software_schema/edges.json"
BUILDER_RULES_PATH = BUILDER_DIR.parent / "builder_rules.json"

# ORM field constructor patterns (universal across Django, SQLAlchemy, etc.)
# Used by StructureWalker to classify assignments as Field instead of Variable.
ORM_FIELD_MODULES = {"models", "fields", "Column", "db"}
ORM_FIELD_SUFFIXES = {"Field", "Column", "Relationship", "ForeignKey", "OneToOneField",
                      "ManyToManyField", "OneToMany", "ManyToOne", "BooleanField",
                      "CharField", "TextField", "IntegerField", "FloatField",
                      "DateTimeField", "DateField", "DecimalField", "JSONField",
                      "UUIDField", "BinaryField", "FileField", "ImageField",
                      "URLField", "EmailField", "SlugField", "AutoField",
                      "BigAutoField", "SmallIntegerField", "BigIntegerField",
                      "PositiveIntegerField", "GenericForeignKey"}

# FK-like field types that reference another model
FK_FIELD_TYPES = {"ForeignKey", "OneToOneField", "ManyToManyField",
                  "ManyToOne", "OneToMany", "ForeignKeyField"}

# Known test base classes (universal)
TEST_BASE_CLASSES = {"TestCase", "TransactionTestCase", "SimpleTestCase",
                     "LiveServerTestCase", "StaticLiveServerTestCase",
                     "APITestCase", "APITransactionTestCase"}


def load_scan_exclusions():
    """Loads exclusion rules from builder_rules.json + project/profile.json."""
    exclude_dirs = set([".venv", "__pycache__"])  # Defaults

    # 1. Universal exclusions from builder_rules.json
    exclude_patterns = []
    if BUILDER_RULES_PATH.exists():
        try:
            rules = json.loads(BUILDER_RULES_PATH.read_text("utf-8"))
            policy = rules.get("scan_policy", {})
            exclude_dirs.update(policy.get("exclude_dirs", []))
            exclude_patterns = policy.get("exclude_file_patterns", [])
        except Exception:
            pass

    # 2. Project-specific exclusions from profile.json
    profile_path = PROJECT_ROOT / "project" / "profile.json"
    if profile_path.exists():
        try:
            profile = json.loads(profile_path.read_text("utf-8"))
            project_excluded = profile.get("excluded", {}).get("directories", [])
            exclude_dirs.update(project_excluded)
        except Exception:
            pass

    return exclude_dirs, exclude_patterns

# ---------------------------------------------------------
# SCHEMA ENFORCER
# ---------------------------------------------------------

class SchemaEnforcer:
    """
    Validates edge creation against the Core Schema.
    Ensures that only allowed relationships (e.g. Class -> extends -> Class) are emitted.
    """
    def __init__(self, mapping: dict, edges_schema: dict):
        # Strictness: Explicitly focus ONLY on builder-relevant sections.
        # Sections like "symbolic_reference_rules" or "literal_fragment_detection" 
        # are for Agents/Adapters and MUST be ignored by the strict builder.
        self.mapping = {
            "node_mappings": mapping.get("node_mappings", {}),
            "edge_mappings": mapping.get("edge_mappings", {})
        }
        # Config-driven URL route extraction (framework-agnostic): how each framework registers a
        # route in code. Additive; empty {} = feature off (no route extraction, graph unchanged).
        self.route_registrations = mapping.get("route_registrations", {})
        # Config-driven cross-language couplings from a call site (render()->Template, reverse()->Route,
        # HX-Trigger helper->Event). Additive; empty {} = off.
        self.call_couplings = mapping.get("call_couplings", {})
        # Config-driven URLconf include-tree extraction (include('app.urls') -> includes_urlconf File->File).
        # Additive; empty {} = off.
        self.include_registrations = mapping.get("include_registrations", {})
        # Config-driven GENERIC inline HTMX event dispatch (response['HX-Trigger'] = '<event>' /
        # json.dumps({'<event>': ...}) -> dispatches_event). Additive; empty {} = off.
        self.header_event_dispatch = mapping.get("header_event_dispatch", {})
        # Config-driven Django-layer bindings: ModelForm -> Model (uses_model) + @receiver -> Signal
        # (listens_to). Additive; empty {} = off.
        self.model_form_binding = mapping.get("model_form_binding", {})
        self.signal_receivers = mapping.get("signal_receivers", {})
        
        # Flatten edge schema for easier lookup: {edge_name: {from: [], to: []}}
        self.edge_rules = {}
        for category in edges_schema.values():
            if isinstance(category, dict):
                 # Handle nested categories like "direct_structural"
                 for k, v in category.items():
                     if isinstance(v, dict) and "from" in v: # Valid edge def
                         self.edge_rules[k] = v
                         
        self.edge_map = self.mapping.get("edge_mappings", {})
        self.node_map = self.mapping.get("node_mappings", {})

    def map_node_type(self, ast_type: str) -> str:
        """Maps AST type (FunctionDef) to Core type (Function)."""
        return self.node_map.get(ast_type, ast_type)

    def get_core_edge_type(self, logical_name: str) -> Optional[str]:
        """
        Maps logical name (contains_method) to Core name (contains_member).
        Strictness: If logical name is not in mapping, returns None (triggering ambiguity).
        """
        # Strict check: logical edge MUST be in mapping
        if logical_name not in self.edge_map:
            return None
        return self.edge_map.get(logical_name)

    def is_allowed(self, edge_type: str, src_type: str, dst_type: str) -> bool:
        """Checks if Core Schema allows this connection."""
        rule = self.edge_rules.get(edge_type)
        if not rule:
            return False # Unknown edge type
            
        allowed_src = rule.get("from", [])
        allowed_dst = rule.get("to", [])
        
        return (src_type in allowed_src) and (dst_type in allowed_dst)

# ---------------------------------------------------------
# BUILD CONTEXT
# ---------------------------------------------------------

class BuildContext:
    """
    Holds the state of the build process (Registry, Nodes, Edges).
    Acts as the central bus for submitting data.
    """
    def __init__(self, root_path: Path, instructions: dict, schema_enforcer: SchemaEnforcer):
        self.root_path = root_path
        self.instructions = instructions
        self.schema = schema_enforcer
        
        self.registry: Dict[str, Dict] = {}
        self.nodes: List[Dict] = []
        self.edges: List[Dict] = []
        self.ambiguities: List[Dict] = []
        self.logs: List[Dict] = []

    def register_node(self, node_id: str, node_data: dict):
        """Pass 1: Store confirmed nodes."""
        self.registry[node_id] = node_data
        self.nodes.append(node_data)

    def emit_edge(self, logical_edge: str, src_id: str, dst_id: str, **metadata):
        """
        Emits an edge after strict validation against Core Schema.
        1. Map logical name to Schema name.
        2. Validate Schema Allow rules.
        3. Emit or Raise Ambiguity.
        
        Optional metadata (e.g., call_line) is included in the edge.
        """
        src_node = self.registry.get(src_id)
        dst_node = self.registry.get(dst_id)
        
        if not src_node or not dst_node:
             return 

        core_edge = self.schema.get_core_edge_type(logical_edge)
        
        if not core_edge:
             self.emit_ambiguity(
                "mapping_violation",
                logical_edge,
                f"Logical edge '{logical_edge}' not found in language mapping",
                src_id,
                confidence="structural_violation"
             )
             return

        if self.schema.is_allowed(core_edge, src_node["node_type"], dst_node["node_type"]):
            edge_data = {
                "edge": core_edge,
                "from": src_id,
                "to": dst_id
            }
            # Include any additional metadata (e.g., call_line)
            edge_data.update(metadata)
            self.edges.append(edge_data)
        else:
            self.emit_ambiguity(
                "schema_violation",
                f"{logical_edge} -> {core_edge}",
                f"Edge not allowed between {src_node['node_type']} and {dst_node['node_type']}",
                src_id,
                confidence="structural_violation"
            )

    def emit_ambiguity(self, kind: str, expression: str, reason: str, scope: str, confidence: str = "unresolved"):
        """Emit structured ambiguity ticket."""
        self.ambiguities.append({
            "id": str(uuid.uuid4()),
            "kind": kind,
            "source_file": scope.split("::")[0] if "::" in scope else scope,
            "source_scope": scope,
            "expression": expression,
            "reason": reason,
            "confidence": confidence,
            "resolver": self.instructions.get("ambiguity_policy", {}).get("default_resolver", "agent")
        })

    def get_node(self, node_id: str) -> Optional[Dict]:
        return self.registry.get(node_id)


# ---------------------------------------------------------
# HELPER: ID GENERATION & PATHS
# ---------------------------------------------------------

def _is_orm_field_call(node: ast.AST) -> tuple:
    """
    Check if an AST node is an ORM field constructor call.
    Returns (is_field: bool, field_type: str, fk_target: str|None).

    Examples:
        models.CharField(max_length=100)  → (True, "CharField", None)
        models.ForeignKey(User)           → (True, "ForeignKey", "User")
        Column(String)                    → (True, "Column", None)
    """
    if not isinstance(node, ast.Call):
        return False, "", None

    func = node.func
    field_type = ""

    # Pattern 1: models.CharField(...) or models.ForeignKey(...)
    if isinstance(func, ast.Attribute):
        field_type = func.attr
    # Pattern 2: CharField(...) directly imported
    elif isinstance(func, ast.Name):
        field_type = func.id

    if not field_type:
        return False, "", None

    # Check if it matches known field patterns
    is_field = (field_type in ORM_FIELD_SUFFIXES or
                field_type.endswith("Field") or
                field_type.endswith("Column"))

    if not is_field:
        return False, "", None

    # Check for FK target (first positional arg that's a Name)
    fk_target = None
    if field_type in FK_FIELD_TYPES and node.args:
        first_arg = node.args[0]
        if isinstance(first_arg, ast.Name):
            fk_target = first_arg.id
        elif isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            fk_target = first_arg.value  # String reference like "self" or "auth.User"

    return True, field_type, fk_target


def _is_constant_name(name: str) -> bool:
    """Check if a variable name follows UPPER_CASE constant convention."""
    return (name.isupper() or
            (name == name.upper() and "_" in name and len(name) > 1))


def _is_test_class(node: ast.ClassDef) -> bool:
    """Check if a class is a test case by inheritance or naming."""
    # Check base classes
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id in TEST_BASE_CLASSES:
            return True
        if isinstance(base, ast.Attribute) and base.attr in TEST_BASE_CLASSES:
            return True
    # Check name pattern
    if node.name.startswith("Test") or node.name.endswith("Test"):
        return True
    return False


def _is_test_function(name: str, file_path: str) -> bool:
    """Check if a function is a test by name + file location."""
    if not name.startswith("test_"):
        return False
    # Must be in a test file
    fp = file_path.lower()
    return ("test_" in fp.split("/")[-1] or "/tests/" in fp or "/tests." in fp)


def get_file_id(rel_path: str) -> str:
    """unique ID for file node"""
    return rel_path.replace("\\", "/")

def get_symbol_id(parent_id: str, name: str) -> str:
    """unique ID for symbol within parent"""
    return f"{parent_id}::{name}"

def resolve_relative_import(base_file_path: str, level: int, module: Optional[str]) -> str:
    """
    Resolve relative import path.
    level 1 = ., level 2 = ..
    """
    parts = base_file_path.split("/")
    current_dir_parts = parts[:-1]
    steps_up = level - 1
    
    if steps_up > len(current_dir_parts):
        return None
        
    base_parts = current_dir_parts[:len(current_dir_parts)-steps_up]
    if module:
        base_parts.append(module.replace(".", "/"))
    return "/".join(base_parts)


# ---------------------------------------------------------
# URL ROUTE REGISTRATION (config-driven, framework-agnostic — spec/frontend-route-coupling.md)
# ---------------------------------------------------------
def _route_call_name(func) -> Optional[str]:
    if isinstance(func, ast.Attribute): return func.attr
    if isinstance(func, ast.Name): return func.id
    return None

def iter_route_registrations(module_node, regs):
    """Yield (name_literal|None, is_dynamic_name, full_name|None, view_node) for each configured
    route-registration call (Django path/re_path/url). Shared by pass 1 (register the Route node, per
    the node_classification_policy — a specialised node from a structural pattern, like Field/Constant)
    and pass 2 (resolve the view + emit resolves_to). Structural only — no semantic inference."""
    ns_vars = {c.get("namespace_var") for c in regs.values()
               if isinstance(c, dict) and c.get("namespace_var")}
    ns_values = {}
    for stmt in module_node.body:
        if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Constant) \
           and isinstance(stmt.value.value, str):
            for t in stmt.targets:
                if isinstance(t, ast.Name) and t.id in ns_vars:
                    ns_values[t.id] = stmt.value.value
    for cfg in regs.values():
        if not isinstance(cfg, dict) or "call_names" not in cfg:
            continue
        call_names = set(cfg["call_names"])
        name_kw = cfg.get("name_kwarg", "name")
        view_idx = cfg.get("view_arg_index", 1)
        ns = ns_values.get(cfg.get("namespace_var"))
        for n in ast.walk(module_node):
            if not isinstance(n, ast.Call) or _route_call_name(n.func) not in call_names:
                continue
            name_val, dynamic = None, False
            for kw in n.keywords:
                if kw.arg == name_kw:
                    if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        name_val = kw.value.value
                    else:
                        dynamic = True
            full = f"{ns}:{name_val}" if (ns and name_val) else name_val
            view_node = n.args[view_idx] if len(n.args) > view_idx else None
            yield name_val, dynamic, full, view_node


# ---------------------------------------------------------
# SYMBOL TABLE
# ---------------------------------------------------------

class SymbolTable:
    """
    Hierarchical symbol table for variable/method resolution.
    Follows Python scoping: Local -> Enclosing (Parent) -> Global (File).
    """
    def __init__(self, parent: Optional['SymbolTable'] = None, scope_id: Optional[str] = None):
        self.parent = parent
        self.scope_id = scope_id 
        self.symbols: Dict[str, str] = {} 

    def define(self, name: str, node_id: str):
        self.symbols[name] = node_id

    def lookup(self, name: str) -> Optional[str]:
        if name in self.symbols:
            return self.symbols[name]
        if self.parent:
            return self.parent.lookup(name)
        return None

# ---------------------------------------------------------
# PASS 1: STRUCTURE WALKER
# ---------------------------------------------------------

class StructureWalker(ast.NodeVisitor):
    """
    Pass 1: Traverses AST to Identify and Register Proven Definitions (Structure).
    Populates the Registry with Files, Classes, Functions, and Variables.
    """
    def __init__(self, ctx: BuildContext, rel_path: str, file_content: str):
        self.ctx = ctx
        self.rel_path = rel_path
        self.file_id = get_file_id(rel_path)
        self.file_content = file_content
        self.scope_stack: List[tuple] = [] # (id, type)

    def _extract_metadata(self, node: ast.AST) -> dict:
        """Safely extracts optional metadata (lines, docstrings)."""
        meta = {}
        
        # 1. Line Numbers
        if hasattr(node, "lineno"):
            meta["line_start"] = node.lineno
            meta["line_end"] = getattr(node, "end_lineno", node.lineno)

        # 2. Docstrings (Only for nodes with a body)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            doc = ast.get_docstring(node)
            if doc:
                meta["docstring"] = doc

        # 3. Function Signatures (Functions/Methods only)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            meta["signature"] = self._extract_signature(node)
        
        return meta

    def _extract_signature(self, node) -> dict:
        """Extracts args, return type, and decorators."""
        sig = {
            "args": [],
            "defaults": [],
            "decorators": [],
            "returns": None
        }
        
        # Args
        if node.args:
            for arg in node.args.args:
                sig["args"].append(arg.arg)
                
            # Defaults (Last n args have defaults)
            # We simplisticly capture them as string if possible
            for d in node.args.defaults:
                if isinstance(d, ast.Constant):
                    sig["defaults"].append(str(d.value))
                elif isinstance(d, ast.Name):
                    sig["defaults"].append(d.id)
                else:
                    sig["defaults"].append("<complex>")

        # Decorators
        for deco in node.decorator_list:
            if isinstance(deco, ast.Name):
                sig["decorators"].append(f"@{deco.id}")
            elif isinstance(deco, ast.Call):
                # Try to get func name of call: @foo(...)
                if isinstance(deco.func, ast.Name):
                    sig["decorators"].append(f"@{deco.func.id}(...)")
                elif isinstance(deco.func, ast.Attribute):
                     sig["decorators"].append(f"@{deco.func.attr}(...)")
                else:
                    sig["decorators"].append("@<complex_call>")
            elif isinstance(deco, ast.Attribute):
                sig["decorators"].append(f"@{deco.attr}")

        # Return Annotation
        if node.returns:
            if isinstance(node.returns, ast.Name):
                sig["returns"] = node.returns.id
            elif isinstance(node.returns, ast.Constant):
                 sig["returns"] = str(node.returns.value)
            else:
                 sig["returns"] = "<complex>"

        return sig

    def visit_Module(self, node):
        file_hash = hashlib.md5(self.file_content.encode("utf-8")).hexdigest()
        node_type = self.ctx.schema.map_node_type("Module") # Maps to File
        
        node_data = {
            "node_type": node_type, 
            "name": Path(self.rel_path).name,
            "file_path": self.rel_path,
            "id": self.file_id,
            "hash": file_hash,
            "analysis_confidence": "structural",
            **self._extract_metadata(node)
        }
        self.ctx.register_node(self.file_id, node_data)

        # Route nodes are registered HERE in pass 1 (like Field/Constant/TestCase — a specialised node
        # from a structural pattern, node_classification_policy). The resolves_to EDGE to the view is a
        # pass-2 relation. Off when route_registrations={} → no route nodes, graph unchanged.
        regs = self.ctx.schema.route_registrations
        if regs:
            for name_val, _dyn, full, _view in iter_route_registrations(node, regs):
                if not name_val:
                    continue  # dynamic / unnamed → not a node (its ambiguity is raised in pass 2)
                route_id = f"{self.file_id}::Route::{full}"
                if not self.ctx.get_node(route_id):
                    self.ctx.register_node(route_id, {"node_type": "Route", "name": full,
                                                      "id": route_id, "analysis_confidence": "structural"})

        self.scope_stack.append((self.file_id, node_type))
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_ClassDef(self, node):
        parent_id, parent_type = self.scope_stack[-1]
        my_id = get_symbol_id(parent_id, node.name)

        # Classify: TestCase or regular Class
        if _is_test_class(node):
            core_type = self.ctx.schema.map_node_type("TestClassDef")  # TestCase
        else:
            core_type = self.ctx.schema.map_node_type("ClassDef")  # Class

        node_data = {
            "node_type": core_type,
            "name": node.name,
            "id": my_id,
            "analysis_confidence": "structural",
            **self._extract_metadata(node)
        }
        self.ctx.register_node(my_id, node_data)
        
        if parent_type == "File":
            self.ctx.emit_edge("defines_class", parent_id, my_id) # Mapped to defines
        elif parent_type == "Class":
            # Nested Class
            # Strictness: 'contains_member' in schema usually allows Class -> Method/Variable.
            # If schema doesn't allow Class -> Class, this needs explicit handling.
            # We assume Nested Classes are NOT valid structural members in this strict Core.
            self.ctx.emit_ambiguity("nested_class_unmodeled", node.name, "Nested class structure not supported by core schema", parent_id, confidence="structural_violation")
            
        self.scope_stack.append((my_id, core_type))
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node):
        self._handle_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node):
        self._handle_function(node, is_async=True)

    def _handle_function(self, node, is_async):
        parent_id, parent_type = self.scope_stack[-1]

        # Strict Rule: Nested Definitions
        if parent_type in ("Function", "Method", "TestCase"):
             self.ctx.emit_ambiguity("nested_function_unmodeled", node.name, "Nested definition skipped", parent_id)
             return

        my_id = get_symbol_id(parent_id, node.name)
        # Determine internal type based on context, then map
        if parent_type == "Class":
            core_type = "Method"  # Explicitly Method in Core
        elif _is_test_function(node.name, self.rel_path) and parent_type == "File":
            core_type = self.ctx.schema.map_node_type("TestClassDef")  # TestCase (test function)
        else:
            core_type = self.ctx.schema.map_node_type("FunctionDef")

        node_data = {
            "node_type": core_type,
            "name": node.name,
            "id": my_id,
            "is_async": is_async,
            "analysis_confidence": "structural",
            **self._extract_metadata(node)
        }
        self.ctx.register_node(my_id, node_data)
        
        if parent_type == "File":
            self.ctx.emit_edge("defines_function", parent_id, my_id)
        elif parent_type == "Class":
            self.ctx.emit_edge("contains_method", parent_id, my_id)
            
        self.scope_stack.append((my_id, core_type))
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_Assign(self, node):
        parent_id, parent_type = self.scope_stack[-1]

        # Skip local variables inside functions/methods — they have no architectural value
        # and create orphan nodes. Only index File-level and Class-level assignments.
        if parent_type in ("Function", "Method", "TestCase"):
            return

        for target in node.targets:
            if isinstance(target, ast.Name) and isinstance(target.ctx, ast.Store):
                var_name = target.id
                var_id = get_symbol_id(parent_id, var_name)

                if self.ctx.get_node(var_id):
                    continue  # Already registered

                # Classify: Field, Constant, or Variable
                is_field, field_type, fk_target = _is_orm_field_call(node.value)

                if is_field and parent_type == "Class":
                    core_type = self.ctx.schema.map_node_type("FieldAssign")  # Field
                    edge_type = "has_field"
                    meta = {**self._extract_metadata(node), "field_type": field_type}
                    if fk_target:
                        meta["fk_target"] = fk_target
                elif _is_constant_name(var_name) and parent_type in ("File", "Class"):
                    core_type = self.ctx.schema.map_node_type("ConstantAssign")  # Constant
                    edge_type = "defines_constant" if parent_type == "File" else "contains_constant"
                    meta = self._extract_metadata(node)
                else:
                    core_type = self.ctx.schema.map_node_type("Assign")  # Variable
                    edge_type = "defines_variable" if parent_type == "File" else "contains_variable"
                    meta = self._extract_metadata(node)

                self.ctx.register_node(var_id, {
                    "node_type": core_type,
                    "name": var_name,
                    "id": var_id,
                    "analysis_confidence": "structural",
                    **meta
                })
                self.ctx.emit_edge(edge_type, parent_id, var_id)

    def visit_AnnAssign(self, node):
        parent_id, parent_type = self.scope_stack[-1]
        if parent_type in ("Function", "Method", "TestCase"):
            return
        if isinstance(node.target, ast.Name) and isinstance(node.target.ctx, ast.Store):
             var_name = node.target.id
             var_id = get_symbol_id(parent_id, var_name)

             if self.ctx.get_node(var_id):
                 return  # Already registered

             # Classify: Field, Constant, or Variable (same logic as visit_Assign)
             is_field, field_type, fk_target = (False, "", None)
             if node.value:
                 is_field, field_type, fk_target = _is_orm_field_call(node.value)

             if is_field and parent_type == "Class":
                 core_type = self.ctx.schema.map_node_type("FieldAssign")
                 edge_type = "has_field"
                 meta = {**self._extract_metadata(node), "field_type": field_type}
                 if fk_target:
                     meta["fk_target"] = fk_target
             elif _is_constant_name(var_name) and parent_type in ("File", "Class"):
                 core_type = self.ctx.schema.map_node_type("ConstantAssign")
                 edge_type = "defines_constant" if parent_type == "File" else "contains_constant"
                 meta = self._extract_metadata(node)
             else:
                 core_type = self.ctx.schema.map_node_type("AnnAssign")
                 edge_type = "defines_variable" if parent_type == "File" else "contains_variable"
                 meta = self._extract_metadata(node)

             self.ctx.register_node(var_id, {
                 "node_type": core_type,
                 "name": var_name,
                 "id": var_id,
                 "analysis_confidence": "structural",
                 **meta
             })
             self.ctx.emit_edge(edge_type, parent_id, var_id)


# ---------------------------------------------------------
# PASS 2: RELATION WALKER
# ---------------------------------------------------------

class RelationWalker(ast.NodeVisitor):
    """
    Pass 2: Traverses AST to Identify Relationships (Edges).
    Resolves targets using the Registry and Symbol Table to ensure "Proven" links.
    """
    def __init__(self, ctx: BuildContext, rel_path: str):
        self.ctx = ctx
        self.rel_path = rel_path
        self.file_id = get_file_id(rel_path)
        self.scope_stack: List[SymbolTable] = []
        
        root_table = SymbolTable(scope_id=self.file_id)
        self.scope_stack.append(root_table)
        
        for nid, node in self.ctx.registry.items():
            if nid.startswith(self.file_id + "::"):
                remainder = nid[len(self.file_id)+2:]
                if "::" not in remainder:
                    root_table.define(node["name"], nid)

    @property
    def current_scope(self) -> SymbolTable:
        return self.scope_stack[-1]

    def _enter_scope(self, scope_id: str):
        new_table = SymbolTable(parent=self.current_scope, scope_id=scope_id)
        self.scope_stack.append(new_table)
        for nid, node in self.ctx.registry.items():
            if nid.startswith(scope_id + "::"):
                 remainder = nid[len(scope_id)+2:]
                 if "::" not in remainder:
                     new_table.define(node["name"], nid)

    def _exit_scope(self):
        self.scope_stack.pop()

    def visit_ClassDef(self, node):
        my_id = get_symbol_id(self.current_scope.scope_id, node.name)
        if not self.ctx.get_node(my_id): return

        for deco in node.decorator_list: self._handle_decorator(deco, my_id)
        for base in node.bases: self._handle_base(base, my_id)
        self._couple_model_form(node, my_id)  # forms.ModelForm + Meta.model = X -> uses_model

        self._enter_scope(my_id)
        self.generic_visit(node)
        self._exit_scope()

    def visit_FunctionDef(self, node): self._handle_function(node)
    def visit_AsyncFunctionDef(self, node): self._handle_function(node)

    def _handle_function(self, node):
        my_id = get_symbol_id(self.current_scope.scope_id, node.name)
        if not self.ctx.get_node(my_id): return
        
        for deco in node.decorator_list: self._handle_decorator(deco, my_id)
        self._couple_signal_receiver(node, my_id)  # @receiver(SIGNAL, ...) -> listens_to (Function->Signal)

        self._enter_scope(my_id)
        for arg in node.args.args: self.current_scope.define(arg.arg, "local_arg")
        self.generic_visit(node)
        self._exit_scope()

    def _couple_model_form(self, node, class_id):
        """Config-driven form/serializer -> model binding (spec P4): a class extending a configured base
        (forms.ModelForm / DRF ModelSerializer) with a nested `class Meta: model = X` -> a `uses_model` edge
        (this Form Class -> the Model Class, resolved by name, heuristic — like the FK resolver). A
        non-literal `model` attr -> an `unresolved_model_binding` ambiguity. Structural detection (a base
        class + a nested attr), like the TestCase/Field policy. Off when model_form_binding={}."""
        cfgs = self.ctx.schema.model_form_binding
        if not cfgs:
            return
        base_names = {_route_call_name(b) for b in node.bases}
        for cfg in cfgs.values():
            if not isinstance(cfg, dict) or base_names.isdisjoint(set(cfg.get("base_classes", []))):
                continue
            meta = next((s for s in node.body
                         if isinstance(s, ast.ClassDef) and s.name == cfg.get("meta_class", "Meta")), None)
            if meta is None:
                continue
            model_attr = cfg.get("model_attr", "model")
            for stmt in meta.body:
                if not (isinstance(stmt, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == model_attr for t in stmt.targets)):
                    continue
                model_name = _route_call_name(stmt.value)  # a Name/Attribute -> the model class name
                if not model_name:
                    self.ctx.emit_ambiguity("unresolved_model_binding", ast.dump(stmt.value),
                                            "Non-name model attribute", class_id)
                    continue
                target = self._class_by_name(model_name)
                if target:
                    self.ctx.emit_edge(cfg.get("edge", "uses_model"), class_id, target)
                else:
                    self.ctx.emit_ambiguity("unresolved_model_binding", model_name,
                                            f"Model class '{model_name}' not found", class_id)

    def _couple_signal_receiver(self, node, func_id):
        """Config-driven signal receiver detection (spec P4): a function decorated `@receiver(SIGNAL, ...)`
        -> a `listens_to` edge (Function -> Signal), the Signal named by the decorator's signal arg (a
        Name/Attribute, joined to a Signal node by name at merge). A non-name signal arg -> an
        `unresolved_signal` ambiguity. Structural detection (a decorator), like the route/testcase policy.
        Off when signal_receivers={}."""
        cfgs = self.ctx.schema.signal_receivers
        if not cfgs:
            return
        for cfg in cfgs.values():
            if not isinstance(cfg, dict):
                continue
            decos = set(cfg.get("decorators", []))
            idx = cfg.get("signal_arg_index", 0)
            for deco in node.decorator_list:
                if not (isinstance(deco, ast.Call) and _route_call_name(deco.func) in decos):
                    continue
                if len(deco.args) <= idx:
                    continue
                sig_name = _route_call_name(deco.args[idx])  # Name/Attribute -> the signal name
                if not sig_name:
                    self.ctx.emit_ambiguity("unresolved_signal", ast.dump(deco.args[idx]),
                                            "Non-name signal argument to receiver", func_id)
                    continue
                self.ctx.emit_edge(cfg.get("edge", "receives_signal"), func_id,
                                   self._named_target_id(cfg.get("target", "Signal"), sig_name))

    def _class_by_name(self, name: str):
        """A registered Class node with this name (global search, heuristic) — like the FK resolver. None
        if absent (the caller emits an ambiguity)."""
        return next((nid for nid, nd in self.ctx.registry.items()
                     if nd.get("node_type") == "Class" and nd.get("name") == name), None)

    def _handle_decorator(self, deco_node, target_id):
        deco_id = self._resolve_expression(deco_node)
        if deco_id and deco_id != "local_arg":
             self.ctx.emit_edge("decorates", deco_id, target_id)
        else:
             self.ctx.emit_ambiguity("decorator_unknown", ast.dump(deco_node), "Decorator not found", target_id)

    def _handle_base(self, base_node, class_id):
        base_id = self._resolve_expression(base_node)
        if base_id and base_id != "local_arg":
             self.ctx.emit_edge("extends", class_id, base_id)
        else:
             self.ctx.emit_ambiguity("inheritance_target_unproven", ast.dump(base_node), "Base not found", class_id)

    def visit_Call(self, node):
        """Detect function calls and emit 'calls' edges with line numbers."""
        caller_id = self.current_scope.scope_id
        target_id = self._resolve_expression(node.func)
        
        # Capture the line number where the call occurs
        call_line = getattr(node, 'lineno', None)
        
        if target_id and target_id != "local_arg":
             self.ctx.emit_edge("calls", caller_id, target_id, call_line=call_line)
        else:
             self.ctx.emit_ambiguity("call_target_unknown", ast.dump(node.func), "Target not proven", caller_id)
        self._couple_call(node, caller_id)  # render()->Template, reverse()->Route, HX-Trigger->Event
        self.generic_visit(node)

    def _couple_call(self, node, caller_id):
        """Config-driven cross-language coupling: a call to a known function whose Nth arg is a LITERAL
        string → an edge from the enclosing scope to the target node (an existing node by name, e.g. a
        Route from route extraction; else a by-name reference PLACEHOLDER that joins the HTML/JS node at
        merge). A non-literal arg → an ambiguity, never a guessed edge. Off when call_couplings={}."""
        couplings = self.ctx.schema.call_couplings
        if not couplings:
            return
        fname = _route_call_name(node.func)
        if not fname:
            return
        for cfg in couplings.values():
            if not isinstance(cfg, dict) or fname not in cfg.get("calls", {}):
                continue
            idx = cfg["calls"][fname]
            if len(node.args) <= idx:
                continue
            arg = node.args[idx]
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                self.ctx.emit_ambiguity("unresolved_coupling", f"{fname}(arg{idx})",
                                        f"Non-literal argument to {fname}", caller_id)
                continue
            lit = arg.value
            self.ctx.emit_edge(cfg["edge"], caller_id, self._named_target_id(cfg["target"], lit))

    def _named_target_id(self, ttype: str, name: str) -> str:
        """An existing node of that (type, name) — e.g. a Route registered from urls.py — else a by-name
        PLACEHOLDER joined at merge (js-support §0d; a cross-builder Template/Event isn't in the Python
        registry). Confidence 'heuristic' (a name reference, not a proven local def)."""
        tid = next((nid for nid, nd in self.ctx.registry.items()
                    if nd.get("node_type") == ttype and nd.get("name") == name), None)
        if tid is None:
            tid = f"{self.file_id}::{ttype}::{name}"
            if not self.ctx.get_node(tid):
                self.ctx.register_node(tid, {"node_type": ttype, "name": name,
                                             "id": tid, "analysis_confidence": "heuristic"})
        return tid

    def _couple_header_dispatch(self, node):
        """Config-driven GENERIC inline HTMX event dispatch (spec P3): a direct response-header assignment
        `response['HX-Trigger'] = <literal>` dispatches a client-side event WITHOUT any project helper — a
        bare string (optionally comma-separated) -> one Event per name; `json.dumps({'evt': ...})` with a
        DICT LITERAL -> one Event per literal key. Emits `dispatches_event` (enclosing Function/Method ->
        Event, joined to the JS listener by name at merge). A computed value (a variable, a non-literal
        dict) -> an `unresolved_hx_trigger` ambiguity, never a guess. Off when header_event_dispatch={}."""
        cfgs = self.ctx.schema.header_event_dispatch
        if not cfgs:
            return
        caller_id = self.current_scope.scope_id
        for target in node.targets:
            if not (isinstance(target, ast.Subscript)
                    and isinstance(target.slice, ast.Constant)
                    and isinstance(target.slice.value, str)):
                continue
            header = target.slice.value
            for cfg in cfgs.values():
                if not isinstance(cfg, dict) or header not in set(cfg.get("headers", [])):
                    continue
                events = self._hx_trigger_events(node.value, cfg)
                if events is None:
                    self.ctx.emit_ambiguity("unresolved_hx_trigger", header,
                                            "Non-literal HX-Trigger header value", caller_id)
                    continue
                for evt in events:
                    self.ctx.emit_edge(cfg.get("edge", "dispatches_event"), caller_id,
                                       self._named_target_id(cfg.get("target", "Event"), evt))

    @staticmethod
    def _hx_trigger_events(value, cfg):
        """The event name(s) from an HX-Trigger header VALUE, or None if non-literal (an ambiguity). A bare
        string -> its comma-separated names; json.dumps({..}) over a DICT LITERAL -> its string-literal keys."""
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return [n.strip() for n in value.value.split(",") if n.strip()]
        if isinstance(value, ast.Call) and _route_call_name(value.func) in set(cfg.get("json_dumps_calls", [])) \
           and len(value.args) == 1 and isinstance(value.args[0], ast.Dict):
            keys = [k.value for k in value.args[0].keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            # A dict literal whose keys are all string literals is resolvable; a splat/computed key is not.
            if keys and len(keys) == len(value.args[0].keys):
                return keys
        return None

    def _resolve_includes(self, module_node):
        """Config-driven URLconf include-tree extraction: for each `include('module.path')` call in this
        urlconf, emit an `includes_urlconf` edge from THIS File to the resolved sub-URLconf File (matched by
        module path via _find_module_id, the same resolver imports use). A literal `namespace=` is carried
        as edge metadata. A non-literal module arg (a variable, or an inline `include([...])` pattern list)
        -> an `unresolved_include` ambiguity, never a guessed edge. Walked at pass-2 module level (like
        _resolve_routes) because include()/path() live in the `urlpatterns = [...]` RHS, which visit_Assign
        does not recurse into. Off when include_registrations={} (graph unchanged). Deterministic-when-
        literal — the same policy as the route/render couplings."""
        regs = self.ctx.schema.include_registrations
        if not regs:
            return
        for cfg in regs.values():
            if not isinstance(cfg, dict) or "call_names" not in cfg:
                continue
            call_names = set(cfg["call_names"])
            idx = cfg.get("module_arg_index", 0)
            ns_kw = cfg.get("namespace_kwarg", "namespace")
            edge = cfg.get("edge", "includes_urlconf")
            for n in ast.walk(module_node):
                if not isinstance(n, ast.Call) or _route_call_name(n.func) not in call_names:
                    continue
                if len(n.args) <= idx:
                    continue
                arg = n.args[idx]
                if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                    # include([...]) inline patterns or a computed module path — not a literal reference.
                    self.ctx.emit_ambiguity("unresolved_include", f"include(arg{idx})",
                                            "Non-literal module argument to include", self.file_id)
                    continue
                target_id = self._find_module_id(arg.value)
                if not target_id:
                    self.ctx.emit_ambiguity("unresolved_include", arg.value,
                                            "Included URLconf module not found", self.file_id)
                    continue
                ns = next((kw.value.value for kw in n.keywords
                           if kw.arg == ns_kw and isinstance(kw.value, ast.Constant)
                           and isinstance(kw.value.value, str)), None)
                meta = {"namespace": ns} if ns else {}
                self.ctx.emit_edge(edge, self.file_id, target_id, **meta)

    def _is_lazy_scope(self) -> bool:
        """Check if current scope is inside a function/method (lazy import)."""
        scope_node = self.ctx.get_node(self.current_scope.scope_id)
        return scope_node and scope_node.get("node_type") in ("Function", "Method")

    def visit_Import(self, node):
        is_lazy = self._is_lazy_scope()
        for alias in node.names:
            target_id = self._find_module_id(alias.name)
            if target_id:
                target_node = self.ctx.get_node(target_id)
                if target_node:
                     edge_type = "import_lazy" if is_lazy else "import"
                     self.ctx.emit_edge(edge_type, self.current_scope.scope_id, target_id,
                                        **({"lazy": True} if is_lazy else {}))
                     self.current_scope.define(alias.asname or alias.name, target_id)
            else:
                self.ctx.emit_ambiguity("import_module_unknown", alias.name, "File not found", self.current_scope.scope_id)

    def visit_ImportFrom(self, node):
        module_path = node.module
        module_id = None
        is_lazy = self._is_lazy_scope()

        if node.level > 0:
             abs_path_guess = resolve_relative_import(self.rel_path, node.level, module_path)
             if abs_path_guess:
                 candidate = f"{abs_path_guess}.py"
                 ids = [nid for nid in self.ctx.registry if nid == candidate]
                 if ids: module_id = ids[0]
        elif module_path:
             module_id = self._find_module_id(module_path)
                 
        if module_id:
             lazy_meta = {"lazy": True} if is_lazy else {}
             edge_type = "import_lazy" if is_lazy else "import_from"
             self.ctx.emit_edge(edge_type, self.current_scope.scope_id, module_id, **lazy_meta)
             for alias in node.names:
                 target_symbol = get_symbol_id(module_id, alias.name)
                 target_node = self.ctx.get_node(target_symbol)
                 if target_node:
                      symbol_edge = "import_lazy" if is_lazy else "import"
                      self.ctx.emit_edge(symbol_edge, self.current_scope.scope_id, target_symbol, **lazy_meta)
                      self.current_scope.define(alias.asname or alias.name, target_symbol)
                 else:
                      self.ctx.emit_ambiguity("import_symbol_type_unknown", alias.name, "Symbol missing in target", self.current_scope.scope_id)
        else:
             self.ctx.emit_ambiguity("import_module_unknown", str(module_path), "Module not found", self.current_scope.scope_id)

    def visit_Assign(self, node):
        parent_id = self.current_scope.scope_id
        for target in node.targets:
            if isinstance(target, ast.Name):
                # Resolve target to see if it's a known Variable (Global or Class member)
                resolved = self.current_scope.lookup(target.id)
                if resolved and resolved != "local_arg":
                     var_node = self.ctx.get_node(resolved)
                     if var_node and var_node["node_type"] == "Variable":
                         self.ctx.emit_edge("writes_to", parent_id, resolved)
        self._couple_header_dispatch(node)  # response['HX-Trigger'] = '<event>' -> dispatches_event

    def _resolve_expression(self, node) -> Optional[str]:
        if isinstance(node, ast.Name): return self.current_scope.lookup(node.id)
        elif isinstance(node, ast.Attribute):
            val_id = self._resolve_expression(node.value)
            if val_id and val_id != "local_arg":
                candidate = get_symbol_id(val_id, node.attr)
                if self.ctx.get_node(candidate): return candidate
            # Self-method resolution: self.X() → EnclosingClass::X
            if isinstance(node.value, ast.Name) and node.value.id == "self":
                cls_id = self._find_enclosing_class()
                if cls_id:
                    cand = get_symbol_id(cls_id, node.attr)
                    if self.ctx.get_node(cand): return cand
            # Super-method resolution: super().X() → parent class via extends
            if isinstance(node.value, ast.Call):
                func = node.value.func
                if isinstance(func, ast.Name) and func.id == "super":
                    cls_id = self._find_enclosing_class()
                    if cls_id:
                        # Find parent class via extends edges
                        for edge in self.ctx.edges:
                            if edge.get("from") == cls_id and edge.get("edge") == "extends":
                                parent_cand = get_symbol_id(edge["to"], node.attr)
                                if self.ctx.get_node(parent_cand): return parent_cand
        return None

    def _find_module_id(self, name: str) -> Optional[str]:
        guess = name.replace(".", "/") + ".py"
        for nid in self.ctx.registry:
             if nid == guess or nid.endswith("/" + guess): return nid
        return None
        
    def _find_enclosing_class(self) -> Optional[str]:
        for i in range(len(self.scope_stack)-1, -1, -1):
             node = self.ctx.get_node(self.scope_stack[i].scope_id)
             if node and node["node_type"] == "Class": return self.scope_stack[i].scope_id
        return None

    # ── URL route extraction (config-driven, framework-agnostic — spec/frontend-route-coupling.md) ──
    # A Route(url-name) node + a resolves_to edge to the view it maps to, so a template's calls_api
    # placeholder (hx-get="{% url 'name' %}") joins BY NAME to the view. Additive: fires ONLY for a
    # configured route-registration call (route_registrations={} → off, graph unchanged).
    def visit_Module(self, node):
        # Pass-2 traversal FIRST (defines the symbol table so imports resolve the view), THEN the
        # resolves_to EDGES. The Route NODES were registered in pass 1 (StructureWalker).
        self.generic_visit(node)
        self._resolve_routes(node)
        self._resolve_includes(node)  # include('app.urls') -> includes_urlconf (File->File)

    def _module_import_map(self, module_node) -> dict:
        """alias -> "pkg/path/mod.py" for `from pkg import mod [as alias]` / `import pkg.mod`, so a
        view ref like `views.foo` (a package-submodule import the symbol table doesn't resolve) can be
        landed on its real file id."""
        imports = {}
        for stmt in module_node.body:
            if isinstance(stmt, ast.ImportFrom) and stmt.module and stmt.level == 0:
                pkg = stmt.module.replace(".", "/")
                for a in stmt.names:
                    imports[a.asname or a.name] = f"{pkg}/{a.name}.py"
            elif isinstance(stmt, ast.Import):
                for a in stmt.names:
                    imports[a.asname or a.name] = a.name.replace(".", "/") + ".py"
        return imports

    def _resolve_view(self, view_node, imports):
        """Return (view_node_id, confidence) or (None, None). `confidence` is 'structural' for a PROVEN
        resolution (import-map file match / the builder's symbol table) and 'heuristic' for a
        one-or-none (app, unique-name) match (name-based inference — heuristic_policy)."""
        # CBV: MyView.as_view() → resolve the RECEIVER MyView (a Class); works for views.MyView too.
        if isinstance(view_node, ast.Call) and isinstance(view_node.func, ast.Attribute) \
           and view_node.func.attr == "as_view":
            view_node = view_node.func.value
        # The attribute/name being called as the view (views.foo → 'foo'; a bare `foo` → 'foo').
        attr = None
        if isinstance(view_node, ast.Attribute) and isinstance(view_node.value, ast.Name):
            attr = view_node.attr
            # MODULE.attr resolved via the import map (PROVEN file) → module.py::attr.
            modfile = imports.get(view_node.value.id)
            if modfile and self.ctx.get_node(f"{modfile}::{attr}"):
                return f"{modfile}::{attr}", "structural"
        elif isinstance(view_node, ast.Name):
            attr = view_node.id
        # (app, unique-name), one-or-none HEURISTIC: an app's urls.py references its OWN app's views
        # (Django convention). (a) the import module's app, then (b) THIS urls.py's app — the latter
        # covers a decomposed views/ PACKAGE (re-exported def), a relative `from . import views`, and any
        # import the map can't prove. Deterministic (>1 candidate → skip), reproducible; never a guess.
        if attr:
            candidate_apps = []
            if isinstance(view_node, ast.Attribute) and isinstance(view_node.value, ast.Name):
                mf = imports.get(view_node.value.id)  # module.attr → the import module's app
            else:
                mf = imports.get(attr)  # bare `from app.views import name` → that app (import map keys it)
            if mf:
                candidate_apps.append(mf.split("/")[0])
            candidate_apps.append(self.file_id.split("/")[0])  # this urls.py's own app
            for app in dict.fromkeys(candidate_apps):
                hits = [nid for nid, nd in self.ctx.registry.items()
                        if nid.startswith(app + "/") and nd.get("name") == attr
                        and nd.get("node_type") in ("Function", "Method", "Class")]
                if len(hits) == 1:
                    return hits[0], "heuristic"
        # Last resort: the builder's own resolution (a same-module def, a PROVEN direct import).
        rid = self._resolve_expression(view_node)
        return (rid, "structural") if rid and rid != "local_arg" else (None, None)

    def _resolve_routes(self, module_node):
        """Pass 2: resolve each route's VIEW and emit the resolves_to EDGE (the Route node exists from
        pass 1). Dynamic url-name / unproven view → an ambiguity, never a guessed edge."""
        regs = self.ctx.schema.route_registrations
        if not regs:
            return
        imports = self._module_import_map(module_node)
        for name_val, dynamic, full, view_node in iter_route_registrations(module_node, regs):
            if dynamic:
                self.ctx.emit_ambiguity("unresolved_route", "name=<non-literal>",
                                        "Dynamic url-name (not a literal)", self.file_id)
            if not name_val:
                continue
            route_id = f"{self.file_id}::Route::{full}"  # registered in pass 1
            if view_node is None:
                continue
            view_id, confidence = self._resolve_view(view_node, imports)
            if view_id:
                self.ctx.emit_edge("resolves_to", route_id, view_id, confidence=confidence)
            else:  # a string-path view / an unproven CBV / a lambda → ambiguity, not a guess
                self.ctx.emit_ambiguity("unresolved_route_view", ast.dump(view_node),
                                        f"View for route '{full}' not proven", route_id)


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", default=".")
    parser.add_argument("--out", default="runtime/output.json")
    args = parser.parse_args()
    
    root = Path(args.source_root).resolve()
    
    try:
        instr = json.loads(INSTRUCTIONS_PATH.read_text("utf-8"))
        mapping = json.loads(MAPPING_PATH.read_text("utf-8"))
        edges_schema = json.loads(CORE_EDGES_PATH.read_text("utf-8"))
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)
    
    enforcer = SchemaEnforcer(mapping, edges_schema)
    
    # SCAN FILES (Support Single File or Directory)
    if root.is_file():
        # Case: Unit Test or Single File Scan
        root_dir = root.parent
        py_files = [root]
    else:
        # Case: Project Scan
        root_dir = root
        exclude_dirs, exclude_patterns = load_scan_exclusions()
        
        def should_include(p):
            # Check directory exclusions relative to root
            try:
                rel_parts = p.relative_to(root_dir).parts[:-1]
            except Exception:
                rel_parts = p.parts[:-1]
            for part in rel_parts:
                if part in exclude_dirs:
                    return False
            # Check file pattern exclusions
            import fnmatch
            for pattern in exclude_patterns:
                if fnmatch.fnmatch(p.name, pattern):
                    return False
            return True
        
        py_files = sorted([p for p in root.rglob("*.py") if should_include(p)])

    ctx = BuildContext(root_dir, instr, enforcer)
    
    print(f"Scanning {len(py_files)} files...")
    
    for p in py_files:
        try:
            rel = p.relative_to(root_dir).as_posix()
            content = p.read_text("utf-8")
            StructureWalker(ctx, rel, content).visit(ast.parse(content))
        except Exception as e: ctx.logs.append({"error": str(e), "file": str(p)})
            
    for p in py_files:
        try:
            rel = p.relative_to(root_dir).as_posix()
            RelationWalker(ctx, rel).visit(ast.parse(p.read_text("utf-8")))
        except Exception as e: ctx.logs.append({"error_pass2": str(e), "file": str(p)})

    # ── Pass 3: Post-processing (FK references) ──────────
    # Field nodes with fk_target metadata → emit references edge to target Class
    for node_data in ctx.nodes:
        if node_data.get("node_type") == "Field" and node_data.get("fk_target"):
            fk_target_name = node_data["fk_target"]
            field_id = node_data["id"]
            # Find the owning class (parent in the ID path)
            parts = field_id.rsplit("::", 1)
            owner_id = parts[0] if len(parts) > 1 else None
            owner_node = ctx.get_node(owner_id) if owner_id else None

            if owner_node and owner_node.get("node_type") == "Class":
                # Resolve fk_target to a Class node in registry
                # Try: same file (ClassName), or full search
                target_class_id = None
                # 1. Same-file lookup
                file_id = owner_id.split("::")[0] if "::" in owner_id else owner_id
                candidate = get_symbol_id(file_id, fk_target_name)
                if ctx.get_node(candidate) and ctx.get_node(candidate).get("node_type") == "Class":
                    target_class_id = candidate
                else:
                    # 2. Global search (any Class with that name)
                    for nid, ndata in ctx.registry.items():
                        if ndata.get("node_type") == "Class" and ndata.get("name") == fk_target_name:
                            target_class_id = nid
                            break

                if target_class_id:
                    ctx.emit_edge("references_model", owner_id, target_class_id,
                                  via_field=node_data["name"],
                                  field_type=node_data.get("field_type", ""))
                else:
                    ctx.emit_ambiguity("fk_target_unresolved", fk_target_name,
                                       f"ForeignKey target class '{fk_target_name}' not found in registry",
                                       field_id)

    out_data = {
        "_meta": {
            "builder": "build_python_ast.py",
            "builder_version": instr.get("builder_identity", {}).get("version", "unknown"),
            "schema_version": mapping.get("_meta", {}).get("supported_core_schema", "unknown"),
            "generated_at": datetime.datetime.now().isoformat()
        },
        "nodes": ctx.nodes,
        "edges": ctx.edges,
        "ambiguities": ctx.ambiguities,
        "logs": ctx.logs
    }
    
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_data, indent=2), encoding="utf-8")
    print(f"Done. {len(ctx.nodes)} nodes, {len(ctx.edges)} edges.")

if __name__ == "__main__":
    main()
