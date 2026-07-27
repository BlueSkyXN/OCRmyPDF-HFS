#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"

bash -n \
  entrypoint.sh \
  cloud/hfs/entrypoint.sh \
  cloud/hfs/export_space_bundle.sh \
  cloud/hfs/verify_space_bundle.sh \
  scripts/static-check.sh

PYTHONDONTWRITEBYTECODE=1 python3 - \
  main.py \
  test/test.py \
  cloud/hfs/sync_space_bundle.py \
  scripts/hf_space_sync.py <<'PY'
import sys
from pathlib import Path

for name in sys.argv[1:]:
    compile(Path(name).read_text(encoding="utf-8"), name, "exec")
PY

python3 - <<'PY'
import re
import tomllib
from pathlib import Path

production = tomllib.loads(Path("hfs-dev.toml").read_text(encoding="utf-8"))
candidate = tomllib.loads(Path("hfs-dev.candidate.toml").read_text(encoding="utf-8"))
expected = {
    "standard": "2.0",
    "project": "ocrmypdf-hfs",
    "space": "BlueSkyXN/OCRmyPDF-HFS",
    "sovereignty": "sovereign",
    "lane": "source",
    "version_source": "commit",
}
for key, value in expected.items():
    if production.get(key) != value:
        raise SystemExit(f"hfs-dev.toml {key} must be {value!r}")
if production.get("local_only") != ["HF_TOKEN", "GH_TOKEN"]:
    raise SystemExit("HFS control credentials must be local_only")
if production.get("secrets") != [] or production.get("variables") != []:
    raise SystemExit("OCRmyPDF currently has no Space Settings")
if candidate.get("space") != "BlueSkyXN/OCRmyPDF-HFS-v2-candidate":
    raise SystemExit("candidate manifest has the wrong Space id")
for key in sorted(set(production) | set(candidate)):
    if key != "space" and production.get(key) != candidate.get(key):
        raise SystemExit(f"candidate manifest differs from production at {key}")

workflow = Path(".github/workflows/sync-to-hf-space.yml").read_text(encoding="utf-8")
for fragment in (
    "workflow_dispatch:",
    "target:",
    "HFS_MANIFEST:",
    "docker buildx imagetools inspect",
    "--require-private",
    "confirm_deploy == 'deploy'",
):
    if fragment not in workflow:
        raise SystemExit(f"deploy workflow misses {fragment!r}")
for forbidden in ("allow-space-tree-prune", "CommitOperationDelete", "git push", "--force"):
    if forbidden in workflow or forbidden in Path("cloud/hfs/sync_space_bundle.py").read_text(encoding="utf-8"):
        raise SystemExit(f"deployment must not contain {forbidden!r}")

test_contract = Path("test/test.py").read_text(encoding="utf-8")
for fragment in ("--require-pdfa", "--max-output-bytes", "--max-seconds", "--reject-fixture"):
    if fragment not in test_contract:
        raise SystemExit(f"OCR corpus contract misses {fragment!r}")
if not re.search(r'"build": build', Path("main.py").read_text(encoding="utf-8")):
    raise SystemExit("health response must expose additive build provenance")
PY

git diff --check
printf 'PASS static-check\n'
