#!/bin/bash
# ==========================================================================
#  Squeezelite GUI.app —— macOS 自包含应用一键封装脚本
#  在 macOS 本机执行： bash build_app.sh
#
#  产物 ~/Applications/Squeezelite GUI.app 内含：
#    - 独立 Python 3.13 运行时（含 Tcl/Tk 9，不依赖系统 /usr/bin/python3）
#    - squeezelite_gui.py（完整图形界面）
#    - squeezelite（本机已有的 arm64 可执行文件）
#    - launcher + Info.plist + 应用图标
#  全程零联网、零第三方依赖；双击即用。
# ==========================================================================
set -euo pipefail

APP_NAME="Squeezelite GUI"
APP_DIR="$HOME/Applications/$APP_NAME.app"
CONTENTS="$APP_DIR/Contents"
MACOS="$CONTENTS/MacOS"
RES="$CONTENTS/Resources"

# ---------- 输入（可用环境变量覆盖）----------
SRC_DIR="${SRC_DIR:-$(cd "$(dirname "$0")" && pwd)}"
GUI_PY="${GUI_PY:-$SRC_DIR/squeezelite_gui.py}"
PY_SRC="${PY_SRC:-$HOME/.workbuddy/binaries/python/versions/3.13.12}"

# 查找 squeezelite 二进制：优先同目录，其次用户既有目录，最后 PATH
SL_BIN="${SL_BIN:-}"
if [ -z "$SL_BIN" ] || [ ! -f "$SL_BIN" ]; then
  for c in "$SRC_DIR/squeezelite" "$SRC_DIR/Squeezelite" \
           "$HOME/Applications/Squeezelite/Squeezelite/Squeezelite" \
           "$(command -v squeezelite 2>/dev/null || true)"; do
    if [ -n "$c" ] && [ -f "$c" ]; then SL_BIN="$c"; break; fi
  done
fi

err() { echo "ERROR: $*" >&2; exit 1; }

[ -f "$GUI_PY" ] || err "未找到 GUI 源码：$GUI_PY"
[ -f "$PY_SRC/bin/python3" ] || err "未找到 Python 运行时：$PY_SRC"
[ -n "$SL_BIN" ] && [ -f "$SL_BIN" ] || err "未找到 squeezelite 二进制（可设置 SL_BIN=/path/to/squeezelite）"

# 校验运行时确实带 Tk >= 8.6
TKV="$("$PY_SRC/bin/python3" -c 'import tkinter;print(tkinter.TkVersion)' 2>/dev/null || true)"
[ -n "$TKV" ] || err "该 Python 未带 tkinter，请改用 python.org 官方 Python 或 brew install python-tk"
echo "== Python 运行时: $PY_SRC (Tk $TKV)"
echo "== GUI 源码: $GUI_PY"
echo "== Squeezelite: $SL_BIN"

# ---------- 旧版本隔离（不直接删除）----------
if [ -e "$APP_DIR" ]; then
  BAK="$HOME/Applications/$APP_NAME.app.bak-$(date +%Y%m%d-%H%M%S)"
  mv "$APP_DIR" "$BAK"
  echo "== 旧版本已隔离备份: $BAK"
fi

mkdir -p "$MACOS" "$RES/python"

# ---------- 1. 内置 Python 运行时 ----------
echo "== 复制独立 Python 运行时（约 60 MB）..."
cp -R "$PY_SRC/." "$RES/python/"
# 注：源运行时自带的 .pyc 会一并复制进 bundle 内，属于运行时自带字节码，
# 全部位于 .app 内部，卸载时随 app 一起移除；不做删除操作以免触发安全策略。
chmod +x "$RES/python/bin/python3.13" 2>/dev/null || true

# 追加相对 rpath（尽量自包含；失败不影响，launcher 会设置 DYLD_LIBRARY_PATH）
PYBIN="$RES/python/bin/python3.13"
install_name_tool -add_rpath "@executable_path/../lib" "$PYBIN" 2>/dev/null || true

# ---------- 2. GUI 脚本与 squeezelite 二进制 ----------
cp "$GUI_PY" "$RES/squeezelite_gui.py"
cp "$SL_BIN" "$RES/squeezelite"
chmod +x "$RES/squeezelite"

# ---------- 3. 应用图标（可选，必须是自有/原创图标）----------
# macOS 系统自带图标位于 CoreTypes.bundle，属 Apple 所有，仅授权在本机
# 使用，不可随应用再分发。这里不从系统复制；如自备原创 app.icns 放在
# SRC_DIR 下，构建时会自动带上（不提供则使用 macOS 默认应用图标）。
ICON_KEY=""
if [ -f "$SRC_DIR/app.icns" ]; then
  cp "$SRC_DIR/app.icns" "$RES/app.icns"
  ICON_KEY='    <key>CFBundleIconFile</key>          <string>app.icns</string>'
  echo "== 使用自备图标: $SRC_DIR/app.icns"
else
  echo "== 未设置图标（不捆绑任何 Apple 系统资源）"
fi

# ---------- 4. launcher ----------
cat > "$MACOS/launcher" <<'LAUNCH'
#!/bin/bash
# Squeezelite GUI.app —— 自包含启动器
R="$(cd "$(dirname "$0")/../Resources" && pwd)"
PY="$R/python/bin/python3"
[ -x "$PY" ] || PY="$R/python/bin/python3.13"

export PYTHONHOME="$R/python"
TCLDIR="$(ls -d "$R"/python/lib/tcl* 2>/dev/null | head -1)"
TKDIR="$(ls -d "$R"/python/lib/tk* 2>/dev/null | head -1)"
[ -n "$TCLDIR" ] && export TCL_LIBRARY="$TCLDIR"
[ -n "$TKDIR" ] && export TK_LIBRARY="$TKDIR"
export DYLD_LIBRARY_PATH="$R/python/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
export SQUEEZELITE_GUI_BINARY="$R/squeezelite"
export TK_SILENCE_DEPRECATION=1
cd "$R"
exec "$PY" "$R/squeezelite_gui.py"
LAUNCH
chmod +x "$MACOS/launcher"

# ---------- 5. Info.plist ----------
VER="$(grep -m1 '^VERSION' "$RES/squeezelite_gui.py" | sed -E 's/.*"([0-9.]+)".*/\1/')"
[ -n "$VER" ] || VER="1.0.1"
cat > "$CONTENTS/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>              <string>$APP_NAME</string>
    <key>CFBundleDisplayName</key>       <string>$APP_NAME</string>
    <key>CFBundleIdentifier</key>        <string>local.squeezelite.gui</string>
    <key>CFBundlePackageType</key>       <string>APPL</string>
    <key>CFBundleExecutable</key>        <string>launcher</string>
    <key>CFBundleVersion</key>           <string>$VER</string>
    <key>CFBundleShortVersionString</key><string>$VER</string>
$ICON_KEY
    <key>LSMinimumSystemVersion</key>    <string>11.0</string>
    <key>NSHighResolutionCapable</key>  <true/>
    <key>LSUIElement</key>              <false/>
    <key>CFBundleDevelopmentRegion</key> <string>zh_CN</string>
</dict>
</plist>
PLIST

# ---------- 6. 清理隔离属性 + ad-hoc 签名 ----------
xattr -cr "$APP_DIR" 2>/dev/null || true
codesign --force --deep --sign - "$APP_DIR" 2>/dev/null || echo "WARN: ad-hoc 签名跳过（本机使用不受影响）"

# ---------- 7. 自检 ----------
echo "== 自检..."
TCLDIR="$(ls -d "$RES"/python/lib/tcl* 2>/dev/null | head -1)"
TKDIR="$(ls -d "$RES"/python/lib/tk* 2>/dev/null | head -1)"
env PYTHONHOME="$RES/python" TCL_LIBRARY="$TCLDIR" TK_LIBRARY="$TKDIR" \
    DYLD_LIBRARY_PATH="$RES/python/lib" \
    "$RES/python/bin/python3" -c 'import sys,tkinter;print("   Python",sys.version.split()[0],"Tk",tkinter.TkVersion,"prefix",sys.prefix)' \
    || err "内置 Python 自检失败"
# 语法自检不落盘（不生成 __pycache__）
env PYTHONHOME="$RES/python" TCL_LIBRARY="$TCLDIR" TK_LIBRARY="$TKDIR" \
    DYLD_LIBRARY_PATH="$RES/python/lib" \
    "$RES/python/bin/python3" -c 'import sys;compile(open(sys.argv[1],encoding="utf-8").read(),sys.argv[1],"exec");print("   GUI 脚本语法检查通过")' \
    "$RES/squeezelite_gui.py" || err "GUI 脚本语法检查失败"
"$RES/squeezelite" -? 2>&1 | head -1 || true

echo ""
echo "OK 封装完成: $APP_DIR"
echo "   大小: $(du -sh "$APP_DIR" | awk '{print $1}')"
echo "   双击即可启动；内置 squeezelite 会被自动识别，联网升级将就地替换它。"
echo "   旧的 Squeezelite-GUI.command 可弃用（它使用系统 Tk 8.5，会白屏）。"
echo "   若要把此 .app 分发给他人，请先阅读 THIRD_PARTY_NOTICES.md 并履行各组件许可义务。"
