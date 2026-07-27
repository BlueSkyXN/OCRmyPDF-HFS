#!/usr/bin/env bash
# Verify that an exported Space bundle is a wrapper, not a repository copy.
set -euo pipefail

readonly SOURCE_REPOSITORY="https://github.com/BlueSkyXN/OCRmyPDF-HFS.git"
readonly EXPECTED_FILES=$'.dockerignore\nBUILD_SOURCE.json\nDockerfile\nREADME.md\nentrypoint.sh\nhfs-dev.toml'

bundle_dir="${1:-}"
[[ -n "$bundle_dir" && -d "$bundle_dir" ]] || {
    printf 'Usage: %s <bundle-directory>\n' "$0" >&2
    exit 2
}

PYTHONDONTWRITEBYTECODE=1 python3 - "$bundle_dir" "$SOURCE_REPOSITORY" "$EXPECTED_FILES" <<'PY'
import json
import re
import sys
from pathlib import Path

bundle_dir = Path(sys.argv[1]).resolve()
expected_repository = sys.argv[2]
expected_files = set(sys.argv[3].splitlines())

files: set[str] = set()
for path in bundle_dir.rglob("*"):
    if path.is_symlink():
        raise SystemExit("Space bundle must not contain symbolic links.")
    if path.is_file():
        files.add(path.relative_to(bundle_dir).as_posix())
if files != expected_files:
    raise SystemExit(
        "Space bundle contains an unexpected or missing file. "
        f"Expected: {sorted(expected_files)}; actual: {sorted(files)}"
    )

build_source_path = bundle_dir / "BUILD_SOURCE.json"
try:
    build_source = json.loads(build_source_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(f"BUILD_SOURCE.json is invalid: {exc}") from exc
if set(build_source) != {"base_image", "ocrmypdf_version", "source_repository", "source_ref"}:
    raise SystemExit("BUILD_SOURCE.json has an unexpected provenance schema")
if build_source["source_repository"] != expected_repository:
    raise SystemExit("BUILD_SOURCE.json source_repository is not the canonical public repository")
if not re.fullmatch(r"[0-9a-f]{40}", build_source["source_ref"]):
    raise SystemExit("BUILD_SOURCE.json source_ref must be a full lowercase commit")
if not re.fullmatch(r"[^@\s]+@sha256:[0-9a-f]{64}", build_source["base_image"]):
    raise SystemExit("BUILD_SOURCE.json base_image must be an immutable digest")
if build_source["ocrmypdf_version"] != "16.0.4":
    raise SystemExit("BUILD_SOURCE.json must record the approved OCRmyPDF version")

dockerfile = (bundle_dir / "Dockerfile").read_text(encoding="utf-8")
if "jbarlow83/ocrmypdf-alpine" in dockerfile:
    raise SystemExit("Space Dockerfile must not inherit the legacy OCR business image.")
base_image = re.search(r"^ARG\s+PYTHON_BASE_IMAGE=([^\s]+)\s*$", dockerfile, flags=re.MULTILINE)
if base_image is None or not re.fullmatch(r"[^@\s]+@sha256:[0-9a-f]{64}", base_image.group(1)):
    raise SystemExit(
        "Space Dockerfile must pin PYTHON_BASE_IMAGE to an approved immutable sha256 digest "
        "before export."
    )
if base_image.group(1) != build_source["base_image"]:
    raise SystemExit("Dockerfile base image differs from BUILD_SOURCE.json")
if expected_repository not in dockerfile or f"ARG SOURCE_REPOSITORY={expected_repository}" not in dockerfile:
    raise SystemExit("Space Dockerfile must use the canonical public source repository")
if "checkout --detach \"$source_ref\"" not in dockerfile:
    raise SystemExit("Space Dockerfile must check out the declared source commit")
if 'test "$(git -C /opt/source rev-parse HEAD)" = "$source_ref"' not in dockerfile:
    raise SystemExit("Space Dockerfile must verify the checked-out source commit")
if "BUILD_SOURCE.json must contain a 40-character lowercase commit" not in dockerfile:
    raise SystemExit("Space Dockerfile must reject non-commit source provenance")

logical_lines: list[str] = []
current = ""
for raw_line in dockerfile.splitlines():
    stripped = raw_line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    current = f"{current} {stripped}".strip() if current else stripped
    if current.endswith("\\"):
        current = current[:-1].rstrip()
        continue
    logical_lines.append(current)
    current = ""
if current:
    raise SystemExit("Space Dockerfile has an unterminated continuation")

copy_instructions = [
    line for line in logical_lines if re.match(r"^(?:COPY|ADD)\b", line, flags=re.IGNORECASE)
]
expected_copies = {
    "COPY BUILD_SOURCE.json /opt/hfs/BUILD_SOURCE.json",
    "COPY entrypoint.sh /app/entrypoint.sh",
}
if set(copy_instructions) != expected_copies or len(copy_instructions) != len(expected_copies):
    raise SystemExit(
        "Space Dockerfile may only copy BUILD_SOURCE.json and entrypoint.sh; "
        f"actual copy/add instructions: {copy_instructions}"
    )

print(f"Verified thin Space wrapper: {bundle_dir}")
PY
