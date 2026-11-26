#!/usr/bin/env python3
"""Check pinned source bytes and a static import graph; this is NOT a Lean checker.

Python 3.11+, standard library only. Run from any directory:
  python3 scripts/verify_sources.py --output /path/to/static-source-report.json
"""
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tomllib

REVISION = "72fead102f663d5c7a407964a13dc0cf9d977207"
REPOSITORY = "https://github.com/lsernau/grh-lean"
CONFIGS = {"lean-toolchain", "lake-manifest.json", "lakefile.toml"}
FORBIDDEN = set("axiom sorry admit unsafe implemented_by extern elab elab_rules macro syntax "
                "run_elab run_tac evalExpr addDecl partial skipKernelTC trustLevel ofReduceBool "
                "native_decide initialize builtin_initialize".split())
TOKEN = re.compile(r"[A-Za-z_][A-Za-z_0-9']*")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def masked_code(text):
    """Mask nested comments and ordinary string contents, retaining newlines.

    This conservative lexer covers the pinned source. It is not Lean's parser;
    quoted identifiers and general macro syntax are not semantically interpreted.
    """
    result, i, depth, string = [], 0, 0, False
    while i < len(text):
        if depth:
            if text.startswith("/-", i):
                depth += 1; result.extend("  "); i += 2
            elif text.startswith("-/", i):
                depth -= 1; result.extend("  "); i += 2
            else:
                result.append("\n" if text[i] == "\n" else " "); i += 1
        elif string:
            if text[i] == "\\" and i + 1 < len(text):
                result.extend("  "); i += 2
            elif text[i] == '"':
                string = False; result.append('"'); i += 1
            else:
                result.append("\n" if text[i] == "\n" else " "); i += 1
        elif text.startswith("--", i):
            end = text.find("\n", i)
            end = len(text) if end < 0 else end
            result.extend(" " * (end - i)); i = end
        elif text.startswith("/-", i):
            depth = 1; result.extend("  "); i += 2
        elif text[i] == '"':
            string = True; result.append('"'); i += 1
        else:
            result.append(text[i]); i += 1
    require(depth == 0 and not string, "Unclosed comment/string or unsupported lexical form")
    return "".join(result)


def imports(code):
    result = []
    for line in re.findall(r"^\s*(?:public\s+)?import\s+([^\n]+)", code, re.M):
        names = line.split()
        require(all(re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*", n)
                    for n in names), "Unsupported import syntax; use Lean to inspect the header")
        result.extend(names)
    return result


def safe_file(root, name):
    path = PurePosixPath(name)
    require(name == path.as_posix() and not path.is_absolute() and ".." not in path.parts
            and "\\" not in name and bool(path.parts), "Invalid manifest path: " + name)
    candidate = root.joinpath(*path.parts)
    require(not any(p.is_symlink() for p in (candidate, *candidate.parents) if p != root.parent),
            "Symlink is not allowed: " + name)
    require(stat.S_ISREG(candidate.stat().st_mode), "Not an ordinary file: " + name)
    require(candidate.resolve().is_relative_to(root), "Path escapes the project: " + name)
    return candidate


def verify(root):
    provenance_bytes = (root / "UPSTREAM.json").read_bytes()
    manifest = json.loads(provenance_bytes)
    require(manifest["schema"] == "grh-compact-import-v1", "Unknown provenance schema")
    require(manifest["source_repo"] == REPOSITORY and manifest["source_commit"] == REVISION
            and manifest["source_subdirectory"] == "grh-compact", "Unexpected pinned source")
    rows = manifest["source_files"]
    names = [row["path"] for row in rows]
    require(len(names) == len(set(names)), "Duplicate source manifest paths")
    require(not (root / "src").is_symlink(), "src must not be a symlink")
    require(not any(p.is_symlink() for p in (root / "src").rglob("*")), "Symlink under src")
    actual = {p.relative_to(root).as_posix() for p in (root / "src").rglob("*.lean")}
    require(set(names) == actual | CONFIGS, "Manifest differs from actual src files plus three configurations")
    graph, statistics = {}, dict(lean_files=0, lean_bytes=0, physical_lines=0,
                                nonblank_lines=0, noncomment_code_lines=0)
    for row in rows:
        name = row["path"]
        raw = safe_file(root, name).read_bytes()
        require(type(row["bytes"]) is int and len(raw) == row["bytes"], "Size mismatch: " + name)
        require(hashlib.sha256(raw).hexdigest() == row["sha256"], "SHA-256 mismatch: " + name)
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        require(blob == row["git_blob_sha1"], "Git blob mismatch: " + name)
        if name not in actual:
            continue
        text = raw.decode("utf-8")
        code = masked_code(text)
        found = sorted(set(TOKEN.findall(code)) & FORBIDDEN)
        require(not found, "Static trust keyword in " + name + ": " + ", ".join(found))
        module = ".".join(PurePosixPath(name).relative_to("src").with_suffix("").parts)
        graph[module] = imports(code)
        statistics["lean_files"] += 1
        statistics["lean_bytes"] += len(raw)
        statistics["physical_lines"] += len(text.splitlines())
        statistics["nonblank_lines"] += sum(bool(x.strip()) for x in text.splitlines())
        statistics["noncomment_code_lines"] += sum(bool(x.strip()) for x in code.splitlines())
    require("Main" in graph and "Statements" in graph, "Missing public entry modules")
    external = sorted({i for values in graph.values() for i in values if i not in graph})
    require(external == ["Mathlib"], "Unexpected external import: " + repr(external))
    require(not any(n.startswith("Lib.") and i.startswith("New.")
                    for n, values in graph.items() for i in values), "Lib imports New")
    require(not any(i == "Challenge" or i.startswith("Challenge.")
                    for values in graph.values() for i in values), "Production imports Challenge")
    degree = {n: sum(i in graph for i in set(values)) for n, values in graph.items()}
    users = {n: [] for n in graph}
    for n, values in graph.items():
        for i in set(values):
            if i in users:
                users[i].append(n)
    ready, ordered = deque(n for n in graph if degree[n] == 0), []
    while ready:
        n = ready.popleft(); ordered.append(n)
        for user in users[n]:
            degree[user] -= 1
            if degree[user] == 0:
                ready.append(user)
    require(len(ordered) == len(graph), "Explicit module import cycle")
    reached, pending = set(), ["Main"]
    while pending:
        n = pending.pop()
        if n not in reached:
            reached.add(n); pending.extend(i for i in graph[n] if i in graph)
    require(reached == set(graph), "Source modules outside Main import closure")
    challenge = masked_code(safe_file(root, "Challenge.lean").read_text())
    sorry_count = TOKEN.findall(challenge).count("sorry")
    require(sorry_count == 5 and imports(challenge) == ["Statements"], "Unexpected Challenge scaffold")
    options = tomllib.loads((root / "lakefile.toml").read_text())
    require("Challenge" not in options.get("defaultTargets", []), "Challenge is a default build target")
    return {"passed": True, "source_repo": REPOSITORY, "source_commit": REVISION,
            "manifest_sha256": hashlib.sha256(provenance_bytes).hexdigest(),
            "verified_source_and_config_files": len(rows), "statistics": statistics,
            "main_import_closure_size": len(reached), "import_graph_is_dag": True,
            "external_imports": external, "lib_imports_new": False, "forbidden_src_tokens": [],
            "challenge": {"excluded_from_production": True, "sorry_tokens": sorry_count,
                          "imported_by_src": False, "default_target": False},
            "scope": "Local manifest consistency and static lexical/import checks only. The manifest is not a signature. No Lean build, elaborated theorem-type comparison, axiom closure, kernel replay or mathematical correctness is established."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    target = args.output.resolve()
    require(not target.is_relative_to(root / "src") and target not in
            {root / p for p in CONFIGS | {"UPSTREAM.json", "Challenge.lean"}} and
            target != Path(__file__).resolve(), "Report must not overwrite project inputs")
    try:
        result = verify(root)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {"passed": False, "error": str(error), "scope": "Static source verification failed"}
    result["verifier_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
