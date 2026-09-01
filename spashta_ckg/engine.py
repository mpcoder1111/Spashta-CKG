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
__version__ = "3.2.7"

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
        self.graph_data = data
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
            root / ".spashta.json",
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
        """Generates a clean, directory-exclusion .spashta.json in the target project root."""
        root = Path(project_root).resolve() if project_root else Path.cwd()
        target_path = root / ".spashta.json"
        legacy_path = root / "profile.json"
        if (target_path.exists() or legacy_path.exists()) and not force:
            exist_file = target_path if target_path.exists() else legacy_path
            raise FileExistsError(f"Configuration profile already exists at {exist_file}. Use force=True to overwrite.")

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
        """Updates or creates .spashta.json with modified directory exclusions."""
        root = Path(project_root).resolve() if project_root else Path.cwd()
        if (root / ".spashta.json").exists():
            target_path = root / ".spashta.json"
        elif (root / "profile.json").exists():
            target_path = root / "profile.json"
        elif (root / ".spashta" / "profile.json").exists():
            target_path = root / ".spashta" / "profile.json"
        else:
            target_path = root / ".spashta.json"
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
            root / ".spashta.json",
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
                "generator": f"Spashta-CKG {__version__}",
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

        # Write scan_meta.json for instant mtime-based incremental refreshes
        try:
            meta = {}
            for n in ast_data.get("nodes", []):
                if n.get("node_type") in ("File", "Stylesheet", "Template"):
                    rel = n.get("id")
                    h = n.get("file_hash") or n.get("hash")
                    fpath = root / rel
                    if fpath.exists():
                        st = fpath.stat()
                        meta[rel] = {"mtime": st.st_mtime, "size": st.st_size, "hash": h}
            with open(out / "scan_meta.json", "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
        except Exception:
            pass

        return cls(enriched_data, project_root=root)

    @classmethod
    def refresh(cls, project_root: Optional[Union[str, Path]] = None,
                output_dir: Optional[Union[str, Path]] = None,
                files: Optional[Union[str, List[str]]] = None) -> "CKG":
        """
        Incrementally updates the CKG graph by re-parsing only changed or specified files.
        If no graph exists, runs full build. If no files changed, returns existing graph in ~5ms.
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

        # Version guard: auto-rebuild if graph was generated by an older/different version
        current_gen = f"Spashta-CKG {__version__}"
        meta_gen = ast_data.get("_meta", {}).get("generator", "")
        if current_gen not in meta_gen:
            return cls.build(project_root=root, output_dir=out)

        def get_node_file_rel(n):
            if "::" in n.get("id", ""):
                return None
            f = n.get("file_path") or n.get("file")
            if f:
                return f
            nid = n.get("id", "")
            if nid.startswith("File:"):
                return nid[5:]
            if n.get("node_type") in ("File", "Stylesheet", "Template"):
                return nid
            return None

        existing_physical_files = {}
        for n in ast_data.get("nodes", []):
            if n.get("node_type") in ("File", "Stylesheet", "Template"):
                rel = get_node_file_rel(n)
                if rel:
                    existing_physical_files[rel] = n
        existing_file_hashes = {rel: n.get("file_hash") or n.get("hash") for rel, n in existing_physical_files.items()}

        target_files_to_refresh = set()
        deleted_files = set()
        meta_path = out / "scan_meta.json"
        cached_meta = {}
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    cached_meta = json.load(f)
            except Exception:
                pass

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
                    rel_posix = fp.relative_to(root).as_posix() if fp.is_relative_to(root) else f_str
                    deleted_files.add(rel_posix)
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
                            st = p.stat()
                            cur_mtime = st.st_mtime
                            cur_size = st.st_size
                            meta_entry = cached_meta.get(rel_posix, {})
                            
                            # Fast-path: if mtime & size match cached meta, skip hashing
                            if meta_entry.get("mtime") == cur_mtime and meta_entry.get("size") == cur_size:
                                current_project_files[rel_posix] = (p, meta_entry.get("hash"))
                            else:
                                content_bytes = p.read_bytes()
                                h = hashlib.md5(content_bytes).hexdigest()
                                current_project_files[rel_posix] = (p, h)
                                cached_meta[rel_posix] = {"mtime": cur_mtime, "size": cur_size, "hash": h}
                                if existing_file_hashes.get(rel_posix) != h:
                                    target_files_to_refresh.add(p)
                        except Exception:
                            pass

            for old_rel in existing_physical_files.keys():
                if old_rel not in current_project_files:
                    deleted_files.add(old_rel)
                    cached_meta.pop(old_rel, None)

        # Fast exit if nothing changed
        if not target_files_to_refresh and not deleted_files and not files:
            with open(enriched_path, "r", encoding="utf-8") as f:
                return cls(json.load(f), project_root=root)

        # Build set of affected file relative paths
        affected_rel_paths = set(deleted_files)
        for tf in target_files_to_refresh:
            try:
                affected_rel_paths.add(tf.relative_to(root).as_posix())
            except Exception:
                affected_rel_paths.add(tf.name)

        # Identify existing nodes belonging to affected files
        def is_node_affected(n):
            nid = n.get("id", "")
            fpath = n.get("file_path") or n.get("file") or ""
            if nid.startswith("File:"):
                fpath = nid[5:]
            for aff in affected_rel_paths:
                if fpath == aff or nid == aff or nid.startswith(f"{aff}::") or nid == f"File:{aff}":
                    return True
            return False

        retained_nodes = [n for n in ast_data.get("nodes", []) if not is_node_affected(n)]
        removed_node_ids = {n["id"] for n in ast_data.get("nodes", []) if is_node_affected(n)}

        # Re-parse only the changed files by language passing existing AST for global resolution
        frag_dir = out / "fragments"
        frag_dir.mkdir(parents=True, exist_ok=True)
        
        ext_map = {
            ".py": "python",
            ".js": "js",
            ".html": "html",
            ".css": "css"
        }
        
        files_by_lang = {}
        for tf in target_files_to_refresh:
            l = ext_map.get(tf.suffix.lower())
            if l:
                rel = tf.relative_to(root).as_posix() if tf.is_relative_to(root) else tf.as_posix()
                files_by_lang.setdefault(l, []).append(rel)

        cfg = cls.get_profile_info(project_root=root)
        exclude_arg = ",".join(sorted(cfg.get("excluded_directories", [])))

        new_fragment_nodes = []
        new_fragment_edges = []
        new_fragment_ambiguities = []

        for lang, lang_files in files_by_lang.items():
            builder_file = PACKAGE_ROOT / "builders" / lang / f"build_{lang}_ast.py"
            if not builder_file.exists():
                continue
            frag_path = frag_dir / f"fragment_{lang}_refresh.json"
            files_arg = ",".join(lang_files)
            cmd = [
                sys.executable, str(builder_file),
                "--source-root", str(root),
                "--files", files_arg,
                "--existing-ast", str(raw_ast_path),
                "--out", str(frag_path),
                "--exclude", exclude_arg
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0 and frag_path.exists():
                with open(frag_path, "r", encoding="utf-8") as f:
                    fdata = json.load(f)
                new_fragment_nodes.extend(fdata.get("nodes", []))
                new_fragment_edges.extend(fdata.get("edges", []))
                new_fragment_ambiguities.extend(fdata.get("ambiguities", []))
                try:
                    frag_path.unlink()
                except Exception:
                    pass

        # Build merged node map
        node_map = {n["id"]: n for n in retained_nodes}
        for n in new_fragment_nodes:
            nid = n.get("id") or f"{n.get('node_type')}:{n.get('name')}"
            if nid not in node_map:
                node_map[nid] = n
            else:
                node_map[nid].update(n)

        new_node_ids = {n["id"] for n in new_fragment_nodes}

        # Deterministic Edge Splicing:
        # 1. Edges from retained nodes pointing to retained nodes -> KEEP
        # 2. Edges from retained nodes pointing to affected files:
        #    - If target symbol still exists in new_node_ids -> KEEP (Preserve incoming caller edges!)
        #    - If target symbol was deleted -> DROP
        # 3. Edges from affected files (outgoing) -> DISCARD (replaced by new_fragment_edges)
        merged_edges = []
        seen_edges = set()

        for e in ast_data.get("edges", []):
            src = e.get("source", e.get("from"))
            tgt = e.get("target", e.get("to"))
            typ = e.get("type", e.get("edge"))
            
            # If source was in removed files, discard (replaced by new outgoing edges)
            if src in removed_node_ids:
                continue

            # If target was in removed files:
            if tgt in removed_node_ids:
                # Keep if target symbol still exists in the newly parsed version
                if tgt in new_node_ids:
                    key = (typ, src, tgt)
                    if key not in seen_edges:
                        seen_edges.add(key)
                        merged_edges.append(e)
                continue

            # Otherwise source & target are in retained files -> keep
            key = (typ, src, tgt)
            if key not in seen_edges:
                seen_edges.add(key)
                merged_edges.append(e)

        # Add newly emitted fragment edges
        for e in new_fragment_edges:
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
                "generator": f"Spashta-CKG {__version__} (Incremental)",
                "project_root": str(root),
                "languages": ["python", "html", "css", "js"]
            },
            "nodes": list(node_map.values()),
            "edges": merged_edges,
            "ambiguities": ast_data.get("ambiguities", []) + new_fragment_ambiguities
        }

        # Atomic write of raw AST
        tmp_raw = raw_ast_path.with_suffix(".json.tmp")
        with open(tmp_raw, "w", encoding="utf-8") as f:
            json.dump(ast_data, f, indent=2)
        import os
        os.replace(tmp_raw, raw_ast_path)

        # Stage 2 enrichment
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

        # Atomic write of enriched graph
        tmp_enriched = enriched_path.with_suffix(".json.tmp")
        with open(tmp_enriched, "w", encoding="utf-8") as f:
            json.dump(enriched_data, f, indent=2)
        os.replace(tmp_enriched, enriched_path)

        try:
            for n in ast_data.get("nodes", []):
                if n.get("node_type") in ("File", "Stylesheet", "Template"):
                    rel = n.get("id")
                    h = n.get("file_hash") or n.get("hash")
                    fpath = root / rel
                    if fpath.exists():
                        st = fpath.stat()
                        cached_meta[rel] = {"mtime": st.st_mtime, "size": st.st_size, "hash": h}
            with open(out / "scan_meta.json", "w", encoding="utf-8") as f:
                json.dump(cached_meta, f, indent=2)
        except Exception:
            pass

        return cls(enriched_data, project_root=root)

    def search(self, query: str, node_type: Optional[str] = None, include_full: bool = False) -> List[Dict[str, Any]]:
        """Finds nodes matching query string and optional node_type, prioritized by exact match relevance and symbol type tiering."""
        from spashta_ckg.runtime.query_spashta import smart_search, make_compact_node
        raw_results = smart_search(self.graph_data, query, type_filter=node_type)
        if include_full:
            return raw_results
        return [make_compact_node(n, include_full=False) for n in raw_results]

    def locate(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Finds file path, line numbers, and metadata for a symbol with type weighting."""
        from spashta_ckg.runtime.query_spashta import resolve_symbol_node
        winner, is_ambiguous, alts = resolve_symbol_node(self.graph_data, symbol)
        if winner:
            fpath = winner.get("file_path") or winner.get("file") or winner.get("scope")
            if not fpath and "::" in winner.get("id", ""):
                fpath = winner.get("id", "").split("::")[0]
            if fpath and fpath.startswith("File:"):
                fpath = fpath[5:]
            return {
                "id": winner.get("id"),
                "name": winner.get("name"),
                "node_type": winner.get("node_type") or winner.get("type"),
                "file_path": fpath,
                "line_start": winner.get("line_start"),
                "line_end": winner.get("line_end"),
                "semantic_roles": winner.get("semantic_roles", []),
                "ambiguous": is_ambiguous,
                "alternatives": alts
            }
        return None

    def impact(self, symbol: str, depth: int = 3) -> Dict[str, Any]:
        """Calculates upstream blast-radius: who depends on or calls this symbol, returned in universal envelope schema."""
        from spashta_ckg.runtime.query_spashta import resolve_symbol_node, trace_deps, make_envelope, get_node
        target_node, is_ambiguous, alts = resolve_symbol_node(self.graph_data, symbol)
        if not target_node:
            return make_envelope(
                command="impact",
                status="not_found",
                target={"query": symbol},
                error=f"Node not found: {symbol}",
                project_root=self.project_root
            )

        target_id = target_node.get("id")
        impact_map = trace_deps(self.graph_data, target_id, "incoming", depth)

        impacted_items = []
        breakdown = {}
        for nid, info in impact_map.items():
            n = get_node(self.graph_data, nid)
            ntype = info.get("node_type") or (n.get("node_type") if n else "Unknown")
            breakdown[ntype] = breakdown.get(ntype, 0) + 1
            fpath = info.get("file_path") or (n.get("file_path") if n else None) or (nid.split("::")[0] if "::" in nid else "")
            if fpath.startswith("File:"): fpath = fpath[5:]
            impacted_items.append({
                "id": nid,
                "name": info.get("name") or (n.get("name") if n else nid.split("::")[-1]),
                "node_type": ntype,
                "file_path": fpath,
                "line_start": info.get("line_start") or (n.get("line_start") if n else None),
                "relation": info.get("relation") or info.get("edge_type", "calls"),
                "depth": info.get("depth", 1)
            })

        # Check if all callers share identical parent module (discriminating check)
        parent_modules = {item.get("file_path", "") for item in impacted_items}
        is_discriminating = len(parent_modules) > 1 or len(impacted_items) <= 1

        target_info = {
            "query": symbol,
            "resolved_id": target_id,
            "name": target_node.get("name"),
            "node_type": target_node.get("node_type"),
            "file_path": target_node.get("file_path") or (target_id.split("::")[0] if "::" in target_id else None),
            "line_start": target_node.get("line_start"),
            "line_end": target_node.get("line_end")
        }

        summary = {
            "total_items": len(impacted_items),
            "returned_items": len(impacted_items),
            "truncated": False,
            "discriminating": is_discriminating,
            "breakdown": breakdown
        }

        return make_envelope(
            command="impact",
            status="ok",
            target=target_info,
            items=impacted_items,
            summary=summary,
            ambiguous=is_ambiguous,
            alternatives=alts,
            project_root=self.project_root
        )

    def can_delete(self, symbol: str, depth: int = 3) -> Dict[str, Any]:
        """Evaluates whether a symbol can be safely deleted without breaking working code."""
        from spashta_ckg.runtime.query_spashta import can_delete as qs_can_delete
        return qs_can_delete(self.graph_data, symbol, depth=depth, project_root=self.project_root)

    def dead_code(self, language: Optional[str] = None) -> Dict[str, Any]:
        """Identifies definitions with zero inbound usage edges with provenance."""
        from spashta_ckg.runtime.query_spashta import make_envelope
        referenced_targets = set()
        for e in self.edges:
            t = e.get("target", e.get("to"))
            if t:
                referenced_targets.add(str(t))

        dead_items = []
        breakdown = {}
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
                breakdown[ntype] = breakdown.get(ntype, 0) + 1
                dead_items.append({
                    "id": nid,
                    "name": name,
                    "node_type": ntype,
                    "semantic_roles": n.get("semantic_roles", []),
                    "file_path": n.get("file_path"),
                    "line_start": n.get("line_start")
                })

        all_files = {n.get("file_path") for n in self.nodes if n.get("file_path")}

        summary = {
            "total_candidates": len(dead_items),
            "total_items": len(dead_items),
            "returned_items": len(dead_items),
            "truncated": False,
            "breakdown": breakdown
        }

        provenance = {
            "files_analyzed": len(all_files),
            "symbols_considered": len(self.nodes),
            "language_filter": language
        }

        return make_envelope(
            command="dead_code",
            status="ok",
            items=dead_items,
            summary=summary,
            provenance=provenance,
            project_root=self.project_root,
            extra={
                "total_candidates": len(dead_items),
                "language_filter": language,
                "dead_items": dead_items
            }
        )

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
        """Returns high-level graph statistics in standardized schema."""
        from spashta_ckg.runtime.query_spashta import check_freshness
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
            "status": "ok",
            "command": "stats",
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "ambiguities": len(self.graph_data.get("ambiguities", [])),
            "node_breakdown": type_counts,
            "semantic_roles": role_counts,
            "edge_breakdown": edge_counts,
            "meta": self.graph_data.get("_meta", {}),
            "_meta": check_freshness(self.project_root)
        }
