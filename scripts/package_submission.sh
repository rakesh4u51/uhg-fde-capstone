#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE_NAME="intelligent-claims-capstone"
STAGING_DIR="$(mktemp -d -t "${STAGE_NAME}-XXXXXX")"
ZIP_PATH="${ROOT}/${STAGE_NAME}.zip"

cleanup() {
  rm -rf "${STAGING_DIR}"
}
trap cleanup EXIT

cd "${ROOT}"

if [ -e "${ZIP_PATH}" ]; then
  rm -f "${ZIP_PATH}"
fi

mkdir -p "${STAGING_DIR}/${STAGE_NAME}"

rsync -a \
  --exclude='.git' \
  --exclude='.env' \
  --exclude='.env.*' \
  --exclude='!.env.example' \
  --exclude='.streamlit' \
  --exclude='.venv' \
  --exclude='venv' \
  --exclude='env' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache' \
  --exclude='.mypy_cache' \
  --exclude='.ruff_cache' \
  --exclude='logs' \
  --exclude='tmp' \
  --exclude='temp' \
  --exclude='uploads' \
  --exclude='uploaded_documents' \
  --exclude='claim_documents' \
  --exclude='runtime_data' \
  --exclude='checkpoints' \
  --exclude='pgdata' \
  --exclude='postgres-data' \
  --exclude='*.db' \
  --exclude='*.sqlite' \
  --exclude='*.sqlite3' \
  --exclude='*.dump' \
  --exclude='*.backup' \
  --exclude='.vscode' \
  --exclude='.idea' \
  --exclude='.claude' \
  --exclude='.copilot-state' \
  --exclude='*.log' \
  --exclude='*.lock' \
  --exclude='**/.pytest_cache' \
  --exclude='**/__pycache__' \
  --exclude='**/*.pyc' \
  --exclude='**/uploads' \
  --exclude='**/checkpoints' \
  --exclude='**/runtime_data' \
  --exclude='**/pgdata' \
  --exclude='**/medical_bill.md' \
  ./ "${STAGING_DIR}/${STAGE_NAME}/"

export STAGING_DIR STAGE_NAME ZIP_PATH

python - <<'PY'
import hashlib
import os
from pathlib import Path

root = Path(os.environ['STAGING_DIR']) / os.environ['STAGE_NAME']
manifest = Path(os.environ['STAGING_DIR']) / 'MANIFEST.sha256'
entries = []
for path in sorted(root.rglob('*')):
    if path.is_file():
        rel = path.relative_to(root.parent)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append(f"{digest}  {rel}\n")
manifest.write_text(''.join(entries), encoding='utf-8')
PY

python - <<'PY'
import os
import zipfile
from pathlib import Path

root = Path(os.environ['STAGING_DIR'])
stage = root / os.environ['STAGE_NAME']
zip_path = Path(os.environ['ZIP_PATH'])
with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
    for path in sorted(stage.rglob('*')):
        if path.is_file():
            zf.write(path, arcname=str(path.relative_to(root)))
print(f'ZIP created at: {zip_path}')
PY

python - <<'PY'
import os
import zipfile
from pathlib import Path

zip_path = Path(os.environ['ZIP_PATH'])
with zipfile.ZipFile(zip_path) as zf:
    names = zf.namelist()
    print('--- archive entries ---')
    for name in names:
        print(name)
    forbidden = ['.env', '.venv', '__pycache__', 'uploads', 'checkpoints', 'runtime_data', 'logs', 'tmp', 'pgdata', 'postgres-data', '.pytest_cache', '.mypy_cache', '.ruff_cache']
    hits = [name for name in names if any(part in name for part in forbidden) or name.endswith(('.pyc', '.sqlite', '.sqlite3', '.dump', '.backup', '.log'))]
    print('--- forbidden filename scan ---')
    for name in hits:
        print(name)
PY

mkdir -p "${STAGING_DIR}/verify-extract"
rm -rf "${STAGING_DIR}/verify-extract/*"
unzip -q "${ZIP_PATH}" -d "${STAGING_DIR}/verify-extract"

if [ ! -f "${STAGING_DIR}/verify-extract/${STAGE_NAME}/README.md" ]; then
  echo 'ERROR: README missing in extracted archive.' >&2
  exit 1
fi

if [ -e "${STAGING_DIR}/verify-extract/${STAGE_NAME}/.env" ]; then
  echo 'ERROR: .env exists in archive.' >&2
  exit 1
fi

if [ -e "${STAGING_DIR}/verify-extract/${STAGE_NAME}/.venv" ]; then
  echo 'ERROR: .venv exists in archive.' >&2
  exit 1
fi

if [ -d "${STAGING_DIR}/verify-extract/${STAGE_NAME}/__pycache__" ]; then
  echo 'ERROR: __pycache__ exists in archive.' >&2
  exit 1
fi

if [ -d "${STAGING_DIR}/verify-extract/${STAGE_NAME}/uploads" ]; then
  echo 'ERROR: uploads directory exists in archive.' >&2
  exit 1
fi

printf '\nArchive verification passed.\n'
