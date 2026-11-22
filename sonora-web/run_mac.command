#!/bin/bash
# ============================================================================
#  Sonora 颂诺 · Web 版  —  macOS 一键启动脚本（双击即用）
#  首次运行会自动创建 .venv 并安装 pywebview / Pillow（需联网一次），
#  之后启动无需再联网。使用系统自带 WKWebView，不打包浏览器内核。
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")" || exit 1

APP="Sonora 颂诺"
VENV=".venv"
REQ="requirements.txt"

say() { printf '\n[%s] %s\n' "$APP" "$*"; }
err() { printf '\n[ERROR] %s\n' "$*" >&2; }

# ---------- 1. 选 Python ----------
PY=""
for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 \
         "$HOME/.workbuddy/binaries/python/versions/3.13.12/bin/python3" \
         /usr/bin/python3 python3; do
  if command -v "$c" >/dev/null 2>&1 || [ -x "$c" ]; then
    VER="$("$c" -c 'import sys;print("%d %d"%sys.version_info[:2])' 2>/dev/null || true)"
    MAJOR="$(echo "$VER" | awk '{print $1}')"
    MINOR="$(echo "$VER" | awk '{print $2}')"
    if [ "$MAJOR" = "3" ] && [ -n "$MINOR" ] && [ "$MINOR" -ge 9 ] 2>/dev/null; then
      PY="$c"; break
    fi
  fi
done
if [ -z "$PY" ]; then
  err "未找到 Python 3.9+。请安装 python.org 官方 Python 或 brew install python。"
  osascript -e 'display alert "Sonora 颂诺" message "未找到 Python 3.9+，请先安装 python.org 官方 Python 或 brew install python。"' 2>/dev/null || true
  exit 1
fi
say "使用 Python: $PY ($("$PY" -c 'import sys;print(sys.version.split()[0])'))"

# ---------- 2. 虚拟环境 ----------
if [ ! -x "$VENV/bin/python" ]; then
  say "首次运行：创建虚拟环境 $VENV …"
  "$PY" -m venv "$VENV" || { err "创建虚拟环境失败"; exit 1; }
fi
VPY="$VENV/bin/python"

# ---------- 3. 依赖 ----------
if ! "$VPY" -c 'import webview' >/dev/null 2>&1; then
  if [ ! -f "$REQ" ]; then
    err "缺少 $REQ，无法安装依赖。"; exit 1
  fi
  say "安装依赖（pywebview / Pillow），仅首次需要联网 …"
  "$VENV/bin/pip" install --upgrade pip >/dev/null 2>&1 || true
  "$VENV/bin/pip" install -r "$REQ" || { err "依赖安装失败，请检查网络后重试"; exit 1; }
fi

# ---------- 4. 启动 ----------
say "启动 $APP …"
exec "$VPY" main.py
