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
  test/generate_corpus.py \
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
    "FORMAL_SPACE: BlueSkyXN/OCRmyPDF-HFS",
    "--require-private",
    "confirm_deploy == 'deploy'",
    '[[ "${SOURCE_REF}" =~ ^[0-9a-f]{40}$ ]]',
    "huggingface_hub==1.5.0",
    "click==8.3.3",
    "python -m huggingface_hub.cli.hf version",
    "python -m huggingface_hub.cli.hf --help",
):
    if fragment not in workflow:
        raise SystemExit(f"deploy workflow misses {fragment!r}")

publish_call = 'PYTHONDONTWRITEBYTECODE=1 python cloud/hfs/sync_space_bundle.py'
publish_offset = workflow.index(publish_call)
required_before_publish = (
    'if [ "$HFS_TARGET" = production ] && [ "$SPACE_ID" != "$FORMAL_SPACE" ]; then',
    'if [ "$HFS_TARGET" = production ]; then',
    'test "$GITHUB_REF" = "refs/heads/main"',
    'git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main',
    'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"',
    'test "$SOURCE_REF" = "$GITHUB_SHA"',
    'test "$(git rev-parse origin/main)" = "$GITHUB_SHA"',
)
for fragment in required_before_publish:
    offset = workflow.index(fragment)
    if offset >= publish_offset:
        raise SystemExit(f"formal deploy gate must precede the publish helper: {fragment}")
if '--apply --require-private' not in workflow[publish_offset:]:
    raise SystemExit("candidate and production publishes must both require a private target")
production_gate = workflow.index('if [ "$HFS_TARGET" = production ]; then')
fetch_gate = workflow.index('git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main')
if not production_gate < fetch_gate < publish_offset:
    raise SystemExit("fresh origin/main fetch must be production-only and immediately precede publish")

sync_source = Path("cloud/hfs/sync_space_bundle.py").read_text(encoding="utf-8")
upload_offset = sync_source.index("commit = api.create_commit(")
for fragment in (
    'fail("target Space must be private")',
    "remote Space contains non-wrapper files",
):
    if sync_source.index(fragment) >= upload_offset:
        raise SystemExit(f"Space gate must fail before any HF upload: {fragment}")
for forbidden in ("allow-space-tree-prune", "CommitOperationDelete", "git push", "--force"):
    if forbidden in workflow or forbidden in Path("cloud/hfs/sync_space_bundle.py").read_text(encoding="utf-8"):
        raise SystemExit(f"deployment must not contain {forbidden!r}")

test_contract = Path("test/test.py").read_text(encoding="utf-8")
for fragment in ("--require-pdfa", "--max-output-bytes", "--max-seconds", "--reject-fixture", "--expect-text", "X-HF-Authorization"):
    if fragment not in test_contract:
        raise SystemExit(f"OCR corpus contract misses {fragment!r}")
for fixture in ("english.pdf", "chinese.pdf", "mixed.pdf", "existing-text.pdf", "deskew.pdf", "corrupt.pdf"):
    if not (Path("test/fixtures") / fixture).is_file():
        raise SystemExit(f"fixed OCR corpus misses {fixture}")
if not re.search(r'"build": build', Path("main.py").read_text(encoding="utf-8")):
    raise SystemExit("health response must expose additive build provenance")
if "cmd.extend(['--skip-text', '--output-type', 'pdf'])" not in Path("main.py").read_text(encoding="utf-8"):
    raise SystemExit("skip-text must avoid the known Ghostscript 10.0.0 PDF/A corruption path")
PY

git diff --check
printf 'PASS static-check\n'
