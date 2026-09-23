#!/usr/bin/env bash
set -euo pipefail

GAOS_VERSION="${GAOS_VERSION:-1.0.0}"
GAOS_INSTALL_DIR="${GAOS_INSTALL_DIR:-$HOME/.local/share/general-agent-os}"
GAOS_BIN_DIR="${GAOS_BIN_DIR:-$HOME/.local/bin}"
GAOS_PYTHON="${GAOS_PYTHON:-python3}"
"$GAOS_PYTHON" -c 'import sys; assert sys.version_info >= (3,10), "Python 3.10+ is required"'

script_dir=""
if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
fi
source_path="${GAOS_SOURCE:-$script_dir}"
mkdir -p "$GAOS_INSTALL_DIR" "$GAOS_BIN_DIR"
if [[ -e "$GAOS_BIN_DIR/gaos" || -L "$GAOS_BIN_DIR/gaos" ]]; then
  if [[ ! -L "$GAOS_BIN_DIR/gaos" || "$(readlink "$GAOS_BIN_DIR/gaos")" != "$GAOS_INSTALL_DIR/venv/bin/gaos" ]]; then
    echo "Refusing to overwrite existing $GAOS_BIN_DIR/gaos; choose GAOS_BIN_DIR." >&2
    exit 1
  fi
fi
if [[ ! -x "$GAOS_INSTALL_DIR/venv/bin/python" ]]; then
  "$GAOS_PYTHON" -m venv "$GAOS_INSTALL_DIR/venv"
fi
python="$GAOS_INSTALL_DIR/venv/bin/python"
"$python" -m pip install --upgrade pip
if [[ -n "$source_path" && -f "$source_path/pyproject.toml" ]]; then
  "$python" -m pip install --upgrade "$source_path[mcp]"
else
  temp_dir="$(mktemp -d)"
  trap 'rm -rf "$temp_dir"' EXIT
  asset="general_agent_os-${GAOS_VERSION}-py3-none-any.whl"
  release="https://github.com/Ancientshi/GeneralAgentOS/releases/download/v${GAOS_VERSION}"
  curl -fsSL --retry 3 "$release/$asset" -o "$temp_dir/$asset"
  curl -fsSL --retry 3 "$release/SHA256SUMS" -o "$temp_dir/SHA256SUMS"
  "$python" - "$temp_dir" "$asset" <<'PY'
import hashlib, pathlib, sys
root, name = pathlib.Path(sys.argv[1]), sys.argv[2]
checksums = dict(line.split(maxsplit=1)[::-1] for line in (root/'SHA256SUMS').read_text().splitlines() if line.strip())
expected = {k.strip().lstrip('*'): v for k,v in checksums.items()}.get(name)
if not expected or hashlib.sha256((root/name).read_bytes()).hexdigest() != expected:
    raise SystemExit('Release checksum verification failed')
PY
  "$python" -m pip install --upgrade "$temp_dir/$asset[mcp]"
fi
ln -sfn "$GAOS_INSTALL_DIR/venv/bin/gaos" "$GAOS_BIN_DIR/gaos"
"$GAOS_BIN_DIR/gaos" --version
echo "Installed. Add $GAOS_BIN_DIR to PATH if needed. Next: gaos init my-agent"
