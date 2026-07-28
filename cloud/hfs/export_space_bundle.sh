#!/usr/bin/env bash
# Export the deployable Space wrapper without copying product source or local state.
set -euo pipefail

readonly SOURCE_REPOSITORY="https://github.com/BlueSkyXN/OCRmyPDF-HFS.git"
readonly EXPECTED_FILES=(
    .dockerignore
    Dockerfile
    README.md
    entrypoint.sh
    hfs-dev.toml
)

usage() {
    printf 'Usage: %s --source-ref <40-char-commit> --base-image <tag@sha256> --manifest <file> --output <new-directory>\n' "$0" >&2
    exit 2
}

source_ref=""
output_dir=""
base_image=""
manifest_file=""
while (($#)); do
    case "$1" in
        --source-ref)
            source_ref="${2:-}"
            shift 2
            ;;
        --output)
            output_dir="${2:-}"
            shift 2
            ;;
        --base-image)
            base_image="${2:-}"
            shift 2
            ;;
        --manifest)
            manifest_file="${2:-}"
            shift 2
            ;;
        *)
            usage
            ;;
    esac
done

[[ "$source_ref" =~ ^[0-9a-f]{40}$ ]] || {
    printf '%s\n' 'source-ref must be a full lowercase 40-character Git commit.' >&2
    exit 2
}
[[ -n "$output_dir" ]] || usage
[[ "$base_image" =~ ^[^[:space:]@]+@sha256:[0-9a-f]{64}$ ]] || {
    printf '%s\n' 'base-image must be pinned with @sha256:<64 lowercase hex>.' >&2
    exit 2
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root_dir="$(cd -- "$script_dir/../.." && pwd)"
cd "$root_dir"
case "$manifest_file" in
    hfs-dev.toml|hfs-dev.candidate.toml) ;;
    *) printf '%s\n' 'manifest must be hfs-dev.toml or hfs-dev.candidate.toml.' >&2; exit 2 ;;
esac
[[ -f "$manifest_file" ]] || { printf 'Missing manifest: %s\n' "$manifest_file" >&2; exit 1; }

# Root Docker builds and exported Space builds must use the same runtime preflight.
# Refuse to create a deployment bundle if their fail-closed entrypoints diverge.
cmp -s "$script_dir/entrypoint.sh" "$root_dir/entrypoint.sh" || {
    printf '%s\n' 'Root and Space entrypoints differ; refuse to export a split runtime contract.' >&2
    exit 1
}

resolved_ref="$(git rev-parse --verify "${source_ref}^{commit}")"
[[ "$resolved_ref" == "$source_ref" ]] || {
    printf '%s\n' 'source-ref must resolve exactly to the requested commit.' >&2
    exit 1
}
[[ "$(git rev-parse HEAD)" == "$source_ref" ]] || {
    printf '%s\n' 'source-ref must be the checked-out deployment commit.' >&2
    exit 1
}

# A wrapper can only represent one committed source tree. Reject dirty or
# untracked deploy inputs rather than exporting an unverifiable mixed tree.
if ! git diff --quiet --exit-code; then
    printf '%s\n' 'Refusing to export a wrapper from unstaged changes.' >&2
    exit 1
fi
if ! git diff --cached --quiet --exit-code; then
    printf '%s\n' 'Refusing to export a wrapper from staged changes.' >&2
    exit 1
fi
if [[ -n "$(git ls-files --others --exclude-standard)" ]]; then
    printf '%s\n' 'Refusing to export a wrapper with untracked deploy inputs.' >&2
    exit 1
fi

if [[ -e "$output_dir" ]]; then
    printf 'Output directory already exists: %s\n' "$output_dir" >&2
    exit 1
fi
mkdir -p "$output_dir"

for relative_path in "${EXPECTED_FILES[@]}"; do
    source_path="$script_dir/$relative_path"
    if [[ "$relative_path" == "hfs-dev.toml" ]]; then
        source_path="$root_dir/$manifest_file"
    fi
    cp -p "$source_path" "$output_dir/$relative_path"
done

python3 - "$output_dir/Dockerfile" "$base_image" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
updated, count = re.subn(r"(?m)^ARG PYTHON_BASE_IMAGE=.*$", f"ARG PYTHON_BASE_IMAGE={sys.argv[2]}", text)
if count != 1:
    raise SystemExit("Space Dockerfile must declare PYTHON_BASE_IMAGE exactly once")
path.write_text(updated, encoding="utf-8")
PY

printf '{\n  "base_image": "%s",\n  "ocrmypdf_version": "16.0.4",\n  "pikepdf_version": "8.15.1",\n  "source_repository": "%s",\n  "source_ref": "%s"\n}\n' \
    "$base_image" "$SOURCE_REPOSITORY" "$source_ref" > "$output_dir/BUILD_SOURCE.json"

"$script_dir/verify_space_bundle.sh" "$output_dir"
printf 'Exported verified Space wrapper: %s\n' "$output_dir"
