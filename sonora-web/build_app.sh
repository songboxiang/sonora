#!/bin/bash
# ============================================================================
#  Sonora 颂诺 · Web 版  —  macOS 独立 App 一键封装脚本
#  在 macOS 本机执行： bash build_app.sh
#
#  产物： ~/Applications/Sonora 颂诺.app
#    - 用 PyInstaller 打包，自包含 Python 运行时 + pywebview + Pillow
#    - 使用 macOS 系统自带 WKWebView，不打包浏览器内核
#    - 双击即用，无需终端、无需预装 Python、无需联网（构建时需联网一次）
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")" || exit 1

APP_NAME="Sonora 颂诺"
APP_DIR="$HOME/Applications/$APP_NAME.app"
BUILD_VENV=".build-venv"
ICON="web/assets/Sonora.icns"

say() { printf '\n[build] %s\n' "$*"; }
err() { printf '\n[ERROR] %s\n' "$*" >&2; exit 1; }

# ---------- 1. 找 Python 3.9+ ----------
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
[ -n "$PY" ] || err "未找到 Python 3.9+，请安装 python.org 官方 Python 或 brew install python。"
say "Python: $PY ($("$PY" -c 'import sys;print(sys.version.split()[0])'))"

# ---------- 2. 构建用虚拟环境 + 依赖 ----------
if [ ! -x "$BUILD_VENV/bin/python" ]; then
  say "创建构建虚拟环境 $BUILD_VENV …"
  "$PY" -m venv "$BUILD_VENV" || err "创建虚拟环境失败"
fi
VPY="$BUILD_VENV/bin/python"
say "安装构建依赖（pyinstaller / pywebview / Pillow，需联网）…"
"$BUILD_VENV/bin/pip" install --upgrade pip >/dev/null 2>&1 || true
"$BUILD_VENV/bin/pip" install pyinstaller "pywebview>=6.0,<7" "Pillow>=10.0" \
  || err "构建依赖安装失败，请检查网络"

# ---------- 3. 旧版隔离（不直接删除）----------
if [ -e "$APP_DIR" ]; then
  BAK="${APP_DIR%.app}.bak.$(date +%Y%m%d_%H%M%S).app"
  say "已存在旧版，隔离到: $BAK"
  mv "$APP_DIR" "$BAK"
fi

# ---------- 3.5 查找本机 squeezelite 二进制（用于内置） ----------
SL_BIN=""
SL_ENV="${SQUEEZELITE_GUI_BINARY:-}"
for c in "$SL_ENV" \
         "$HOME/Applications/Squeezelite/Squeezelite/Squeezelite" \
         "$HOME/Applications/Squeezelite/Squeezelite/squeezelite" \
         /opt/homebrew/bin/squeezelite /usr/local/bin/squeezelite \
         /usr/bin/squeezelite "$HOME/bin/squeezelite" \
         /Applications/Squeezelite/squeezelite; do
  if [ -n "$c" ] && [ -x "$c" ]; then SL_BIN="$c"; break; fi
done
[ -n "$SL_BIN" ] || SL_BIN="$(command -v squeezelite 2>/dev/null || true)"
if [ -n "$SL_BIN" ] && [ -x "$SL_BIN" ]; then
  say "squeezelite 二进制: $SL_BIN （将内置到 app）"
else
  say "警告：未找到本机 squeezelite，app 将不含二进制。可在「升级与更新」页在线安装。"
fi

# ---------- 4. PyInstaller 打包 ----------
say "PyInstaller 打包中（首次约 1-3 分钟）…"
[ -f "$ICON" ] || err "缺少图标 $ICON"
rm -rf build dist Sonora.spec
"$VPY" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "$APP_NAME" \
  --icon "$ICON" \
  --add-data "web:web" \
  --paths backend \
  --hidden-import api \
  --hidden-import legacy_core \
  --hidden-import webview.platforms.cocoa \
  --osx-bundle-identifier com.sonora.app \
  main.py || err "PyInstaller 打包失败"

[ -d "dist/$APP_NAME.app" ] || err "未找到产物 dist/$APP_NAME.app"

# 内置二进制到 app（放在 Resources 与 MacOS 两处，find_binary 都能找到）
if [ -n "$SL_BIN" ] && [ -x "$SL_BIN" ]; then
  APP_RES="dist/$APP_NAME.app/Contents/Resources"
  APP_MAC="dist/$APP_NAME.app/Contents/MacOS"
  mkdir -p "$APP_RES" "$APP_MAC"
  cp "$SL_BIN" "$APP_RES/squeezelite" && chmod +x "$APP_RES/squeezelite"
  cp "$SL_BIN" "$APP_MAC/squeezelite" && chmod +x "$APP_MAC/squeezelite"
  xattr -d com.apple.quarantine "$APP_RES/squeezelite" 2>/dev/null || true
  xattr -d com.apple.quarantine "$APP_MAC/squeezelite" 2>/dev/null || true
  say "已内置 squeezelite 到 app"
fi

# ---------- 5. 安装到 ~/Applications ----------
mkdir -p "$HOME/Applications"
cp -R "dist/$APP_NAME.app" "$APP_DIR"
say "完成！已生成: $APP_DIR"
printf '\n  双击即可启动。首次若被 Gatekeeper 拦截，执行：\n'
printf '    xattr -cr "%s"\n' "$APP_DIR"
printf '  或从「系统设置 → 隐私与安全性」点「仍要打开」。\n'
