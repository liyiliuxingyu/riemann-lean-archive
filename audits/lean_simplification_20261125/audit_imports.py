#!/usr/bin/env python3
"""Conservative, read-only Lean source import audit.

Writes reports and a proposed duplicate-import patch under --output.  Never edits
source files.  Graph reachability is not declaration dependency analysis or a
Lean elaboration/kernel check.  No third-party Python packages are required.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
import difflib
import hashlib
import heapq
import json
import os
from pathlib import Path
import re
import time
import tomllib


@dataclass(slots=True, frozen=True)
class Token:
    value: str
    start: int
    end: int
    line: int


@dataclass(slots=True, frozen=True)
class Import:
    target: str
    modifiers: tuple[str, ...]
    line: int
    start: int
    end: int


@dataclass(slots=True)
class Header:
    imports: list[Import]
    is_module: bool
    prelude: bool
    body_token: str | None

    @property
    def ordinary(self):
        return not self.is_module and not self.prelude and not any(i.modifiers for i in self.imports)


def token_stream(text):
    """Lex just enough for a standard header; respect nested/line comments.

    Quoted identifier components may contain whitespace and dots.  The generator
    stops being consumed at the first nonheader command, so strings and custom
    syntax in declarations never become fake imports.
    """
    pos, line, n = 0, 1, len(text)
    if text.startswith("\ufeff"):
        pos = 1
    while pos < n:
        ch = text[pos]
        if ch.isspace():
            line += ch == "\n"
            pos += 1
            continue
        if text.startswith("--", pos):
            end = text.find("\n", pos + 2)
            pos = n if end < 0 else end
            continue
        if text.startswith("/-", pos):
            depth = 1
            pos += 2
            while pos < n and depth:
                if text.startswith("/-", pos):
                    depth += 1
                    pos += 2
                elif text.startswith("-/", pos):
                    depth -= 1
                    pos += 2
                else:
                    line += text[pos] == "\n"
                    pos += 1
            if depth:
                raise ValueError("unterminated block comment in header")
            continue
        start, start_line, quoted = pos, line, False
        while pos < n:
            ch = text[pos]
            if quoted:
                if ch == "»":
                    quoted = False
                line += ch == "\n"
                pos += 1
            elif ch == "«":
                quoted = True
                pos += 1
            elif ch.isspace() or text.startswith("--", pos) or text.startswith("/-", pos):
                break
            else:
                pos += 1
        if quoted:
            raise ValueError("unterminated quoted identifier in header")
        yield Token(text[start:pos], start, pos, start_line)


def quote_component(part):
    return "«" + part + "»" if any(c in part for c in ". «»\t\r\n") else part


def normalize_module(raw):
    parts, current, quoted = [], [], False
    for ch in raw:
        if ch == "«" and not quoted:
            quoted = True
        elif ch == "»" and quoted:
            quoted = False
        elif ch == "." and not quoted:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    if quoted or any(not p for p in parts) or any(c in raw for c in '";()[]{}'):
        raise ValueError(f"unsupported import name {raw!r}")
    return ".".join(quote_component(p) for p in parts)


def parse_header(text):
    tokens = iter(token_stream(text))
    current = next(tokens, None)
    is_module = bool(current and current.value == "module")
    if is_module:
        current = next(tokens, None)
    prelude = bool(current and current.value == "prelude")
    if prelude:
        current = next(tokens, None)
    imports = []
    while current:
        start_token, modifiers = current, []
        while current and current.value in {"public", "meta"}:
            modifiers.append(current.value)
            current = next(tokens, None)
        if not current or current.value != "import":
            return Header(imports, is_module, prelude, start_token.value)
        import_line = current.line
        target = next(tokens, None)
        if target and target.value == "all":
            modifiers.append("all")
            target = next(tokens, None)
        if not target or target.value in {"import", "public", "meta", "module", "prelude"}:
            raise ValueError(f"missing import target at line {import_line}")
        imports.append(Import(normalize_module(target.value), tuple(modifiers), import_line, start_token.start, target.end))
        current = next(tokens, None)
    return Header(imports, is_module, prelude, None)


def semantics(header):
    return {
        "module": header.is_module,
        "prelude": header.prelude,
        "imports": [[i.target, list(i.modifiers)] for i in header.imports],
    }


def first_unique(header):
    return list(dict.fromkeys((i.target, i.modifiers) for i in header.imports))


def duplicate_patch(text, header, repo_path):
    seen, candidates, removed_lines = set(), [], set()
    lines = text.splitlines(keepends=True)
    for imp in header.imports:
        key = (imp.target, imp.modifiers)
        if key in seen:
            reason = None
            if not header.ordinary:
                reason = "advanced_or_prelude_header"
            line_start = text.rfind("\n", 0, imp.start) + 1
            line_end = text.find("\n", imp.end)
            if line_end < 0:
                line_end = len(text)
            if "\n" in text[imp.start:imp.end] or text[line_start:imp.start].strip() or text[imp.end:line_end].strip():
                reason = reason or "not_an_uncommented_standalone_import_line"
            if reason is None:
                removed_lines.add(imp.line)
            candidates.append({"module": imp.target, "modifiers": list(imp.modifiers), "line": imp.line, "proposed": reason is None, "skip_reason": reason})
        else:
            seen.add(key)
    if not removed_lines:
        return candidates, None, ""
    after = "".join(line for i, line in enumerate(lines, 1) if i not in removed_lines)
    after_header = parse_header(after)
    invariants = {
        "module_and_prelude_preserved": (header.is_module, header.prelude) == (after_header.is_module, after_header.prelude),
        "effective_direct_import_tuple_set_preserved": set(first_unique(header)) == set(first_unique(after_header)),
        "first_occurrence_tuple_sequence_preserved": first_unique(header) == first_unique(after_header),
        "remaining_source_bytes_unchanged": after == "".join(line for i, line in enumerate(lines, 1) if i not in removed_lines),
        "reachable_import_closure_preserved_by_identical_unique_adjacency": set(first_unique(header)) == set(first_unique(after_header)),
    }
    if not all(invariants.values()):
        raise AssertionError(f"duplicate patch invariant failed: {repo_path}")
    change = {
        "path": repo_path,
        "before_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "after_sha256": hashlib.sha256(after.encode("utf-8")).hexdigest(),
        "removed_lines": sorted(removed_lines),
        "before_header": semantics(header),
        "after_header": semantics(after_header),
        "invariants": invariants,
        "lean_compilation_performed": False,
    }
    diff = difflib.unified_diff(lines, after.splitlines(keepends=True), fromfile="a/" + repo_path, tofile="b/" + repo_path)
    patch = "".join(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n" for line in diff)
    return candidates, change, patch


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def closure(roots, adjacency):
    seen, todo = set(), list(roots)
    while todo:
        node = todo.pop()
        if node not in seen:
            seen.add(node)
            todo.extend(adjacency[node])
    return seen


def topological_order(adjacency):
    incoming = [[] for _ in adjacency]
    remaining = []
    for node, deps in enumerate(adjacency):
        remaining.append(len(deps))
        for dep in deps:
            incoming[dep].append(node)
    ready = [node for node, count in enumerate(remaining) if not count]
    heapq.heapify(ready)
    order = []
    while ready:
        node = heapq.heappop(ready)
        order.append(node)
        for user in incoming[node]:
            remaining[user] -= 1
            if not remaining[user]:
                heapq.heappush(ready, user)
    if len(order) != len(adjacency):
        blocked = [i for i, n in enumerate(remaining) if n]
        raise ValueError(f"import cycle or dependent modules: {blocked[:30]} ({len(blocked)} nodes)")
    return order, incoming


def transitive_candidates(adjacency, ordinary, names, output_path):
    """Exact reachability on legacy import paths, with bounded live bitsets.

    Every output records A->C together with another A->B and a certified graph
    path B->...->C.  External and modern-module nodes are opaque.  Bitsets are
    freed after their final importer has been processed.  No source is changed.
    """
    order, incoming = topological_order(adjacency)
    rank = [0] * len(order)
    for i, node in enumerate(order):
        rank[node] = i
    users_left = [len(v) for v in incoming]
    reach = [0] * len(order)
    counts, peak_bytes, live_bytes = Counter(), 0, 0
    with output_path.open("w", encoding="utf-8") as out:
        for index, node in enumerate(order):
            deps = adjacency[node]
            bits = 1 << rank[node]
            if ordinary[node]:
                covered, providers = 0, []
                for dep in sorted(deps, key=rank.__getitem__, reverse=True):
                    bit = 1 << rank[dep]
                    if covered & bit:
                        via = next(p for p in providers if reach[p] & bit)
                        row = {"source": names[node], "redundant_direct_import": names[dep], "also_directly_imported": names[via], "witness": "The also-directly-imported node transitively imports the redundant node through plain legacy headers.", "scope": "legacy_import_paths_with_external_modules_opaque", "deletion_authorized_by_analysis": False, "lean_compilation_performed": False}
                        out.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                        counts["candidates"] += 1
                    else:
                        providers.append(dep)
                    covered |= reach[dep]
                bits |= covered
            reach[node] = bits
            live_bytes += (bits.bit_length() + 7) // 8
            peak_bytes = max(peak_bytes, live_bytes)
            for dep in deps:
                users_left[dep] -= 1
                if not users_left[dep]:
                    live_bytes -= (reach[dep].bit_length() + 7) // 8
                    reach[dep] = 0
            if not users_left[node]:
                live_bytes -= (reach[node].bit_length() + 7) // 8
                reach[node] = 0
            if index and index % 25000 == 0:
                print(json.dumps({"phase": "transitive", "processed": index, "candidates": counts["candidates"], "live_bitset_bytes_estimate": live_bytes}), flush=True)
    return {"count": counts["candidates"], "peak_live_bitset_payload_bytes_estimate": peak_bytes, "exact_for_eligible_graph": True, "modern_module_headers_traversed": False, "external_dependency_contents_analyzed": False}


def configured_roots(config_path, source_root, names, local_count):
    if not config_path or not config_path.exists():
        return set(), {"verified": False, "reason": "lakefile.toml missing"}
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    configured_source_root = (config_path.parent / config.get("srcDir", ".")).resolve()
    if configured_source_root != source_root.resolve():
        return set(), {"verified": False, "reason": "package srcDir differs from scanned source root"}
    name_to_id = {name: i for i, name in enumerate(names[:local_count])}
    targets = config.get("defaultTargets", [])
    libraries = {lib["name"]: lib for lib in config.get("lean_lib", [])}
    executables = {exe["name"]: exe for exe in config.get("lean_exe", [])}
    all_roots, detail, errors = set(), [], []
    for target in targets:
        roots = set()
        if target in libraries:
            lib = libraries[target]
            if lib.get("srcDir", ".") not in {".", ""}:
                errors.append(f"unsupported target-specific srcDir: {target}")
                continue
            globs = lib.get("globs", lib.get("roots", [target]))
            for glob in globs:
                if glob.endswith(".+") or glob.endswith(".*"):
                    prefix = glob[:-2]
                    roots.update(i for name, i in name_to_id.items() if name.startswith(prefix + ".") or (glob.endswith(".*") and name == prefix))
                elif glob in name_to_id:
                    roots.add(name_to_id[glob])
                else:
                    errors.append(f"missing module selected by target {target}: {glob}")
            detail.append({"target": target, "globs": globs, "source_modules_selected": len(roots)})
        elif target in executables:
            root = executables[target].get("root", target)
            if root in name_to_id:
                roots.add(name_to_id[root])
            else:
                errors.append(f"missing executable root: {root}")
            detail.append({"target": target, "root": root, "source_modules_selected": len(roots)})
        elif target in name_to_id:
            roots.add(name_to_id[target])
            detail.append({"target": target, "source_modules_selected": 1})
        else:
            errors.append(f"unsupported or unknown default target: {target}")
        all_roots.update(roots)
    return all_roots, {"verified": bool(targets) and not errors, "default_targets": targets, "targets": detail, "errors": errors, "configuration_execution_performed": False}


def run(args):
    started = time.monotonic()
    root, output = args.source_root.resolve(), args.output.resolve()
    if output == root or root in output.parents:
        raise ValueError("output must not be inside the read-only source tree")
    output.mkdir(parents=True, exist_ok=True)
    paths = sorted(root.rglob("*.lean"))
    if any(p.is_symlink() for p in paths):
        raise ValueError("source symlinks are not accepted")
    names = [".".join(quote_component(s) for s in p.relative_to(root).with_suffix("").parts) for p in paths]
    if len(set(names)) != len(names):
        raise ValueError("module name collision in source tree")
    local_count = len(names)
    headers, hashes, errors, patch_changes, duplicate_rows = [], [], [], [], []
    root_counts, total_bytes, total_lines = Counter(), 0, 0
    patch_path = output / "direct_duplicates.patch"
    with patch_path.open("w", encoding="utf-8", newline="") as patch_stream:
        for n, (path, name) in enumerate(zip(paths, names)):
            raw = path.read_bytes()
            total_bytes += len(raw)
            total_lines += raw.count(b"\n") + int(bool(raw) and not raw.endswith(b"\n"))
            hashes.append(hashlib.sha256(raw).hexdigest())
            root_counts[name.split(".")[0]] += 1
            try:
                text = raw.decode("utf-8")
                header = parse_header(text)
            except (ValueError, UnicodeError) as exc:
                errors.append({"module": name, "error": str(exc)})
                header = Header([], True, False, "PARSE_ERROR")
            headers.append(header)
            repo_path = str(Path(args.repo_prefix) / path.relative_to(root))
            candidates, change, patch = duplicate_patch(text, header, repo_path) if not errors or errors[-1]["module"] != name else ([], None, "")
            for candidate in candidates:
                duplicate_rows.append({"source": name, "path": repo_path, **candidate})
            if change:
                patch_changes.append(change)
                patch_stream.write(patch)
            if n and n % 25000 == 0:
                print(json.dumps({"phase": "parse", "processed": n, "duplicates": len(duplicate_rows)}), flush=True)
    write_jsonl(output / "parse_errors.jsonl", errors)
    write_jsonl(output / "duplicate_candidates.jsonl", duplicate_rows)
    write_jsonl(output / "duplicate_changes.jsonl", patch_changes)
    if errors:
        raise ValueError(f"{len(errors)} parse errors; graph audit aborted")
    local_ids = {name: i for i, name in enumerate(names)}
    all_imports = {i.target for header in headers for i in header.imports}
    external_names = sorted(all_imports - set(local_ids))
    names.extend(external_names)
    ids = {name: i for i, name in enumerate(names)}
    adjacency = [list(dict.fromkeys(ids[i.target] for i in h.imports)) for h in headers] + [[] for _ in external_names]
    ordinary = [h.ordinary for h in headers] + [False] * len(external_names)
    order, incoming = topological_order(adjacency)
    allowed = set(args.external_root)
    unresolved = [name for name in external_names if name.split(".")[0] not in allowed]
    write_json(output / "unresolved_imports.json", unresolved)
    write_jsonl(output / "import_graph.jsonl", ({"module": names[n], "path": str(paths[n].relative_to(root)), "ordinary_legacy_header": h.ordinary, "import_only": h.body_token is None, "imports": semantics(h)["imports"]} for n, h in enumerate(headers)))
    entry_ids = [ids[name] for name in args.entry if name in local_ids]
    missing_entries = [name for name in args.entry if name not in local_ids]
    main_reach = closure(entry_ids, adjacency)
    build_roots, build_info = configured_roots(args.lakefile, root, names, local_count)
    build_reach = closure(build_roots, adjacency)
    outside_main = [names[i] for i in range(local_count) if i not in main_reach]
    outside_build = [names[i] for i in range(local_count) if i not in build_reach]
    write_json(output / "outside_entry_closure.json", outside_main)
    write_json(output / "outside_default_build_closure.json", outside_build)
    write_json(output / "lake_default_targets.json", build_info)
    digest_paths = defaultdict(list)
    for i, digest in enumerate(hashes):
        digest_paths[digest].append(i)
    content_groups = []
    for digest, group in sorted(digest_paths.items()):
        if len(group) > 1:
            content_groups.append({"sha256": digest, "copies": len(group), "all_import_only": all(headers[i].body_token is None for i in group), "modules": [{"module": names[i], "path": str(paths[i].relative_to(root)), "import_only": headers[i].body_token is None, "ordinary_legacy_header": headers[i].ordinary, "imports": semantics(headers[i])["imports"], "direct_importer_count": len(incoming[i]), "direct_importers": [names[j] for j in incoming[i]], "in_entry_closure": i in main_reach, "in_default_build_closure": i in build_reach} for i in group], "module_deletion_justified": False})
    write_json(output / "duplicate_content_modules.json", content_groups)
    transitive_info = {"performed": False}
    if not args.skip_transitive:
        transitive_info = {"performed": True, **transitive_candidates(adjacency, ordinary, names, output / "transitive_candidates.jsonl")}
    raw_internal = sum(i.target in local_ids for h in headers for i in h.imports)
    unique_internal = sum(dep < local_count for deps in adjacency[:local_count] for dep in deps)
    summary = {
        "source_root": str(root), "lean_files": local_count, "lean_bytes": total_bytes, "physical_lines": total_lines,
        "root_counts": dict(sorted(root_counts.items())), "raw_import_occurrences": sum(len(h.imports) for h in headers),
        "raw_internal_import_occurrences": raw_internal, "unique_internal_edges": unique_internal,
        "unique_all_edges": sum(map(len, adjacency)), "external_modules": external_names,
        "external_roots_assumed": sorted(allowed), "unresolved_import_count": len(unresolved),
        "internal_import_graph_acyclic": len(order) == len(adjacency), "parse_errors": len(errors),
        "advanced_or_prelude_headers": sum(not h.ordinary for h in headers), "import_only_modules": sum(h.body_token is None for h in headers),
        "entry_modules": args.entry, "missing_entry_modules": missing_entries, "entry_closure_internal_modules": sum(i < local_count for i in main_reach),
        "outside_entry_closure_count": len(outside_main), "default_build_configuration_supported": build_info["verified"],
        "default_build_roots": len(build_roots), "default_build_closure_internal_modules": sum(i < local_count for i in build_reach),
        "outside_default_build_closure_count": len(outside_build), "exact_duplicate_import_occurrences": len(duplicate_rows),
        "proposed_duplicate_line_removals": sum(len(row["removed_lines"]) for row in patch_changes), "proposed_changed_files": len(patch_changes),
        "duplicate_content_groups": len(content_groups), "duplicate_content_copies": sum(g["copies"] for g in content_groups),
        "duplicate_content_groups_all_import_only": sum(g["all_import_only"] for g in content_groups),
        "transitive": transitive_info, "source_files_modified": False, "lean_compilation_performed": False,
        "declaration_dependencies_analyzed": False, "main_proof_minimality_established": False,
        "duplicate_patch_static_guarantee": "Only later uncommented standalone repeated ordinary imports are removed; module/prelude flags, distinct import tuples, first-occurrence tuple sequence and hence the explicit module graph/closure are preserved.",
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    write_json(output / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--lakefile", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo-prefix", default="project/lean/original/src")
    parser.add_argument("--entry", action="append", default=[])
    parser.add_argument("--external-root", action="append", default=[])
    parser.add_argument("--skip-transitive", action="store_true")
    options = parser.parse_args()
    options.entry = options.entry or ["Main"]
    options.external_root = options.external_root or ["Mathlib", "Lean", "Batteries", "Init"]
    run(options)
