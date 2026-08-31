"""
Spashta CKG Engine - Core Orchestrator for Building, Enriching, and Querying Code Knowledge Graphs.
Executes Stage 1 (Body - Structural AST) + Stage 2 (Mind - Semantic Adapter Enrichment).
"""

import sys
import os
import json
import subprocess
import fnmatch
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Union

# Base package directory
PACKAGE_ROOT = Path(__file__).resolve().parent

def apply_enrichment_logic(node: Dict[str, Any], edges_from: Dict[str, List], edges_to: Dict[str, List], node_map: Dict[str, Any], detection_rules: Dict[str, Any]) -> bool:
    """Evaluates 9 deterministic detection rules against a node to assign semantic roles."""
    node_id = node.get("id")
    node_name = node.get("name", "")
    match = True

    # 1. inheritance_includes
    if match and "inheritance_includes" in detection_rules:
        found = False
        for edge_type, target_id in edges_from.get(node_id, []):
            if edge_type == "extends":
                target_node = node_map.get(target_id)
                target_name = target_node.get("name") if target_node else (target_id.split("::")[-1] if "::" in target_id else target_id)
                if target_name in detection_rules["inheritance_includes"]:
                    found = True
                    break
        if not found: match = False

    # 2. file_path_contains
    if match and "file_path_contains" in detection_rules:
        fpath = node.get("file_path", "")
        patterns = detection_rules["file_path_contains"]
        if isinstance(patterns, str): patterns = [patterns]
        if not any(fnmatch.fnmatch(fpath, pat) or fnmatch.fnmatch(Path(fpath).name, pat) for pat in patterns):
            match = False

    # 3. decorated_by
    if match and "decorated_by" in detection_rules:
        found_dec = False
        for edge_type, src_id in edges_to.get(node_id, []):
            if edge_type == "decorates":
                dec_node = node_map.get(src_id)
                if dec_node and dec_node.get("name") in detection_rules["decorated_by"]:
                    found_dec = True
                    break
        if not found_dec: match = False

    # 4. requires_import
    if match and "requires_import" in detection_rules:
        req_imports = detection_rules["requires_import"]
        found_imp = False
        fpath = node.get("file_path")
        for nid, n in node_map.items():
            if n.get("node_type") == "File" and n.get("file_path") == fpath:
                for edge_type, target_id in edges_from.get(nid, []):
                    if edge_type == "imports":
                        t_node = node_map.get(target_id)
                        if t_node and t_node.get("name") in req_imports:
                            found_imp = True
                            break
        if not found_imp: match = False

    # 5. used_in_calls
    if match and "used_in_calls" in detection_rules:
        found_call = False
        for edge_type, target_id in edges_from.get(node_id, []):
            if edge_type == "calls":
                t_node = node_map.get(target_id)
                if t_node and t_node.get("name") in detection_rules["used_in_calls"]:
                    found_call = True
                    break
        if not found_call: match = False

    # 6. function_name
    if match and "function_name" in detection_rules:
        if node_name not in detection_rules["function_name"]:
            match = False

    # 7. has_outgoing_edge
    if match and "has_outgoing_edge" in detection_rules:
        req_types = detection_rules["has_outgoing_edge"]
        found_edge = False
        for edge_type, _ in edges_from.get(node_id, []):
            if edge_type in req_types:
                found_edge = True
                break
        if not found_edge: match = False

    # 8. arg_names_include
    if match and "arg_names_include" in detection_rules:
        req_args = detection_rules["arg_names_include"]
        sig = node.get("signature", {})
        node_args = sig.get("args", []) if isinstance(sig, dict) else []
        if not any(arg in node_args for arg in req_args):
            match = False

    # 9. decorators
    if match and "decorators" in detection_rules:
        req_decs = detection_rules["decorators"]
        sig = node.get("signature", {})
        node_decs = sig.get("decorators", []) if isinstance(sig, dict) else []
        normalized_decs = [d.lstrip("@").split("(")[0] for d in node_decs]
        if not any(rd in normalized_decs for rd in req_decs):
            match = False

    return match


class CKG:
    """
    Code Knowledge Graph representation and query engine.
    """
    def __init__(self, data: Dict[str, Any], project_root: Optional[Path] = None):
        self.data = data
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.nodes = data.get("nodes", [])
        self.edges = data.get("edges", [])
        self._node_by_id = {n.get("id"): n for n in self.nodes if n.get("id")}
        self._nodes_by_name = {}
        for n in self.nodes:
            name = n.get("name")
            if name:
                self._nodes_by_name.setdefault(name, []).append(n)

    @classmethod
    def load(cls, ckg_path: Optional[Union[str, Path]] = None, project_root: Optional[Union[str, Path]] = None) -> "CKG":
        """Loads an existing CKG JSON file."""
        root = Path(project_root).resolve() if project_root else Path.cwd()
        if ckg_path:
            p = Path(ckg_path)
            if not p.is_absolute():
                p = root / p
        else:
            candidates = [
                root / ".spashta" / "code_knowledge_graph_enriched.json",
                root / "runtime" / "code_knowledge_graph_enriched.json",
                PACKAGE_ROOT / "runtime" / "code_knowledge_graph_enriched.json",
            ]
            p = None
            for c in candidates:
                if c.exists():
                    p = c
                    break
            if not p:
                raise FileNotFoundError(f"No CKG found in {root}. Run 'spashta_ckg scan' first.")

        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(data, project_root=root)

    @classmethod
    def get_profile_info(cls, project_root: Optional[Union[str, Path]] = None) -> dict:
        """Retrieves active project exclusions and config location."""
        root = Path(project_root).resolve() if project_root else Path.cwd()
        candidates = [
            root / "profile.json",
            root / ".spashta" / "profile.json",
            PACKAGE_ROOT / "project" / "profile.json"
        ]
        profile_path = next((p for p in candidates if p.exists()), PACKAGE_ROOT / "project" / "profile.json")
            
        with open(profile_path, "r", encoding="utf-8") as f:
            profile = json.load(f)

        # Extract exclusions (supports both new "exclude": [] and legacy "excluded": {"directories": []})
        excluded_dirs = profile.get("exclude")
        if excluded_dirs is None:
            excluded_dirs = profile.get("excluded", {}).get("directories", [])

        return {
            "path": str(profile_path),
            "is_custom": (profile_path.parent == root or profile_path.parent == (root / ".spashta")),
            "project_root": str(root),
            "excluded_directories": list(excluded_dirs),
            "profile": profile
        }

    @classmethod
    def init_profile(cls, project_root: Optional[Union[str, Path]] = None,
                     excluded_dirs: Optional[List[str]] = None,
                     force: bool = False) -> Path:
        """Generates a clean, directory-exclusion profile.json in the target project root."""
        root = Path(project_root).resolve() if project_root else Path.cwd()
        target_path = root / "profile.json"
        if target_path.exists() and not force:
            raise FileExistsError(f"profile.json already exists at {target_path}. Use force=True to overwrite.")

        default_excludes = ["venv", ".venv", "env", "node_modules", ".git", "build", "dist", "Spashta-CKG", "_archive"]
        if excluded_dirs:
            for d in excluded_dirs:
                if d not in default_excludes:
                    default_excludes.append(d)

        # Auto-detect other common development scratch folders
        for d_name in [".idea", ".vscode", "coverage", ".pytest_cache", "site-packages", "misc", "reference", "fixtures"]:
            if (root / d_name).exists() and d_name not in default_excludes:
                default_excludes.append(d_name)

        profile_content = {
          "exclude": default_excludes
        }

        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(profile_content, f, indent=2)

        return target_path

    @classmethod
    def update_profile(cls, project_root: Optional[Union[str, Path]] = None,
                       set_exclude: Optional[List[str]] = None,
                       add_exclude: Optional[List[str]] = None) -> dict:
        """Updates or creates profile.json with modified directory exclusions."""
        root = Path(project_root).resolve() if project_root else Path.cwd()
        target_path = root / "profile.json"
        if not target_path.exists():
            cls.init_profile(project_root=root)
        
        with open(target_path, "r", encoding="utf-8") as f:
            profile = json.load(f)

        if set_exclude is not None:
            profile["exclude"] = set_exclude
            if "excluded" in profile and "directories" in profile["excluded"]:
                profile["excluded"]["directories"] = set_exclude
        elif add_exclude:
            current = profile.get("exclude")
            if current is None:
                current = profile.setdefault("excluded", {}).setdefault("directories", [])
            for item in add_exclude:
                if item not in current:
                    current.append(item)
            profile["exclude"] = current

        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2)

        return cls.get_profile_info(project_root=root)

    @classmethod
    def build(cls, project_root: Optional[Union[str, Path]] = None,
              output_dir: Optional[Union[str, Path]] = None,
              excluded_dirs: Optional[List[str]] = None) -> "CKG":
        """Scans project across all supported languages (Python, JS, HTML, CSS), merges AST, and runs framework semantic enrichment."""
        root = Path(project_root).resolve() if project_root else Path.cwd()
        out = Path(output_dir).resolve() if output_dir else (root / ".spashta")
        out.mkdir(parents=True, exist_ok=True)

        # Profile detection for exclusions
        candidates = [
            root / "profile.json",
            root / ".spashta" / "profile.json",
            PACKAGE_ROOT / "project" / "profile.json"
        ]
        profile_path = next((p for p in candidates if p.exists()), PACKAGE_ROOT / "project" / "profile.json")

        with open(profile_path, "r", encoding="utf-8") as f:
            profile = json.load(f)

        # Exclusions (supports "exclude": [] and legacy "excluded.directories")
        configured_excludes = profile.get("exclude")
        if configured_excludes is None:
            configured_excludes = profile.get("excluded", {}).get("directories", [])

        all_excluded = set(configured_excludes)
        if excluded_dirs:
            all_excluded.update(excluded_dirs)
        exclude_arg = ",".join(sorted(all_excluded))

        # ── STAGE 1: BODY (Structure) - Run Language Builders ──────────
        frag_dir = out / "fragments"
        frag_dir.mkdir(parents=True, exist_ok=True)
        fragments = []

        all_languages = ["python", "html", "css", "js"]
        for lang in all_languages:
            builder_file = PACKAGE_ROOT / "builders" / lang / f"build_{lang}_ast.py"
            if not builder_file.exists():
                continue
            frag_path = frag_dir / f"fragment_{lang}.json"
            cmd = [
                sys.executable, str(builder_file),
                "--source-root", str(root),
                "--out", str(frag_path),
                "--exclude", exclude_arg
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0 and frag_path.exists():
                fragments.append(frag_path)

        # Merge AST Fragments
        merged_nodes = {}
        merged_edges = []
        seen_edges = set()
        ambiguities = []

        for frag in fragments:
            with open(frag, "r", encoding="utf-8") as f:
                fdata = json.load(f)
            ambiguities.extend(fdata.get("ambiguities", []))
            for n in fdata.get("nodes", []):
                nid = n.get("id") or f"{n.get('node_type')}:{n.get('name')}"
                if nid not in merged_nodes:
                    merged_nodes[nid] = n
                else:
                    merged_nodes[nid].update(n)

            for e in fdata.get("edges", []):
                src = e.get("source", e.get("from"))
                tgt = e.get("target", e.get("to"))
                typ = e.get("type", e.get("edge"))
                key = (typ, src, tgt)
                if key not in seen_edges:
                    seen_edges.add(key)
                    merged_edges.append(e)

        ast_data = {
            "_meta": {
                "schema_version": "2.2",
                "generator": "Spashta-CKG 3.0",
                "project_root": str(root),
                "languages": all_languages
            },
            "nodes": list(merged_nodes.values()),
            "edges": merged_edges,
            "ambiguities": ambiguities
        }

        raw_ast_path = out / "code_knowledge_graph_ast.json"
        with open(raw_ast_path, "w", encoding="utf-8") as f:
            json.dump(ast_data, f, indent=2)

        # ── STAGE 2: MIND (Semantics) - Rule-Based Adapter Enrichment ──
        node_map = {n["id"]: n for n in ast_data["nodes"]}
        edges_from = {}
        edges_to = {}

        for e in ast_data["edges"]:
            src = e.get("source", e.get("from"))
            tgt = e.get("target", e.get("to"))
            typ = e.get("type", e.get("edge"))
            if src and tgt:
                edges_from.setdefault(src, []).append((typ, tgt))
                edges_to.setdefault(tgt, []).append((typ, src))

        # Apply all available framework adapters (Django, FastAPI, HTMX, Vanilla)
        all_frameworks = ["django", "fastapi", "htmx", "vanilla"]
        for fw in all_frameworks:
            mapping_path = PACKAGE_ROOT / "adapters" / fw / "framework_mapping.json"
            if not mapping_path.exists():
                continue
            with open(mapping_path, "r", encoding="utf-8") as mf:
                mapping = json.load(mf)

            for rule in mapping.get("mappings", []):
                role = rule.get("semantic_role")
                target_core_node = rule.get("core_node")
                detection = rule.get("detection_rules", {})

                for nid, node in node_map.items():
                    ntype = node.get("node_type", node.get("type"))
                    if ntype != target_core_node:
                        continue
                    if apply_enrichment_logic(node, edges_from, edges_to, node_map, detection):
                        current_roles = node.get("semantic_roles", [])
                        if role not in current_roles:
                            current_roles.append(role)
                            node["semantic_roles"] = current_roles

        enriched_data = dict(ast_data)
        enriched_data["nodes"] = list(node_map.values())
        enriched_data["_meta"]["enriched"] = True
        enriched_data["_meta"]["frameworks"] = all_frameworks

        enriched_path = out / "code_knowledge_graph_enriched.json"
        with open(enriched_path, "w", encoding="utf-8") as f:
            json.dump(enriched_data, f, indent=2)

        return cls(enriched_data, project_root=root)

    @classmethod
    def refresh(cls, project_root: Optional[Union[str, Path]] = None,
                output_dir: Optional[Union[str, Path]] = None,
                files: Optional[Union[str, List[str]]] = None) -> "CKG":
        """
        Incrementally updates the CKG graph by re-parsing only changed or specified files.
        If no graph exists, runs full build. If no files changed, returns existing graph in ~10ms.
        """
        root = Path(project_root).resolve() if project_root else Path.cwd()
        out = Path(output_dir).resolve() if output_dir else (root / ".spashta")
        raw_ast_path = out / "code_knowledge_graph_ast.json"
        enriched_path = out / "code_knowledge_graph_enriched.json"

        # Fallback to full build if graph does not exist
        if not raw_ast_path.exists() or not enriched_path.exists():
            return cls.build(project_root=root, output_dir=out)

        with open(raw_ast_path, "r", encoding="utf-8") as f:
            ast_data = json.load(f)

        existing_file_nodes = {n["id"]: n for n in ast_data.get("nodes", []) if n.get("node_type") == "File"}
        existing_file_hashes = {nid: n.get("file_hash") for nid, n in existing_file_nodes.items()}

        target_files_to_refresh = set()

        if files:
            if isinstance(files, str):
                file_list = [f.strip() for f in files.split(",") if f.strip()]
            else:
                file_list = list(files)
            for f_str in file_list:
                fp = (root / f_str).resolve() if not Path(f_str).is_absolute() else Path(f_str).resolve()
                if fp.exists():
                    target_files_to_refresh.add(fp)
        else:
            cfg = cls.get_profile_info(project_root=root)
            exclude_dirs = set(cfg.get("excluded_directories", []))
            
            def should_include(p):
                try:
                    rel_parts = p.relative_to(root).parts[:-1]
                except Exception:
                    rel_parts = p.parts[:-1]
                return not any(part in exclude_dirs for part in rel_parts)

            all_exts = ("*.py", "*.js", "*.html", "*.css")
            current_project_files = {}
            for ext in all_exts:
                for p in root.rglob(ext):
                    if should_include(p):
                        try:
                            rel_posix = p.relative_to(root).as_posix()
                            content_bytes = p.read_bytes()
                            h = hashlib.md5(content_bytes).hexdigest()
                            current_project_files[rel_posix] = (p, h)
                        except Exception:
                            pass

            for rel_posix, (p, h) in current_project_files.items():
                old_h = existing_file_hashes.get(rel_posix)
                if old_h != h:
                    target_files_to_refresh.add(p)

        if not target_files_to_refresh and not files:
            with open(enriched_path, "r", encoding="utf-8") as f:
                return cls(json.load(f), project_root=root)

        # Re-parse changed languages
        frag_dir = out / "fragments"
        frag_dir.mkdir(parents=True, exist_ok=True)
        
        ext_map = {
            ".py": "python",
            ".js": "js",
            ".html": "html",
            ".css": "css"
        }
        langs_to_reparse = set()
        for tf in target_files_to_refresh:
            l = ext_map.get(tf.suffix.lower())
            if l:
                langs_to_reparse.add(l)

        cfg = cls.get_profile_info(project_root=root)
        exclude_arg = ",".join(sorted(cfg.get("excluded_directories", [])))

        for lang in (langs_to_reparse or ["python", "html", "css", "js"]):
            builder_file = PACKAGE_ROOT / "builders" / lang / f"build_{lang}_ast.py"
            if not builder_file.exists():
                continue
            frag_path = frag_dir / f"fragment_{lang}.json"
            cmd = [
                sys.executable, str(builder_file),
                "--source-root", str(root),
                "--out", str(frag_path),
                "--exclude", exclude_arg
            ]
            subprocess.run(cmd, capture_output=True, text=True)

        # Merge AST fragments
        fragments = list(frag_dir.glob("fragment_*.json"))
        merged_nodes = {}
        merged_edges = []
        seen_edges = set()
        ambiguities = []

        for frag in fragments:
            with open(frag, "r", encoding="utf-8") as f:
                fdata = json.load(f)
            ambiguities.extend(fdata.get("ambiguities", []))
            for n in fdata.get("nodes", []):
                nid = n.get("id") or f"{n.get('node_type')}:{n.get('name')}"
                if nid not in merged_nodes:
                    merged_nodes[nid] = n
                else:
                    merged_nodes[nid].update(n)

            for e in fdata.get("edges", []):
                src = e.get("source", e.get("from"))
                tgt = e.get("target", e.get("to"))
                typ = e.get("type", e.get("edge"))
                key = (typ, src, tgt)
                if key not in seen_edges:
                    seen_edges.add(key)
                    merged_edges.append(e)

        ast_data = {
            "_meta": {
                "schema_version": "2.2",
                "generator": "Spashta-CKG 3.2.2 (Incremental)",
                "project_root": str(root),
                "languages": ["python", "html", "css", "js"]
            },
            "nodes": list(merged_nodes.values()),
            "edges": merged_edges,
            "ambiguities": ambiguities
        }

        with open(raw_ast_path, "w", encoding="utf-8") as f:
            json.dump(ast_data, f, indent=2)

        # Stage 2 enrichment
        node_map = {n["id"]: n for n in ast_data["nodes"]}
        edges_from = {}
        edges_to = {}
        for e in ast_data["edges"]:
            src = e.get("source", e.get("from"))
            tgt = e.get("target", e.get("to"))
            typ = e.get("type", e.get("edge"))
            if src and tgt:
                edges_from.setdefault(src, []).append((typ, tgt))
                edges_to.setdefault(tgt, []).append((typ, src))

        all_frameworks = ["django", "fastapi", "htmx", "vanilla"]
        for fw in all_frameworks:
            mapping_path = PACKAGE_ROOT / "adapters" / fw / "framework_mapping.json"
            if not mapping_path.exists():
                continue
            with open(mapping_path, "r", encoding="utf-8") as mf:
                mapping = json.load(mf)
            for rule in mapping.get("mappings", []):
                role = rule.get("semantic_role")
                target_core_node = rule.get("core_node")
                detection = rule.get("detection_rules", {})
                for nid, node in node_map.items():
                    ntype = node.get("node_type", node.get("type"))
                    if ntype != target_core_node:
                        continue
                    if apply_enrichment_logic(node, edges_from, edges_to, node_map, detection):
                        current_roles = node.get("semantic_roles", [])
                        if role not in current_roles:
                            current_roles.append(role)
                            node["semantic_roles"] = current_roles

        enriched_data = dict(ast_data)
        enriched_data["nodes"] = list(node_map.values())
        enriched_data["_meta"]["enriched"] = True
        enriched_data["_meta"]["frameworks"] = all_frameworks

        with open(enriched_path, "w", encoding="utf-8") as f:
            json.dump(enriched_data, f, indent=2)

        return cls(enriched_data, project_root=root)

    def search(self, query: str, node_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Finds nodes matching query string and optional node_type."""
        q = query.lower()
        results = []
        for n in self.nodes:
            if node_type and (n.get("node_type") != node_type and n.get("type") != node_type):
                continue
            name = (n.get("name") or "").lower()
            nid = (n.get("id") or "").lower()
            if q in name or q in nid:
                results.append(n)
        return results

    def locate(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Finds file path, line numbers, and metadata for a symbol."""
        matches = self.search(symbol)
        if matches:
            m = matches[0]
            return {
                "id": m.get("id"),
                "name": m.get("name"),
                "node_type": m.get("node_type") or m.get("type"),
                "file_path": m.get("file_path"),
                "line_start": m.get("line_start"),
                "line_end": m.get("line_end"),
                "semantic_roles": m.get("semantic_roles", [])
            }
        return None

    def impact(self, symbol: str, depth: int = 3) -> Dict[str, Any]:
        """Calculates upstream blast-radius: who depends on or calls this symbol."""
        target_nodes = self.search(symbol)
        if not target_nodes:
            return {"target": symbol, "found": False, "impacted_nodes": [], "edges": []}

        target = target_nodes[0]
        target_id = target.get("id") or target.get("name")

        impacted_nodes = {}
        relevant_edges = []
        visited = set()
        queue = [(target_id, 0)]

        while queue:
            curr_id, curr_depth = queue.pop(0)
            if curr_id in visited or curr_depth >= depth:
                continue
            visited.add(curr_id)

            for e in self.edges:
                t = e.get("target", e.get("to"))
                s = e.get("source", e.get("from"))
                if t == curr_id or (curr_id in str(t)):
                    relevant_edges.append(e)
                    if s in self._node_by_id and s not in impacted_nodes:
                        node_obj = self._node_by_id[s]
                        impacted_nodes[s] = {
                            "id": s,
                            "name": node_obj.get("name"),
                            "node_type": node_obj.get("node_type") or node_obj.get("type"),
                            "semantic_roles": node_obj.get("semantic_roles", []),
                            "file_path": node_obj.get("file_path"),
                            "line_start": node_obj.get("line_start"),
                            "edge_type": e.get("type", e.get("edge"))
                        }
                        queue.append((s, curr_depth + 1))

        return {
            "target": target_id,
            "found": True,
            "target_node": target,
            "impact_count": len(impacted_nodes),
            "impacted_nodes": list(impacted_nodes.values()),
            "edges": relevant_edges
        }

    def dead_code(self, language: Optional[str] = None) -> Dict[str, Any]:
        """Identifies definitions with zero inbound usage edges."""
        referenced_targets = set()
        for e in self.edges:
            t = e.get("target", e.get("to"))
            if t:
                referenced_targets.add(str(t))

        dead_items = []
        for n in self.nodes:
            ntype = n.get("node_type") or n.get("type")
            nid = n.get("id") or n.get("name")
            name = n.get("name", "")

            if language:
                fpath = (n.get("file_path") or "").lower()
                if language == "css" and not fpath.endswith(".css"): continue
                if language == "js" and not (fpath.endswith(".js") or fpath.endswith(".jsx")): continue
                if language == "py" and not fpath.endswith(".py"): continue

            if ntype in ("Route", "TestCase", "File", "Package", "Module"):
                continue

            is_referenced = (
                nid in referenced_targets or 
                name in referenced_targets or
                any(name in ref for ref in referenced_targets)
            )

            if not is_referenced:
                dead_items.append({
                    "id": nid,
                    "name": name,
                    "node_type": ntype,
                    "semantic_roles": n.get("semantic_roles", []),
                    "file_path": n.get("file_path"),
                    "line_start": n.get("line_start")
                })

        return {
            "total_candidates": len(dead_items),
            "language_filter": language,
            "dead_items": dead_items
        }

    def routes(self) -> List[Dict[str, Any]]:
        """Extracts full route map linking templates, views, and endpoints."""
        route_list = []
        for n in self.nodes:
            if (n.get("node_type") or n.get("type")) == "Route":
                nid = n.get("id")
                connected_views = []
                connected_templates = []
                for e in self.edges:
                    tgt = e.get("target", e.get("to"))
                    src = e.get("source", e.get("from"))
                    if tgt == nid:
                        src_node = self._node_by_id.get(src)
                        if src_node:
                            stype = src_node.get("node_type") or src_node.get("type")
                            if stype in ("Function", "Method", "View"):
                                connected_views.append(src_node.get("name"))
                            elif stype in ("Template", "Fragment"):
                                connected_templates.append(src_node.get("name") or src_node.get("file_path"))

                route_list.append({
                    "route": n.get("name") or n.get("pattern"),
                    "id": nid,
                    "file_path": n.get("file_path"),
                    "line_start": n.get("line_start"),
                    "views": connected_views,
                    "templates": connected_templates
                })
        return route_list

    def stats(self) -> Dict[str, Any]:
        """Returns high-level graph statistics."""
        type_counts = {}
        role_counts = {}
        for n in self.nodes:
            t = n.get("node_type") or n.get("type") or "Unknown"
            type_counts[t] = type_counts.get(t, 0) + 1
            for r in n.get("semantic_roles", []):
                role_counts[r] = role_counts.get(r, 0) + 1

        edge_counts = {}
        for e in self.edges:
            t = e.get("type", e.get("edge")) or "Unknown"
            edge_counts[t] = edge_counts.get(t, 0) + 1

        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "node_breakdown": type_counts,
            "semantic_roles": role_counts,
            "edge_breakdown": edge_counts
        }
