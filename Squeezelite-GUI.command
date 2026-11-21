#!/bin/bash
# Squeezelite GUI -- macOS 双击启动脚本
# 优先使用自包含 .app 内置运行时（Tk 9），否则寻找 Tk >= 8.6 的 Python。
APP="$HOME/Applications/Squeezelite GUI.app/Contents"
if [ -x "$APP/MacOS/launcher" ]; then
  exec "$APP/MacOS/launcher"
fi
cd "$(dirname "$0")" || exit 1
PY=""
for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 \
         "$HOME/.workbuddy/binaries/python/versions/3.13.12/bin/python3" \
         /usr/bin/python3 python3; do
  if command -v "$c" >/dev/null 2>&1 || [ -x "$c" ]; then
    if "$c" -c 'import tkinter,sys;sys.exit(0 if tkinter.TkVersion>=8.6 else 1)' >/dev/null 2>&1; then
      PY="$c"; break
    fi
  fi
done
if [ -z "$PY" ]; then
  osascript -e 'display alert "Squeezelite GUI" message "未找到 Tk 8.6+ 的 Python。请运行 build_app.sh 生成自包含应用，或安装 python.org 官方 Python / brew install python-tk。"' 2>/dev/null
  echo "ERROR: 未找到带 Tk 8.6+ 的 Python 3" >&2
  exit 1
fi
exec "$PY" squeezelite_gui.py
