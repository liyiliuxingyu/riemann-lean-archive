#!/usr/bin/env python3
"""Compile a UTF-8 CTeX book with the task-private compatible XeLaTeX tree.

Example:
  python build_pdf.py main.tex --output-dir build
  python build_pdf.py /absolute/path/main.tex --tex-root /path/runtime/tex_human

This wrapper does not edit the manuscript, download packages, or change global TeX
settings. It records the exact command, environment, diagnostics and PDF hash.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Main .tex file; its directory is the working directory")
    parser.add_argument("--output-dir", type=Path, help="Defaults to SOURCE_PARENT/build")
    parser.add_argument("--evidence-dir", type=Path, help="Defaults to SOURCE_PARENT/evidence/pdf_build")
    parser.add_argument("--tex-root", type=Path,
                        default=Path(__file__).resolve().parents[2]/"runtime"/"tex_human")
    args = parser.parse_args()
    source = args.source.resolve()
    if not source.is_file() or source.suffix.lower() != ".tex":
        parser.error("source must be an existing .tex file")
    tex_root = args.tex_root.resolve()
    setup_path = tex_root/"compatible_setup.json"
    setup = json.loads(setup_path.read_text(encoding="utf-8")) if setup_path.exists() else None
    if setup is not None and not setup.get("success"):
        raise SystemExit("Private XeLaTeX setup is incomplete")
    if setup is not None:
        overrides = json.loads((tex_root/"environment.json").read_text(encoding="utf-8"))
    else:
        # In a normal TeX Live installation the system supplies the format;
        # the package's small TEXMF tree supplies Chinese styles and fonts.
        bundled = Path(__file__).resolve().parent/"texmf"
        overrides = {"TEXINPUTS":".:"}
        if bundled.exists():
            overrides["TEXMFHOME"] = str(bundled)
            overrides["TEXINPUTS"] = str(bundled/"tex")+"//:.:"
    env = os.environ.copy()
    env.update(overrides)
    # Chapter paths resolve from the manuscript's own directory. All original
    # system packages remain read-only through the explicit TEXMF search tree.
    env["TEXINPUTS"] = str(source.parent)+"//:"+overrides["TEXINPUTS"]
    out_dir = (args.output_dir or source.parent/"build").resolve()
    evidence = (args.evidence_dir or source.parent/"evidence"/"pdf_build").resolve()
    out_dir.mkdir(parents=True,exist_ok=True)
    evidence.mkdir(parents=True,exist_ok=True)
    command = ["latexmk", "-norc", "-xelatex", "-interaction=nonstopmode", "-halt-on-error",
               "-file-line-error", "-latexoption=-no-shell-escape", "-outdir="+str(out_dir), source.name]
    report = {"started_at_utc":datetime.now(timezone.utc).isoformat(),"source":str(source),
              "source_sha256":sha(source),"command":command,"cwd":str(source.parent),
              "private_tex_root":str(tex_root) if setup is not None else None,
              "setup_sha256":sha(setup_path) if setup is not None else None,
              "environment":{k:env[k] for k in overrides},"system_global_settings_modified":False}
    started = time.monotonic()
    result = subprocess.run(command,cwd=source.parent,env=env,capture_output=True,text=True)
    process_log = evidence/(source.stem+".latexmk.log")
    process_log.write_text(result.stdout+"\nSTDERR:\n"+result.stderr,encoding="utf-8")
    report.update(exit_code=result.returncode,elapsed_seconds=round(time.monotonic()-started,3),
                  process_log=str(process_log))
    latex_log_path = out_dir/(source.stem+".log")
    log = latex_log_path.read_text(encoding="utf-8",errors="replace") if latex_log_path.exists() else ""
    report["diagnostics"] = {
        "missing_character_lines":[line for line in log.splitlines() if "Missing character:" in line],
        "overfull_boxes":[line for line in log.splitlines() if "Overfull " in line],
        "undefined_reference_warning":bool(re.search(r"undefined references|Reference .+ undefined|Citation .+ undefined",log)),
        "font_warning_lines":[line for line in log.splitlines() if "Font Warning:" in line],
    }
    pdf = out_dir/(source.stem+".pdf")
    report["success"] = result.returncode == 0 and pdf.is_file()
    if report["success"]:
        info = subprocess.run(["pdfinfo",str(pdf)],capture_output=True,text=True,check=True).stdout
        (evidence/(source.stem+".pdfinfo.txt")).write_text(info,encoding="utf-8")
        pages = re.search(r"^Pages:\s+(\d+)",info,re.MULTILINE)
        report.update(pdf=str(pdf),pdf_bytes=pdf.stat().st_size,pdf_sha256=sha(pdf),
                      pages=int(pages.group(1)) if pages else None)
    report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    record_path = evidence/(source.stem+".build.json")
    record_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if not report["success"]:
        print(result.stdout[-5000:])
        print(result.stderr[-2000:])
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
