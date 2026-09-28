#!/usr/bin/env bash
# Update a GitHub checkout without touching local .env or data/.
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo 'Thư mục này chưa phải Git checkout. Cài từ repo GitHub trước.' >&2
  exit 2
fi
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo 'Có mã nguồn đã sửa trên Ubuntu. Hãy commit/stash trước khi cập nhật.' >&2
  exit 2
fi
if ! git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' >/dev/null 2>&1; then
  echo 'Nhánh hiện tại chưa liên kết GitHub (upstream).' >&2
  exit 2
fi
before=$(git rev-parse HEAD)
git pull --ff-only
after=$(git rev-parse HEAD)
if [[ "$after" == "$before" ]]; then
  echo 'Mã nguồn đã ở phiên bản mới nhất.'
  exit 0
fi
if sudo docker compose up -d --build; then
  printf 'Đã cập nhật %s → %s. data/ và .env giữ nguyên.\n' "${before:0:8}" "${after:0:8}"
else
  echo 'Không khởi động được bản mới; khôi phục mã nguồn trước cập nhật.' >&2
  git reset --hard "$before"
  sudo docker compose up -d --build || echo 'Không tự khởi động được bản cũ; kiểm tra docker compose logs.' >&2
  exit 1
fi
