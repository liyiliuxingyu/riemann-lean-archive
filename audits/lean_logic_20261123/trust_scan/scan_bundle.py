#!/usr/bin/env python3
"""Read exact source-record bytes, verify hashes, scan Lean trust-boundary syntax.

This is a conservative lexical review aid, not the Lean parser/elaborator/kernel.
It strips nested block comments, line comments, and ordinary/raw string literals.
Matches hidden in strings are separately retained for manual review (not silently
discarded), including possible interpolated-string expression code.
"""
import argparse
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import time

START = b"-- @LEAN_SOURCE_BUNDLE_FILE "
AUX = b"-- @LEAN_SOURCE_BUNDLE_AUX "
END = b"\n-- @LEAN_SOURCE_BUNDLE_END_FILE\n"
META = b"-- @LEAN_SOURCE_BUNDLE_META "
FOOTER = b"-- @LEAN_SOURCE_BUNDLE_COMPLETE "

KEYWORDS = [
    "sorry", "sorryAx", "admit", "axiom", "unsafe", "partial", "implemented_by",
    "extern", "native_decide", "ofReduceBool", "ofReduceNat", "run_tac", "run_elab",
    "run_cmd", "elab", "elab_rules", "macro", "macro_rules", "syntax", "initialize",
    "builtin_initialize", "register_option", "set_option", "trustLevel", "skipKernelTC",
    "debug.skipKernelTC", "addDecl", "addAndCompile", "addConst", "setEnv", "modifyEnv",
    "evalExpr", "evalConst", "mkSorry", "mkSyntheticSorry", "unsafeCast", "opaque",
    "implementedBy", "compiler_extract_closed", "compiler_csimp", "externC",
    "axiomDecl", "addDeclCore", "importModules", "withImportModules", "set_option_in",
    "native", "bv_decide", "trustCompiler", "run_meta", "run_io", "setKernelEnv",
    "mkEnvironment", "addAndCompileUnsafe", "addImportedFn", "mkThmOrUnsafeDef",
]
TOK = re.compile(rb"(?<![A-Za-z0-9_'])\b(?:" + b"|".join(re.escape(x.encode()) for x in sorted(KEYWORDS, key=len, reverse=True)) + rb")\b(?![A-Za-z0-9_'])")
COMMANDS = re.compile(rb"(?m)^\s*#(?:eval|reduce|check|print|guard|guard_msgs|exit|compile|import|assert|synth)\b")
MARKER = re.compile(rb'r#*"|/-|--|"')
BLOCK = re.compile(rb"/-|-/")
MASK = bytes(10 if x == 10 else 13 if x == 13 else 32 for x in range(256))


def masked_source(data):
    result = bytearray(data)
    cursor = 0
    stripped = []
    warnings = []
    while True:
        match = MARKER.search(data, cursor)
        if match is None:
            break
        start = match.start()
        marker = match.group()
        if marker == b"--":
            stop = data.find(b"\n", match.end())
            if stop < 0:
                stop = len(data)
            kind = "line_comment"
        elif marker == b"/-":
            pos, depth = match.end(), 1
            while depth:
                inner = BLOCK.search(data, pos)
                if inner is None:
                    warnings.append({"offset": start, "kind": "unterminated_block_comment"})
                    pos = len(data)
                    break
                depth += 1 if inner.group() == b"/-" else -1
                pos = inner.end()
            stop, kind = pos, "block_comment"
        elif marker.startswith(b"r"):
            terminator = b'"' + b"#" * (len(marker) - 2)
            end = data.find(terminator, match.end())
            if end < 0:
                warnings.append({"offset": start, "kind": "unterminated_raw_string"})
                stop = len(data)
            else:
                stop = end + len(terminator)
            kind = "raw_string"
        else:
            pos = match.end()
            while pos < len(data):
                if data[pos] == 92:
                    pos += 2
                elif data[pos] == 34:
                    pos += 1
                    break
                else:
                    pos += 1
            else:
                warnings.append({"offset": start, "kind": "unterminated_string"})
            stop, kind = pos, "string"
        if kind in ("string", "raw_string") and TOK.search(data[start:stop]):
            stripped.append({"offset": start, "end_offset": stop, "kind": kind,
                             "text": data[start:stop].decode("utf-8", errors="replace")})
        result[start:stop] = data[start:stop].translate(MASK)
        cursor = stop
    return bytes(result), stripped, warnings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    evidence_dir = args.output / "source_evidence"
    evidence_dir.mkdir(exist_ok=True)
    counts, module_counts = Counter(), Counter()
    modules = source_bytes = original_lines = aux_count = 0
    suspicious_modules = 0
    evidence_modules = 0
    option_counts = Counter()
    lexical_warnings, string_exclusions, shadow_modules = [], [], []
    seen = set()
    bundle_sha = hashlib.sha256()
    started = time.monotonic()
    with (args.output / "matches.jsonl").open("w", encoding="utf-8") as output, args.bundle.open("rb") as stream:
        while line := stream.readline():
            bundle_sha.update(line)
            if line.startswith(META):
                metadata = json.loads(line[len(META):])
            elif line.startswith(AUX):
                r = json.loads(line[len(AUX):])
                value = base64.b64decode(r["base64"], validate=True)
                assert len(value) == r["bytes"] and hashlib.sha256(value).hexdigest() == r["sha256"]
                aux_count += 1
                (args.output / r["path"]).write_bytes(value)
            elif line.startswith(START):
                r = json.loads(line[len(START):])
                assert r["path"] not in seen
                seen.add(r["path"])
                data = stream.read(r["bytes"])
                end = stream.read(len(END))
                bundle_sha.update(data)
                bundle_sha.update(end)
                assert len(data) == r["bytes"] and end == END
                assert hashlib.sha256(data).hexdigest() == r["sha256"], r["path"]
                modules += 1
                source_bytes += len(data)
                original_lines += r["lines"]
                if r["module"].split(".")[0] in {"Init", "Lean", "Std", "Mathlib", "Aesop", "Batteries", "Qq", "Lake", "Cli", "ProofWidgets", "Plausible", "LeanSearchClient", "ImportGraph"}:
                    shadow_modules.append(r)
                clean, strings, warnings = masked_source(data)
                for item in strings:
                    item.update(module=r["module"], path=r["path"], line=data.count(b"\n", 0, item["offset"]) + 1)
                    string_exclusions.append(item)
                for item in warnings:
                    item.update(module=r["module"], path=r["path"], line=data.count(b"\n", 0, item["offset"]) + 1)
                    lexical_warnings.append(item)
                matches = []
                for m in TOK.finditer(clean):
                    matches.append((m.start(), m.group().decode()))
                for m in COMMANDS.finditer(clean):
                    offset = m.end() - len(m.group().lstrip())
                    matches.append((offset, m.group().strip().decode()))
                seen_tokens = set()
                for offset, token in sorted(matches):
                    start_line = data.rfind(b"\n", 0, offset) + 1
                    end_line = data.find(b"\n", offset)
                    if end_line < 0:
                        end_line = len(data)
                    item = {"module": r["module"], "path": r["path"], "source_sha256": r["sha256"],
                            "line": data.count(b"\n", 0, offset) + 1, "token": token,
                            "code_line": data[start_line:end_line].decode("utf-8", errors="replace")}
                    output.write(json.dumps(item, ensure_ascii=False) + "\n")
                    counts[token] += 1
                    seen_tokens.add(token)
                    if token == "set_option":
                        option_counts[item["code_line"].split("set_option", 1)[1].strip()] += 1
                module_counts.update(seen_tokens)
                if matches or strings or warnings:
                    suspicious_modules += 1
                risky_option = re.search(rb"set_option\s+(?:allowUnsafeReducibility|quotPrecheck|hygiene|.*skipKernelTC|.*trustLevel)\b", clean)
                if seen_tokens - {"set_option"} or risky_option or strings or warnings:
                    evidence_modules += 1
                    destination = evidence_dir / r["path"]
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(data)
                if modules % 25000 == 0:
                    print(json.dumps({"modules_scanned": modules, "source_bytes": source_bytes, "elapsed_s": round(time.monotonic() - started, 2), "matches": sum(counts.values())}), flush=True)
            elif line.startswith(FOOTER):
                footer = json.loads(line[len(FOOTER):])
                assert footer == {"module_count": modules, "auxiliary_count": aux_count, "original_source_bytes": source_bytes}
                assert not stream.read()
                break
            else:
                assert line.startswith(b"--") or not line.strip()
    assert metadata["module_count"] == modules and metadata["original_source_bytes"] == source_bytes
    summary = {"bundle": str(args.bundle), "bundle_sha256": bundle_sha.hexdigest(),
               "module_count": modules, "source_bytes": source_bytes, "source_lines": original_lines,
               "auxiliary_count": aux_count, "all_embedded_hashes_match": True,
               "keyword_occurrences": {k: counts[k] for k in sorted(set(KEYWORDS) | set(counts))}, "modules_per_keyword": dict(sorted(module_counts.items())),
               "matched_source_modules": suspicious_modules, "source_evidence_modules": evidence_modules, "shadow_core_module_count": len(shadow_modules),
               "lexical_warning_count": len(lexical_warnings), "strings_with_keywords": len(string_exclusions),
               "elapsed_seconds": round(time.monotonic() - started, 2),
               "limits": ["Static lexical audit only; not Lean elaboration or kernel checking.",
                          "Does not recursively scan external dependency packages.",
                          "String literals are masked; literals containing keywords are separately retained for review.",
                          "Quoted identifiers and macro quotations require manual interpretation."]}
    for filename, obj in [("summary.json", summary), ("lexical_warnings.json", lexical_warnings),
                          ("strings_with_keywords.json", string_exclusions), ("shadow_modules.json", shadow_modules),
                          ("option_counts.json", dict(option_counts.most_common()))]:
        (args.output / filename).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
