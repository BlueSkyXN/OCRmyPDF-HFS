#!/usr/bin/env python3
"""Safely plan or publish one verified OCRmyPDF HFS wrapper bundle.

The script deliberately uses the Hugging Face HTTP API instead of a credential-bearing
Git URL. ``--apply`` is required for writes. If the current Space contains files outside
the wrapper allowlist, publishing fails. Legacy cleanup is deliberately outside this tool.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

MANAGED_FILES = {
    ".dockerignore",
    "BUILD_SOURCE.json",
    "Dockerfile",
    "README.md",
    "entrypoint.sh",
    "hfs-dev.toml",
}
ALLOWED_REMOTE_FILES = MANAGED_FILES | {".gitattributes"}
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def verify_bundle_contract(bundle_dir: Path) -> None:
    """Apply the same immutable source-wrapper gate before a direct publish."""
    verifier = Path(__file__).with_name("verify_space_bundle.sh")
    try:
        result = subprocess.run([str(verifier), str(bundle_dir)], check=False)
    except OSError as exc:
        fail(f"cannot run local wrapper verifier: {exc}")
    if result.returncode != 0:
        fail("bundle failed the local source-wrapper verification gate")


def load_bundle(bundle_dir: Path, source_ref: str) -> None:
    if not bundle_dir.is_dir():
        fail(f"bundle directory does not exist: {bundle_dir}")
    actual_files = {
        path.relative_to(bundle_dir).as_posix()
        for path in bundle_dir.rglob("*")
        if path.is_file()
    }
    if actual_files != MANAGED_FILES:
        fail(f"bundle file set is not the wrapper allowlist: {sorted(actual_files)}")
    if any(path.is_symlink() for path in bundle_dir.rglob("*")):
        fail("bundle must not contain symbolic links")
    verify_bundle_contract(bundle_dir)

    try:
        provenance = json.loads((bundle_dir / "BUILD_SOURCE.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read BUILD_SOURCE.json: {exc}")
    if provenance.get("source_ref") != source_ref or not COMMIT_RE.fullmatch(source_ref):
        fail("source-ref must be the full commit recorded in BUILD_SOURCE.json")
    if provenance.get("source_repository") != "https://github.com/BlueSkyXN/OCRmyPDF-HFS.git":
        fail("BUILD_SOURCE.json does not name the canonical public source repository")


def remote_file_paths(api: object, space: str) -> set[str]:
    entries = api.list_repo_tree(repo_id=space, repo_type="space", recursive=True, expand=False)
    return {entry.path for entry in entries if hasattr(entry, "path") and getattr(entry, "type", "file") == "file"}


def verify_remote_contents(
    download: Callable[..., str], space: str, revision: str, bundle_dir: Path, token: str
) -> None:
    """Read every managed file from the written revision and compare exact bytes."""
    with tempfile.TemporaryDirectory(prefix="ocrmypdf-hfs-readback-") as temporary_dir:
        destination = Path(temporary_dir)
        for path in sorted(MANAGED_FILES):
            downloaded = download(
                repo_id=space,
                repo_type="space",
                filename=path,
                revision=revision,
                local_dir=destination,
                token=token,
            )
            if Path(downloaded).read_bytes() != (bundle_dir / path).read_bytes():
                fail(f"post-write content readback differs for {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--space", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--apply", action="store_true", help="perform the remote write")
    parser.add_argument("--require-private", action="store_true", help="refuse a non-private target Space")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_bundle(args.bundle.resolve(), args.source_ref)
    print(f"Verified local wrapper bundle for {args.space} at {args.source_ref}")
    print("Managed files:")
    for path in sorted(MANAGED_FILES):
        print(f"  - {path}")

    if not args.apply:
        print("Dry run only; no remote request or write was made.")
        return 0

    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        fail("HF_TOKEN is required only for --apply")
    try:
        from huggingface_hub import (
            CommitOperationAdd,
            HfApi,
            hf_hub_download,
        )
    except ImportError:
        fail("huggingface_hub is required for --apply")

    api = HfApi(token=token)
    info_before = api.repo_info(repo_id=args.space, repo_type="space")
    if args.require_private and not info_before.private:
        fail("candidate Space must be private")
    remote_before = remote_file_paths(api, args.space)
    unexpected = sorted(remote_before - ALLOWED_REMOTE_FILES)
    if unexpected:
        fail(
            "remote Space contains non-wrapper files; cleanup requires a separate owner-approved procedure: "
            + ", ".join(unexpected)
        )

    operations = [
        CommitOperationAdd(path_in_repo=path, path_or_fileobj=args.bundle / path)
        for path in sorted(MANAGED_FILES)
    ]
    commit = api.create_commit(
        repo_id=args.space,
        repo_type="space",
        operations=operations,
        commit_message=f"Deploy OCRmyPDF HFS wrapper for {args.source_ref}",
    )

    remote_after = remote_file_paths(api, args.space)
    missing = sorted(MANAGED_FILES - remote_after)
    remaining_unexpected = sorted(remote_after - ALLOWED_REMOTE_FILES)
    if missing or remaining_unexpected:
        fail(
            "post-write readback failed; "
            f"missing={missing}, unexpected={remaining_unexpected}"
        )
    info = api.repo_info(repo_id=args.space, repo_type="space")
    if info.sha != commit.oid:
        fail(
            "post-write revision readback differs from the deployment commit; "
            f"expected={commit.oid}, actual={info.sha}"
        )
    verify_remote_contents(hf_hub_download, args.space, info.sha, args.bundle.resolve(), token)
    print(f"Post-write readback passed. Space revision: {info.sha}; commit URL: {commit.commit_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
