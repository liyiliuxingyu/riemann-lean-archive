#!/usr/bin/env python3
"""Fetch the nine locked public dependencies without their full Git histories.

Run from any directory. Existing repositories are reused only when their HEAD,
origin and tracked/untracked worktree state match the expected clean checkout.
An existing different checkout is never reset, replaced, or deleted.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import urlsplit

LOCK = {
    "mathlib": ("leanprover-community/mathlib4", "56a005855ea17e0b0958f73ec801ae140b0a1679"),
    "plausible": ("leanprover-community/plausible", "dfa4f38190d07c37e315953e08b90fe2d95b3c24"),
    "LeanSearchClient": ("leanprover-community/LeanSearchClient", "d6b4c7be5be75ec4917c873ac50c756dc1436372"),
    "importGraph": ("leanprover-community/import-graph", "a41f0e9a4dea23188ea9cc1c41ac9f8bbafe0b93"),
    "proofwidgets": ("leanprover-community/ProofWidgets4", "df72b022e558978a1c50264cfc4d7fec86fa8e04"),
    "aesop": ("leanprover-community/aesop", "4a174c490d8707121c4a9290800489f105d85e07"),
    "Qq": ("leanprover-community/quote4", "dce0ad79c486cb1fb504af04f953c3466b0c6db8"),
    "batteries": ("leanprover-community/batteries", "66e469188fe07963e5cf666c7d4433f45b8131c5"),
    "Cli": ("leanprover/lean4-cli", "c24fe6078c630e89b489bffe59b3e20ac30d12c8"),
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def canonical_url(url: str) -> str:
    parsed = urlsplit(url)
    require(parsed.scheme == "https" and parsed.hostname == "github.com"
            and parsed.port is None and not parsed.username and not parsed.password
            and not parsed.query and not parsed.fragment, "Only credential-free public GitHub HTTPS origins are allowed")
    path = parsed.path.removesuffix(".git")
    require(re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", path) is not None, "Invalid GitHub repository path")
    return "https://github.com" + path


def git(directory: Path, *args: str) -> str:
    env = dict(os.environ)
    for key in ("GH_TOKEN", "GITHUB_TOKEN"):
        env.pop(key, None)
    env["GIT_TERMINAL_PROMPT"] = "0"
    proc = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "credential.helper=", "-C", str(directory), *args],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=600,
    )
    # Do not echo remote/config text or credentials from inherited Git settings.
    require(proc.returncode == 0, f"Git {args[0]} failed for dependency {directory.name} (exit {proc.returncode})")
    return proc.stdout.strip()


def verify_checkout(directory: Path, url: str, revision: str) -> None:
    require(not directory.is_symlink(), f"Dependency path is a symlink: {directory.name}")
    require((directory / ".git").is_dir(), f"Existing dependency is not a standalone Git checkout: {directory.name}")
    require(Path(git(directory, "rev-parse", "--show-toplevel")).resolve() == directory.resolve(), "Unexpected repository root")
    require(git(directory, "rev-parse", "HEAD") == revision,
            f"Existing dependency HEAD differs; preserving it without reset: {directory.name}")
    require(canonical_url(git(directory, "config", "--get", "remote.origin.url")) == url,
            f"Existing dependency origin differs: {directory.name}")
    require(git(directory, "status", "--porcelain", "--untracked-files=all") == "",
            f"Existing dependency has local changes; preserving them: {directory.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--jobs", type=int, choices=(1, 2, 3, 4), default=3)
    parser.add_argument("--check-only", action="store_true", help="Verify existing dependencies; never create or fetch")
    args = parser.parse_args()
    project = args.project_dir.resolve(strict=True)
    manifest = json.loads((project / "lake-manifest.json").read_text(encoding="utf-8"))
    require(manifest.get("packagesDir") == ".lake/packages", "Unexpected Lake packages directory")
    packages = manifest.get("packages", [])
    require(len(packages) == len(LOCK) and {p.get("name") for p in packages} == set(LOCK), "Manifest package set differs from the fixed nine dependencies")
    checked = []
    for package in packages:
        name = package["name"]
        repository, revision = LOCK[name]
        url = canonical_url(package["url"])
        require(package.get("type") == "git" and package.get("subDir") is None, f"Unexpected dependency kind: {name}")
        require(re.fullmatch(r"[0-9a-f]{40}", package.get("rev", "")) is not None, "Revision must be an exact Git SHA")
        require(package["rev"] == revision and url == "https://github.com/" + repository, f"Dependency lock changed: {name}")
        checked.append((name, url, revision))
    destination = project / ".lake" / "packages"
    require(destination.resolve().is_relative_to(project), "Dependency directory escapes this project")
    if not args.check_only:
        destination.mkdir(parents=True, exist_ok=True)

    def prepare(item):
        name, url, revision = item
        target = destination / name
        if target.exists() or target.is_symlink():
            verify_checkout(target, url, revision)
            return {"name": name, "revision": revision, "action": "verified_existing"}
        require(not args.check_only, f"Dependency is missing: {name}")
        temporary = Path(tempfile.mkdtemp(prefix=f".bootstrap-{name}-", dir=destination))
        try:
            git(temporary, "init", "-q")
            git(temporary, "remote", "add", "origin", url)
            git(temporary, "fetch", "--depth", "1", "origin", revision)
            git(temporary, "checkout", "--detach", revision)
            verify_checkout(temporary, url, revision)
            require(not target.exists() and not target.is_symlink(), f"Dependency appeared concurrently; preserving it: {name}")
            # rename refuses an existing nonempty repository; no overwrite/reset.
            temporary.rename(target)
            return {"name": name, "revision": revision, "action": "shallow_fetched"}
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for result in pool.map(prepare, checked):
            print(json.dumps(result), flush=True)


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print(json.dumps({"passed": False, "error": str(error)}), flush=True)
        raise SystemExit(1)
