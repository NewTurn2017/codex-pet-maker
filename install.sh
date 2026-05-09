#!/usr/bin/env sh
set -eu

# Install codex-pet-maker as a Codex skill bundle.
# Local checkout:  cd codex-pet-maker && ./install.sh
# curl install:    curl -fsSL https://raw.githubusercontent.com/NewTurn2017/codex-pet-maker/main/install.sh | sh

REPO_DEFAULT="NewTurn2017/codex-pet-maker"
REF_DEFAULT="main"

CODEX_HOME=${CODEX_HOME:-"$HOME/.codex"}
TARGET=${CODEX_PET_MAKER_TARGET:-"$CODEX_HOME/skills/codex-pet-maker"}
PYTHON_BIN=${PYTHON:-python3}
REPO=${CODEX_PET_MAKER_REPO:-$REPO_DEFAULT}
REF=${CODEX_PET_MAKER_REF:-$REF_DEFAULT}
ARCHIVE_URL=${CODEX_PET_MAKER_ARCHIVE_URL:-"https://github.com/$REPO/archive/refs/heads/$REF.tar.gz"}
ARCHIVE_PATH=${CODEX_PET_MAKER_ARCHIVE_PATH:-""}
TMP_ROOT=""

cleanup() {
  if [ -n "$TMP_ROOT" ] && [ -d "$TMP_ROOT" ]; then
    rm -rf "$TMP_ROOT"
  fi
}
trap cleanup EXIT INT TERM

fail() {
  echo "codex-pet-maker install failed: $*" >&2
  exit 2
}

abs_dir_for_script() {
  # When run through `curl ... | sh`, $0 is usually `sh`; in that case this
  # intentionally returns a directory that will not contain SKILL.md.
  case "$0" in
    */*) CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd -P ;;
    *) CDPATH= cd -- "." 2>/dev/null && pwd -P ;;
  esac
}

find_source_root() {
  root="$1"
  if [ -f "$root/SKILL.md" ] && [ -f "$root/pyproject.toml" ]; then
    printf '%s\n' "$root"
    return 0
  fi
  found=$(find "$root" -maxdepth 3 -type f -name SKILL.md -print | head -n 1 || true)
  if [ -n "$found" ]; then
    dirname -- "$found"
    return 0
  fi
  return 1
}

download_remote_source() {
  TMP_ROOT=$(mktemp -d 2>/dev/null || mktemp -d -t codex-pet-maker)
  extract_dir="$TMP_ROOT/extract"
  mkdir -p "$extract_dir"

  if [ -n "$ARCHIVE_PATH" ]; then
    archive="$ARCHIVE_PATH"
    [ -f "$archive" ] || fail "archive not found: $archive"
  else
    archive="$TMP_ROOT/source.tar.gz"
    if command -v curl >/dev/null 2>&1; then
      curl -fsSL "$ARCHIVE_URL" -o "$archive"
    elif command -v wget >/dev/null 2>&1; then
      wget -qO "$archive" "$ARCHIVE_URL"
    else
      fail "curl or wget is required for remote install"
    fi
  fi

  case "$archive" in
    *.zip)
      command -v unzip >/dev/null 2>&1 || fail "unzip is required for zip archives"
      unzip -q "$archive" -d "$extract_dir"
      ;;
    *)
      tar -xzf "$archive" -C "$extract_dir"
      ;;
  esac

  src=$(find_source_root "$extract_dir") || fail "downloaded archive does not contain SKILL.md"
  printf '%s\n' "$src"
}

copy_source_to_target() {
  src="$1"

  case "$TARGET" in
    ""|"/"|"$HOME"|"$CODEX_HOME" )
      fail "refusing unsafe install target: $TARGET"
      ;;
  esac

  parent_dir=$(dirname -- "$TARGET")
  mkdir -p "$parent_dir"

  src_real=$(CDPATH= cd -- "$src" && pwd -P)
  target_real=""
  if [ -d "$TARGET" ]; then
    target_real=$(CDPATH= cd -- "$TARGET" && pwd -P)
  fi

  if [ "$src_real" = "$target_real" ]; then
    return 0
  fi

  tmp_target="$TARGET.tmp.$$"
  rm -rf "$tmp_target"
  mkdir -p "$tmp_target"

  if command -v rsync >/dev/null 2>&1; then
    rsync -a \
      --exclude '.git/' \
      --exclude '.venv/' \
      --exclude '.pytest_cache/' \
      --exclude '.omx/' \
      --exclude '__pycache__/' \
      --exclude '*.pyc' \
      --exclude '*.egg-info/' \
      --exclude 'pet-runs/' \
      --exclude 'pet_request.json' \
      --exclude 'uv.lock' \
      "$src_real/" "$tmp_target/"
  else
    (
      cd "$src_real"
      tar \
        --exclude='.git' \
        --exclude='.venv' \
        --exclude='.pytest_cache' \
        --exclude='.omx' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='*.egg-info' \
        --exclude='pet-runs' \
        --exclude='pet_request.json' \
        --exclude='uv.lock' \
        -cf - .
    ) | (cd "$tmp_target" && tar -xf -)
  fi

  rm -rf "$TARGET"
  mv "$tmp_target" "$TARGET"
}

install_python_deps() {
  if [ "${CODEX_PET_MAKER_SKIP_VENV:-0}" = "1" ]; then
    return 0
  fi
  if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    fail "Python executable not found: $PYTHON_BIN"
  fi
  "$PYTHON_BIN" -m venv "$TARGET/.venv"
  "$TARGET/.venv/bin/python" -m pip install --upgrade pip
  "$TARGET/.venv/bin/python" -m pip install -e "$TARGET"
}

SCRIPT_DIR=$(abs_dir_for_script)
if [ -f "$SCRIPT_DIR/SKILL.md" ] && [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
  SOURCE_DIR="$SCRIPT_DIR"
else
  SOURCE_DIR=$(download_remote_source)
fi

copy_source_to_target "$SOURCE_DIR"
install_python_deps

cat <<EOF
✅ codex-pet-maker installed
Skill: $TARGET
Python: $TARGET/.venv/bin/python

Restart Codex, then ask:
  \$codex-pet-maker make me a codex pet
EOF
