#!/usr/bin/env python3
"""Independent byte-roundtrip and malformed-input tests for the streaming splitter."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--sample", type=Path, required=True,
                    help="The 147,492-record real sample TXT; its .txt.zst sibling is required")
parser.add_argument("--binary", type=Path, default=HERE / "split_annotations")
args = parser.parse_args()
BIN = args.binary.resolve()
SAMPLE = args.sample.resolve()
RESULTS = []


def compress(raw, output):
    completed = subprocess.run(["zstd", "-q", "-c"], input=raw, capture_output=True, check=True)
    output.write_bytes(completed.stdout)


def run_case(name, raw, first, last, cap, *, allowed_no_lf=False,
             expect_success=True, expected_error=None, compressed=None,
             leave_chunk=False, bad_ack=False, existing_chunk=False):
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="case_", dir=HERE) as folder:
        root = Path(folder)
        source, out = root / "input.zst", root / "out"
        out.mkdir()
        if compressed is None:
            compress(raw, source)
        else:
            source.write_bytes(compressed)
        if existing_chunk:
            (out / "chunk0001.txt").write_bytes(b"do not replace")
        args = [str(BIN), "--source", str(source), "--out", str(out),
                "--first", str(first), "--last", str(last), "--max-bytes", str(cap)]
        if allowed_no_lf:
            args.append("--allow-final-no-lf")
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, encoding="utf-8")
        concatenated = bytearray()
        events, complete = [], None
        next_line = first
        for event_line in process.stdout:
            event = json.loads(event_line)
            if event["type"] == "chunk":
                events.append(event)
                path = out / event["file"]
                content = path.read_bytes()
                assert content and len(content) <= cap
                assert len(content) == event["bytes"]
                assert hashlib.sha256(content).hexdigest() == event["sha256"]
                lines = content.splitlines(keepends=True)
                assert len(lines) % 2 == 0
                labels = []
                for i in range(0, len(lines), 2):
                    match = re.match(rb"-- @line ([1-9][0-9]*) ", lines[i])
                    assert match
                    labels.append(int(match[1]))
                    assert lines[i].endswith(b"\n")
                    assert lines[i + 1].strip().startswith(b"{")
                    assert lines[i + 1].strip().endswith(b"}")
                assert labels == list(range(next_line, next_line + len(labels)))
                assert event["first_line"] == labels[0]
                assert event["last_line"] == labels[-1]
                assert event["records"] == len(labels)
                next_line += len(labels)
                concatenated.extend(content)
                if not leave_chunk:
                    path.unlink()
                process.stdin.write("wrong\n" if bad_ack else "ok\n")
                process.stdin.flush()
            elif event["type"] == "complete":
                assert complete is None
                complete = event
            else:
                raise AssertionError(event)
        process.stdin.close()
        stderr = process.stderr.read()
        code = process.wait(timeout=15)
        if expect_success:
            assert code == 0, (name, code, stderr)
            assert complete is not None
            assert bytes(concatenated) == raw
            originals = b"".join(raw.splitlines(keepends=True)[1::2])
            assert complete["annotated_sha256"] == hashlib.sha256(raw).hexdigest()
            assert complete["annotated_bytes"] == len(raw)
            assert complete["original_sha256"] == hashlib.sha256(originals).hexdigest()
            assert complete["original_bytes"] == len(originals)
            assert complete["records"] == last - first + 1
            assert complete["chunks"] == len(events)
            assert complete["last_original_has_lf"] == raw.endswith(b"\n")
            pairs = raw.splitlines(keepends=True)
            assert complete["maximum_record_pair_bytes"] == max(len(pairs[i]) + len(pairs[i + 1]) for i in range(0, len(pairs), 2))
            assert not list(out.iterdir())
        else:
            assert code != 0, name
            assert complete is None, name
            if expected_error is not None:
                assert expected_error in stderr, (name, stderr)
        if existing_chunk:
            assert (out / "chunk0001.txt").read_bytes() == b"do not replace"
        result = {"name": name, "passed": True, "success_expected": expect_success,
                  "chunks_emitted": len(events), "seconds": round(time.monotonic() - start, 3)}
        RESULTS.append(result)
        print(json.dumps(result), flush=True)
        return complete


sample = SAMPLE.read_bytes()
meta = run_case("real_sample_forced_1MiB_chunks", sample, 1, 147492, 1024 * 1024,
               compressed=SAMPLE.with_suffix(".txt.zst").read_bytes())
assert meta["original_bytes"] == 7864317
assert meta["original_sha256"] == "f959708c341f065e3b4e29df328f385eb34481462bf1ba9a3fe9c94dc3091380"

small = b'-- @line 10 alpha\n{"a":1}\n-- @line 11 beta\n{"b":2}\n'
run_case("non_one_start_exact_pair_cap", small, 10, 11, len(small.splitlines(keepends=True)[0]) + len(small.splitlines(keepends=True)[1]))
run_case("CRLF_preserved", small.replace(b"\n", b"\r\n"), 10, 11, 40)
run_case("final_original_without_LF", small[:-1], 10, 11, 40, allowed_no_lf=True)
run_case("no_LF_rejected_without_flag", small[:-1], 10, 11, 40, expect_success=False, expected_error="lacks final LF")
run_case("wrong_line_number", small.replace(b"@line 11", b"@line 12"), 10, 11, 40, expect_success=False, expected_error="Nonconsecutive")
run_case("empty_annotation", small.replace(b"alpha", b" \t\r"), 10, 11, 40, expect_success=False, expected_error="Empty annotation")
run_case("missing_original", b'-- @line 10 alpha\n', 10, 10, 40, expect_success=False, expected_error="missing its original")
run_case("bad_original_boundary", small.replace(b'{"a":1}', b'null'), 10, 11, 40, expect_success=False, expected_error="JSON object boundaries")
run_case("record_pair_over_limit", small, 10, 11, 5, expect_success=False, expected_error="exceeds max-bytes")
run_case("manifest_last_mismatch", small, 10, 12, 100, expect_success=False, expected_error="record range")
run_case("existing_chunk_not_overwritten", small, 10, 11, 100, expect_success=False, expected_error="without overwriting", existing_chunk=True)
run_case("ack_rejected", small, 10, 11, 100, expect_success=False, expected_error="acknowledge", bad_ack=True)
run_case("ack_requires_parent_cleanup", small, 10, 11, 100, expect_success=False, expected_error="still exists", leave_chunk=True)

packed = subprocess.run(["zstd", "-q", "-c"], input=small, capture_output=True, check=True).stdout
run_case("truncated_zstd", small, 10, 11, 100, compressed=packed[:-3], expect_success=False)
run_case("zstd_trailing_garbage", small, 10, 11, 100, compressed=packed + b"garbage", expect_success=False)
second = b'-- @line 12 gamma\n{"c":3}\n'
packed_second = subprocess.run(["zstd", "-q", "-c"], input=second, capture_output=True, check=True).stdout
run_case("concatenated_zstd_frames", small + second, 10, 12, 40, compressed=packed + packed_second)

long_pair = b'-- @line 1 ' + b'x' * (4 * 1024 * 1024 + 23) + b'\n{"s":"' + b'y' * (4 * 1024 * 1024 + 17) + b'"}\n'
run_case("lines_cross_decompression_buffers", long_pair, 1, 1, len(long_pair))
run_case("cross_buffer_pair_over_limit", long_pair, 1, 1, len(long_pair) - 1, expect_success=False, expected_error="exceeds max-bytes")

report = {"scope": "streaming split roundtrip and failure handling; not Lean proof verification", "passed": len(RESULTS), "failed": 0, "cases": RESULTS}
(HERE / "test_results.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"passed": len(RESULTS), "failed": 0}), flush=True)
