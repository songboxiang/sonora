#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Squeezelite GUI Web 版 — pywebview 入口（阶段 1 验证）。"""
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))

def resource_path(rel):
    """返回资源绝对路径；兼容 PyInstaller 冻结环境（sys._MEIPASS）。"""
    base = getattr(sys, "_MEIPASS", None) or HERE
    return os.path.join(base, rel)

sys.path.insert(0, resource_path("backend"))

# ---- 定位内置 squeezelite 二进制并注入环境变量（供 find_binary 优先识别）----
# 兼容三种形态：
#   1) 源码运行：HERE/squeezelite
#   2) 文本型 .app：launcher 已注入 SQUEEZELITE_GUI_BINARY，且资源在 ../Resources
#   3) PyInstaller 冻结：sys._MEIPASS 与 App bundle 的 MacOS/Resources
def _probe_bundled_squeezelite():
    if os.environ.get("SQUEEZELITE_GUI_BINARY"):
        return  # launcher 已指定，尊重之
    cands = [
        resource_path("squeezelite"),
        os.path.join(HERE, "squeezelite"),
        os.path.join(HERE, "..", "MacOS", "squeezelite"),
        os.path.join(HERE, "..", "Resources", "squeezelite"),
    ]
    # PyInstaller: 可执行文件在 Contents/MacOS，资源在 Contents/Resources
    mf = getattr(sys, "_MEIPASS", None)
    if mf:
        cands += [os.path.join(mf, "squeezelite"),
                  os.path.join(os.path.dirname(mf), "MacOS", "squeezelite"),
                  os.path.join(os.path.dirname(mf), "Resources", "squeezelite")]
        # sys.executable 在 Contents/MacOS/<app>
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        cands += [os.path.join(exe_dir, "squeezelite"),
                  os.path.join(exe_dir, "..", "Resources", "squeezelite")]
    for p in cands:
        if p and os.path.isfile(p) and os.access(p, os.X_OK):
            os.environ["SQUEEZELITE_GUI_BINARY"] = os.path.abspath(p)
            break
_probe_bundled_squeezelite()

import webview
from api import api as bridge_api

VERSION = "2.0.7"


def main():
    web_dir = resource_path("web")
    window = webview.create_window(
        "Sonora 颂诺",
        os.path.join(web_dir, "index.html"),
        js_api=bridge_api,
        width=1280,
        height=820,
        min_size=(1120, 760),
        background_color="#FAFAFA",
        text_select=True,
    )
    webview.start(debug=os.environ.get("SQWEB_DEBUG") == "1")


if __name__ == "__main__":
    main()
