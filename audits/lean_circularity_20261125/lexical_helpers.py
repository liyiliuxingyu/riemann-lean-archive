#!/usr/bin/env python3
"""Lexical helpers reused from the archived source trust audit.

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

