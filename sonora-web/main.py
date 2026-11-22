#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Squeezelite GUI Web 版 — pywebview 入口（阶段 1 验证）。"""
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "backend"))

import webview
from api import api as bridge_api

VERSION = "2.0.0"


def main():
    web_dir = os.path.join(HERE, "web")
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
