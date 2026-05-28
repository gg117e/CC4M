#!/usr/bin/env bash
set -euo pipefail

# ccfindersw-parser を取得してリリースビルドするヘルパー

REPO_URL="https://github.com/YukiOhta0519/ccfindersw-parser.git"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TARGET_DIR="${PROJECT_ROOT}/lib/ccfindersw-parser"

if ! command -v git >/dev/null 2>&1; then
  echo "git が見つかりません。インストールしてください。" >&2
  exit 1
fi

if ! command -v cargo >/dev/null 2>&1; then
  echo "Rust toolchain (cargo) が必要です。https://www.rust-lang.org/tools/install を参照してください。" >&2
  exit 1
fi

mkdir -p "${TARGET_DIR}"

if [ ! -d "${TARGET_DIR}/.git" ]; then
  echo "cloning ${REPO_URL} into ${TARGET_DIR}..."
  git clone "${REPO_URL}" "${TARGET_DIR}"
else
  echo "updating existing repository in ${TARGET_DIR}..."
  git -C "${TARGET_DIR}" fetch --tags
  git -C "${TARGET_DIR}" pull --ff-only
fi

echo "building release binary..."
cargo build --release --manifest-path "${TARGET_DIR}/Cargo.toml"

BINARY="${TARGET_DIR}/target/release/ccfindersw-parser"
if [ ! -x "${BINARY}" ]; then
  echo "ビルドに失敗しました: ${BINARY} が見つかりません。" >&2
  exit 1
fi

echo "done. binary: ${BINARY}"
