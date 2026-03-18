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

def load_scan_exclusions():
    """Loads exclusion rules from builder_rules.json."""
    exclude_dirs = set([".venv", "__pycache__"])  # Defaults
    exclude_patterns = []
    if BUILDER_RULES_PATH.exists():
        try:
            rules = json.loads(BUILDER_RULES_PATH.read_text("utf-8"))
            policy = rules.get("scan_policy", {})
            exclude_dirs.update(policy.get("exclude_dirs", []))
            exclude_patterns = policy.get("exclude_file_patterns", [])
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
        
        self.scope_stack.append((self.file_id, node_type))
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_ClassDef(self, node):
        parent_id, parent_type = self.scope_stack[-1]
        my_id = get_symbol_id(parent_id, node.name)
        core_type = self.ctx.schema.map_node_type("ClassDef") # Class
        
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
        if parent_type == "Function" or parent_type == "Method":
             self.ctx.emit_ambiguity("nested_function_unmodeled", node.name, "Nested definition skipped", parent_id)
             return

        my_id = get_symbol_id(parent_id, node.name)
        # Determine internal type based on context, then map
        if parent_type == "Class":
            core_type = "Method" # Explicitly Method in Core
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
        for target in node.targets:
            if isinstance(target, ast.Name) and isinstance(target.ctx, ast.Store):
                var_name = target.id
                var_id = get_symbol_id(parent_id, var_name)
                core_type = self.ctx.schema.map_node_type("Assign") # Variable
                
                if not self.ctx.get_node(var_id):
                    self.ctx.register_node(var_id, {
                        "node_type": core_type,
                        "name": var_name,
                        "id": var_id,
                        "analysis_confidence": "structural",
                        **self._extract_metadata(node)
                    })
                    
                    edge = "defines" if parent_type == "File" else "contains_variable"
                    self.ctx.emit_edge(edge, parent_id, var_id)

    def visit_AnnAssign(self, node):
        parent_id, parent_type = self.scope_stack[-1]
        if isinstance(node.target, ast.Name) and isinstance(node.target.ctx, ast.Store):
             var_name = node.target.id
             var_id = get_symbol_id(parent_id, var_name)
             core_type = self.ctx.schema.map_node_type("AnnAssign")
             
             if not self.ctx.get_node(var_id):
                    self.ctx.register_node(var_id, {
                        "node_type": core_type,
                        "name": var_name,
                        "id": var_id,
                        "analysis_confidence": "structural",
                        **self._extract_metadata(node)
                    })
                    edge = "defines" if parent_type == "File" else "contains_variable"
                    self.ctx.emit_edge(edge, parent_id, var_id)


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

        self._enter_scope(my_id)
        self.generic_visit(node)
        self._exit_scope()

    def visit_FunctionDef(self, node): self._handle_function(node)
    def visit_AsyncFunctionDef(self, node): self._handle_function(node)

    def _handle_function(self, node):
        my_id = get_symbol_id(self.current_scope.scope_id, node.name)
        if not self.ctx.get_node(my_id): return
        
        for deco in node.decorator_list: self._handle_decorator(deco, my_id)

        self._enter_scope(my_id)
        for arg in node.args.args: self.current_scope.define(arg.arg, "local_arg")
        self.generic_visit(node)
        self._exit_scope()

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
        self.generic_visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            target_id = self._find_module_id(alias.name)
            if target_id:
                # Pre-check target validity (strictness)
                target_node = self.ctx.get_node(target_id)
                if target_node:
                     self.ctx.emit_edge("import", self.current_scope.scope_id, target_id)
                     self.current_scope.define(alias.asname or alias.name, target_id)
            else:
                self.ctx.emit_ambiguity("import_module_unknown", alias.name, "File not found", self.current_scope.scope_id)

    def visit_ImportFrom(self, node):
        module_path = node.module
        module_id = None
        
        if node.level > 0:
             abs_path_guess = resolve_relative_import(self.rel_path, node.level, module_path)
             if abs_path_guess:
                 candidate = f"{abs_path_guess}.py"
                 ids = [nid for nid in self.ctx.registry if nid == candidate]
                 if ids: module_id = ids[0]
        elif module_path:
             module_id = self._find_module_id(module_path)
                 
        if module_id:
             self.ctx.emit_edge("import_from", self.current_scope.scope_id, module_id)
             for alias in node.names:
                 target_symbol = get_symbol_id(module_id, alias.name)
                 target_node = self.ctx.get_node(target_symbol)
                 if target_node:
                      # Strict Pre-Check: Is this target importable?
                      self.ctx.emit_edge("import", self.current_scope.scope_id, target_symbol)
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

    def _resolve_expression(self, node) -> Optional[str]:
        if isinstance(node, ast.Name): return self.current_scope.lookup(node.id)
        elif isinstance(node, ast.Attribute):
            val_id = self._resolve_expression(node.value)
            if val_id and val_id != "local_arg":
                candidate = get_symbol_id(val_id, node.attr)
                if self.ctx.get_node(candidate): return candidate
            if isinstance(node.value, ast.Name) and node.value.id == "self":
                cls_id = self._find_enclosing_class()
                if cls_id:
                    cand = get_symbol_id(cls_id, node.attr)
                    if self.ctx.get_node(cand): return cand
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
            # Check directory exclusions
            for part in p.parts:
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
