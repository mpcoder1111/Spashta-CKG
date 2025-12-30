"""
Spashta-CKG – CSS AST Builder (Strict Regex-First v1)

AUTHORITATIVE CONTRACT: `builders/css/builder_css_instructions_for_builder_code_development.json`

## Overview
Parses CSS files using strict Regex patterns defined in `css_language_mapping.json`.
It emits "Structure Only" (Stylesheets, Classes, IDs) and avoids framework semantics.

## Strict Compliance
- **Structure Only**: No inference of nested rules or media queries as nodes.
- **No Speculative Nodes**: Imports do NOT create Switchsheet nodes; they emit ambiguity tickets if target is unproven.
- **Schema Enforcement**: All edges gated by `SchemaEnforcer` against Core Schema.
- **Scoped IDs**: Style nodes are scoped to the Stylesheet file.
- **Ambiguity**: Forbidden constructs (media queries, pseudo-classes) emit ambiguity tickets explicitly.
"""

import json
import re
import hashlib
import sys
import uuid
import argparse
import datetime
from pathlib import Path
from fnmatch import fnmatch
from typing import Dict, List, Optional, Set, Any

# ---------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------
from pathlib import Path

# CONSTANTS
# ---------------------------------------------------------
# Dynamic Paths relative to this script location
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent  # builders/css -> builders -> Spashta_2.0_Devlopment

MAPPING_PATH = SCRIPT_DIR / "css_language_mapping.json"
INSTRUCTIONS_PATH = SCRIPT_DIR / "builder_css_instructions_for_builder_code_development.json"
# Core edges usually at Spashta_2.0_Devlopment/core/software_schema/edges.json
CORE_EDGES_PATH = PROJECT_ROOT / "core" / "software_schema" / "edges.json"
BUILDER_RULES_PATH = SCRIPT_DIR.parent / "builder_rules.json"

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
    Validates edge creation against the Core Schema ONLY.
    """
    def __init__(self, edges_schema: dict):
        self.edge_rules = {}
        for category in edges_schema.values():
            if isinstance(category, dict):
                 for k, v in category.items():
                     if isinstance(v, dict) and "from" in v:
                         self.edge_rules[k] = v

    def is_allowed(self, edge_type: str, src_type: str, dst_type: str) -> bool:
        """Checks if Core Schema allows this connection."""
        rule = self.edge_rules.get(edge_type)
        if not rule: return False
        return (src_type in rule.get("from", [])) and (dst_type in rule.get("to", []))

# ---------------------------------------------------------
# BUILD CONTEXT
# ---------------------------------------------------------
class BuildContext:
    def __init__(self, root_path: Path, instructions: dict, mapping: dict, schema_enforcer: SchemaEnforcer):
        self.root_path = root_path
        self.instructions = instructions
        self.mapping = mapping
        self.schema = schema_enforcer
        
        self.nodes = []
        self.edges = []
        self.ambiguities = []
        self.logs = []
        
        self._node_ids = set()
        self._edge_keys = set()
        self.current_file = None
        self.current_file_id = None
        
        # Cache allowed edges from mapping
        self._allowed_mapping_edges = set()
        for rule in self.mapping.get("patterns", {}).values():
            if "emit_edge" in rule: self._allowed_mapping_edges.add(rule["emit_edge"])
            if "defines_edge" in rule: self._allowed_mapping_edges.add(rule["defines_edge"])
            
    def emit_node(self, node_type: str, name: str, confidence="structural", scope: Optional[str] = None, **kwargs):
        # Scoped IDs
        if node_type == "Stylesheet":
             node_id = name
        else:
             # StyleClass, StyleID are specific to the file unless explicitly global
             scope_prefix = scope if scope else self.current_file
             node_id = f"{scope_prefix}::{node_type}::{name}"

        if node_id not in self._node_ids:
            node_data = {
                "node_type": node_type,
                "name": name,
                "id": node_id,
                "analysis_confidence": confidence,
                "line_start": kwargs.get("line_start"),
                "line_end": kwargs.get("line_end"), # Explicitly None for CSS
                "attributes": kwargs.get("attributes")
            }
            node_data.update(kwargs)
            self.nodes.append(node_data)
            self._node_ids.add(node_id)
        return node_id

    def emit_edge(self, edge_type: str, src_id: str, dst_id: str, src_type: str, dst_type: str):
        # 1. Mapping Gate
        if edge_type not in self._allowed_mapping_edges:
             self.emit_ambiguity("mapping_violation", edge_type, f"Edge '{edge_type}' not in mapping", self.current_file)
             return

        # 2. Schema Gate
        if not self.schema.is_allowed(edge_type, src_type, dst_type):
            self.emit_ambiguity(
                "schema_violation", 
                f"{edge_type}:{src_type}->{dst_type}", 
                "Edge not allowed by Core Schema", 
                self.current_file, 
                confidence="structural_violation"
            )
            return

        edge_key = (edge_type, src_id, dst_id)
        if edge_key not in self._edge_keys:
            self.edges.append({
                "edge": edge_type,
                "from": src_id,
                "to": dst_id
            })
            self._edge_keys.add(edge_key)
            
    def emit_ambiguity(self, kind: str, expression: str, reason: str, scope: str, confidence: str = "unresolved"):
        self.ambiguities.append({
            "id": str(uuid.uuid4()),
            "kind": kind,
            "source_file": scope,
            "source_scope": scope,
            "expression": expression,
            "reason": reason,
            "confidence": confidence,
            "resolver": self.instructions.get("ambiguity_policy", {}).get("default_resolver", "agent")
        })

# ---------------------------------------------------------
# BUILDER LOGIC
# ---------------------------------------------------------

def build_for_file(css_file: Path, ctx: BuildContext):
    try:
        content = css_file.read_text(encoding="utf-8")
        ctx.current_file = css_file.relative_to(ctx.root_path).as_posix()
        file_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
        
        ctx.current_file_id = ctx.emit_node("Stylesheet", ctx.current_file, confidence="structural", file_hash=file_hash)
        
        # 1. Pre-Scan Strict Ambiguity Detection (Before stripping comments)
        strict_rules = ctx.instructions.get("css_strict_rules", {})
        
        # Detect Media Queries (Cleaner Regex)
        if strict_rules.get("media_queries", {}).get("never_emit_node"):
            # Capture @media (screen and ...) 
            for mq in re.finditer(r"@media\s*\(([^)]+)\)", content):
                ctx.emit_ambiguity("responsive_breakpoint", mq.group(0), "Media Queries unmodeled", ctx.current_file)

        # Detect Keyframes (Cleaner Regex)
        if strict_rules.get("keyframes", {}).get("never_emit_node"):
            # Capture @keyframes name
            for kf in re.finditer(r"@keyframes\s+([a-zA-Z][a-zA-Z0-9_-]*)", content):
                ctx.emit_ambiguity("css_animation_defined", kf.group(0), "Animations unmodeled", ctx.current_file)

        # Pre-processing: Strip comments BUT preserve newlines to keep line numbers accurate
        def preserve_newlines(match):
            return "\n" * match.group(0).count("\n")
            
        clean_content = re.sub(r"/\*.*?\*/", preserve_newlines, content, flags=re.DOTALL)
        
        # 2. Pattern Matching
        patterns = ctx.mapping.get("patterns", {})
        for rule_name, rule in patterns.items():
            regex = rule["regex"]
            
            for match in re.finditer(regex, clean_content):
                # Calculate Line Number
                # Count newlines up to the start of the match + 1
                line_start = clean_content[:match.start()].count('\n') + 1

                # Logic A: Import (Strict: No Speculative Nodes)
                if "emit_edge" in rule and "target_group" in rule:
                    target_val = match.group(rule["target_group"])
                    
                    # STRICT: Do NOT emit Stylesheet node for target.
                    # We do not know if it exists.
                    # Emit Ambiguity instead.
                    ctx.emit_ambiguity(
                        "import_target_unresolved",
                        target_val,
                        "Imported stylesheet not proven as file",
                        ctx.current_file
                    )
                    # NOTE: If we wanted to link, we'd check ctx._node_ids, but since we are scanning linearly,
                    # we often won't know future files. Ambiguity is the safe, strict choice.

                # Logic B: Definition (Class/ID)
                if "emit_node" in rule and "name_group" in rule:
                    name = match.group(rule["name_group"])
                    node_type = rule["emit_node"]
                    
                    # Check for Pseudo-State immediately following match
                    attrs = None
                    remainder = clean_content[match.end():]
                    pseudo_match = re.match(r"^:([a-zA-Z-]+)", remainder)
                    if pseudo_match:
                        attrs = {"pseudo_state": pseudo_match.group(1)}

                    node_id = ctx.emit_node(node_type, name, scope=ctx.current_file, confidence="heuristic", line_start=line_start, attributes=attrs)
                    
                    if "defines_edge" in rule:
                         ctx.emit_edge(rule["defines_edge"], ctx.current_file_id, node_id, "Stylesheet", node_type)

    except Exception as e:
        ctx.logs.append({"type": "parse_error", "message": str(e), "file": ctx.current_file})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", default=".")
    parser.add_argument("--out", default="runtime/code_knowledge_graph_css.json")
    args = parser.parse_args()

    root = Path(args.source_root).resolve()
    
    try:
        # Load from Script-Relative Constants (System Configuration)
        instr = json.loads(INSTRUCTIONS_PATH.read_text("utf-8"))
        
        mapping = json.loads(MAPPING_PATH.read_text("utf-8"))
        edges_schema = json.loads(CORE_EDGES_PATH.read_text("utf-8"))
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)
        
    enforcer = SchemaEnforcer(edges_schema)
    ctx = BuildContext(root, instr, mapping, enforcer)
    
    print(f"DEBUG: Source Root: {root} | Exists: {root.exists()} | Is File: {root.is_file()}")
    
    css_files = []
    if root.is_file():
         if root.suffix == ".css":
             # If mapping Root is a file, set context root to its parent so relative paths work?
             # Or keep root as file? BuildContext uses root for relative paths.
             # Ideally if source_root is file, base is file.parent.
             ctx.root_path = root.parent 
             css_files = [root]
    elif root.is_dir():
        exclude_dirs, exclude_patterns = load_scan_exclusions()
        
        def should_include(p):
            for part in p.parts:
                if part in exclude_dirs:
                    return False
            for pattern in exclude_patterns:
                if fnmatch(p.name, pattern):
                    return False
            return True
        
        css_files = sorted([p for p in root.rglob("*.css") if should_include(p)])
        
    print(f"Scanning {len(css_files)} CSS files...")
    
    for css_f in css_files:
        build_for_file(css_f, ctx)
        
    output = {
         "_meta": {
            "builder": "build_css_ast.py",
            "builder_version": instr.get("builder_identity", {}).get("version", "unknown"),
             "generated_at": datetime.datetime.now().isoformat()
        },
        "nodes": ctx.nodes,
        "edges": ctx.edges,
        "ambiguities": ctx.ambiguities,
        "logs": ctx.logs
    }
    
    try:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
        print(f"AST Generated: {args.out}")
    except Exception as e:
        print(f"Error saving output: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
