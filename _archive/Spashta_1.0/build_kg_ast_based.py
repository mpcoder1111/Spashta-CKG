# Copyright 2025 mpcoder1111
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Script: Code Knowledge Graph Builder (build_kg_ast_based.py)
Version: 1.0

Purpose:
    This script programmatically analyzes the current codebase to generate a 
    Code Knowledge Graph (CKG) in JSON format.
    
    ROLE: OBJECTIVE TRUTH GENERATOR
    - It captures the "Body" of the code (Syntax, Structure, Imports).
    - It generates the 'code_knowledge_graph_AST_based.json'.
    - Agents should trust this file for structural validation (e.g., "Does file A import file B?").

How it Works (Q1 & Q2):
    1. Static Analysis: It uses Python's `ast` (Abstract Syntax Tree) module to parse 
       source code without executing it. This makes it safe and fully programmatic.
    2. Dynamic Discovery: It crawls the project directory to find all relevant .py files, 
       minimizing the gap between the actual codebase and the KG.
    3. Self-Awareness: The CKG includes this script (`build_kg_ast_based.py`) and other metadata tools 
       within itself, classified under the "Meta-Tooling" layer.
    4. Output: Generates `Spashta-CKG/code_knowledge_graph_AST_based.json`, a structured JSON file 
       containing metadata about files, classes, functions, inputs, and their relationships.

Usage (Q3):
    The CKG generation is a two-step process:
    
    1. Structure Generation (This Script):
       $ python Spashta-CKG/build_kg_ast_based.py
       - Scans code, builds structure, and writes `code_knowledge_graph_AST_based.json`.
       
    2. Semantic Enrichment (AI Agent Task):
       - The AI Agent reads the AST-based JSON.
       - Checks for drift (Rule 3).
       - Updates `code_knowledge_graph_AST_Enriched_by_AI.json` with semantic metadata.
       - STRICT RULE: Agent must verify new nodes and flip status to "fully_enriched".

    It should be run whenever significant architectural changes (new files, classes, 
    key dependencies) occur.

Format (Q4):
    The output follows the schema defined in `Spashta-CKG/Code_Knowledge_Graph_Readme.md`.
    - Maps code elements to nodes (File, Class, Function).
    - Uses Standardized Layers: UI, Application, Service, Domain, Infrastructure.
    - Includes Self-Documenting Keys (`_comment_*`) to explain schema intent inline.
    - Captures qualified calls (e.g., `module.Class.method`) and incremental MD5 hashes.

Gap Management (Q5):
    - Code drift is handled by the dynamic file discovery in this script.
    - If new files are added, running this script automatically adds them to the CKG.
    - If the Schema definition changes, this script must be updated to reflect the new structure.

Overwriting Behavior:
    - CAUTION: This script runs in WRITE mode ('w').
    - It OVERWRITES 'code_knowledge_graph_AST_based.json'.
    - To persist information, the AI Agent must update `code_knowledge_graph_AST_Enriched_by_AI.json`.
"""

import ast
import json
import os
import hashlib
from typing import List, Dict, Any

# Configuration
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_FILE = os.path.join(PROJECT_ROOT, "Spashta-CKG", "code_knowledge_graph_AST_based.json")

# Directories to ignore during dynamic discovery
IGNORE_DIRS = {".git", ".idea", ".venv", "venv", "__pycache__", "Backups", "reference code"}

def calculate_file_hash(file_path: str) -> str:
    """Calculate MD5 hash of a file."""
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

def get_layer(path: str) -> str:
    """Do logic to determine the architectural layer based on file path."""
    path = path.replace("\\", "/")
    if "Spashta-CKG" in path:
        return "Meta-Tooling"
    if "pages" in path or "app.py" in path:
        return "UI"
    if "backend.py" in path:
        return "Application"
    if "config.py" in path:
        return "Infrastructure"
    if "utils.py" in path:
        return "Infrastructure"
    return "Unknown"

def find_python_files(root_dir: str) -> List[str]:
    """Dynamically find python files to prevent gaps between code and KG."""
    py_files = []
    for root, dirs, files in os.walk(root_dir):
        # Modify dirs in-place to skip ignored directories
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        
        for file in files:
            if file.endswith(".py"):
                # Create relative path
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, root_dir)
                py_files.append(rel_path)
    return py_files

class CodeAnalyzer(ast.NodeVisitor):
    def __init__(self, filename: str, path: str):
        self.filename = filename
        self.path = path
        self.imports = []
        self.calls = []
        self.classes = []
        self.functions = []
        self.docstring = ""

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module or ""
        for alias in node.names:
             self.imports.append(f"{module}.{alias.name}" if module else alias.name)
        self.generic_visit(node)

    def visit_Call(self, node):
        # Improved call extraction
        if isinstance(node.func, ast.Name):
            self.calls.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            # Try to capture obj.method
            if isinstance(node.func.value, ast.Name):
                self.calls.append(f"{node.func.value.id}.{node.func.attr}")
            else:
                self.calls.append(node.func.attr)
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        class_info = {
            "node_type": "Class",
            "name": node.name,
            "purpose": ast.get_docstring(node) or "No docstring provided",
            "pure_logic": True, # Default assumption for class container
            "edges": {
                "calls": [], 
                "side_effects": False 
            },
            "key_methods": []
        }
        
        # Analyze methods
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                 method_info = {
                    "node_type": "Function",
                    "name": item.name,
                    "purpose": ast.get_docstring(item) or "No docstring provided",
                    "pure_logic": False 
                 }
                 class_info["key_methods"].append(method_info)
        
        self.classes.append(class_info)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        # Top-level functions handled in main loop or generic visit. 
        # But generic visit is messy. We rely on the main loop iteration for top-level.
        # So we pass here.
        pass

    def visit_Module(self, node):
        self.docstring = ast.get_docstring(node)
        self.generic_visit(node)

def analyze_file(file_path: str, relative_path: str) -> Dict[str, Any]:
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()
    
    file_hash = calculate_file_hash(file_path)
    
    tree = ast.parse(source)
    analyzer = CodeAnalyzer(os.path.basename(file_path), relative_path)
    
    # We want to capture top-level functions separately from class methods
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            analyzer.visit_ClassDef(node)
        elif isinstance(node, ast.FunctionDef):
             func_info = {
                "node_type": "Function",
                "name": node.name,
                "purpose": ast.get_docstring(node) or "No docstring provided",
                "pure_logic": False, 
                "edges": {"calls": [], "side_effects": False} 
             }
             analyzer.functions.append(func_info)
        else:
             # Visit imports/calls
             analyzer.visit(node)
    
    return {
        "node_type": "File",
        "_comment_node_type": "Explicit typing prevents semantic guessing.",
        "filename": os.path.basename(file_path),
        "path": relative_path,
        "_comment_path": "Absolute or relative path to allow direct file access.",
        "file_hash": file_hash,
        "_comment_file_hash": "MD5 checksum for incremental update detection.",
        "analysis_confidence": "structural_only",
        "_comment_analysis_confidence": "Indicates if node needs AI Agent review.",
        "layer": get_layer(relative_path),
        "_comment_layer": "Standardized Architecture Layer. Agent must override if incorrect.",
        "framework_bound": False, # Placeholder
        "_comment_framework_bound": "True if code is coupled to framework (e.g. Django/Streamlit) and hard to reuse.",
        "purpose": analyzer.docstring or "Analyzed file",
        "why_developed": "Core project file", # Placeholder
        "responsibility_scope": "See components",
        "pure_logic": False,
        "_comment_pure_logic": "True if function/file has NO side effects (IO/State) and is deterministic.",
        "public_contract": {
            "inputs": [], # Requires more analysis
            "outputs": [],
            "guarantees": []
        },
        "edges": {
            "imports": list(set(analyzer.imports)),
            "calls": list(set(analyzer.calls)),
            "_comment_calls": "Approximation only (Stage 1). Resolving complex chains requires dynamic analysis.",
            "uses_state": [],
            "_comment_uses_state": "Explicitly defined scope: 'global', 'session', or 'request'.",
            "reads_from": [],
            "writes_to": [],
            "side_effects": False
        },
        "classes": analyzer.classes,
        "functions": analyzer.functions
    }

def main():
    print(f"Analyzing project at: {PROJECT_ROOT}")
    ckg_data = {
        "app_name": os.path.basename(PROJECT_ROOT),
        "_comment_app_name": "Logical app name for scoping queries.",
        "generated_by": "build_kg_ast_based.py v1.0",
        "_comment_generated_by": "Tracks tool version to manage schema drift.",
        "files": []
    }
    
    files_to_analyze = find_python_files(PROJECT_ROOT)
    
    for rel_path in files_to_analyze:
        full_path = os.path.join(PROJECT_ROOT, rel_path)
        if os.path.exists(full_path):
            print(f"Processing {rel_path}...")
            try:
                file_node = analyze_file(full_path, rel_path)
                ckg_data["files"].append(file_node)
            except Exception as e:
                print(f"Error processing {rel_path}: {e}")
        else:
            print(f"Skipping {rel_path} (not found)")
            
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(ckg_data, f, indent=2)
    
    print(f"CKG generated at: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
