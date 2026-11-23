#!/usr/bin/env python3
"""Small, meaningful integrity/round-trip tests for the independent verifier.

Fixture compression uses Python zstandard only. The production verifier is C++.
Corrupt-text fixtures have their compressed hashes recomputed so that row
structure checks, rather than an incidental compressed-hash mismatch, catch them.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tempfile
import zstandard


HERE = Path(__file__).resolve().parent
BASE = HERE.parent
BIN = HERE / "verify_annotations"
RESULTS = []


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fixture(root, name, groups):
    """Each group contains pairs (annotation bytes including LF, original bytes)."""
    directory = root / name
    directory.mkdir()
    entries = []
    line_number = 1
    all_original = b""
    for i, group in enumerate(groups, 1):
        original = b"".join(raw for _, raw in group)
        annotated = b"".join(comment + raw for comment, raw in group)
        compressed = zstandard.ZstdCompressor(level=1, write_checksum=True).compress(annotated)
        filename = f"test.part{i:03}.txt.zst"
        (directory / filename).write_bytes(compressed)
        entries.append({
            "file": filename, "first_line": line_number,
            "last_line": line_number + len(group) - 1, "records": len(group),
            "original_bytes": len(original), "original_sha256": sha(original),
            "annotated_bytes": len(annotated), "compressed_bytes": len(compressed),
            "compressed_sha256": sha(compressed),
        })
        all_original += original
        line_number += len(group)
    write_manifest(directory, entries)
    return directory, all_original, entries


def write_manifest(directory, entries):
    (directory / "parts.jsonl").write_text("".join(json.dumps(e, separators=(",", ":")) + "\n" for e in entries))


def run_case(name, directory, original, *, valid, restore=False, small_buffer=True, expected_sha=None, error_contains=None):
    cmd = [str(BIN), "--manifest", str(directory / "parts.jsonl"),
           "--expected-bytes", str(len(original)), "--expected-sha256", expected_sha or sha(original)]
    if small_buffer:
        cmd += ["--io-buffer-bytes", "257"]
    target = directory / "restored.ndjson"
    if restore:
        cmd += ["--restore", str(target)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if valid:
        assert result.returncode == 0, (name, result.stderr)
        report = json.loads(result.stdout)
        assert report["success"] and report["original_sha256"] == sha(original)
        assert report["original_bytes"] == len(original)
        assert report["last_original_line_has_lf"] == original.endswith(b"\n")
        if restore:
            assert target.read_bytes() == original, name
            assert not Path(str(target) + ".partial").exists()
        else:
            assert not target.exists()
        RESULTS.append({"name": name, "passed": True, "accepted": True,
                        "records": report["records"], "parts": report["parts_verified"],
                        "elapsed_seconds": report["elapsed_seconds"]})
    else:
        assert result.returncode != 0, (name, "Unexpected successful verification")
        message = json.loads(result.stderr.splitlines()[-1])["message"]
        if error_contains:
            assert error_contains in message, (name, message)
        assert not target.exists(), (name, "Failure must not publish a restored file")
        RESULTS.append({"name": name, "passed": True, "accepted": False, "detected_error": message})


def main():
    with tempfile.TemporaryDirectory(prefix="verify_annotations_tests_", dir=BASE / "benchmark") as temp:
        root = Path(temp)
        # Use actual engine output, not a reimplementation of its annotations.
        actual = BASE / "benchmark" / "prefix_output_v2"
        with (actual / "solution_annotated.part001.txt.zst").open("rb") as source:
            annotated = zstandard.ZstdDecompressor().stream_reader(source).read()
        lines = annotated.splitlines(keepends=True)
        pairs = [(lines[2*i], lines[2*i+1]) for i in range(64)]
        original_prefix = (BASE / "source" / "prefix.ndjson").read_bytes()
        run_case("actual_engine_prefix_all_147492_rows", actual, original_prefix,
                 valid=True, small_buffer=False)

        groups = [pairs[:5], pairs[5:28], pairs[28:]]
        directory, raw, entries = fixture(root, "cross_volume_with_lf", groups)
        run_case("cross_volume_with_lf_and_small_io_fragments", directory, raw, valid=True, restore=True)

        no_lf = list(pairs)
        no_lf[-1] = (no_lf[-1][0], no_lf[-1][1].removesuffix(b"\n"))
        directory, raw, entries = fixture(root, "cross_volume_no_final_lf", [no_lf[:5], no_lf[5:28], no_lf[28:]])
        run_case("cross_volume_preserves_absent_final_lf", directory, raw, valid=True, restore=True)

        crlf = [(b"-- @line 1 first\n", b'{"a":1}\r\n'), (b"-- @line 2 second\n", b'{"b":2}\r\n')]
        directory, raw, entries = fixture(root, "crlf_source", [crlf])
        run_case("preserves_original_crlf", directory, raw, valid=True, restore=True)

        huge = [(b"-- @line 1 " + "说明".encode() + b"x" * (1024*1024) + b"\n",
                 b'{"long":"' + b"y" * (1024*1024) + b'"}')]
        directory, raw, entries = fixture(root, "long_lines", [huge])
        run_case("very_long_lines_with_no_final_lf", directory, raw, valid=True, restore=True)

        for name, replacement, needle in [
            ("damaged_comment_prefix", b"#- @line 2 corrupted\n", "Bad annotation prefix"),
            ("wrong_comment_number", b"-- @line 9 wrong number\n", "not globally consecutive"),
            ("empty_comment", b"-- @line 2 \t \r\n", "Empty annotation text"),
            ("missing_comment", b"", "Bad annotation prefix"),
            ("extra_comment", b"-- @line 2 extra\n-- @line 2 duplicate\n", "JSON object"),
        ]:
            bad = list(pairs[:3])
            bad[1] = replacement, bad[1][1]
            directory, raw, entries = fixture(root, name, [bad])
            run_case(name, directory, raw, valid=False, restore=True, error_contains=needle)

        bad_shape = [(b"-- @line 1 wrong source shape\n", b"[]\n")]
        directory, raw, entries = fixture(root, "invalid_source_shape", [bad_shape])
        run_case("invalid_source_shape", directory, raw, valid=False, error_contains="JSON object")

        earlier = list(pairs[:6])
        earlier[2] = earlier[2][0], earlier[2][1].removesuffix(b"\n")
        directory, raw, entries = fixture(root, "nonfinal_part_no_lf", [earlier[:3], earlier[3:]])
        run_case("nonfinal_part_no_lf", directory, raw, valid=False, error_contains="non-final volume")

        for name, field, value, needle in [
            ("wrong_compressed_hash", "compressed_sha256", "0" * 64, "Compressed SHA-256"),
            ("wrong_source_part_hash", "original_sha256", "0" * 64, "original SHA-256"),
            ("wrong_source_part_bytes", "original_bytes", 999999, "Invalid manifest byte counts"),
            ("wrong_last_line", "last_line", 99, "line ranges"),
            ("wrong_record_count", "records", 99, "line ranges"),
        ]:
            directory, raw, entries = fixture(root, name, [pairs[:3]])
            entries[0][field] = value
            write_manifest(directory, entries)
            run_case(name, directory, raw, valid=False, error_contains=needle)

        directory, raw, entries = fixture(root, "wrong_global_hash", [pairs[:3]])
        run_case("wrong_global_hash", directory, raw, valid=False, restore=True,
                 expected_sha="0" * 64, error_contains="Global original SHA-256")

        directory, raw, entries = fixture(root, "damaged_compressed", [pairs[:3]])
        path = directory / entries[0]["file"]
        data = bytearray(path.read_bytes())
        data[len(data)//2] ^= 1
        path.write_bytes(data)
        run_case("damaged_compressed_payload", directory, raw, valid=False)

        directory, raw, entries = fixture(root, "truncated_frame", [pairs[:3]])
        path = directory / entries[0]["file"]
        data = path.read_bytes()[:-1]
        path.write_bytes(data)
        entries[0]["compressed_bytes"] = len(data)
        entries[0]["compressed_sha256"] = sha(data)
        write_manifest(directory, entries)
        run_case("truncated_zstd_frame_even_with_matching_manifest_hash", directory, raw,
                 valid=False, error_contains="Truncated")

    report = {"success": True, "test_count": len(RESULTS), "tests": RESULTS,
              "scope": "Small actual-prefix and targeted round-trip/corruption tests; no full-source run"}
    destination = BASE / "benchmark" / "independent_verifier_tests.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
