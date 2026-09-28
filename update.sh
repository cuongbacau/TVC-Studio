#!/usr/bin/env bash
# TVC Downloader: apply a small release ZIP while retaining .env and data/.
set -Eeuo pipefail
if [[ $# -ne 1 || ! -f "$1" ]]; then
  echo "Cách dùng: ./update.sh /đường/dẫn/TVC_Downloader_update.zip" >&2
  exit 2
fi
archive=$(realpath "$1")
cd "$(dirname "${BASH_SOURCE[0]}")"
root=$(pwd)
mkdir -p .updates
stage=$(mktemp -d "$root/.updates/stage.XXXXXXXX")
backup=$(mktemp -d "$root/.updates/backup.XXXXXXXX")
cleanup() { rm -rf "$stage"; }
rollback() {
  echo 'Cập nhật lỗi; đang khôi phục mã nguồn cũ.' >&2
  for file in app Dockerfile compose.yaml requirements.txt README.md VERSION update.sh update-git.sh .env.example .gitignore; do
    rm -rf "$root/$file"
    if [[ -e "$backup/$file" ]]; then cp -a "$backup/$file" "$root/$file"; fi
  done
  docker compose up -d --build || true
}
trap cleanup EXIT
# Reject path traversal, links, oversized bundles, and updates to saved content.
python3 - "$archive" "$stage" <<'PY'
import pathlib, sys, zipfile
source, dest = sys.argv[1:]
allow = {'app/', 'Dockerfile', 'compose.yaml', 'requirements.txt', 'README.md', 'VERSION', 'update.sh', 'update-git.sh', '.env.example', '.gitignore'}
with zipfile.ZipFile(source) as z:
    members = z.infolist()
    if len(members) > 1000 or sum(i.file_size for i in members) > 20_000_000:
        raise SystemExit('Gói cập nhật quá lớn')
    for i in members:
        name = i.filename
        parts = pathlib.PurePosixPath(name).parts
        if not parts or any(p in ('..', '.') for p in parts) or name.startswith('/') or '\\' in name:
            raise SystemExit('Đường dẫn không hợp lệ trong ZIP: ' + name)
        if not (name.startswith('app/') or name in allow):
            raise SystemExit('Gói chứa đường dẫn không được cập nhật: ' + name)
        if (i.external_attr >> 16) & 0o170000 == 0o120000:
            raise SystemExit('Gói có liên kết mềm: ' + name)
    if not {'VERSION', 'app/main.py', 'app/static/index.html'} <= set(z.namelist()):
        raise SystemExit('Gói cập nhật thiếu file bắt buộc')
    z.extractall(dest)
PY
python3 -m py_compile "$stage/app/main.py"
for file in app Dockerfile compose.yaml requirements.txt README.md VERSION update.sh update-git.sh .env.example .gitignore; do
  [[ ! -e "$root/$file" ]] || cp -a "$root/$file" "$backup/$file"
done
trap 'rollback; cleanup' ERR
for file in app Dockerfile compose.yaml requirements.txt README.md VERSION update.sh update-git.sh .env.example .gitignore; do
  if [[ -e "$stage/$file" ]]; then
    rm -rf "$root/$file"
    cp -a "$stage/$file" "$root/$file"
  fi
done
chmod +x update.sh
docker compose up -d --build
trap - ERR
printf 'Đã cập nhật TVC Downloader lên bản %s. Video, hàng đợi và .env được giữ nguyên.\n' "$(cat VERSION)"
printf 'Bản sao mã nguồn cũ: %s\n' "$backup"
