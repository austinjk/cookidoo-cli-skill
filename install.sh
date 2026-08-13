#!/usr/bin/env bash
set -euo pipefail

COOKIDOO_REPOSITORY="${COOKIDOO_GITHUB_REPO:-austinjk/cookidoo-cli-skill}"
COOKIDOO_REF="${COOKIDOO_INSTALL_REF:-main}"
COOKIDOO_TARGET="codex"
COOKIDOO_SOURCE=""
COOKIDOO_DRY_RUN="false"
COOKIDOO_TEMP_DIR=""

usage() {
  cat <<'EOF'
Install the Cookidoo CLI and manage-cookidoo Skill.

Usage: install.sh [options]

Options:
  --target codex|claude|both  Skill host to install for (default: codex)
  --source PATH               Install from a local checkout instead of GitHub
  --dry-run                   Show resolved actions without changing anything
  -h, --help                  Show this help

Environment:
  CODEX_HOME                  Codex home (default: ~/.codex)
  CLAUDE_HOME                 Claude home (default: ~/.claude)
  COOKIDOO_GITHUB_REPO        GitHub owner/repo override
  COOKIDOO_INSTALL_REF        GitHub branch or tag override (default: main)
EOF
}

log() {
  printf '%s\n' "$*"
}

cleanup() {
  if [[ -n "$COOKIDOO_TEMP_DIR" && -d "$COOKIDOO_TEMP_DIR" ]]; then
    rm -rf "$COOKIDOO_TEMP_DIR"
  fi
}
trap cleanup EXIT

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      [[ $# -ge 2 ]] || { log "error: --target requires a value" >&2; exit 2; }
      COOKIDOO_TARGET="$2"
      shift 2
      ;;
    --source)
      [[ $# -ge 2 ]] || { log "error: --source requires a path" >&2; exit 2; }
      COOKIDOO_SOURCE="$2"
      shift 2
      ;;
    --dry-run)
      COOKIDOO_DRY_RUN="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      log "error: unknown option $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$COOKIDOO_TARGET" in
  codex|claude|both) ;;
  *) log "error: --target must be codex, claude, or both" >&2; exit 2 ;;
esac

resolve_source() {
  if [[ -n "$COOKIDOO_SOURCE" ]]; then
    COOKIDOO_SOURCE="$(cd "$COOKIDOO_SOURCE" && pwd)"
  else
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || true)"
    if [[ -n "$script_dir" && -f "$script_dir/pyproject.toml" && -d "$script_dir/skills/manage-cookidoo" ]]; then
      COOKIDOO_SOURCE="$script_dir"
    else
      command -v curl >/dev/null 2>&1 || { log "error: curl is required" >&2; exit 1; }
      command -v tar >/dev/null 2>&1 || { log "error: tar is required" >&2; exit 1; }
      COOKIDOO_TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/cookidoo-install.XXXXXX")"
      mkdir -p "$COOKIDOO_TEMP_DIR/source"
      local archive_url="$COOKIDOO_REPOSITORY/archive/$COOKIDOO_REF.tar.gz"
      archive_url="https://github.com/$archive_url"
      log "Downloading $COOKIDOO_REPOSITORY@$COOKIDOO_REF..."
      curl -fsSL "$archive_url" -o "$COOKIDOO_TEMP_DIR/source.tar.gz"
      tar -xzf "$COOKIDOO_TEMP_DIR/source.tar.gz" --strip-components=1 -C "$COOKIDOO_TEMP_DIR/source"
      COOKIDOO_SOURCE="$COOKIDOO_TEMP_DIR/source"
    fi
  fi

  [[ -f "$COOKIDOO_SOURCE/pyproject.toml" ]] || { log "error: pyproject.toml not found in $COOKIDOO_SOURCE" >&2; exit 1; }
  [[ -f "$COOKIDOO_SOURCE/skills/manage-cookidoo/SKILL.md" ]] || { log "error: manage-cookidoo Skill not found in $COOKIDOO_SOURCE" >&2; exit 1; }
}

ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    return
  fi
  if [[ "$COOKIDOO_DRY_RUN" == "true" ]]; then
    log "Would install uv from https://astral.sh/uv/install.sh"
    return
  fi
  command -v curl >/dev/null 2>&1 || { log "error: curl is required to install uv" >&2; exit 1; }
  COOKIDOO_TEMP_DIR="${COOKIDOO_TEMP_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/cookidoo-install.XXXXXX")}"
  log "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh -o "$COOKIDOO_TEMP_DIR/install-uv.sh"
  sh "$COOKIDOO_TEMP_DIR/install-uv.sh"
  export PATH="$HOME/.local/bin:$PATH"
  command -v uv >/dev/null 2>&1 || { log "error: uv installed but is not available on PATH" >&2; exit 1; }
}

install_cli() {
  if [[ "$COOKIDOO_DRY_RUN" == "true" ]]; then
    log "Would install CLI: uv tool install --force --python 3.12 $COOKIDOO_SOURCE"
    return
  fi
  log "Installing Cookidoo CLI..."
  uv tool install --force --python 3.12 "$COOKIDOO_SOURCE"
}

install_skill() {
  local skill_root="$1"
  local destination="$skill_root/manage-cookidoo"
  local source_skill="$COOKIDOO_SOURCE/skills/manage-cookidoo"
  if [[ "$COOKIDOO_DRY_RUN" == "true" ]]; then
    log "Would install Skill: $source_skill -> $destination"
    return
  fi

  mkdir -p "$skill_root"
  if [[ -e "$destination" ]]; then
    local backup="$destination.backup.$(date -u +%Y%m%dT%H%M%SZ).$$"
    mv "$destination" "$backup"
    log "Preserved previous Skill at $backup"
  fi
  mkdir -p "$destination"
  cp -R "$source_skill/." "$destination/"
  chmod +x "$destination/scripts/cookidoo"
  log "Installed Skill at $destination"
}

resolve_source
ensure_uv
install_cli

case "$COOKIDOO_TARGET" in
  codex)
    install_skill "${CODEX_HOME:-$HOME/.codex}/skills"
    ;;
  claude)
    install_skill "${CLAUDE_HOME:-$HOME/.claude}/skills"
    ;;
  both)
    install_skill "${CODEX_HOME:-$HOME/.codex}/skills"
    install_skill "${CLAUDE_HOME:-$HOME/.claude}/skills"
    ;;
esac

if [[ "$COOKIDOO_DRY_RUN" == "true" ]]; then
  log "Dry run complete; no changes made."
else
  log "Installation complete."
  log "Next: cookidoo login --email you@example.com"
fi
