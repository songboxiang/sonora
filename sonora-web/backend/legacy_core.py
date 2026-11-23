#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Squeezelite GUI  --  macOS 图形化配置 / 启动 / 升级工具
=====================================================
零第三方依赖（仅 Python 标准库 + tkinter），单文件运行。

功能：
  1. 启动自动扫描音频输出设备，手动选择
  2. 每个参数提供下拉选项、具体效果说明、最优音质推荐，并支持自定义值与范围校验
  3. 播放器名称 = 本机名称 + 音频设备简称（通过 -n 传给 LMS 服务端显示）
  4. 联网升级 Squeezelite（SourceForge 官方 macOS 二进制 / Homebrew），
     检查 LMS 服务端版本更新并提示，标注升级内容（GitHub commit 日志）
  5. 「正在播放」：通过 LMS JSON-RPC 获取播放器状态、曲目信息、专辑封面，
     并从 LMS 端（songinfo tags:w）取歌词，支持 LRC 时间轴逐行同步

数据来源（均可自定义/降级）：
  - 参数说明：官方 manpage https://ralph-irving.github.io/squeezelite.html (2025-10-10)
  - LMS 版本库：https://lyrion.org/lms-server-repository/servers.json
  - LMS 当前版本：JSON-RPC  POST /jsonrpc.js  {"params":[0,["version","?"]]}
  - 正在播放：JSON-RPC serverstatus / status / songinfo(tags:w) / artwork /
    musicartistinfo（Music & Artist Information 插件，v1.5.1 起）
  - Squeezelite 二进制：https://sourceforge.net/projects/lmsclients/files/squeezelite/osx/{m1,intel}/
  - 升级内容：GitHub Atom commits（api.github.com 不可用时自动降级）

配置目录： ~/.squeezelite_gui/
"""

import os
import re
import io
import sys
import json
import html
import base64
import time
import shlex
import shutil
import socket
import platform
import tarfile
import hashlib
import subprocess
import threading
import queue
import traceback
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime

# --- Web 版兼容：tkinter 为可选依赖 -------------------------------------
# 本文件是 Tk 版单文件原样复用；Web(pywebview)版只调用前段的纯函数，
# 不实例化 class App。无 Tk 的 Python（如 homebrew）在此处会 ImportError，
# 故用轻量 stub 占位，保证纯函数可导入；若真去实例化 App 会给出明确提示。
try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog, scrolledtext, font as tkfont
    _HAS_TK = True
except Exception:                       # noqa: BLE001 - 缺 Tk 是预期降级
    _HAS_TK = False
    class _NoTk:
        """仅占位：使 class App(tk.Tk) / @ttk.Style 等定义期语句可通过。"""
        TkVersion = 0
        def __getattr__(self, _name):
            return _NoTk()
        def __call__(self, *_a, **_kw):
            return _NoTk()
    tk = _NoTk()
    ttk = messagebox = filedialog = scrolledtext = tkfont = _NoTk()

    class _AppMissingTk:
        def __init__(self, *_a, **_kw):
            raise RuntimeError(
                "Tk GUI 不可用：当前 Python 缺少 tkinter。Web 版无需 tkinter，"
                "请通过 main.py 启动；如需 Tk 版请使用带 Tk 的 Python。")
    _AppBase = _AppMissingTk
else:
    _AppBase = tk.Tk

VERSION = "1.6.0"
APP_NAME = "Squeezelite GUI"
UA = "SqueezeliteGUI/1.0 (macOS; Python; +https://lyrion.org/)"

CONFIG_DIR = os.path.expanduser("~/.squeezelite_gui")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
CACHE_PATH = os.path.join(CONFIG_DIR, "update_cache.json")
BACKUP_DIR = os.path.join(CONFIG_DIR, "backups")
LAUNCH_AGENT = os.path.expanduser("~/Library/LaunchAgents/com.squeezelite.gui.plist")

IS_MAC = (sys.platform == "darwin")

# ---------------------------------------------------------------------------
# Lyrion Material Skin 配色（取自官方 lms-material 仓库，MIT）:
#   css/colors/lyrion.css        --primary-color #589e81 / --accent-color #6cac92
#   css/themes/light.css         --std-background-color #fafafa
#   css/themes/dark-lyrion.css   --std-background-color #081f22 / popup #0d292d
# 本项目仅借用其配色与 Material 视觉语言；GUI 代码、图标均为原创。
# ---------------------------------------------------------------------------
THEMES = {
    # v1.6.0: design-tokens.json v1.1 精确落地。
    # primary = 可交互主色 (WCAG AA: 浅 6.01:1 / 深 8.60:1)
    # brand / prog_fg = Lyrion 原色，仅用于进度条与装饰，不用于正文。
    "light": {
        "bg": "#FAFAFA", "topbar": "#FFFFFF", "surface": "#FFFFFF",
        "surface2": "#F5F8F6", "card": "#FFFFFF", "card_border": "#E0E7E3",
        "border": "#E0E7E3", "divider": "#E4EAE7",
        "text": "#1B2A26", "text2": "#53655E", "text3": "#8E9B95",
        "muted": "#53655E", "disabled": "#8E9B95",
        "primary": "#2F6B52", "primary_dark": "#2A5F49",
        "on_primary": "#FFFFFF", "on_accent": "#FFFFFF",
        "accent": "#2F6B52", "brand": "#589E81", "brand_decorative": "#589E81",
        "app_bar": "#FFFFFF", "on_app_bar": "#1B2A26",
        "ok": "#3E7D62", "warn": "#9A6100", "err": "#B5352B", "error": "#B5352B",
        "sel": "#E2F0EA", "sel_text": "#2F6B52",
        "hover": "#EEF5F1", "selected": "#E2F0EA",
        "link": "#2F6B52", "row_alt": "#F5F8F6",
        "prog_bg": "#DCE5E0", "prog_fg": "#589E81",
        "cover_pad": "#E9EEF0",
        "scroll": "#E0E7E3", "scroll_active": "#2F6B52",
        "terminal_bg": "#12211f", "terminal_fg": "#dceae5", "code_bg": "#F1F5F3",
    },
    "dark": {
        "bg": "#081F22", "topbar": "#0D292D", "surface": "#0D292D",
        "surface2": "#0F2C2F", "card": "#0D292D", "card_border": "#22444A",
        "border": "#22444A", "divider": "#22444A",
        "text": "#EAF3EF", "text2": "#A6BDB6", "text3": "#6E8984",
        "muted": "#A6BDB6", "disabled": "#6E8984",
        "primary": "#7CC7A6", "primary_dark": "#6DB99A",
        "on_primary": "#081F22", "on_accent": "#081F22",
        "accent": "#7CC7A6", "brand": "#6CAC92", "brand_decorative": "#6CAC92",
        "app_bar": "#0D292D", "on_app_bar": "#EAF3EF",
        "ok": "#7CC7A6", "warn": "#E9B15C", "err": "#F0857A", "error": "#F0857A",
        "sel": "#17453E", "sel_text": "#EAF3EF",
        "hover": "#153A3C", "selected": "#17453E",
        "link": "#7CC7A6", "row_alt": "#0F2C2F",
        "prog_bg": "#22444A", "prog_fg": "#6CAC92",
        "cover_pad": "#12332F",
        "scroll": "#22444A", "scroll_active": "#7CC7A6",
        "terminal_bg": "#06171a", "terminal_fg": "#d5e8e1", "code_bg": "#0D292D",
    },
}

# ---------------------------------------------------------------- 数据源
SOURCES = {
    "manpage":        "https://ralph-irving.github.io/squeezelite.html",
    "lms_repo":       "https://lyrion.org/lms-server-repository/servers.json",
    "lms_repo_alt":   "https://lms-community.github.io/lms-server-repository/servers.json",
    "lms_downloads":  "https://downloads.lyrion.org/",
    "sl_atom":        "https://github.com/ralph-irving/squeezelite/commits/master.atom",
    "sl_api":         "https://api.github.com/repos/ralph-irving/squeezelite/commits?per_page=12",
    "lms_atom":       "https://github.com/LMS-Community/slimserver/commits/public/9.1.atom",
    "lms_api":        "https://api.github.com/repos/LMS-Community/slimserver/commits?per_page=12",
    "lms_changelog":  "https://lyrion.org/downloads/",
    "sf_m1":          "https://sourceforge.net/projects/lmsclients/files/squeezelite/osx/m1/",
    "sf_intel":       "https://sourceforge.net/projects/lmsclients/files/squeezelite/osx/intel/",
    "sf_m1_rss":      "https://sourceforge.net/projects/lmsclients/rss?path=/squeezelite/osx/m1",
    "sf_intel_rss":   "https://sourceforge.net/projects/lmsclients/rss?path=/squeezelite/osx/intel",
    "sf_root":        "https://sourceforge.net/projects/lmsclients/files/squeezelite/osx/",
    "sf_dl":          "https://downloads.sourceforge.net/project/lmsclients/squeezelite/osx",
}

DEFAULT_CONFIG = {
    "binary": "",
    "device": "",
    "device_name": "",
    "host_name": "",
    "name_template": "{host} - {short}",
    "device_short": "",
    "params": {},
    "extra": "",
    "lms_host": "",
    "lms_port": "9000",
    "slim_port": "3483",  # SlimProto 端口（-s），区别于 HTTP 9000
    "install_method": "auto",
    "brew_formula": "tsirysndr/tap/squeezelite",
    "sources": {},
    "auto_scan": True,
    "auto_upgrade_check": False,
    "audio_preset": "best",
    "np_auto": True,
    "np_interval": "2",
    "np_playerid": "",
    "lms_user": "",
    "lms_pass": "",
    "theme_mode": "system",
}

# ---------------------------------------------------------------- 参数库
# 每个 option = (实际值, 下拉显示名, 该取值具体效果)
# recommend = 最优音质（bit-perfect）推荐值
PARAMS = [
    # ---------------- 连接 ----------------
    {"key":"server","flag":"-s","name":"LMS 服务器","group":"连接","platform":"all","kind":"text",
     "default":"","recommend":"",
     "options":[
        ("", "自动发现（不传 -s）", "通过 UDP 广播自动发现同网段 LMS，最省心；跨网段或发现失败时改用手动指定"),
        ("127.0.0.1:3483", "本机 127.0.0.1:3483", "LMS 与播放器在同一台 Mac 时使用，连接最稳（3483 是 SlimProto 端口）"),
        ("{LMS_HOST}", "使用「升级」页填写的服务器地址", "自动填入 LMS 主机 + SlimProto 端口 3483，避免两处重复维护"),
     ],
     "effect":"决定播放器连接哪台 LMS；留空则由 squeezelite 自动发现。",
     "detail":"格式 host[:port]，端口是 SlimProto 端口，默认 3483（不是 HTTP 9000）。自动发现依赖 UDP 3483 广播，跨 VLAN/路由器时通常无效，此时必须手动指定。",
     "range":"IP / 主机名 [ :3483 ]，如 192.168.1.10:3483；留空=自动使用 LMS 地址 + 3483"},

    {"key":"name","flag":"-n","name":"播放器名称 (-n)","group":"连接","platform":"all","kind":"text",
     "default":"","recommend":"",
     "options":[("", "由「设备与名称」页自动生成", "自动使用『本机名称 + 音频设备简称』，切换设备时自动更新")],
     "effect":"LMS 服务端「播放器」列表里显示的名字；本工具按所选设备自动生成。",
     "detail":"与 -N（允许服务端改名）互斥。名称会随所选输出设备变化，例如 MyMac - USBDAC，便于在多房间/多设备环境辨认。",
     "range":"任意字符串；建议 ≤ 40 字符，避免空格与特殊符号过多"},

    {"key":"mac","flag":"-m","name":"MAC 地址","group":"连接","platform":"all","kind":"text",
     "default":"","recommend":"",
     "options":[("", "自动检测（推荐）", "使用网卡真实 MAC，LMS 端播放器设置可持久保留"),
                ("ab:cd:ef:12:34:56", "自定义（示例）", "多实例/克隆环境需唯一 MAC，否则 LMS 会把两个播放器认成同一个")],
     "effect":"覆盖播放器的 MAC 地址（LMS 用它作为播放器唯一 ID）。",
     "detail":"同一台机器跑多个 squeezelite 实例时必须各自指定不同 MAC，否则服务端设置互相覆盖。",
     "range":"冒号分隔 6 组十六进制，如 ab:cd:ef:12:34:56"},

    {"key":"model","flag":"-M","name":"型号名称","group":"连接","platform":"all","kind":"text",
     "default":"","recommend":"",
     "options":[("", "默认 SqueezeLite", "标准型号名，兼容性最好"),
                ("SqueezeLite", "显式 SqueezeLite", "与默认相同，便于某些插件识别"),
                ("Squeezebox3", "模拟 Squeezebox3", "让老插件按 SB3 能力处理")],
     "effect":"覆盖 helo 中上报的硬件型号名，影响部分插件的能力判定。",
     "detail":"一般无需修改；仅在某些按型号区别对待的插件/控制器下才需要。",
     "range":"任意字符串"},

    # ---------------- 输出设备（音质核心） ----------------
    {"key":"output","flag":"-o","name":"输出设备 (-o)","group":"输出设备","platform":"all","kind":"text",
     "default":"","recommend":"",
     "options":[("", "由「设备与名称」页选择", "选中设备后自动填入 squeezelite -l 列出的设备名/编号")],
     "effect":"指定音频输出设备；不填用 default，填 - 则把原始 PCM 写到标准输出。",
     "detail":"设备列表由 squeezelite -l（及 macOS system_profiler）扫描得到。设备名含空格时本工具会自动正确加引号。",
     "range":"squeezelite -l 列出的设备名或编号；留空=default"},

    {"key":"device_args","flag":"-a","name":"设备打开参数 (-a)","group":"输出设备","platform":"mac","kind":"text",
     "default":"","recommend":"100:0",
     "options":[
        ("", "默认（由 PortAudio 决定）", "不传 -a；延迟与共享模式交给驱动，通常是最保守的 Play Nice 行为"),
        ("100:0", "★ Pro Mode 独占 + 100ms 延迟（最优音质）", "格式 <延迟ms>:0；Pro Mode(Hog Mode) 独占设备，绕过系统混音器与采样率转换，是实现 bit-perfect 的关键"),
        ("50:0",  "Pro Mode 独占 + 50ms", "独占且更低延迟；网络/USB 不稳时可能出现欠载爆音"),
        ("200:0", "Pro Mode 独占 + 200ms", "独占且更大缓冲，抗抖动最强；切歌/切采样率响应略慢"),
        ("100:1", "Play Nice 共享 + 100ms", "格式 <延迟ms>:1；与其他应用共享输出，系统会重采样到统一时钟，音质有损"),
        ("30:1",  "Play Nice 共享 + 30ms", "共享模式低延迟，适合边听边用其它 App，非音质优先"),
     ],
     "effect":"macOS 专有： -a <l>:<r>，l=目标延迟(ms)，r=0 Pro Mode(独占) / 1 Play Nice(共享)。",
     "detail":"这是 macOS 上最影响音质的参数。Pro Mode 会独占（hog）音频设备，使 CoreAudio 不再做混音/SRC，DAC 收到的即是源码流原始采样率；代价是播放期间其它程序无法出声。Linux ALSA 用 <b>:<p>:<f>:<m>:<d>，Windows 用 <l>:<e>，格式完全不同。",
     "range":"macOS: <延迟ms>:<0|1>，如 100:0；延迟建议 20~500"},

    {"key":"rates","flag":"-r","name":"采样率 (-r)","group":"输出设备","platform":"all","kind":"text",
     "default":"","recommend":"44100-384000",
     "options":[
        ("", "不指定（设备/服务端协商）", "squeezelite 自动探测设备能力；若设备启动时不在线可能探测不到"),
        ("44100-384000", "★ 44.1k ~ 384k 全范围（最优音质）", "声明设备支持 44.1k 到 384k 全部速率，最大程度避免 LMS 端重采样，保持源码流原采样率"),
        ("44100,48000,88200,96000,176400,192000,352800,384000", "枚举全部常见速率", "同上，但以列表精确声明；某些 DAC 对非列表速率支持不佳时更保险"),
        ("44100-192000", "44.1k ~ 192k", "主流 USB DAC 的常见范围，兼容性好"),
        ("44100-96000", "44.1k ~ 96k", "保守设置；高码率文件会被服务端降频"),
        ("44100-384000:500", "全范围 + 切速率等待 500ms", "追加 :<delay>，切换采样率之间等待，给 DAC 锁定时钟，减少切歌爆音"),
     ],
     "effect":"声明输出设备支持的采样率；这是实现 bit-perfect（不重采样）的关键参数。",
     "detail":"格式：单个最大值 / min-max 范围 / 逗号分隔列表，可选追加 :<delay>ms。若不声明且设备启动时关闭，squeezelite 无法探测能力，LMS 可能按保守值转码。注意：还要在 LMS 服务端把该播放器的「音量固定/比特率限制/转码」关掉，才能真正 bit-perfect。",
     "range":"单值 如 192000 / 范围 44100-384000 / 列表 44100,48000 / 追加 :延迟ms"},

    {"key":"report_rate","flag":"-Z","name":"上报最大采样率 (-Z)","group":"输出设备","platform":"all","kind":"text",
     "default":"","recommend":"",
     "options":[("", "不设置（推荐）", "由 -r 与设备探测结果决定 helo 上报值"),
                ("384000", "强制上报 384000", "覆盖 helo 中最大采样率，某些 DAC 需要"),
                ("192000", "强制上报 192000", "限制服务端送来的最高速率")],
     "effect":"覆盖 helo 包里向服务端上报的最大采样率。",
     "detail":"仅影响服务端决策，不改变实际输出。一般不需要；-r 已足够。",
     "range":"正整数 Hz，如 192000"},

    {"key":"dsd","flag":"-D","name":"DSD / DoP (-D)","group":"输出设备","platform":"all","kind":"text",
     "default":"","recommend":"",
     "options":[("", "不启用（PCM 用户推荐）", "不做任何 DSD 处理，纯 PCM bit-perfect 路径最短"),
                ("dop", "DoP（DSD over PCM）", "把 DSD 打包进 PCM 帧送给支持 DoP 的 DAC"),
                ("500:dop", "DoP + 切换延迟 500ms", "PCM/DSD 切换时等待，减少爆音"),
                ("u32le", "原生 DSD u32le", "按 DAC 要求的原生 DSD 格式输出"),
                ("u32be", "原生 DSD u32be", "按 DAC 要求的原生 DSD 格式输出")],
     "effect":"启用 DSD over PCM 或原生 DSD 输出，仅当 DAC 支持 DSD 时才需要。",
     "detail":"格式 [delay][:format]，format 可为 dop(默认)/u8/u16le/u16be/u32le/u32be。普通 PCM 听音不要开，否则路径多余。",
     "range":"dop / u8 / u16le / u16be / u32le / u32be，可前缀 <延迟ms>:"},

    # ---------------- 重采样与处理 ----------------
    {"key":"resample","flag":"-u|-R","name":"重采样 / 升频 (-u / -R)","group":"重采样与处理","platform":"all","kind":"text",
     "default":"","recommend":"",
     "options":[
        ("", "★ 不启用（最优音质 / bit-perfect）", "不对数据做任何重采样，DAC 收到源文件原始采样率与位深"),
        ("vLs", "极高质量 vLs", "v=Very High、L=线性相位、s=99% 带宽；音质最好的重采样，但已改变原始数据"),
        ("hL",  "高质量 hL（默认 recipe）", "High + 线性相位，等同于只写 -u"),
        ("hMX", "高质量 + 异步升频到设备最高速率", "hM 最小相位 + X 异步升频，所有素材统一升到最高速率"),
        ("E",   "仅必要时重采样", "E 标志：设备原生支持该速率时跳过重采样，兼容性折中方案"),
        (":::", "高级自定义 recipe", "在自定义框里填写完整 <recipe>:<flags>:<attenuation>:<precision>:... 参数"),
     ],
     "effect":"用 SoX Resampler 对音频重采样/升频；音质优先应关闭。",
     "detail":"-u 与 -R 等价。参数格式 <recipe>:<flags>:<attenuation>:<precision>:<passband_end>:<stopband_start>:<phase_response>。recipe 由 [v|h|m|l|q][L|I|M][s][E|X] 组成，默认 hL；默认带 -1dB 衰减防削波（::0 可关）。一旦启用，输出不再是 bit-perfect。",
     "range":"recipe 如 vLs / hMX / E，或完整 7 段冒号参数（见说明）"},

    {"key":"wave_header","flag":"-W","name":"从 WAV/AIFF 头读取 (-W)","group":"重采样与处理","platform":"all","kind":"bool",
     "default":"","recommend":"",
     "options":[("", "不启用（推荐）", "遵循服务端给出的格式参数，标准路径"),
                ("1", "启用", "忽略服务端参数，改从 wave/aiff 文件头解析格式")],
     "effect":"忽略服务端声明的格式，直接从文件头读取 WAV/AIFF 信息。",
     "detail":"只在服务端参数明显错误、或播放特殊封装文件时才需要；常规使用不要开。",
     "range":"开关：留空=关 / 1=开"},

    {"key":"visualiser","flag":"-v","name":"可视化支持 (-v)","group":"重采样与处理","platform":"all","kind":"bool",
     "default":"","recommend":"",
     "options":[("", "不启用（推荐）", "不创建共享内存，路径最干净、开销最低"),
                ("1", "启用", "创建共享内存供外部可视化程序读取音频数据")],
     "effect":"开启后 squeezelite 会把部分音频写入共享内存供可视化器读取。",
     "detail":"只是旁路拷贝，理论上不改数据，但会增加内存/CPU 开销；音质优先不建议开。",
     "range":"开关：留空=关 / 1=开"},

    {"key":"codecs","flag":"-c","name":"限制编解码 (-c)","group":"重采样与处理","platform":"all","kind":"text",
     "default":"","recommend":"",
     "options":[("", "不限制（推荐，加载全部）", "自动加载编译时内置的全部解码器，兼容性最好"),
                ("flac,mp3", "仅 FLAC / MP3", "减少解码器加载，排错时可缩小范围"),
                ("flac,mp3,aac,alac,ogg", "常见无损+有损组合", "覆盖绝大多数曲库")],
     "effect":"只启用指定的解码器；不设则加载全部内置 codec。",
     "detail":"用 squeezelite -? 可查看本机构建包含的 codec 列表。限制后对应格式将无法播放（可能被服务端转码）。",
     "range":"逗号分隔 codec 名，如 flac,mp3,aac"},

    {"key":"exclude","flag":"-e","name":"排除编解码 (-e)","group":"重采样与处理","platform":"all","kind":"text",
     "default":"","recommend":"",
     "options":[("", "不排除（推荐）", "全部格式原生支持"),
                ("mp3", "排除 MP3 原生支持", "强制服务端把 MP3 转码（一般只用于排错）")],
     "effect":"显式排除某些格式的原生支持，使服务端改为转码。",
     "detail":"与 -c 相反；通常不需要，排除会让 LMS 介入转码，反而降低音质。",
     "range":"逗号分隔 codec 名"},

    # ---------------- 缓冲与稳定性 ----------------
    {"key":"buffer","flag":"-b","name":"流/输出缓冲 (-b)","group":"缓冲与稳定性","platform":"all","kind":"text",
     "default":"","recommend":"8192:8192",
     "options":[
        ("", "默认 2048:3445", "官方默认值；网络稳定时够用"),
        ("4096:4096", "4096:4096 中等", "适度增大，兼顾延迟与抗抖动"),
        ("8192:8192", "★ 8192:8192（推荐）", "流缓冲与输出缓冲都加大，显著减少 Wi-Fi 抖动导致的欠载/爆音；不改变音质，只提升稳定性"),
        ("16384:16384", "16384:16384 大缓冲", "网络很差或高码率 DSD 时用；切歌响应变慢、内存占用增加"),
     ],
     "effect":"设置内部流缓冲与输出缓冲大小（KB），只影响稳定性，不改变音频数据。",
     "detail":"格式 <stream>:<output>，官方默认 2048:3445。缓冲太小在网络抖动时会产生 buffer underrun（爆音）；太大则切歌/暂停响应变慢。",
     "range":"<整数>:<整数>，单位 KB，建议 512~32768"},

    {"key":"idle_close","flag":"-C","name":"空闲关闭设备 (-C)","group":"缓冲与稳定性","platform":"all","kind":"text",
     "default":"","recommend":"",
     "options":[("", "★ 永不关闭（最优音质）", "播放器开机期间一直占用输出设备，避免重新打开时的时钟/采样率重新协商"),
                ("30", "空闲 30 秒后关闭", "省电，但再次播放需重新打开设备"),
                ("300", "空闲 5 分钟后关闭", "折中方案")],
     "effect":"播放器空闲 N 秒后关闭输出设备；默认保持设备一直打开。",
     "detail":"对 USB DAC，反复开关设备可能导致重新枚举、采样率回落；音质优先保持常开。",
     "range":"正整数秒；留空=一直保持打开"},

    {"key":"priority","flag":"-p","name":"输出线程实时优先级 (-p)","group":"缓冲与稳定性","platform":"all","kind":"int",
     "default":"","recommend":"45",
     "options":[("", "默认 45", "官方默认值"),
                ("45", "★ 45（macOS 推荐保持默认）", "macOS 使用 PortAudio 后端时 -p 不适用，保持默认最稳妥"),
                ("80", "80 较高", "Linux ALSA 下可减少调度抖动；Mac 上无效"),
                ("99", "99 最高", "仅特殊实时内核环境使用")],
     "effect":"设置输出线程的实时优先级（1-99，默认 45）。",
     "detail":"官方注明：使用 PortAudio 时不适用（macOS 构建即 PortAudio），因此 Mac 上改这个值通常没有效果；Linux ALSA 下提高可减少 xrun。",
     "range":"整数 1~99；留空=默认 45"},

    # ---------------- 日志与进程 ----------------
    {"key":"loglevel","flag":"-d","name":"日志级别 (-d)","group":"日志与进程","platform":"all","kind":"text",
     "default":"","recommend":"all=info",
     "options":[("", "不设置（默认）", "使用程序内置日志级别"),
                ("all=info", "★ all=info（推荐）", "只输出关键信息，磁盘/终端 I/O 最少，避免日志写入干扰播放线程"),
                ("all=debug", "all=debug 排错", "输出全部调试日志，定位问题时用；平时不要开"),
                ("output=debug", "仅输出线程 debug", "排查设备/采样率问题时很有用"),
                ("stream=info", "仅流缓冲 info", "排查网络欠载时使用")],
     "effect":"按类别设置日志级别，可重复传 -d 多次（用自定义参数框追加）。",
     "detail":"类别 all/slimproto/stream/decode/output/ir，级别 info/debug/sdebug。排错期可开 debug，稳定听音建议 all=info 或配合 -f 写文件。",
     "range":"<类别>=<级别>，如 all=info；多个用自定义参数重复 -d"},

    {"key":"logfile","flag":"-f","name":"日志文件 (-f)","group":"日志与进程","platform":"all","kind":"text",
     "default":"","recommend":"",
     "options":[("", "输出到终端 / GUI", "由本工具实时捕获显示"),
                ("~/Library/Logs/squeezelite.log", "写入 macOS 日志目录", "后台长期运行时便于事后排查")],
     "effect":"把日志写入文件而不是 stdout/stderr。",
     "detail":"GUI 运行时日志已实时显示；只有做开机自启/后台守护时才需要落文件。",
     "range":"可写文件路径"},

    {"key":"pidfile","flag":"-P","name":"PID 文件 (-P)","group":"日志与进程","platform":"all","kind":"text",
     "default":"","recommend":"",
     "options":[("", "不写（推荐）", "由本工具直接管理进程"),
                ("~/Library/Logs/squeezelite.pid", "写入 PID 文件", "配合 -z 守护进程或外部脚本管理")],
     "effect":"把进程号写入指定文件。",
     "detail":"仅在以守护方式运行、需要外部脚本 stop/restart 时才用。",
     "range":"可写文件路径"},

    {"key":"daemon","flag":"-z","name":"后台守护 (-z)","group":"日志与进程","platform":"all","kind":"bool",
     "default":"","recommend":"",
     "options":[("", "不启用（GUI 推荐）", "前台运行，GUI 可实时显示日志与停止进程"),
                ("1", "启用 daemon", "脱离终端后台运行；GUI 将无法再捕获日志")],
     "effect":"让 squeezelite 以守护进程方式脱离终端运行。",
     "detail":"由本工具「启动控制」管理时请勿开启，否则点停止会失效。开机自启 LaunchAgent 场景也不需要（launchd 自己管理）。",
     "range":"开关：留空=关 / 1=开"},

    {"key":"server_name_file","flag":"-N","name":"允许服务端改名 (-N)","group":"日志与进程","platform":"all","kind":"text",
     "default":"","recommend":"",
     "options":[("", "不启用（推荐由本工具命名）", "使用 -n 固定为『本机名+设备简称』，与需求一致"),
                ("~/.squeezelite_gui/name.txt", "启用并持久化到文件", "由 LMS 端改名并保存；注意与 -n 互斥")],
     "effect":"允许 LMS 服务端设置播放器名称，名称持久化到指定文件。",
     "detail":"官方注明与 -n 互斥。若启用本项，请务必把 -n（播放器名称）清空，否则参数冲突。",
     "range":"可写文件路径；与 -n 互斥"},

    # ---------------- 高级 / 平台专用 ----------------
    {"key":"mixer","flag":"-O","name":"混音设备 (-O)","group":"高级与平台专用","platform":"linux","kind":"text",
     "default":"","recommend":"",
     "options":[("", "默认（同输出设备）", "Linux ALSA 专用")],
     "effect":"指定 ALSA mixer 设备，默认与 -o 相同。","detail":"仅 Linux ALSA；macOS 不适用。","range":"ALSA 设备名"},
    {"key":"gpio","flag":"-G","name":"GPIO 功放继电器 (-G)","group":"高级与平台专用","platform":"linux","kind":"text",
     "default":"","recommend":"",
     "options":[("", "不启用", "树莓派等 GPIO 控制功放电源时才用")],
     "effect":"指定 GPIO chip:line:H/L，播放时控制功放继电器。","detail":"仅 Linux；与 -S 互斥。","range":"<chip>:<#>:<H|L>"},
    {"key":"power_script","flag":"-S","name":"电源脚本 (-S)","group":"高级与平台专用","platform":"linux","kind":"text",
     "default":"","recommend":"",
     "options":[("", "不启用", "收到 LMS 电源命令时执行外部脚本")],
     "effect":"指定电源控制脚本绝对路径。","detail":"仅 Linux；与 -G 互斥。","range":"脚本绝对路径"},
    {"key":"lirc","flag":"-i","name":"LIRC 遥控 (-i)","group":"高级与平台专用","platform":"linux","kind":"text",
     "default":"","recommend":"",
     "options":[("", "不启用", "Linux 红外遥控支持")],
     "effect":"启用 LIRC 遥控，可选指定 ~/.lircrc 路径。","detail":"仅 Linux。","range":"留空=不启用 / 配置文件路径"},
    {"key":"alsa_vol","flag":"-V","name":"ALSA 硬件音量 (-V)","group":"高级与平台专用","platform":"linux","kind":"text",
     "default":"","recommend":"",
     "options":[("", "软件音量（默认）", "squeezelite 内部软件调音量，路径最短"),
                ("PCM", "使用 PCM 硬件控制", "用声卡硬件调音量；与 -U 互斥")],
     "effect":"用指定 ALSA 控件调音量，禁用软件音量。","detail":"仅 Linux ALSA；与 -U 互斥，另有 -U(启动时取消静音) 与 -X(线性音量)。","range":"ALSA 控件名"},
]

# ---------------------------------------------------------------- 通用工具
def now_str():
    return datetime.now().strftime("%H:%M:%S")

def http_request(url, data=None, headers=None, timeout=12, log=None, progress=None):
    h = {"User-Agent": UA, "Accept-Encoding": "identity", "Accept": "*/*"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h,
                                 method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        chunks, total = [], 0
        while True:
            b = r.read(65536)
            if not b:
                break
            chunks.append(b); total += len(b)
            if progress:
                progress(total)
        return b"".join(chunks)

def http_get(url, timeout=12, log=None):
    return http_request(url, timeout=timeout, log=log).decode("utf-8", "replace")

def fetch_any(urls, parser, log, label):
    """依次尝试多个数据源；返回 (结果, 实际使用的 URL)。全失败抛异常。"""
    errors = []
    for u in [x for x in urls if x]:
        try:
            if log:
                log("  → 尝试源: %s" % u)
            text = http_get(u, timeout=12, log=log)
            result = parser(text)
            if result:
                if log:
                    log("  ✓ 命中源: %s" % u)
                return result, u
            errors.append("%s: 返回空结果" % u)
        except Exception as e:
            errors.append("%s: %s" % (u, str(e)[:90]))
    raise RuntimeError("%s 全部数据源不可用：\n  " % label + "\n  ".join(errors))

def parse_version(s):
    """把 LMS 版本号（如 9.x / 2.0.0.x）转成可比较元组。"""
    if not s:
        return (0,)
    nums = [int(x) for x in re.findall(r"\d+", str(s))]
    return tuple(nums[:5]) or (0,)

def ver_cmp(a, b):
    x, y = parse_version(a), parse_version(b)
    n = max(len(x), len(y))
    x += (0,) * (n - len(x)); y += (0,) * (n - len(y))
    return (x > y) - (x < y)

def ver_display(ver, rev=""):
    return str(ver) + ((" (r" + str(rev) + ")") if rev else "")

# ---------------------------------------------------------------- 名称与设备
STOP_WORDS = {"built", "in", "output", "device", "audio", "speaker", "speakers",
              "default", "coreaudio", "the", "and", "digital", "external", "stereo"}
SHORT_MAP = [
    (r"built.?in.*(output|speaker)|internal.?speaker", "BuiltIn"),
    (r"headphone|耳机|headset", "Headphone"),
    (r"airpod|bluetooth", "BT"),
    (r"hdmi", "HDMI"),
    (r"displayport", "DP"),
    (r"optical|toslink|spdif|s\/pdif", "SPDIF"),
    (r"usb", "USB"),
    (r"thunderbolt", "TB"),
]

def device_short(name):
    """由音频设备全名生成简短标识，如 'Built-in Output' -> BuiltIn / 'USB Audio DAC' -> USBDac。"""
    if not name:
        return "AUDIO"
    low = name.lower()
    words = re.findall(r"[A-Za-z0-9]+", name)
    for pat, tag in SHORT_MAP:
        if re.search(pat, low):
            rest = [w for w in words
                    if w.lower() not in STOP_WORDS and w.lower() not in tag.lower()
                    and not re.search(pat, w.lower())]
            suffix = "".join(w[:1].upper() + w[1:].lower() for w in rest[:1])
            return (tag + suffix)[:16]
    core = [w for w in words if w.lower() not in STOP_WORDS] or words or ["Audio"]
    return "".join(w[:1].upper() + w[1:].lower() for w in core[:2])[:16]

def local_host_name():
    """macOS 用 ComputerName；其它平台回退 hostname。"""
    try:
        if IS_MAC:
            r = subprocess.run(["scutil", "--get", "ComputerName"],
                               capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
    except Exception:
        pass
    try:
        r = subprocess.run(["hostname", "-s"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return socket.gethostname().split(".")[0] or "Mac"

def make_player_name(host, short, template):
    t = (template or "{host} - {short}").strip()
    try:
        v = t.format(host=host, short=short)
    except Exception:
        v = "%s - %s" % (host, short)
    return v.strip()[:60]

def find_binary(cfg):
    """定位 squeezelite 可执行文件。

    优先级：用户显式配置 > .app 内置（launcher 注入的环境变量 / 脚本同目录）
    > PATH 与常见安装位置。打包成 Squeezelite GUI.app 后双击即可识别内置
    二进制；联网升级会就地替换它，旧版备份到 ~/.squeezelite_gui/backups/。
    """
    c = (cfg.get("binary") or "").strip()
    here = os.path.dirname(os.path.abspath(__file__))
    cands = ([c] if c else []) + [
        os.environ.get("SQUEEZELITE_GUI_BINARY", ""),
        os.path.join(here, "squeezelite"),
        os.path.join(here, "..", "MacOS", "squeezelite"),
        shutil.which("squeezelite"),
        "/opt/homebrew/bin/squeezelite", "/usr/local/bin/squeezelite",
        "/usr/bin/squeezelite", os.path.expanduser("~/bin/squeezelite"),
        "/Applications/Squeezelite/squeezelite",
    ]
    for p in cands:
        if p and os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return c if c else ""

def parse_l_output(text):
    """解析 squeezelite -l 的设备列表（兼容多种后端格式）。"""
    devs = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        if re.match(r"^(output devices|available|squeezelite\s+v)", s, re.I):
            continue
        # 兼容 "0 - 设备"、"3: 设备"、"* default : 设备" 等多种后端输出
        m = re.match(r"^(\*|\d+)\s*(?:default\s*)?[-:]\s*(.+)$", s)
        if not m:
            m = re.match(r"^(\d+)\)\s*(.+)$", s)
        if not m and " - " in s and not re.match(
                r"^(output|available|squeezelite|device)", s, re.I):
            nm = s.split(" - ", 1)[0].strip()
            if nm and len(nm) < 80 and not nm.startswith("-") \
                    and "copyright" not in nm.lower():
                devs.append({"id": "", "name": nm, "raw": s,
                             "source": "squeezelite -l", "is_default": False})
            continue
        if not m:
            continue
        idx, rest = m.group(1), m.group(2).strip()
        name = rest
        for _ in range(2):   # 剥离顺序可能是 [CoreAudio] (default) 或反之
            name = re.sub(r"\s*\((?:default|Default)\)\s*$", "", name, flags=re.I).strip()
            name = re.sub(r"\s*\[[^\]]*\]\s*$", "", name).strip()
        if not name or name.lower() in ("default", "-"):
            continue
        devs.append({"id": "" if idx == "*" else idx, "name": name,
                     "raw": rest, "source": "squeezelite -l",
                     "is_default": idx == "*" or "default" in rest.lower()})
    return devs

def system_profiler_devices():
    """macOS 原生音频设备枚举（system_profiler SPAudioDataType -json），作为 -l 的补充。"""
    if not IS_MAC:
        return []
    try:
        r = subprocess.run(["system_profiler", "SPAudioDataType", "-json"],
                           capture_output=True, text=True, timeout=20)
        d = json.loads(r.stdout or "{}")
        out = []
        for it in d.get("SPAudioDataType", []) or []:
            nm = it.get("_name")
            if not nm:
                continue
            out.append({
                "id": "", "name": nm, "raw": "%s | %s Hz" % (
                    it.get("coreaudio_device_manufacturer", ""),
                    it.get("coreaudio_device_srate", "")),
                "source": "system_profiler",
                "is_default": str(it.get("coreaudio_default_audio_output_device", "")).lower() in ("yes", "1", "true"),
                "srate": it.get("coreaudio_device_srate", ""),
            })
        return out
    except Exception:
        return []

def scan_devices(cfg, log=None):
    """自动扫描：squeezelite -l 为主，macOS system_profiler 补充；失败时返回空并给出原因。"""
    binary = find_binary(cfg)
    result, reasons = [], []
    if binary:
        try:
            r = subprocess.run([binary, "-l"], capture_output=True, text=True, timeout=15)
            devs = parse_l_output((r.stdout or "") + "\n" + (r.stderr or ""))
            if devs:
                result.extend(devs)
                if log:
                    log("squeezelite -l 发现 %d 个输出设备" % len(devs))
            else:
                reasons.append("squeezelite -l 未解析出设备（输出：%s）" % (r.stdout or r.stderr or "")[:120])
        except Exception as e:
            reasons.append("squeezelite -l 执行失败: %s" % str(e)[:120])
    else:
        reasons.append("未找到 squeezelite 可执行文件（可在「设备」页手动指定，或先到「升级」页安装）")

    extra = system_profiler_devices()
    if extra:
        known = {d["name"].lower() for d in result}
        for d in extra:
            if d["name"].lower() not in known:
                result.append(d)
        if log:
            log("system_profiler 补充 %d 个设备" % len(extra))
    if not extra and IS_MAC:
        reasons.append("system_profiler 未返回音频设备")

    # 去重 + 默认项排前
    seen, uniq = set(), []
    for d in sorted(result, key=lambda x: not x.get("is_default")):
        k = (d["name"].lower(), d.get("id", ""))
        if k in seen:
            continue
        seen.add(k); uniq.append(d)
    return uniq, reasons, binary

# ---------------------------------------------------------------- 命令构建
def resolve_special(v, cfg):
    if not v:
        return v
    host = (cfg.get("lms_host") or "").strip()
    if host:
        if "://" in host:
            host = host.split("://", 1)[1]
        host = host.rstrip("/")
        if host.startswith("["):
            host = host.split("]", 1)[0] + "]"
        elif ":" in host:
            host = host.rsplit(":", 1)[0]
        slim = str(cfg.get("slim_port") or "3483").strip() or "3483"
        host = host + ":" + slim
    return v.replace("{LMS_HOST}", host).replace("{HOST}", host)

PARAM_VALIDATORS = {
    "device_args": (r"^\d+(?::[01])?$", "macOS 格式 <延迟ms>:<0|1>，如 100:0（第二位 0=Pro Mode / 1=Play Nice）"),
    "rates":       (r"^\d+(?:-\d+|(?:,\d+)+)?(?::\d+)?$", "格式：单值 / min-max / 逗号列表，可追加 :延迟ms"),
    "report_rate": (r"^\d+$", "正整数 Hz"),
    "buffer":      (r"^\d+(?::\d+)?$", "格式 <stream>:<output>，单位 KB"),
    "idle_close":  (r"^\d+$", "正整数秒"),
    "priority":    (r"^\d{1,2}$", "1~99 的整数"),
    "mac":         (r"^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$", "冒号分隔 6 组十六进制"),
    "loglevel":    (r"^[a-z]+=[a-z]+$", "格式 <类别>=<级别>，如 all=info"),
    "server":      (r"^[^\s:]+(?::\d+)?$", "host[:port]，如 192.168.1.10:9000"),
}

def validate_param(p, v):
    v = ("" if v is None else str(v)).strip()
    if not v:
        return True, ""
    if p["kind"] == "bool":
        return (True, "") if v in ("", "0", "1", "true", "false", "yes", "no") else (False, "开关值只能是 1 或留空")
    pat = PARAM_VALIDATORS.get(p["key"])
    if pat and not re.match(pat[0], v):
        return False, "取值不合法：" + pat[1]
    if p["key"] == "priority" and not (1 <= int(v) <= 99):
        return False, "优先级必须在 1~99"
    if p["key"] == "dsd" and v not in ("dop", "u8", "u16le", "u16be", "u32le", "u32be") \
            and not re.match(r"^\d+:(?:dop|u8|u16le|u16be|u32le|u32be)$", v):
        return False, "DSD 格式应为 dop/u8/u16le/u16be/u32le/u32be（可加 延迟: 前缀）"
    return True, ""

def _link_values(cfg, values):
    """把「设备与名称」页 / LMS 页维护的配置联动到 squeezelite 启动参数。

    此前 server / name / output 三个字段只在界面回显，从未进入 argv：
    没有 -s 就只能靠 UDP 自动发现（跨网段/远程 LMS 必然失败），
    没有 -n / -o 则播放器名和输出设备也不受界面控制。
    所有构建命令的入口统一经过这里，保证界面选择与真实命令一致。
    """
    eff = dict(values or {})
    # 1) LMS 地址：参数页留空时，自动使用「升级与更新」页填写的服务器
    if not str(eff.get("server") or "").strip():
        host = str(cfg.get("lms_host") or "").strip()
        if host:
            if "://" in host:
                host = host.split("://", 1)[1]
            host = host.rstrip("/")
            if host.startswith("["):
                host = host.split("]", 1)[0] + "]"
            elif ":" in host:
                host = host.rsplit(":", 1)[0]
            slim = str(cfg.get("slim_port") or "3483").strip() or "3483"
            eff["server"] = host + ":" + slim
    # 2) 播放器名：使用「设备与名称」页生成的名字
    if not str(eff.get("name") or "").strip():
        try:
            nm = make_player_name(
                cfg.get("host_name") or local_host_name(),
                cfg.get("device_short") or "",
                cfg.get("name_template") or "{host} - {short}")
        except Exception:
            nm = ""
        if nm:
            eff["name"] = nm
    # 3) 输出设备：使用「设备与名称」页选中的设备
    if not str(eff.get("output") or "").strip():
        dev = str(cfg.get("device") or "").strip() or str(cfg.get("device_name") or "").strip()
        if dev:
            eff["output"] = dev
    return eff


def build_argv(cfg, values):
    binary = find_binary(cfg) or "squeezelite"
    argv = [binary]
    eff = _link_values(cfg, values)
    for p in PARAMS:
        v = eff.get(p["key"], p.get("default", ""))
        if v is None:
            continue
        v = str(v).strip()
        if not v:
            continue
        v = resolve_special(v, cfg)
        if p["kind"] == "bool":
            if v in ("1", "true", "yes", "on", "启用"):
                argv.append(p["flag"])
            continue
        flag = p["flag"].split("|")[0]
        argv += [flag, v]
    extra = (cfg.get("extra") or "").strip()
    if extra:
        try:
            argv += shlex.split(extra)
        except ValueError:
            argv += [extra]
    return argv

def preview_cmd(argv):
    try:
        return shlex.join(argv)
    except AttributeError:
        return " ".join(shlex.quote(a) for a in argv)

def validate_all(values, extra=""):
    problems = []
    if (values.get("name") or "").strip() and (values.get("server_name_file") or "").strip():
        problems.append("-n 与 -N 互斥（官方说明）：请清空「允许服务端改名」或播放器名称")
    for p in PARAMS:
        ok, msg = validate_param(p, values.get(p["key"], ""))
        if not ok:
            problems.append("%s (%s): %s" % (p["name"], p["flag"], msg))
    if extra.strip():
        try:
            toks = shlex.split(extra)
        except ValueError as e:
            problems.append("自定义参数引号不匹配: %s" % e)
        else:
            used = {p["flag"].split("|")[0] for p in PARAMS}
            repeatable = {"-d"}  # -d 可重复，用于给不同类别设置日志级别
            for t in toks:
                if t.startswith("-") and t in used and t not in repeatable:
                    problems.append("自定义参数重复了已在上方配置的 %s，请用上方下拉修改" % t)
    return problems

def best_preset():
    return {p["key"]: p.get("recommend", "") for p in PARAMS}

# ---------------------------------------------------------------- 版本检测
def sq_local_version(binary, log=None):
    if not binary or not os.path.isfile(binary):
        return None
    for flag in ("-t", "--version", "-?"):
        try:
            r = subprocess.run([binary, flag], capture_output=True, text=True, timeout=8)
            out = (r.stdout or "") + "\n" + (r.stderr or "")
            m = re.search(r"Squeezelite\s+v?([\d][\d.]*)", out, re.I)
            if m:
                rev = re.search(r"(?:revision|rev)\s*[:#]?\s*(\d+)", out, re.I)
                return {"version": m.group(1).rstrip("."),
                        "revision": rev.group(1) if rev else "",
                        "raw": " ".join(out.split())[:220]}
        except Exception:
            continue
    return None

def brew_version(cfg, log=None):
    brew = shutil.which("brew") or ("/opt/homebrew/bin/brew" if os.path.isfile("/opt/homebrew/bin/brew")
                                   else "/usr/local/bin/brew")
    formula = (cfg.get("brew_formula") or "tsirysndr/tap/squeezelite").strip()
    if not os.path.isfile(brew):
        return None
    try:
        r = subprocess.run([brew, "list", "--versions", formula],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            return {"version": r.stdout.strip(), "formula": formula, "brew": brew}
    except Exception:
        pass
    return None

SF_FILE_RE = re.compile(
    r"(squeezelite-(\d+\.\d+(?:\.\d+)?)[.\-](\d+)-osx-(m1|intel)\.(?:tar\.gz|tgz|zip))", re.I)

def parse_sf_filenames(text):
    """解析 SourceForge 上的两种 macOS 发布命名：
       Intel : squeezelite-2.0.0.1465-osx-intel.tar.gz   (tar.gz)
       M1    : Squeezelite-M1-2.0.0r1610.dmg              (dmg 安装包)
       优先从页面/RSS 的 /download 链接取精确 URL。
    """
    text = text or ""
    patterns = [
        (re.compile(r"^squeezelite-(\d+\.\d+(?:\.\d+)?)[.\-](\d+)-osx-(m1|intel)\.(?:tar\.gz|tgz|zip)$", re.I), "targz"),
        (re.compile(r"^squeezelite-(m1|intel)-(\d+\.\d+(?:\.\d+)?)r(\d+)\.dmg$", re.I), "dmg"),
    ]
    cands = {}
    for u in re.findall(r'https?://[^\s"\'<>]+?/download', text, re.I):
        fn = urllib.parse.unquote(u.rsplit("/download", 1)[0].rstrip("/").split("/")[-1])
        if "squeezelite" in fn.lower():
            cands.setdefault(fn, u)
    for fn in re.findall(
            r"[A-Za-z0-9._+-]*squeezelite[A-Za-z0-9._+-]*\.(?:tar\.gz|tgz|zip|dmg)", text, re.I):
        cands.setdefault(fn, "")
    out, seen = [], set()
    for fn, url in cands.items():
        rec = None
        for pat, kind in patterns:
            m = pat.match(fn)
            if not m:
                continue
            if kind == "targz":
                ver, rev, arch = m.group(1), m.group(2), m.group(3).lower()
            else:
                arch, ver, rev = m.group(1).lower(), m.group(2), m.group(3)
            rec = {"filename": fn, "version": ver, "revision": rev,
                   "arch": arch, "kind": kind}
            break
        if not rec or fn.lower() in seen:
            continue
        seen.add(fn.lower())
        rec["url"] = url or ("https://sourceforge.net/projects/lmsclients/files/"
                             "squeezelite/osx/%s/%s/download" % (rec["arch"], fn))
        rec["label"] = "v%s (r%s) · %s · %s" % (
            rec["version"], rec["revision"], rec["arch"], rec["kind"])
        out.append(rec)
    out.sort(key=lambda x: (parse_version(x["version"]), int(x["revision"])), reverse=True)
    return out

def sf_arch():
    m = platform.machine().lower()
    return "m1" if m in ("arm64", "aarch64") else "intel"

def sq_latest(log=None, cfg=None):
    """聚合当前架构 + 另一架构的 SourceForge 源；并记录源码最新 revision。"""
    cfg = cfg or {}
    arch = sf_arch()
    other = "intel" if arch == "m1" else "m1"
    custom = [cfg.get("sources", {}).get("sf_" + a) for a in (arch, other)]
    urls = (custom
            + [SOURCES["sf_" + a + "_rss"] for a in (arch, other)]
            + [SOURCES["sf_" + a] for a in (arch, other)]
            + [SOURCES["sf_root"]])
    items, used = [], []
    for u in [x for x in urls if x]:
        try:
            if log:
                log("  → 尝试源: %s" % u)
            got = parse_sf_filenames(http_get(u, timeout=8, log=log))
            if got:
                items.extend(got)
                used.append(u)
                if log:
                    log("  ✓ 命中 %d 个文件: %s" % (len(got), u))
        except Exception as e:
            if log:
                log("  ! 源失败 %s (%s)" % (u, str(e)[:70]))
    uniq = {}
    for x in items:
        uniq.setdefault(x["filename"].lower(), x)
    items = sorted(uniq.values(),
                   key=lambda x: (parse_version(x["version"]), int(x["revision"])), reverse=True)
    pref = [x for x in items if x["arch"] == arch] or items
    # 源码最新 revision（Atom <content> 里的 "Increase squeezelite revision to NNNN"）
    src_rev = ""
    try:
        ch, _ = changelog("sl", log, cfg)
        for c in ch:
            m = re.search(r"revision\s+to\s+(\d+)",
                          (c.get("body") or c.get("title") or ""), re.I)
            if m:
                src_rev = m.group(1)
                break
    except Exception:
        pass
    latest = pref[0] if pref else {
        "filename": "", "version": "", "revision": src_rev, "arch": arch,
        "kind": "", "url": SOURCES["sf_" + arch],
        "label": ("源码最新 r" + src_rev) if src_rev else "请到 SourceForge 查看"}
    return {"arch": arch, "items": items, "latest": latest, "source_rev": src_rev,
            "source": " + ".join(used) if used else "GitHub commits（降级）",
            "degraded": not items}

def parse_atom(text):
    out = []
    for e in re.findall(r"<entry>(.*?)</entry>", text or "", re.S):
        t = re.search(r"<title[^>]*>(.*?)</title>", e, re.S)
        u = (re.search(r"<updated>(.*?)</updated>", e, re.S)
             or re.search(r"<published>(.*?)</published>", e, re.S))
        l = re.search(r'<link[^>]+href="([^"]+)"', e)
        c = re.search(r"<content[^>]*>(.*?)</content>", e, re.S)
        title = html.unescape(re.sub(r"<[^>]+>", " ", t.group(1))) if t else ""
        body = re.sub(r"<[^>]+>", " ", html.unescape(c.group(1))) if c else ""
        out.append({"date": (u.group(1)[:10] if u else ""),
                    "title": re.sub(r"\s+", " ", title).strip(),
                    "body": re.sub(r"\s+", " ", body).strip(),
                    "url": l.group(1) if l else ""})
    return out

def parse_api_commits(text):
    data = json.loads(text)
    out = []
    for c in data if isinstance(data, list) else []:
        cm = c.get("commit", {}) or {}
        msg = (cm.get("message") or "").strip().splitlines()
        out.append({"date": (cm.get("author", {}) or {}).get("date", "")[:10],
                    "title": (msg[0] if msg else "").strip(),
                    "url": c.get("html_url", "")})
    return out

def changelog(kind, log=None, cfg=None):
    """升级内容：优先 GitHub Atom（无需 API、可达性最好），API 作为增强源。"""
    cfg = cfg or {}
    atom = cfg.get("sources", {}).get(kind + "_atom") or SOURCES[kind + "_atom"]
    api = cfg.get("sources", {}).get(kind + "_api") or SOURCES[kind + "_api"]
    for u in (atom, api):
        try:
            text = http_get(u, timeout=10, log=log)
            items = parse_atom(text) if ("<feed" in text[:600] or "atom" in u) else parse_api_commits(text)
            if items:
                return items[:20], u
        except Exception as e:
            if log:
                log("  ! 更新日志源不可用 %s (%s)" % (u, str(e)[:70]))
    return [], ""

def lms_auth_headers(cfg):
    """LMS 启用密码保护时返回 Basic Auth 头；用户名可为空（仅设密码的情形）。"""
    user = (cfg.get("lms_user") or "").strip()
    passwd = cfg.get("lms_pass") or ""
    if not (user or passwd):
        return {}
    import base64
    tok = base64.b64encode(("%s:%s" % (user, passwd)).encode("utf-8")).decode("ascii")
    return {"Authorization": "Basic " + tok}


def lms_current(cfg, log=None):
    host = (cfg.get("lms_host") or "").strip()
    port = (cfg.get("lms_port") or "9000").strip()
    if not host:
        return {"ok": False, "error": "未填写 LMS 服务器地址（在「升级与更新」页设置）"}
    base = host if host.startswith("http") else "http://" + host
    if not re.search(r":\d+(?:/|$)", base):
        base = base.rstrip("/") + ":" + port
    url = base.rstrip("/") + "/jsonrpc.js"
    hdr = {"Content-Type": "application/json"}
    hdr.update(lms_auth_headers(cfg))
    payload = json.dumps({"id": 1, "method": "slim.request",
                          "params": [0, ["version", "?"]]}).encode("utf-8")
    try:
        raw = http_request(url, data=payload, headers=hdr, timeout=8, log=log)
        d = json.loads(raw.decode("utf-8", "replace"))
        res = d.get("result", {}) or {}
        v = res.get("_version") or res.get("version")
        if not v:
            return {"ok": False, "error": "服务端返回中没有版本号：%s" % str(d)[:120], "url": url}
        return {"ok": True, "version": str(v), "url": url, "raw": res}
    except Exception as e:
        # 降级：serverstatus 查询
        try:
            p2 = json.dumps({"id": 2, "method": "slim.request",
                             "params": ["", ["serverstatus", 0, 1]]}).encode("utf-8")
            d = json.loads(http_request(url, data=p2, headers=hdr,
                                        timeout=8).decode("utf-8", "replace"))
            v = (d.get("result", {}) or {}).get("version")
            if v:
                return {"ok": True, "version": str(v), "url": url, "raw": d.get("result", {})}
        except Exception:
            pass
        msg = str(e)
        if "401" in msg or "Unauthorized" in msg:
            msg = "LMS 需要密码（HTTP 401），请在「升级与更新」页填写用户名/密码"
        return {"ok": False, "error": msg[:150], "url": url}

# ---------------------------------------------------------------- Now Playing / LMS JSON-RPC
def lms_base(cfg):
    host = (cfg.get("lms_host") or "").strip()
    port = (cfg.get("lms_port") or "9000").strip()
    if not host:
        raise RuntimeError("未填写 LMS 服务器地址（在「升级与更新」页设置）")
    base = host if host.startswith("http") else "http://" + host
    if not re.search(r":\d+(?:/|$)", base):
        base = base.rstrip("/") + ":" + port
    return base.rstrip("/")

def lms_rpc(cfg, cmd, playerid="", timeout=6, _id=1):
    """向 LMS 发 JSON-RPC。对瞬时断连（Remote end closed / reset / timeout）
    做 2 次重试——pywebview/WKWebView 环境下偶发 keep-alive 连接被服务端关闭。"""
    url = lms_base(cfg) + "/jsonrpc.js"
    payload = json.dumps({"id": _id, "method": "slim.request",
                          "params": [playerid or "", list(cmd)]}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    headers.update(lms_auth_headers(cfg))
    last = None
    for attempt in range(3):
        try:
            raw = http_request(url, data=payload, headers=headers,
                               timeout=timeout)
            d = json.loads(raw.decode("utf-8", "replace"))
            if "error" in d:
                raise RuntimeError("LMS 返回错误: %s" % str(d["error"])[:120])
            return d.get("result", {}) or {}
        except Exception as e:
            last = e
            msg = str(e)
            transient = ("Remote end closed" in msg or "reset by peer" in msg
                         or "timed out" in msg.lower() or "BrokenPipe" in msg
                         or "Connection aborted" in msg or "EOF" in msg)
            if transient and attempt < 2:
                import time as _t
                _t.sleep(0.25 * (attempt + 1))
                continue
            raise
    raise last

def np_players(cfg):
    r = lms_rpc(cfg, ["serverstatus", 0, 999], _id=11)
    out = []
    for p in (r.get("players_loop") or []):
        out.append({
            "id": str(p.get("playerid") or ""),
            "name": str(p.get("name") or ""),
            "model": str(p.get("model") or ""),
            "ip": str(p.get("ip") or ""),
            "connected": p.get("connected", 0),
            "isplaying": p.get("isplaying", 0),
        })
    return out

def np_pick_player(cfg, players, saved=""):
    if not players:
        return None
    for p in players:
        if saved and p["id"] == saved:
            return p
    want = ""
    try:
        want = make_player_name(cfg.get("host_name") or local_host_name(),
                                cfg.get("device_short") or "",
                                cfg.get("name_template") or "{host} - {short}")
    except Exception:
        pass
    if want:
        for p in players:
            if p["name"] == want:
                return p
    host = (cfg.get("host_name") or "").strip()
    if host:
        for p in players:
            if host.lower() in p["name"].lower():
                return p
    for p in players:
        if p["isplaying"] and "squeezelite" in (p["model"] + p["name"]).lower():
            return p
    if len(players) == 1:
        return players[0]
    return None

def _to_float(v):
    try:
        return float(v)
    except Exception:
        return 0.0

def fmt_sec(v):
    try:
        n = max(0, int(float(v)))
    except Exception:
        return "0:00"
    return "%d:%02d" % (n // 60, n % 60)

def np_status(cfg, playerid, with_lyrics=False):
    # I=samplesize(位深), T=samplerate, r=bitrate, f=filesize, o=type。
    # 实测 LMS 9.x：缺 I/r/o 时位深显示「—」、码率只能靠文件大小推算。
    tags = "alcKdtugybiTCmSfIro" + ("w" if with_lyrics else "")
    r = lms_rpc(cfg, ["status", "-", "1", "tags:" + tags], playerid, _id=12)
    loop = r.get("playlist_loop") or []
    try:
        idx = int(r.get("playlist_cur_index") or 0)
    except Exception:
        idx = 0
    cur = loop[idx] if 0 <= idx < len(loop) else (loop[0] if loop else {})
    return {
        "mode": str(r.get("mode") or "stop"),
        "power": r.get("power", 1),
        "time": _to_float(r.get("time")),
        "duration": _to_float(cur.get("duration") or r.get("duration")),
        "player_name": str(r.get("player_name") or ""),
        "player_connected": r.get("player_connected", 0),
        "index": idx,
        "count": len(loop),
        "digital_volume_control": r.get("digital_volume_control", 1),
        "volume": r.get("mixer volume", 100),
        "rate": r.get("rate", 1),
        "playlist_mode": str(r.get("playlist mode") or ""),
        "use_volume_control": r.get("use_volume_control", 1),
        "track": {k: ("" if v is None else str(v)) for k, v in cur.items()},
    }

def np_lyrics_from_lms(cfg, track_id, playerid=""):
    # 主路径：songinfo tags:w —— 歌词由 LMS 扫描入库，完全不依赖本地挂载点
    if track_id:
        try:
            r = lms_rpc(cfg, ["songinfo", 0, 100, "track_id:" + str(track_id),
                              "tags:wlc"], _id=13)
            for item in (r.get("songinfo_loop") or []):
                if isinstance(item, dict):
                    for k in ("lyrics", "w"):
                        if item.get(k):
                            return str(item[k]), "LMS songinfo (tags:w)"
            for k in ("lyrics", "w"):
                if r.get(k):
                    return str(r[k]), "LMS songinfo (tags:w)"
        except Exception:
            pass
    # 兜底：部分 LMS 版本把歌词放在 status 的 playlist_loop 里
    try:
        r = lms_rpc(cfg, ["status", "-", "1", "tags:w"], playerid, _id=14)
        for item in (r.get("playlist_loop") or [])[:3]:
            if isinstance(item, dict) and item.get("lyrics"):
                return str(item["lyrics"]), "LMS status (tags:w)"
    except Exception:
        pass
    return "", ""

def parse_lrc(text):
    lines, meta = [], {}
    tag_re = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
    meta_re = re.compile(r"^\[(ti|ar|al|by|offset|re|ve):(.*)\]$", re.I)
    for ln in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        s = ln.strip()
        if not s:
            continue
        m = meta_re.match(s)
        if m:
            meta[m.group(1).lower()] = m.group(2).strip()
            continue
        stamps = list(tag_re.finditer(s))
        if stamps:
            body = s[stamps[-1].end():].strip()
            for st in stamps:
                mm, ss, frac = st.group(1), st.group(2), st.group(3) or "0"
                try:
                    sec = int(mm) * 60 + int(ss) + float("0." + frac)
                except Exception:
                    continue
                lines.append((sec, body))
        else:
            lines.append((-1.0, s))
    timed = any(t >= 0 for t, _ in lines)
    if timed:
        lines = sorted([(t, x) for t, x in lines if t >= 0], key=lambda a: a[0])
    else:
        lines = [(i * 3.0, x) for i, (_, x) in enumerate(lines)]
    return {"timed": timed, "lines": lines, "meta": meta}

def np_cover_url(cfg, coverid, artwork_url=""):
    base = lms_base(cfg)
    a = (artwork_url or "").strip()
    if a:
        if a.startswith("http://") or a.startswith("https://"):
            return a
        return base + (a if a.startswith("/") else "/" + a)
    c = str(coverid or "").strip()
    if not c or c in ("0", "-1"):
        return ""
    return base + "/music/" + urllib.parse.quote(c, safe="") + "/cover_300x300.jpg"

_PNG_MAGIC = bytes((137, 80, 78, 71, 13, 10, 26, 10))
_JPG_MAGIC = bytes((255, 216, 255))
_GIF_MAGIC = (b"GIF87a", b"GIF89a")
_RIFF_MAGIC = b"RIFF"


def _hex_rgb(s):
    s = str(s or "#0d292d").lstrip("#")
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except Exception:
        return (13, 41, 45)


def decode_cover_png(data, max_size=320, square=False, pad_color="#0d292d"):
    """返回可直接喂给 tk.PhotoImage(data=...) 的 PNG 字节；失败返回 None。

    square=True 时统一输出 max_size x max_size 正方形：等比缩放后居中补边，
    不变形。列表缩略图必须用它 —— 原始 PNG 或非正方形封面否则会大小不一。
    """
    if not data:
        return None
    is_png = data[:8] == _PNG_MAGIC
    if not square and is_png:
        return data
    if not (is_png or data[:3] == _JPG_MAGIC or data[:6] in _GIF_MAGIC
            or data[:4] == _RIFF_MAGIC):
        return None
    pad = str(pad_color or "#0d292d").lstrip("#")[:6].upper() or "0D292D"
    tmp = []

    def cleanup():
        for x in tmp:
            try:
                if x and os.path.isfile(x):
                    os.remove(x)
            except Exception:
                pass

    # 1) macOS sips（.app 内置运行时无 Pillow 时首选）
    if IS_MAC and shutil.which("sips"):
        try:
            import tempfile
            fd, sp = tempfile.mkstemp(suffix=".img")
            os.close(fd)
            tmp.append(sp)
            with open(sp, "wb") as f:
                f.write(data)
            mid = sp + "-s.png"
            tmp.append(mid)
            subprocess.run(["sips", "-s", "format", "png",
                            "--resampleHeightWidthMax", str(max_size),
                            sp, "--out", mid],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=8, check=False)
            final = mid
            if square and os.path.isfile(mid):
                sq = sp + "-p.png"
                tmp.append(sq)
                subprocess.run(["sips", "-p", str(max_size), str(max_size),
                                "--padColor", pad, mid, "--out", sq],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=8, check=False)
                if os.path.isfile(sq) and os.path.getsize(sq) > 0:
                    final = sq
            if os.path.isfile(final):
                with open(final, "rb") as f:
                    out = f.read()
                if out[:8] == _PNG_MAGIC:
                    return out
        except Exception:
            pass
        finally:
            cleanup()
    # 2) Pillow
    try:
        from PIL import Image
        resample = getattr(Image, "LANCZOS", 1)
        im = Image.open(io.BytesIO(data))
        im.thumbnail((max_size, max_size), resample)
        if square:
            canvas = Image.new("RGB", (max_size, max_size), _hex_rgb(pad_color))
            rgb = im.convert("RGB")
            canvas.paste(rgb, ((max_size - rgb.width) // 2,
                               (max_size - rgb.height) // 2))
            im = canvas
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "PNG")
        out = buf.getvalue()
        if out[:8] == _PNG_MAGIC:
            return out
    except Exception:
        pass
    # 3) ffmpeg 兜底
    if shutil.which("ffmpeg"):
        try:
            vf = "scale=%d:%d:force_original_aspect_ratio=decrease" % (max_size, max_size)
            if square:
                vf += ",pad=%d:%d:(ow-iw)/2:(oh-ih)/2:color=0x%s" % (
                    max_size, max_size, pad)
            r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                                "-i", "pipe:0", "-frames:v", "1", "-vf", vf,
                                "-f", "image2pipe", "-vcodec", "png", "pipe:1"],
                               input=data, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, timeout=8, check=False)
            if r.stdout[:8] == _PNG_MAGIC:
                return r.stdout
        except Exception:
            pass
    return None

def lms_latest(log=None, cfg=None):
    cfg = cfg or {}
    urls = [cfg.get("sources", {}).get("lms_repo"), SOURCES["lms_repo"], SOURCES["lms_repo_alt"]]
    def parser(text):
        d = json.loads(text)
        chans = []
        for key, val in d.items():
            if not isinstance(val, dict):
                continue
            m = val.get("macos") or val.get("osx") or {}
            if not m.get("version"):
                continue
            if key == "latest":
                label = "正式稳定版 (latest)"
            else:
                label = ("开发版 " if ver_cmp(m.get("version", ""),
                          (d.get("latest", {}).get("macos") or {}).get("version", "")) > 0
                          and parse_version(m.get("version", ""))[:2] >
                              parse_version((d.get("latest", {}).get("macos") or {}).get("version", ""))[:2]
                         else "稳定夜版 ") + str(key)
            chans.append({"channel": key, "label": label,
                          "version": m.get("version", ""), "revision": m.get("revision", ""),
                          "size": m.get("size", ""), "md5": m.get("md5", ""),
                          "url": m.get("url", "")})
        return chans
    chans, used = fetch_any(urls, parser, log, "LMS 官方版本库")
    chans.sort(key=lambda c: (c["channel"] != "latest", parse_version(c["version"])), reverse=False)
    return {"channels": chans, "source": used}

# ---------------------------------------------------------------- 升级执行
def upgrade_squeezelite(cfg, item, log):
    """下载官方 macOS 发布并替换（替换前备份旧版），或用 Homebrew 升级。
       支持 tar.gz / zip（Intel）与 .dmg（Apple Silicon，自动 hdiutil 挂载）。
    """
    method = (cfg.get("install_method") or "auto").strip()
    binary = find_binary(cfg)
    if method == "brew":
        bv = brew_version(cfg, log)
        if not bv:
            return False, "未检测到 Homebrew 或该 formula 未安装，请改用「二进制替换」"
        try:
            r = subprocess.run([bv["brew"], "upgrade", bv["formula"]],
                               capture_output=True, text=True, timeout=900)
            out = (r.stdout + "\n" + r.stderr).strip()
            log(out[-800:] or "brew upgrade 已完成")
            return r.returncode == 0, ("Homebrew 升级完成" if r.returncode == 0 else "Homebrew 升级失败")
        except Exception as e:
            return False, "Homebrew 升级异常: %s" % e
    if not item or not item.get("url"):
        return False, "没有可用的下载地址（版本源降级时请手动下载）"
    if not binary:
        return False, "未找到本机 squeezelite 路径，请先在「设备」页指定二进制路径"
    try:
        dl = os.path.join(CONFIG_DIR, "downloads")
        os.makedirs(dl, exist_ok=True)
        os.makedirs(BACKUP_DIR, exist_ok=True)
        data = http_request(item["url"], timeout=180, log=log,
                            progress=lambda n: None)
        fn = item.get("filename") or urllib.parse.unquote(
            item["url"].rstrip("/").split("/")[-1])
        pkg = os.path.join(dl, fn)
        with open(pkg, "wb") as f:
            f.write(data)
        log("已下载 %s (%.2f MB)" % (fn, len(data) / 1048576.0))
        tmpdir = os.path.join(dl, "extract")
        shutil.rmtree(tmpdir, ignore_errors=True)
        os.makedirs(tmpdir, exist_ok=True)
        newbin = None
        if fn.lower().endswith(".dmg"):
            if not IS_MAC:
                return False, ("已下载 macOS 安装包 %s（%.1f MB）。当前不是 macOS，无法自动挂载。\n"
                               "请把该文件拷到 Mac 上双击安装，或在「设备」页指定新二进制路径。\n"
                               "文件：%s") % (fn, len(data) / 1048576.0, pkg)
            mnt = os.path.join(tmpdir, "mnt")
            os.makedirs(mnt, exist_ok=True)
            r = subprocess.run(["hdiutil", "attach", pkg, "-nobrowse",
                                "-readonly", "-mountpoint", mnt],
                               capture_output=True, text=True, timeout=180)
            if r.returncode != 0:
                return False, "挂载 DMG 失败: %s" % (r.stderr or "")[:200]
            try:
                cand = []
                for root, _dirs, files in os.walk(mnt):
                    for f in files:
                        if f.lower() == "squeezelite" or (
                                f.lower().startswith("squeezelite") and "." not in f):
                            cand.append(os.path.join(root, f))
                if not cand:
                    return False, "DMG 中未找到 squeezelite 可执行文件（可能是 .pkg，需手动安装）"
                cand.sort(key=lambda p: ("Squeezelite.app" not in p, len(p)))
                staged = os.path.join(tmpdir, "squeezelite.new")
                shutil.copy2(cand[0], staged)
                newbin = staged
            finally:
                subprocess.run(["hdiutil", "detach", mnt, "-quiet"],
                               capture_output=True, timeout=60)
        elif fn.lower().endswith((".zip", ".tar.gz", ".tgz")):
            if fn.endswith(".zip"):
                import zipfile
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    z.extractall(tmpdir)
            else:
                with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as t:
                    t.extractall(tmpdir)
            cand = []
            for root, _dirs, files in os.walk(tmpdir):
                for f in files:
                    p2 = os.path.join(root, f)
                    if f.lower().startswith("squeezelite") and not f.lower().endswith(
                            (".txt", ".md", ".html", ".plist", ".so", ".dylib")):
                        cand.append(p2)
            if not cand:
                return False, "压缩包中未找到 squeezelite 可执行文件"
            cand.sort(key=lambda p: (os.path.basename(p) != "squeezelite", len(p)))
            newbin = cand[0]
        else:
            return False, "未知安装包格式: %s" % fn
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        bak = os.path.join(BACKUP_DIR, "squeezelite.%s.bak" % stamp)
        shutil.copy2(binary, bak)
        log("已备份旧版 → %s" % bak)
        shutil.copy2(newbin, binary)
        os.chmod(binary, 0o755)
        if IS_MAC:
            subprocess.run(["xattr", "-d", "com.apple.quarantine", binary],
                           capture_output=True, timeout=10)
        v = sq_local_version(binary, log)
        return True, "已升级为 %s；旧版备份在 %s" % (
            ver_display(v["version"], v["revision"]) if v else item.get("label", "新版本"), bak)
    except Exception as e:
        return False, "升级失败（旧版未改动）: %s" % str(e)[:200]

def make_launch_agent(cfg, argv, log=None):
    """生成 macOS 开机自启 LaunchAgent plist。"""
    if not IS_MAC:
        return False, "开机自启仅支持 macOS（当前是 %s）" % sys.platform
    try:
        import plistlib
        os.makedirs(os.path.dirname(LAUNCH_AGENT), exist_ok=True)
        logs = os.path.join(CONFIG_DIR, "launchd.log")
        plist = {
            "Label": "com.squeezelite.gui",
            "ProgramArguments": argv,
            "RunAtLoad": True,
            "KeepAlive": True,
            "StandardOutPath": logs,
            "StandardErrorPath": logs,
            "ProcessType": "Interactive",
        }
        with open(LAUNCH_AGENT, "wb") as f:
            plistlib.dump(plist, f)
        if log:
            log("已生成 LaunchAgent: %s" % LAUNCH_AGENT)
        return True, LAUNCH_AGENT
    except Exception as e:
        return False, "生成 LaunchAgent 失败: %s" % e

# ---------------------------------------------------------------- 配置
def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        if os.path.isfile(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f) or {})
    except Exception:
        pass
    cfg.setdefault("params", {})
    cfg.setdefault("sources", {})
    if not cfg.get("host_name"):
        cfg["host_name"] = local_host_name()
    return cfg

def save_config(cfg):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        try:
            os.chmod(CONFIG_PATH, 0o600)
        except Exception:
            pass
        return True
    except Exception:
        return False

def load_cache():
    try:
        if os.path.isfile(CACHE_PATH):
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_cache(d):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

PARAM_BY_KEY = {p["key"]: p for p in PARAMS}
GROUPS = []
for _p in PARAMS:
    if _p["group"] not in GROUPS:
        GROUPS.append(_p["group"])


class App(_AppBase):
    """Squeezelite GUI 主窗口。全部耗时操作放后台线程，通过 Queue + after() 回主线程刷新。"""

    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.values = dict(self.cfg.get("params") or {})
        for p in PARAMS:
            self.values.setdefault(p["key"], p.get("default", ""))
        self.devices = []
        self.proc = None
        self.proc_start = None
        self.q = queue.Queue()
        self.busy = False
        self.param_widgets = {}
        self.vars = {}
        self.cache = load_cache()
        self.theme_name = self.cfg.get("theme", "light")
        if self.theme_name not in THEMES:
            self.theme_name = "light"
        self.theme_mode = self.cfg.get("theme_mode", "system")
        if self.theme_mode not in ("manual", "system"):
            self.theme_mode = "system"
        self._terminal_texts = []
        self.title("%s  v%s" % (APP_NAME, VERSION))
        self.geometry("1200x820")
        self.minsize(1120, 760)
        self._init_style()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(120, self._pump)
        self.after(200, self._sys_theme_loop)
        self._log("已启动 %s v%s | 平台 %s %s | Python %s | Tk %s" % (
            APP_NAME, VERSION, sys.platform, platform.machine(),
            platform.python_version(), tk.TkVersion))
        self._log("配置文件: %s" % CONFIG_PATH)
        self._refresh_preview()
        self._mac_render_fix()
        self.after(500, self._np_tick)
        if os.environ.get("SQUEEZELITE_GUI_NO_AUTOSCAN") != "1":
            if self.cfg.get("auto_scan", True):
                self.after(350, self._scan_devices)
            if self.cfg.get("auto_upgrade_check", False):
                self.after(1200, self._check_updates)

    # ------------------------------------------------------------ 渲染兼容
    def _mac_render_fix(self):
        """macOS 系统自带 Tk 8.5（/usr/bin/python3）在新版 macOS 上偶尔只画
        标题栏、内容区全白，但后台线程仍在正常跑。这里强制 update / deiconify /
        lift，并在 Tk < 8.6 时轻微改变几何尺寸触发 Aqua 重绘，同时给出提示。
        打包为 .app 后使用内置 Tk 9 运行时，此兜底不会触发。
        """
        if not IS_MAC:
            return
        try:
            self.update_idletasks()
            self.deiconify()
            self.lift()
            if float(tk.TkVersion) < 8.6:
                self._log("提示: 当前 Tk %s 为系统弃用版本，界面可能显示异常；"
                          "建议使用 App 内置运行时或安装 python-tk" % tk.TkVersion)

                def _nudge():
                    try:
                        w = max(self.winfo_width(), 1020)
                        h = max(self.winfo_height(), 680)
                        self.geometry("%dx%d" % (w + 1, h + 1))
                        self.update_idletasks()
                        self.geometry("%dx%d" % (w, h))
                        self.update_idletasks()
                    except Exception:
                        pass

                self.after(300, _nudge)
        except Exception:
            pass

    # ------------------------------------------------------------ 主题
    def _text_opts(self, terminal=False):
        C = self.C
        bg = C["terminal_bg"] if terminal else C["code_bg"]
        fg = C["terminal_fg"] if terminal else C["text"]
        return dict(background=bg, foreground=fg, insertbackground=fg,
                    selectbackground=C["sel"], selectforeground=C["sel_text"],
                    highlightthickness=1, highlightbackground=C["border"],
                    highlightcolor=C["primary"], relief="flat", borderwidth=0,
                    padx=9, pady=7)

    def _refresh_tree_tags(self):
        C = self.C
        for t in (getattr(self, "dev_tree", None), getattr(self, "lms_tree", None),
                  getattr(self, "lib_tree", None)):
            if t is None:
                continue
            try:
                t.tag_configure("odd", background=C["row_alt"],
                                foreground=C["text"])
                t.tag_configure("chosen", background=C["sel"],
                                foreground=C["sel_text"])
            except Exception:
                pass

    def _retheme_tk(self, w):
        # ttk 控件由 Style 自动更新，这里只刷新 tk 原生控件。
        # 卡片式控件可用 _sq_bg / _sq_fg 标注期望的配色键，避免被刷成页面底色。
        C = self.C
        app_bar = getattr(self, "app_bar", None)
        try:
            cls = w.winfo_class()
            bgk = getattr(w, "_sq_bg", None)
            fgk = getattr(w, "_sq_fg", None)
            if cls == "Frame":
                bg = C[bgk] if bgk in C else (C["app_bar"] if w is app_bar else C["bg"])
                w.configure(background=bg)
            elif cls == "Label":
                bar = (w.master is app_bar)
                bg = C[bgk] if bgk in C else (C["app_bar"] if bar else C["bg"])
                fg = C[fgk] if fgk in C else (C["on_app_bar"] if bar else C["text"])
                w.configure(background=bg, foreground=fg)
            elif cls == "Button":
                bar = (w.master is app_bar)
                bg = C[bgk] if bgk in C else (C["app_bar"] if bar else C["surface"])
                fg = C[fgk] if fgk in C else (C["on_app_bar"] if bar else C["text"])
                w.configure(background=bg, foreground=fg,
                            activebackground=C["primary_dark"],
                            activeforeground=C["on_primary"],
                            relief="flat", bd=0)
            elif cls == "Text":
                term = w in getattr(self, "_terminal_texts", ())
                for k, v in self._text_opts(term).items():
                    try:
                        w.configure(**{k: v})
                    except Exception:
                        pass
            elif cls == "Canvas":
                w.configure(background=C["bg"], highlightthickness=0)
            elif cls == "Toplevel":
                w.configure(background=C["bg"])
            elif cls in ("Entry", "Listbox", "Scrollbar"):
                w.configure(background=C["surface"], foreground=C["text"],
                            highlightbackground=C["border"])
        except Exception:
            pass
        try:
            children = w.winfo_children()
        except Exception:
            return
        for ch in children:
            self._retheme_tk(ch)

    # ------------------------------------------------------------ 滚轮
    def _wheel_steps(self, e, fixed=None):
        if fixed is not None:
            return fixed
        d = getattr(e, "delta", 0)
        if not d:
            return 0
        if IS_MAC:
            # 传统鼠标 delta=+-1；触控板为连续小值，按 2 倍换算并限幅
            n = max(1, min(6, abs(d) * 2))
            return -n if d > 0 else n
        n = max(1, min(6, abs(d) // 40))  # Windows 为 +-120
        return -n if d > 0 else n

    def _on_wheel(self, e, target, fixed=None):
        steps = self._wheel_steps(e, fixed)
        if steps:
            try:
                target.yview_scroll(steps, "units")
            except Exception:
                pass
        return "break"

    def _attach_wheel(self, root, target):
        # 滚轮事件只发给鼠标下的最上层控件，因此必须递归绑定到整棵子树。
        # macOS/Windows 用 <MouseWheel>，X11 用 <Button-4>/<Button-5>。
        def bind_one(w):
            try:
                w.bind("<MouseWheel>",
                       lambda e, t=target: self._on_wheel(e, t), add="+")
                w.bind("<Button-4>",
                       lambda e, t=target: self._on_wheel(e, t, -3), add="+")
                w.bind("<Button-5>",
                       lambda e, t=target: self._on_wheel(e, t, 3), add="+")
            except Exception:
                pass

        def walk(w):
            bind_one(w)
            try:
                kids = w.winfo_children()
            except Exception:
                return
            for c in kids:
                walk(c)
        walk(root)

    # ------------------------------------------------------------ 样式
    def _init_style(self):
        C = self.C = THEMES.get(self.theme_name, THEMES["light"])
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        fam = "PingFang SC"
        try:
            avail = set(tkfont.families(self))
            for c in ("SF Pro Text", "Roboto", "PingFang SC", "Noto Sans CJK SC",
                      "WenQuanYi Zen Hei", "Droid Sans Fallback",
                      "Microsoft YaHei", "Helvetica Neue", "Helvetica"):
                if c in avail:
                    fam = c
                    break
        except Exception:
            pass
        self.fam = fam
        self.ui_font = (fam, 12)          # v1.6.0: 正文 11 -> 12
        self.small_font = (fam, 10)       # v1.6.0: 小字 9 -> 10（设计 caption 12 的子级）
        self.bold_font = (fam, 11, "bold")
        self.head_font = (fam, 10, "bold")
        self.title_font = (fam, 17, "bold")         # v1.6.0: 小节标题 15 -> 17（设计 subtitle）
        self.display_font = (fam, 42, "bold")       # hero 曲名 (design 42)
        self.hero_focus_font = (fam, 56, "bold")    # heroFocus (design 56)
        self.page_title_font = (fam, 24, "bold")    # 页面标题 / 专辑名
        self.subtitle_font = (fam, 18)              # 副标题 / 歌手
        self.caption_font = (fam, 13)               # 元数据 / 歌词
        self.overline_font = (fam, 11, "bold")      # 分组标题 / 角标
        self.body_font = (fam, 14)                  # 正文备用 (全局仍 10pt)
        self.mono_font = ("Menlo", 10) if IS_MAC else ("DejaVu Sans Mono", 10)

        style.configure(".", background=C["bg"], foreground=C["text"],
                        font=(fam, 10), bordercolor=C["border"],
                        lightcolor=C["surface"], darkcolor=C["border"],
                        troughcolor=C["surface2"], focuscolor=C["primary"])
        style.configure("TFrame", background=C["bg"])
        style.configure("TLabel", background=C["bg"], foreground=C["text"],
                        font=(fam, 10), padding=1)
        style.configure("TLabelframe", background=C["bg"],
                        bordercolor=C["border"], lightcolor=C["bg"],
                        darkcolor=C["border"], relief="solid", borderwidth=1)
        style.configure("TLabelframe.Label", background=C["bg"],
                        foreground=C["primary"], font=self.head_font,
                        padding=(8, 2))
        style.configure("TButton", background=C["surface"],
                        foreground=C["text"], bordercolor=C["border"],
                        lightcolor=C["surface"], darkcolor=C["border"],
                        font=(fam, 10), padding=(14, 7), relief="flat",
                        borderwidth=1)
        style.map("TButton",
                  background=[("pressed", C["sel"]), ("active", C["hover"]),
                              ("disabled", C["bg"])],
                  foreground=[("disabled", C["text3"])],
                  bordercolor=[("focus", C["primary"])])
        style.configure("Tool.TButton", background=C["surface"],
                        foreground=C["text"], bordercolor=C["border"],
                        lightcolor=C["surface"], darkcolor=C["border"],
                        font=(fam, 10), padding=(7, 5), relief="flat",
                        borderwidth=1)
        style.map("Tool.TButton",
                  background=[("pressed", C["sel"]), ("active", C["hover"])],
                  foreground=[("disabled", C["text3"])],
                  bordercolor=[("focus", C["primary"])])
        style.configure("Accent.TButton", background=C["primary"],
                        foreground=C["on_primary"], bordercolor=C["primary"],
                        lightcolor=C["primary"], darkcolor=C["primary_dark"],
                        font=(fam, 10, "bold"), padding=(12, 6), relief="flat")
        style.map("Accent.TButton",
                  background=[("pressed", C["primary_dark"]),
                              ("active", C["primary_dark"])],
                  foreground=[("disabled", C["text3"])])
        style.configure("TEntry", fieldbackground=C["surface"],
                        foreground=C["text"], insertcolor=C["text"],
                        bordercolor=C["border"], lightcolor=C["surface"],
                        darkcolor=C["border"], padding=5, relief="flat",
                        borderwidth=1)
        style.map("TEntry", bordercolor=[("focus", C["primary"])],
                  fieldbackground=[("disabled", C["surface2"])])
        style.configure("TCombobox", fieldbackground=C["surface"],
                        background=C["surface"], foreground=C["text"],
                        arrowcolor=C["text2"], bordercolor=C["border"],
                        lightcolor=C["surface"], darkcolor=C["border"],
                        padding=5, relief="flat", borderwidth=1)
        style.map("TCombobox",
                  fieldbackground=[("readonly", C["surface"]),
                                   ("!disabled", C["surface"])],
                  foreground=[("readonly", C["text"]),
                              ("disabled", C["text3"])],
                  bordercolor=[("focus", C["primary"])],
                  arrowcolor=[("active", C["primary"])])
        self.option_add("*TCombobox*Listbox.background", C["surface"])
        self.option_add("*TCombobox*Listbox.foreground", C["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", C["primary"])
        self.option_add("*TCombobox*Listbox.selectForeground", C["on_primary"])
        style.configure("TNotebook", background=C["bg"],
                        bordercolor=C["border"], tabmargins=(4, 10, 4, 0),
                        relief="flat", borderwidth=0)
        style.configure("TNotebook.Tab", background=C["bg"],
                        foreground=C["text2"], padding=(23, 11),
                        font=(fam, 10, "bold"), borderwidth=0, relief="flat")
        style.map("TNotebook.Tab",
                  background=[("selected", C["surface"]),
                              ("active", C["hover"])],
                  foreground=[("selected", C["primary"]),
                              ("active", C["text"])])
        # 音乐库专用列表：更大的行高容纳封面缩略图，避免文字与封面挤在一起
        style.configure("Lib.Treeview", background=C["surface"],
                        fieldbackground=C["surface"], foreground=C["text"],
                        font=(fam, 11), rowheight=56,
                        bordercolor=C["divider"], relief="flat", borderwidth=0)
        style.map("Lib.Treeview",
                  background=[("selected", C["sel"])],
                  foreground=[("selected", C["sel_text"])])
        style.configure("Treeview", background=C["surface"],
                        fieldbackground=C["surface"], foreground=C["text"],
                        font=self.ui_font, rowheight=32,
                        bordercolor=C["divider"], relief="flat", borderwidth=0)
        style.configure("Treeview.Heading", background=C["surface2"],
                        foreground=C["text2"], font=self.head_font,
                        padding=(10, 10), relief="flat",
                        bordercolor=C["divider"])
        style.map("Treeview",
                  background=[("selected", C["sel"])],
                  foreground=[("selected", C["sel_text"])])
        style.configure("TScrollbar", background=C["scroll"],
                        troughcolor=C["bg"], bordercolor=C["bg"],
                        arrowcolor=C["text2"], gripcount=0, relief="flat")
        style.map("TScrollbar",
                  background=[("active", C["scroll_active"]),
                              ("pressed", C["primary"])],
                  arrowcolor=[("active", C["primary"])])
        style.configure("TSeparator", background=C["divider"])
        style.configure("TProgressbar", background=C["prog_fg"],
                        troughcolor=C["prog_bg"], bordercolor=C["prog_bg"],
                        lightcolor=C["prog_fg"], darkcolor=C["prog_fg"],
                        relief="flat", thickness=8, borderwidth=0)
        style.configure("TCheckbutton", background=C["bg"],
                        foreground=C["text"], font=(fam, 10),
                        indicatorcolor=C["surface"], bordercolor=C["border"])
        style.configure("TRadiobutton", background=C["bg"],
                        foreground=C["text"], font=(fam, 10),
                        indicatorcolor=C["surface"], bordercolor=C["border"])
        style.configure("Hint.TLabel", background=C["bg"],
                        foreground=C["text2"], font=self.small_font)
        style.configure("Title.TLabel", background=C["bg"],
                        foreground=C["text"], font=self.title_font)
        style.configure("Hero.TLabel", background=C["bg"],
                        foreground=C["text"], font=self.display_font)
        style.configure("Muted.TLabel", background=C["bg"],
                        foreground=C["text3"], font=self.small_font)
        style.configure("Ok.TLabel", background=C["bg"],
                        foreground=C["ok"], font=(fam, 10, "bold"))
        style.configure("Warn.TLabel", background=C["bg"],
                        foreground=C["warn"], font=(fam, 10, "bold"))
        style.configure("Card.TFrame", background=C["surface"],
                        bordercolor=C["border"], relief="solid", borderwidth=1)
        # 主题分段：ttk 自绘，macOS Aqua 下也能保证三态都清晰
        # 三态分段：未选中项用 muted 保证可读（修复旧版只有选中项可读）
        style.configure("ThemeSeg.TLabel", background=C["topbar"],
                        foreground=C["text2"], font=(fam, 10),
                        padding=(13, 6), anchor="center",
                        bordercolor=C["border"], relief="solid", borderwidth=1)
        style.configure("ThemeSegOn.TLabel", background=C["selected"],
                        foreground=C["primary"], font=(fam, 10, "bold"),
                        padding=(13, 6), anchor="center",
                        bordercolor=C["primary"], relief="solid", borderwidth=1)
        style.map("ThemeSeg.TLabel",
                  background=[("active", C["hover"])],
                  foreground=[("active", C["text"])])
        style.configure("Rec.TLabel", background=C["bg"],
                        foreground=C["ok"], font=self.small_font)
        style.configure("AppBar.TLabel", background=C["app_bar"],
                        foreground=C["on_app_bar"])
        # ---- v1.6.0 设计交付包新增样式 (mapping.md To-Create List) ----
        style.configure("Top.TFrame", background=C["topbar"])
        style.configure("PageTitle.TLabel", background=C["bg"],
                        foreground=C["text"], font=self.page_title_font)
        style.configure("Subtitle.TLabel", background=C["bg"],
                        foreground=C["text2"], font=self.subtitle_font)
        style.configure("Caption.TLabel", background=C["bg"],
                        foreground=C["text2"], font=self.caption_font)
        style.configure("Overline.TLabel", background=C["bg"],
                        foreground=C["text2"], font=self.overline_font)
        style.configure("HeroFocus.TLabel", background=C["bg"],
                        foreground=C["text"], font=self.hero_focus_font)
        style.configure("Error.TLabel", background=C["bg"],
                        foreground=C["error"], font=(fam, 10, "bold"))
        style.configure("Badge.TLabel", background=C["primary"],
                        foreground=C["on_primary"], font=(fam, 10, "bold"),
                        padding=(6, 2))
        style.configure("Status.TLabel", background=C["surface"],
                        foreground=C["text"], font=(fam, 10),
                        padding=(8, 4))
        style.configure("Danger.TButton", background=C["surface"],
                        foreground=C["error"], bordercolor=C["error"],
                        font=(fam, 10), padding=(10, 5), relief="flat",
                        borderwidth=1)
        style.map("Danger.TButton",
                  background=[("pressed", C["error"]), ("active", C["hover"])],
                  foreground=[("pressed", C["on_primary"]),
                              ("disabled", C["disabled"])])
        style.configure("Item.Treeview", background=C["surface"],
                        fieldbackground=C["surface"], foreground=C["text"],
                        font=self.ui_font, rowheight=56,
                        bordercolor=C["divider"], relief="flat", borderwidth=0)
        style.map("Item.Treeview",
                  background=[("selected", C["selected"])],
                  foreground=[("selected", C["sel_text"])])
        self.configure(background=C["bg"])

    # ------------------------------------------------------------ 主框架
    def _build_ui(self):
        C = self.C
        self.app_bar = tk.Frame(self, background=C["app_bar"], height=48)
        self.app_bar.pack(fill="x")
        self.app_bar.pack_propagate(False)
        self._bar_rule = tk.Frame(self, background=C["border"], height=1)
        self._bar_rule.pack(fill="x")
        self._bar_rule._sq_bg = "border"
        tk.Label(self.app_bar, text="Squeezelite GUI", background=C["app_bar"],
                 foreground=C["on_app_bar"], font=(self.fam, 17, "bold")
                 ).pack(side="left", padx=(20, 8))
        tk.Label(self.app_bar, text="高保真播放器  ·  Hi-Res Player",
                 background=C["app_bar"], foreground=C["on_app_bar"],
                 font=(self.fam, 10)).pack(side="left")
        # 主题：Material 分段按钮，自绘以避免 ttk.Combobox 在深色 app bar
        # 上被系统渲染成白底 / 浅色字导致无法辨认。
        self.theme_mode_var = tk.StringVar(
            value=("跟随系统" if self.theme_mode == "system" else
                   ("深色" if self.theme_name == "dark" else "浅色")))
        seg = tk.Frame(self.app_bar, background=C["app_bar"],
                       highlightbackground=C["primary_dark"],
                       highlightthickness=1, bd=0)
        seg.pack(side="right", padx=(6, 18))
        self.theme_segs = {}
        for label in ("浅色", "深色", "跟随系统"):
            b = ttk.Label(seg, text=label, style="ThemeSeg.TLabel",
                          anchor="center", cursor="hand2", padding=(13, 6))
            b.pack(side="left")
            b.bind("<Button-1>", lambda e, v=label: self._on_theme_choice(v))
            self.theme_segs[label] = b
        self._theme_seg_update()
        self.platform_lbl = tk.Label(
            self.app_bar, text="", background=C["app_bar"],
            foreground=C["on_app_bar"], font=(self.fam, 9))
        self.platform_lbl.pack(side="right", padx=6)
        self.platform_lbl.configure(text="v%s  ·  %s / %s" % (
            VERSION, "macOS" if IS_MAC else sys.platform, platform.machine()))

        self.nb = ttk.Notebook(self, padding=(10, 8, 10, 4))
        self.nb.pack(fill="both", expand=True, padx=12, pady=(10, 4))
        self.tab_devices = ttk.Frame(self.nb)
        self.tab_params = ttk.Frame(self.nb)
        self.tab_launch = ttk.Frame(self.nb)
        self.tab_update = ttk.Frame(self.nb)
        self.tab_help = ttk.Frame(self.nb)
        self.tab_now = ttk.Frame(self.nb)
        self.tab_lib = ttk.Frame(self.nb)
        for f, t in [(self.tab_devices, "设备与名称"), (self.tab_params, "参数配置"),
                     (self.tab_launch, "启动控制"), (self.tab_now, "正在播放"),
                     (self.tab_lib, "音乐库"), (self.tab_update, "升级与更新"),
                     (self.tab_help, "日志 / 帮助")]:
            self.nb.add(f, text="  " + t + "  ")
        self._build_tab_params()   # 参数控件需先建立：设备页的命名会写入 -n
        self._build_tab_devices()
        self._build_tab_launch()
        self._build_tab_now()
        self._build_tab_lib()
        self._build_tab_update()
        self._build_tab_help()
        self._refresh_tree_tags()

        foot = ttk.Frame(self, style="Top.TFrame", padding=(14, 8))
        foot.pack(fill="x")
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(foot, textvariable=self.status_var,
                  style="Hint.TLabel").pack(side="left")
        self.pbar = ttk.Progressbar(foot, mode="indeterminate", length=110)
        self.pbar.pack(side="left", padx=10)
        ttk.Button(foot, text="保存配置", style="Accent.TButton",
                   command=self._save_config).pack(side="right", padx=3)
        ttk.Button(foot, text="退出", style="Danger.TButton",
                   command=self._on_close).pack(side="right", padx=3)
        ttk.Button(foot, text="重新生成命令", command=self._refresh_preview).pack(side="right", padx=3)

    # ------------------------------------------------------------ 日志/队列
    def _sl_ingest_log(self, line):
        """从 squeezelite stdout/stderr 解析实际解码状态并刷新音频链路卡片。"""
        try:
            new, changed = parse_sl_output(
                line, getattr(self, "sl_output", {}) or {})
            if not changed:
                return
            self.sl_output = new
            if getattr(self, "np_audio_data", None):
                self._np_render_audio(*self.np_audio_data)
        except Exception:
            pass

    def _log(self, msg):
        line = "[%s] %s" % (now_str(), str(msg))
        try:
            self.log_text.insert("end", line + "\n")
            self.log_text.see("end")
        except Exception:
            pass
        try:
            print(line, flush=True)
        except Exception:
            pass

    def tlog(self, msg):
        self.q.put(("log", str(msg)))

    def _pump(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "log":
                    self._log(data)
                elif kind == "status":
                    self.status_var.set(str(data))
                elif kind == "error":
                    self._log("✗ " + str(data))
                    messagebox.showerror(APP_NAME, str(data)[:400])
                elif kind == "info":
                    messagebox.showinfo(APP_NAME, str(data)[:600])
                elif kind == "done":
                    self.busy = False
                    self.pbar.stop()
                    self.status_var.set("就绪")
                elif kind == "devices":
                    self._fill_devices(data[0], data[1], data[2])
                elif kind == "upgrade_sl":
                    self._fill_sl(data)
                elif kind == "upgrade_lms":
                    self._fill_lms(data)
                elif kind == "proc_log":
                    try:
                        self.proc_text.insert("end", data)
                        self.proc_text.see("end")
                    except Exception:
                        pass
                    self._sl_ingest_log(data)
                elif kind == "proc_exit":
                    self._on_proc_exit(data)
                elif kind == "np_players":
                    self._np_fill_players(data)
                elif kind == "np_update":
                    self._np_render(data)
                elif kind == "np_lyrics":
                    self._np_on_lyrics(data)
                elif kind == "np_cover":
                    self._np_on_cover(data)
                elif kind == "np_bio":
                    self._np_on_bio(data)
                elif kind == "focus_cover":
                    self._focus_on_cover(data)
                elif kind == "np_error":
                    self._np_on_error(str(data))
                elif kind == "sys_theme":
                    self._on_sys_theme(data)
                elif kind == "lib_items":
                    self._lib_on_items(data)
                elif kind == "lib_thumb":
                    self._lib_on_thumb(data)
                elif kind == "lib_cover":
                    self._lib_on_cover(data)
                elif kind == "lib_played":
                    self._lib_on_played(str(data))
                elif kind == "lib_error":
                    self._lib_on_error(str(data))
                elif kind == "refresh":
                    self._refresh_preview()
        except queue.Empty:
            pass
        self.after(120, self._pump)

    def _run_bg(self, fn, tag=""):
        if self.busy:
            messagebox.showinfo(APP_NAME, "已有任务在运行，请稍候")
            return
        self.busy = True
        self.pbar.start(12)
        self.status_var.set("正在执行：%s ..." % (tag or "后台任务"))

        def worker():
            try:
                fn()
            except Exception as e:
                self.q.put(("log", "[异常] %s\n%s" % (e, traceback.format_exc(limit=4))))
                self.q.put(("error", str(e)))
            finally:
                self.q.put(("done", tag))
        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------ Tab1 设备
    def _build_tab_devices(self):
        f = self.tab_devices
        top = ttk.LabelFrame(f, text=" 1 · 音频输出设备（启动自动扫描，手动选择） ", padding=10)
        top.pack(fill="both", expand=True, padx=10, pady=8)

        bar = ttk.Frame(top)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Button(bar, text="重新扫描设备", command=self._scan_devices).pack(side="left", padx=3)
        ttk.Button(bar, text="手动添加设备", command=self._add_device).pack(side="left", padx=3)
        ttk.Button(bar, text="指定 squeezelite 路径", command=self._choose_binary).pack(side="left", padx=3)
        ttk.Button(bar, text="查看 -l 原始输出", command=self._show_raw_l).pack(side="left", padx=3)
        self.binary_var = tk.StringVar(value=find_binary(self.cfg) or "（未找到）")
        ttk.Label(bar, text="二进制：", style="Hint.TLabel").pack(side="left", padx=(14, 2))
        ttk.Label(bar, textvariable=self.binary_var, style="Hint.TLabel").pack(side="left")

        cols = ("sel", "name", "id", "source", "default")
        self.dev_tree = ttk.Treeview(top, columns=cols, show="headings", height=11)
        for c, txt, w in [("sel", "选中", 60), ("name", "设备名称", 420),
                          ("id", "编号", 80), ("source", "来源", 170), ("default", "默认", 80)]:
            self.dev_tree.heading(c, text=txt)
            self.dev_tree.column(c, width=w, minwidth=50,
                                 stretch=(c in ("name", "source")), anchor="w")
        sb = ttk.Scrollbar(top, orient="vertical", command=self.dev_tree.yview)
        self.dev_tree.configure(yscrollcommand=sb.set)
        self.dev_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.dev_tree.bind("<<TreeviewSelect>>", self._on_device_select)
        self._attach_wheel(self.dev_tree, self.dev_tree)

        hint = ttk.Label(top, text="提示：找不到设备时，请先安装/指定 squeezelite；macOS 会同时用 "
                                   "system_profiler SPAudioDataType 补充枚举。也可手动添加 -o 设备名。",
                         style="Hint.TLabel", wraplength=900)
        hint.pack(fill="x", pady=(8, 0))

        bottom = ttk.LabelFrame(f, text=" 2 · 播放器名称（LMS 端显示） = 本机名称 + 音频设备简称 ", padding=10)
        bottom.pack(fill="x", padx=10, pady=(0, 10))

        self.host_var = tk.StringVar(value=self.cfg.get("host_name") or local_host_name())
        self.tpl_var = tk.StringVar(value=self.cfg.get("name_template") or "{host} - {short}")
        self.short_var = tk.StringVar(value=self.cfg.get("device_short") or "")
        self.name_var = tk.StringVar()
        rows = ttk.Frame(bottom)
        rows.pack(fill="x")
        ttk.Label(rows, text="本机名称", width=14).grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(rows, textvariable=self.host_var, width=30).grid(row=0, column=1, sticky="w", pady=3)
        ttk.Label(rows, text="名称模板", width=14).grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(rows, textvariable=self.tpl_var, width=30).grid(row=1, column=1, sticky="w", pady=3)
        ttk.Label(rows, text="可用变量：{host} 本机名称   {short} 设备简称",
                  style="Hint.TLabel").grid(row=1, column=2, sticky="w", padx=8)
        ttk.Label(rows, text="设备简称", width=14).grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(rows, textvariable=self.short_var, width=30).grid(row=2, column=1, sticky="w", pady=3)
        ttk.Label(rows, text="留空则按设备名自动生成（如 BuiltIn / USBDac / HDMI）",
                  style="Hint.TLabel").grid(row=2, column=2, sticky="w", padx=8)
        ttk.Label(rows, text="LMS 显示名", width=14, style="Title.TLabel").grid(row=3, column=0, sticky="w", pady=(10, 3))
        ttk.Label(rows, textvariable=self.name_var, style="Title.TLabel",
                  foreground=self.C["link"]).grid(row=3, column=1, columnspan=2, sticky="w", pady=(10, 3))
        ttk.Button(rows, text="刷新名称并写入 -n", command=self._update_name).grid(row=4, column=1, sticky="w", pady=4)

        for v in (self.host_var, self.tpl_var, self.short_var):
            v.trace_add("write", lambda *a: self._update_name())
        self._update_name()

    # ------------------------------------------------------------ Tab2 参数
    def _build_tab_params(self):
        f = self.tab_params
        bar = ttk.LabelFrame(f, text=" 参数预设 ", padding=8)
        bar.pack(fill="x", padx=10, pady=8)
        ttk.Button(bar, text="★ 一键应用最优音质方案 (bit-perfect)",
                   style="Accent.TButton",
                   command=self._apply_best).pack(side="left", padx=4)
        ttk.Button(bar, text="恢复默认值", command=self._restore_defaults).pack(side="left", padx=4)
        ttk.Button(bar, text="查看全部参数说明", command=self._show_all_params).pack(side="left", padx=4)
        ttk.Button(bar, text="校验当前取值", command=self._check_values).pack(side="left", padx=4)
        ttk.Label(bar, text="下拉选预设 · 文本框可直接改自定义值 · ? 查看效果与范围",
                  style="Hint.TLabel").pack(side="left", padx=14)

        area = ttk.Frame(f)
        area.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        canvas = tk.Canvas(area, highlightthickness=0, background=self.C["bg"])
        sb = ttk.Scrollbar(area, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        canvas.configure(yscrollcommand=sb.set, yscrollincrement=40)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        for gname in GROUPS:
            gf = ttk.LabelFrame(inner, text=" " + gname + " ", padding=6)
            gf.pack(fill="x", padx=4, pady=5)
            for p in [x for x in PARAMS if x["group"] == gname]:
                self._make_param_row(gf, p)

        # 滚轮绑定到参数区整棵控件树（否则事件只发给鼠标下的子控件）
        self.param_canvas = canvas
        self._attach_wheel(area, canvas)

        bottom = ttk.LabelFrame(f, text=" 自定义附加参数与命令预览 ", padding=8)
        bottom.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Label(bottom, text="附加 CLI 参数（直接追加，如 -d output=debug -r 44100-192000:500）：",
                  style="Hint.TLabel").pack(anchor="w")
        self.extra_text = tk.Text(bottom, height=2, font=self.mono_font, wrap="word",
                                  **self._text_opts(False))
        self.extra_text.pack(fill="x", pady=(2, 6))
        self.extra_text.insert("1.0", self.cfg.get("extra", "") or "")
        self.extra_text.bind("<KeyRelease>", lambda e: self._on_extra_change())
        ttk.Label(bottom, text="生成的命令：", style="Hint.TLabel").pack(anchor="w")
        self.mini_cmd = tk.Text(bottom, height=3, font=self.mono_font, wrap="word",
                                **self._text_opts(False))
        self.mini_cmd.pack(fill="x")
        self.mini_cmd.configure(state="disabled")
        self.validate_lbl = ttk.Label(bottom, text="", style="Status.TLabel")
        self.validate_lbl.pack(anchor="w", pady=(4, 0))

    def _make_param_row(self, parent, p):
        row = ttk.Frame(parent, padding=(4, 3))
        row.pack(fill="x")
        plat = "" if p["platform"] == "all" else ("  [%s]" % p["platform"])
        ttk.Label(row, text=p["name"] + plat, width=26, anchor="w").grid(row=0, column=0, sticky="w")
        ttk.Label(row, text=p["flag"], width=13, style="Hint.TLabel",
                  anchor="w").grid(row=0, column=1, sticky="w")
        var = tk.StringVar(value=str(self.values.get(p["key"], "")))
        self.vars[p["key"]] = var
        ent = ttk.Entry(row, textvariable=var, width=24)
        ent.grid(row=0, column=2, sticky="w", padx=(0, 6))
        labels = [o[1] for o in p["options"]]
        combo = ttk.Combobox(row, values=labels, state="readonly", width=40)
        combo.grid(row=0, column=3, sticky="w", padx=3)
        cur = str(self.values.get(p["key"], ""))
        hit = next((o[1] for o in p["options"] if o[0] == cur), "")
        if hit:
            combo.set(hit)
        combo.bind("<<ComboboxSelected>>",
                   lambda e, k=p["key"], c=combo: self._on_combo(k, c))
        ttk.Button(row, text="?", width=3,
                   command=lambda pp=p: self._show_param_detail(pp)).grid(row=0, column=4, padx=3)
        rec_txt = "★ 推荐: " + (p["recommend"] if p.get("recommend") else "不启用 / 默认")
        rec = ttk.Label(row, text=rec_txt, style="Rec.TLabel", cursor="hand2")
        rec.grid(row=0, column=5, sticky="w", padx=4)
        rec.bind("<Button-1>", lambda e, k=p["key"], v=p.get("recommend", ""): self._set_param(k, v))
        eff = ttk.Label(row, text="", style="Hint.TLabel", wraplength=880, justify="left")
        eff.grid(row=1, column=0, columnspan=6, sticky="w", padx=(4, 0), pady=(2, 3))
        ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=1)
        self.param_widgets[p["key"]] = {"entry": ent, "combo": combo, "effect": eff,
                                        "rec": rec, "var": var}
        var.trace_add("write", lambda *a, k=p["key"]: self._on_param_change(k))
        self._refresh_param_effect(p["key"])

    def _on_combo(self, key, combo):
        lab = combo.get()
        p = PARAM_BY_KEY[key]
        for val, label, _eff in p["options"]:
            if label == lab:
                self.vars[key].set(val)
                return

    def _set_param(self, key, value):
        value = value or ""
        self.values[key] = value
        self.cfg["params"] = dict(self.values)
        w = self.param_widgets.get(key)
        if not w:      # 参数页尚未构建时也能安全写入配置
            return
        w["var"].set(value)
        p = PARAM_BY_KEY[key]
        lab = next((o[1] for o in p["options"] if o[0] == value), "")
        w["combo"].set(lab)

    def _on_param_change(self, key):
        v = self.vars[key].get().strip()
        self.values[key] = v
        self.cfg["params"] = dict(self.values)
        self._refresh_param_effect(key)
        self._refresh_preview()

    def _refresh_param_effect(self, key):
        w = self.param_widgets.get(key)
        if not w:
            return
        p = PARAM_BY_KEY[key]
        v = self.vars[key].get().strip()
        ok, msg = validate_param(p, v)
        hit = next((o for o in p["options"] if o[0] == v), None)
        if not ok:
            txt, color = "⚠ " + msg, self.C["err"]
        elif hit:
            txt, color = "效果：" + hit[2], self.C["text2"]
        elif v:
            txt, color = "自定义值 · 合法范围：" + p["range"], self.C["warn"]
        else:
            txt, color = "当前：不设置（使用 squeezelite 默认值） · 合法范围：" + p["range"], self.C["text3"]
        w["effect"].configure(text=txt, foreground=color)

    def _show_param_detail(self, p):
        top = tk.Toplevel(self)
        top.configure(background=self.C["bg"])
        top.title("%s  %s" % (p["name"], p["flag"]))
        top.geometry("760x520")
        txt = scrolledtext.ScrolledText(top, wrap="word", font=self.ui_font,
                                     **self._text_opts(False))
        txt.pack(fill="both", expand=True)
        s = []
        s.append("参数：%s   开关：%s" % (p["name"], p["flag"]))
        s.append("分组：%s   适用平台：%s   类型：%s" % (
            p["group"], {"all": "全部", "mac": "仅 macOS", "linux": "仅 Linux/ALSA"}.get(p["platform"], p["platform"]),
            p["kind"]))
        s.append("\n【总体效果】\n" + p["effect"])
        s.append("\n【详细说明】\n" + p["detail"])
        s.append("\n【合法范围 / 自定义取值范围】\n" + p["range"])
        rec = p.get("recommend", "")
        rec_hit = next((o for o in p["options"] if o[0] == rec), None)
        s.append("\n【★ 最优音质推荐】  %s" % (rec if rec else "不启用 / 保持默认"))
        if rec_hit:
            s.append("推荐理由：%s" % rec_hit[2])
        if not rec:
            s.append("推荐理由：bit-perfect 路径应保持最短，不做任何重采样、混音或额外处理。")
        s.append("\n【可选值与各自效果】")
        for val, label, eff in p["options"]:
            s.append("  • %s  →  %s" % ((val if val else "(留空/不传)"), label))
            s.append("      效果：%s" % eff)
        txt.insert("1.0", "\n".join(s))
        txt.configure(state="disabled")

    def _show_all_params(self):
        top = tk.Toplevel(self)
        top.configure(background=self.C["bg"])
        top.title("Squeezelite 全部参数说明（依据官方 manpage 2025-10-10）")
        top.geometry("900x640")
        txt = scrolledtext.ScrolledText(top, wrap="word", font=self.ui_font,
                                     **self._text_opts(False))
        txt.pack(fill="both", expand=True)
        out = ["Squeezelite 官方参数手册（本工具内置 %d 项）\n" % len(PARAMS), "=" * 70, ""]
        for p in PARAMS:
            out.append("[%s] %s  %s" % (p["group"], p["name"], p["flag"]))
            out.append("  效果：%s" % p["effect"])
            out.append("  范围：%s" % p["range"])
            out.append("  ★推荐：%s" % (p.get("recommend") or "不启用/默认"))
            out.append("  说明：%s" % p["detail"])
            out.append("  可选值：")
            for val, label, eff in p["options"]:
                out.append("    - %s | %s\n        %s" % (val or "(留空)", label, eff))
            out.append("")
        txt.insert("1.0", "\n".join(out))
        txt.configure(state="disabled")

    def _apply_best(self):
        linked = {"output", "name", "server"}   # 由设备/名称/LMS 页维护，预设不得覆盖
        for p in PARAMS:
            if p["key"] in linked:
                continue
            self._set_param(p["key"], p.get("recommend", ""))
        self._refresh_preview()
        messagebox.showinfo(
            "已应用最优音质方案 (bit-perfect)",
            "核心设置：\n"
            "  -a 100:0       macOS Pro Mode 独占设备（绕过系统混音/SRC）\n"
            "  -r 44100-384000  声明全采样率范围，避免服务端重采样\n"
            "  不启用 -u/-R   关闭 SoX 重采样，保持源码流原样\n"
            "  -b 8192:8192  大缓冲，抗网络抖动（不改音质）\n"
            "  -C 不设置      设备常开，避免重新协商时钟\n"
            "  -d all=info    减少日志 I/O 干扰\n\n"
            "已保留你选择的输出设备、播放器名称与 LMS 服务器地址（不被预设覆盖）。\n\n"
            "重要：还需在 LMS 服务端把该播放器的「音量固定 / 比特率限制 / 转码」关闭，"
            "并确认音源为无损格式，才能真正实现 bit-perfect。")
        self._log("已应用最优音质方案")

    def _restore_defaults(self):
        linked = {"output", "name", "server"}
        for p in PARAMS:
            if p["key"] in linked:
                continue
            self._set_param(p["key"], p.get("default", ""))
        self.extra_text.delete("1.0", "end")
        self.cfg["extra"] = ""
        self._refresh_preview()
        self._log("参数已恢复默认值")

    def _on_extra_change(self):
        self.cfg["extra"] = self.extra_text.get("1.0", "end").strip()
        self._refresh_preview()

    def _check_values(self):
        problems = validate_all(self.values, self.cfg.get("extra", ""))
        if problems:
            messagebox.showwarning("参数校验未通过", "\n\n".join(problems))
            self.validate_lbl.configure(text="⚠ 发现 %d 处问题" % len(problems), style="Error.TLabel")
        else:
            self.validate_lbl.configure(text="✓ 全部参数取值合法", style="Ok.TLabel")
            messagebox.showinfo("校验通过", "全部参数与自定义附加参数取值合法。")

    # ------------------------------------------------------------ Tab3 启动控制
    def _build_tab_launch(self):
        f = self.tab_launch
        top = ttk.LabelFrame(f, text=" 完整启动命令（可直接复制） ", padding=8)
        top.pack(fill="x", padx=10, pady=8)
        self.cmd_text = tk.Text(top, height=4, font=self.mono_font, wrap="word",
                                **self._text_opts(False))
        self.cmd_text.pack(fill="x")
        bar = ttk.Frame(top)
        bar.pack(fill="x", pady=6)
        ttk.Button(bar, text="复制命令", command=self._copy_cmd).pack(side="left", padx=3)
        ttk.Button(bar, text="▶ 启动", command=self._start_proc).pack(side="left", padx=3)
        ttk.Button(bar, text="■ 停止", command=self._stop_proc).pack(side="left", padx=3)
        ttk.Button(bar, text="↻ 重启", command=self._restart_proc).pack(side="left", padx=3)
        ttk.Button(bar, text="保存为 .command 启动脚本",
                   command=self._save_launch_script).pack(side="left", padx=3)
        ttk.Button(bar, text="安装开机自启 (LaunchAgent)",
                   command=self._install_launch_agent).pack(side="left", padx=3)
        self.proc_status = ttk.Label(bar, text="未运行", style="Rec.TLabel")
        self.proc_status.pack(side="right", padx=6)

        logf = ttk.LabelFrame(f, text=" 运行日志（squeezelite stdout / stderr） ", padding=8)
        logf.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.proc_text = scrolledtext.ScrolledText(logf, wrap="word", font=self.mono_font,
                                                   **self._text_opts(True))
        self._terminal_texts.append(self.proc_text)
        self.proc_text.pack(fill="both", expand=True)

    # ------------------------------------------------------------ Tab4 升级与更新
    def _build_tab_update(self):
        f = self.tab_update
        # --- Squeezelite ---
        sl = ttk.LabelFrame(f, text=" A · Squeezelite 客户端（本地二进制 / 联网升级） ", padding=8)
        sl.pack(fill="both", expand=True, padx=10, pady=6)
        r1 = ttk.Frame(sl); r1.pack(fill="x")
        ttk.Label(r1, text="安装方式", width=12).pack(side="left")
        self.method_var = tk.StringVar(value=self.cfg.get("install_method", "auto"))
        mcb = ttk.Combobox(r1, textvariable=self.method_var, state="readonly", width=26,
                           values=["auto（二进制替换）", "brew（Homebrew 升级）"])
        mcb.pack(side="left", padx=3)
        mcb.bind("<<ComboboxSelected>>", lambda e: self._on_method_change())
        ttk.Label(r1, text="二进制路径", width=12).pack(side="left", padx=(16, 2))
        self.binpath_var = tk.StringVar(value=self.cfg.get("binary") or "")
        ttk.Entry(r1, textvariable=self.binpath_var, width=42).pack(side="left")
        ttk.Button(r1, text="浏览", command=self._choose_binary).pack(side="left", padx=3)
        self.binpath_var.trace_add("write", lambda *a: self._on_binpath_change())

        r2 = ttk.Frame(sl); r2.pack(fill="x", pady=7)
        self.sl_local_lbl = ttk.Label(r2, text="本机版本：未检测", width=42, anchor="w")
        self.sl_local_lbl.pack(side="left")
        self.sl_latest_lbl = ttk.Label(r2, text="最新版本：未检查", width=62, anchor="w")
        self.sl_latest_lbl.pack(side="left")
        self.sl_status_lbl = ttk.Label(r2, text="状态：待检查", style="Title.TLabel", anchor="w")
        self.sl_status_lbl.pack(side="left")

        r3 = ttk.Frame(sl); r3.pack(fill="x")
        ttk.Button(r3, text="检查更新", command=self._check_updates).pack(side="left", padx=3)
        ttk.Button(r3, text="查看升级内容", command=lambda: self._show_changelog("sl")).pack(side="left", padx=3)
        ttk.Button(r3, text="⬆ 执行升级", command=self._do_upgrade).pack(side="left", padx=3)
        ttk.Button(r3, text="打开 SourceForge 下载页",
                   command=lambda: self._open_url(SOURCES["sf_root"])).pack(side="left", padx=3)
        self.sl_src_lbl = ttk.Label(r3, text="", style="Hint.TLabel")
        self.sl_src_lbl.pack(side="left", padx=10)
        self.sl_changelog = tk.Text(sl, height=6, font=self.small_font, wrap="word",
                                    **self._text_opts(False))
        self.sl_changelog.pack(fill="both", expand=True, pady=(6, 0))
        self.sl_changelog.insert("1.0", "点击「检查更新」后，这里显示官方提交日志（升级内容）。")
        self.sl_changelog.configure(state="disabled")

        # --- LMS ---
        lm = ttk.LabelFrame(f, text=" B · LMS / Lyrion 服务端（版本检查 · 更新提示） ", padding=8)
        lm.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        l1 = ttk.Frame(lm); l1.pack(fill="x")
        ttk.Label(l1, text="服务器地址", width=12).pack(side="left")
        self.lms_host_var = tk.StringVar(value=self.cfg.get("lms_host", ""))
        ttk.Entry(l1, textvariable=self.lms_host_var, width=26).pack(side="left")
        ttk.Label(l1, text="端口").pack(side="left", padx=(10, 2))
        self.lms_port_var = tk.StringVar(value=self.cfg.get("lms_port", "9000"))
        ttk.Entry(l1, textvariable=self.lms_port_var, width=8).pack(side="left")
        ttk.Button(l1, text="测试 JSON-RPC", command=self._test_lms).pack(side="left", padx=8)
        ttk.Button(l1, text="打开下载页",
                   command=lambda: self._open_url(SOURCES["lms_downloads"])).pack(side="left", padx=3)
        for v in (self.lms_host_var, self.lms_port_var):
            v.trace_add("write", lambda *a: self._on_lms_change())

        la = ttk.Frame(lm); la.pack(fill="x", pady=(6, 0))
        ttk.Label(la, text="用户名", width=12).pack(side="left")
        self.lms_user_var = tk.StringVar(value=self.cfg.get("lms_user", "") or "")
        ttk.Entry(la, textvariable=self.lms_user_var, width=18).pack(side="left")
        ttk.Label(la, text="密码").pack(side="left", padx=(10, 2))
        self.lms_pass_var = tk.StringVar(value=self.cfg.get("lms_pass", "") or "")
        ttk.Entry(la, textvariable=self.lms_pass_var, width=18,
                  show="*").pack(side="left")
        ttk.Label(la, text="LMS 启用密码保护时填写；仅设密码则用户名留空",
                  style="Hint.TLabel").pack(side="left", padx=(10, 2))
        for v in (self.lms_user_var, self.lms_pass_var):
            v.trace_add("write", lambda *a: self._on_lms_change())

        l2 = ttk.Frame(lm); l2.pack(fill="x", pady=7)
        self.lms_cur_lbl = ttk.Label(l2, text="服务端当前版本：未检查", width=42, anchor="w")
        self.lms_cur_lbl.pack(side="left")
        self.lms_latest_lbl = ttk.Label(l2, text="最新正式版：未检查", width=38, anchor="w")
        self.lms_latest_lbl.pack(side="left")
        self.lms_status_lbl = ttk.Label(l2, text="状态：待检查", style="Title.TLabel", anchor="w")
        self.lms_status_lbl.pack(side="left")

        l3 = ttk.Frame(lm); l3.pack(fill="x")
        self.lms_tree = ttk.Treeview(l3, columns=("ch", "ver", "rev", "size", "url"),
                                     show="headings", height=4)
        for c, txt, w in [("ch", "渠道", 170), ("ver", "版本", 90), ("rev", "revision", 130),
                          ("size", "大小", 80), ("url", "macOS 下载地址", 460)]:
            self.lms_tree.heading(c, text=txt)
            self.lms_tree.column(c, width=w, minwidth=60, anchor="w",
                                 stretch=(c == "url"))
        self.lms_tree.pack(side="left", fill="both", expand=True)
        self._attach_wheel(self.lms_tree, self.lms_tree)
        ttk.Button(l3, text="检查更新", command=self._check_updates).pack(side="top", padx=4, pady=2)
        ttk.Button(l3, text="查看升级内容", command=lambda: self._show_changelog("lms")).pack(side="top", padx=4, pady=2)
        self.lms_changelog = tk.Text(lm, height=5, font=self.small_font, wrap="word",
                                     **self._text_opts(False))
        self.lms_changelog.pack(fill="both", expand=True, pady=(6, 0))
        self.lms_changelog.insert("1.0", "点击「检查更新」后，这里显示 LMS 官方提交日志（升级内容）。")
        self.lms_changelog.configure(state="disabled")
        self.sl_data, self.lms_data = {}, {}
        self.after(250, self._load_cache_to_ui)

    # ------------------------------------------------------------ Tab5 日志/帮助
    def _build_tab_help(self):
        f = self.tab_help
        lf = ttk.LabelFrame(f, text=" 运行日志 ", padding=6)
        lf.pack(fill="both", expand=True, padx=10, pady=6)
        self.log_text = scrolledtext.ScrolledText(lf, wrap="word", font=self.mono_font,
                                                  **self._text_opts(True))
        self._terminal_texts.append(self.log_text)
        self.log_text.pack(fill="both", expand=True)
        hf = ttk.LabelFrame(f, text=" 使用说明 / 数据源 ", padding=6)
        hf.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        t = scrolledtext.ScrolledText(hf, wrap="word", font=self.small_font,
                                      **self._text_opts(False))
        t.pack(fill="both", expand=True)
        t.insert("1.0", HELP_TEXT)
        t.configure(state="disabled")

    # ------------------------------------------------------------ 设备事件
    def _scan_devices(self):
        def worker():
            devs, reasons, binary = scan_devices(self.cfg, self.tlog)
            for r in reasons:
                self.tlog("扫描提示: " + r)
            self.q.put(("devices", (devs, reasons, binary)))
        self._run_bg(worker, "扫描音频输出设备")

    def _fill_devices(self, devs, reasons, binary):
        self.devices = devs
        self.dev_tree.delete(*self.dev_tree.get_children())
        chosen = (self.cfg.get("device_name") or "").lower()
        for i, d in enumerate(devs):
            is_sel = (d["name"].lower() == chosen)
            self.dev_tree.insert("", "end", iid=str(i), values=(
                "●" if is_sel else "", d["name"], d.get("id", "") or "-",
                d.get("source", ""), "是" if d.get("is_default") else ""),
                tags=("chosen",) if is_sel else (("odd",) if i % 2 else ()))
            if is_sel:
                self.dev_tree.selection_set(str(i))
        self.binary_var.set(binary or "（未找到）")
        self._log("设备扫描完成，共 %d 个" % len(devs))
        if not devs:
            self._log("未发现设备：可手动添加，或先在「升级与更新」页安装/指定 squeezelite")
        self.status_var.set("扫描完成 · %d 个输出设备" % len(devs))

    def _on_device_select(self, event):
        sel = self.dev_tree.selection()
        if not sel:
            return
        try:
            d = self.devices[int(sel[0])]
        except Exception:
            return
        self.cfg["device_name"] = d["name"]
        self.cfg["device"] = d.get("id") or d["name"]
        # -o 用设备名（最通用；需要编号时可在参数页自定义）
        self._set_param("output", d["name"])
        auto = device_short(d["name"])
        prev_auto = getattr(self, "_auto_short", "")
        cur = self.short_var.get().strip()
        if (not cur) or cur == prev_auto:
            self.short_var.set(auto)
            self._auto_short = auto
        self._update_name()
        for iid in self.dev_tree.get_children():
            self.dev_tree.item(iid, tags=())
        self.dev_tree.item(sel[0], tags=("chosen",))
        self.dev_tree.item(sel[0], values=("●", d["name"], d.get("id", "") or "-",
                                           d.get("source", ""),
                                           "是" if d.get("is_default") else ""))
        self._log("已选择输出设备: %s  (简称 %s)" % (d["name"], self.short_var.get()))

    def _update_name(self):
        host = self.host_var.get().strip() or local_host_name()
        short = self.short_var.get().strip() or "AUDIO"
        tpl = self.tpl_var.get()
        name = make_player_name(host, short, tpl)
        self.name_var.set(name)
        self.cfg["host_name"] = host
        self.cfg["name_template"] = tpl
        self.cfg["device_short"] = self.short_var.get().strip()
        self._set_param("name", name)
        self._refresh_preview()

    def _add_device(self):
        import tkinter.simpledialog as sd
        v = sd.askstring("手动添加输出设备",
                         "输入 squeezelite -l 中的设备名或编号（将作为 -o 的值）：", parent=self)
        if not v or not v.strip():
            return
        v = v.strip()
        self.devices.append({"id": "", "name": v, "raw": v, "source": "手动添加",
                             "is_default": False})
        self._fill_devices(self.devices, [], find_binary(self.cfg))
        self._log("已手动添加设备: %s" % v)

    def _choose_binary(self):
        p = filedialog.askopenfilename(title="选择 squeezelite 可执行文件", parent=self)
        if not p:
            return
        self.cfg["binary"] = p
        self.binpath_var.set(p)
        self.binary_var.set(p)
        self._log("已指定 squeezelite: %s" % p)
        self._scan_devices()

    def _on_binpath_change(self):
        self.cfg["binary"] = self.binpath_var.get().strip()

    def _on_method_change(self):
        v = self.method_var.get()
        self.cfg["install_method"] = "brew" if v.startswith("brew") else "auto"

    def _show_raw_l(self):
        def worker():
            b = find_binary(self.cfg)
            if not b:
                self.q.put(("info", "未找到 squeezelite 可执行文件"))
                return
            try:
                r = subprocess.run([b, "-l"], capture_output=True, text=True, timeout=15)
                out = (r.stdout or "") + "\n" + (r.stderr or "")
                self.tlog("=== squeezelite -l 原始输出 ===\n" + out.strip())
                self.q.put(("info", "squeezelite -l 原始输出：\n\n" + out.strip()[:900]))
            except Exception as e:
                self.q.put(("error", str(e)))
        self._run_bg(worker, "读取 -l 输出")

    # ------------------------------------------------------------ 命令与进程
    def _refresh_preview(self):
        try:
            argv = build_argv(self.cfg, self.values)
            text = preview_cmd(argv)
            problems = validate_all(self.values, self.cfg.get("extra", ""))
            if hasattr(self, "mini_cmd"):
                self.mini_cmd.configure(state="normal")
                self.mini_cmd.delete("1.0", "end")
                self.mini_cmd.insert("1.0", text)
                self.mini_cmd.configure(state="disabled")
            if hasattr(self, "cmd_text"):
                self.cmd_text.delete("1.0", "end")
                self.cmd_text.insert("1.0", text)
            if hasattr(self, "validate_lbl"):
                if problems:
                    self.validate_lbl.configure(text="⚠ " + "；".join(problems[:3]), style="Error.TLabel",
                                                foreground=self.C["err"])
                else:
                    self.validate_lbl.configure(text="✓ 全部参数合法 · 共 %d 个参数项" % len(argv), style="Ok.TLabel",
                                                foreground=self.C["ok"])
        except Exception as e:
            self._log("刷新命令预览失败: %s" % e)

    def _start_proc(self):
        if self.proc and self.proc.poll() is None:
            messagebox.showinfo(APP_NAME, "squeezelite 已在运行")
            return
        problems = validate_all(self.values, self.cfg.get("extra", ""))
        if problems:
            messagebox.showwarning("参数校验未通过", "\n\n".join(problems))
            return
        argv = build_argv(self.cfg, self.values)
        # 自动开启 output 模块 info 日志：用于读取实际解码 / 输出采样率，
        # 作为「完美直通」判定的权威依据（用户可在附加参数里自行覆盖）
        if not any("output=" in str(a) for a in argv):
            argv += ["-d", "output=info"]
        b = argv[0]
        if not os.path.isfile(b) or not os.access(b, os.X_OK):
            messagebox.showerror("无法启动",
                "找不到可执行的 squeezelite：%s\n\n请到「设备与名称」页指定路径，"
                "或到「升级与更新」页安装。" % b)
            return
        try:
            self.proc = subprocess.Popen(argv, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, text=True, bufsize=1)
        except Exception as e:
            messagebox.showerror("启动失败", str(e))
            return
        self.proc_start = time.time()
        self.sl_output = {}
        self.proc_text.delete("1.0", "end")
        self.q.put(("proc_log", "$ %s\n\n" % preview_cmd(argv)))
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()
        self.proc_status.configure(text="● 运行中 PID %s" % self.proc.pid)
        self._log("已启动 squeezelite (PID %s)" % self.proc.pid)

    def _reader(self, proc):
        try:
            for line in iter(proc.stdout.readline, ""):
                self.q.put(("proc_log", line))
        except Exception:
            pass
        finally:
            self.q.put(("proc_exit", proc.poll()))

    def _on_proc_exit(self, code):
        self.sl_output = {}
        self.proc_status.configure(text="已退出 (code %s)" % code)
        self._log("squeezelite 进程结束，退出码 %s" % code)
        self.proc = None

    def _stop_proc(self):
        if not self.proc or self.proc.poll() is not None:
            self.proc_status.configure(text="未运行")
            return
        p = self.proc
        try:
            p.terminate()
            p.wait(timeout=4)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
        self.proc_status.configure(text="已停止")
        self._log("已停止 squeezelite")

    def _restart_proc(self):
        self._stop_proc()
        self.after(600, self._start_proc)

    def _copy_cmd(self):
        try:
            txt = self.cmd_text.get("1.0", "end").strip()
            self.clipboard_clear(); self.clipboard_append(txt)
            self.status_var.set("命令已复制到剪贴板")
        except Exception as e:
            self._log("复制失败: %s" % e)

    def _save_launch_script(self):
        p = filedialog.asksaveasfilename(title="保存启动脚本", defaultextension=".command",
                                         initialfile="squeezelite-start.command", parent=self)
        if not p:
            return
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write("#!/bin/bash\n# 由 %s v%s 生成\n" % (APP_NAME, VERSION))
                f.write("exec " + preview_cmd(build_argv(self.cfg, self.values)) + "\n")
            os.chmod(p, 0o755)
            self._log("已保存启动脚本: %s" % p)
            messagebox.showinfo("已保存", "启动脚本：%s\n（macOS 下双击即可运行）" % p)
        except Exception as e:
            self.q.put(("error", str(e)))

    def _install_launch_agent(self):
        ok, msg = make_launch_agent(self.cfg, build_argv(self.cfg, self.values), self._log)
        (messagebox.showinfo if ok else messagebox.showerror)(APP_NAME,
            ("已安装开机自启：\n%s\n\n可用 launchctl unload 取消。" % msg) if ok else msg)

    # ------------------------------------------------------------ 升级检查
    def _on_lms_change(self):
        self.cfg["lms_host"] = self.lms_host_var.get().strip()
        self.cfg["lms_port"] = self.lms_port_var.get().strip() or "9000"
        if hasattr(self, "lms_user_var"):
            self.cfg["lms_user"] = self.lms_user_var.get().strip()
            self.cfg["lms_pass"] = self.lms_pass_var.get()
        self._refresh_preview()

    def _test_lms(self):
        def worker():
            r = lms_current(self.cfg, self.tlog)
            if r.get("ok"):
                self.q.put(("info", "连接成功！\nLMS 服务端版本：%s\n接口：%s" % (
                    r["version"], r.get("url", ""))))
                self.tlog("LMS 当前版本: %s" % r["version"])
            else:
                self.q.put(("error", "连接 LMS 失败：%s" % r.get("error", "")))
        self._run_bg(worker, "测试 LMS JSON-RPC")

    def _check_updates(self):
        def worker():
            log = self.tlog
            log("========== 检查 Squeezelite ==========")
            binary = find_binary(self.cfg)
            local = sq_local_version(binary, log)
            bv = brew_version(self.cfg, log)
            latest = sq_latest(log, self.cfg)
            ch, src = changelog("sl", log, self.cfg)
            sl = {"local": local, "brew": bv, "latest": latest,
                  "changelog": ch, "cl_source": src, "time": datetime.now().isoformat()}
            self.q.put(("upgrade_sl", sl))
            log("========== 检查 LMS 服务端 ==========")
            cur = lms_current(self.cfg, log)
            try:
                rel = lms_latest(log, self.cfg)
            except Exception as e:
                log("  ! LMS 版本库不可用: %s" % str(e)[:110])
                rel = {"channels": [], "source": "", "error": str(e)}
            lch, lsrc = changelog("lms", log, self.cfg)
            lms = {"current": cur, "release": rel, "changelog": lch,
                   "cl_source": lsrc, "time": datetime.now().isoformat()}
            self.q.put(("upgrade_lms", lms))
            save_cache({"sl": sl, "lms": lms})
            log("========== 检查完成，结果已缓存 ==========")
        self._run_bg(worker, "检查版本更新")

    def _fill_sl(self, d):
        self.sl_data = d or {}
        local, latest = d.get("local"), d.get("latest") or {}
        bv = d.get("brew")
        item = latest.get("latest") or {}
        self.sl_local_lbl.configure(text="本机版本：%s" % (
            ver_display(local["version"], local["revision"]) if local
            else (("Homebrew: " + bv["version"]) if bv else "未检测到（二进制缺失）")))
        src_rev = (latest or {}).get("source_rev", "")
        extra = ""
        try:
            if src_rev and item.get("revision") and int(src_rev) > int(item["revision"]):
                extra = "  | 源码最新 r%s" % src_rev
        except Exception:
            pass
        self.sl_latest_lbl.configure(text="最新版本：%s%s" % (
            item.get("label") or "未知", extra))
        st, color = self._sl_status(local, latest)
        self.sl_status_lbl.configure(text="状态：" + st, foreground=color)
        self.sl_src_lbl.configure(text="源: %s · 日志: %s" % (
            (latest.get("source") or "")[:48], (d.get("cl_source") or "无")[:40]))
        self._fill_changelog_text(self.sl_changelog, d.get("changelog") or [],
                                  d.get("cl_source") or "")
        if local and item.get("revision") and local.get("revision"):
            try:
                if int(item["revision"]) > int(local["revision"]):
                    self._log("★ Squeezelite 有更新: r%s → r%s" % (
                        local["revision"], item["revision"]))
            except Exception:
                pass

    def _sl_status(self, local, latest):
        item = (latest or {}).get("latest") or {}
        if not local:
            return "未检测到本机版本", self.C["warn"]
        if not item.get("revision") and not item.get("version"):
            return "无法获取最新版本（源降级）", self.C["warn"]
        try:
            if item.get("revision") and local.get("revision") \
                    and int(item["revision"]) > int(local["revision"]):
                return "发现新版本 r%s（当前 r%s）" % (
                    item["revision"], local["revision"]), self.C["err"]
        except Exception:
            pass
        if item.get("version") and ver_cmp(item["version"], local["version"]) > 0:
            return "发现新版本 %s" % item["version"], self.C["err"]
        return "已是最新版本", self.C["ok"]

    def _fill_lms(self, d):
        self.lms_data = d or {}
        cur, rel = d.get("current") or {}, d.get("release") or {}
        chans = rel.get("channels") or []
        self.lms_cur_lbl.configure(text="服务端当前版本：%s" % (
            cur.get("version") if cur.get("ok") else ("连接失败 / 未配置")))
        official = next((c for c in chans if c["channel"] == "latest"), None)
        self.lms_latest_lbl.configure(text="最新正式版：%s" % (
            official["version"] if official else "未知"))
        if not chans:
            st, color = "版本库不可用", self.C["warn"]
        elif not cur.get("ok"):
            st, color = "请填写 LMS 地址后检查", self.C["warn"]
        elif official and ver_cmp(official["version"], cur["version"]) > 0:
            st, color = "★ 服务端有更新 %s → %s" % (
                cur["version"], official["version"]), self.C["err"]
            self._log("★ LMS 服务端有更新: %s → %s（%s）" % (
                cur["version"], official["version"], official.get("url", "")))
        else:
            st, color = "已是最新正式版", self.C["ok"]
        self.lms_status_lbl.configure(text="状态：" + st, foreground=color)
        self.lms_tree.delete(*self.lms_tree.get_children())
        for i, c in enumerate(chans):
            self.lms_tree.insert("", "end", values=(
                c["label"], c["version"], c.get("revision", ""), c.get("size", ""),
                c.get("url", "")), tags=("odd",) if i % 2 else ())
        self._fill_changelog_text(self.lms_changelog, d.get("changelog") or [],
                                  d.get("cl_source") or "")

    def _fill_changelog_text(self, widget, items, source):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        if not items:
            widget.insert("1.0", "（未获取到升级内容，可能是网络受限；可在帮助页查看数据源）")
        else:
            widget.insert("1.0", "升级内容 / 官方提交日志（来源：%s，共 %d 条）\n" % (
                source or "GitHub", len(items)))
            widget.insert("end", "-" * 78 + "\n")
            for c in items:
                title = c.get("title", "")
                widget.insert("end", "  %s  %s\n" % (c.get("date", ""), title))
                body = (c.get("body") or "").strip()
                if body and body != title:
                    widget.insert("end", "        %s\n" % (body[:150] + ("..." if len(body) > 150 else "")))
        widget.configure(state="disabled")

    def _show_changelog(self, kind):
        d = self.sl_data if kind == "sl" else self.lms_data
        items = (d or {}).get("changelog") or []
        src = (d or {}).get("cl_source") or "未检查"
        title = ("Squeezelite 升级内容" if kind == "sl" else "LMS 服务端升级内容")
        top = tk.Toplevel(self)
        top.configure(background=self.C["bg"])
        top.title(title)
        top.geometry("860x520")
        t = scrolledtext.ScrolledText(top, wrap="word", font=self.ui_font,
                                     **self._text_opts(False))
        t.pack(fill="both", expand=True)
        t.insert("1.0", "%s\n来源：%s\n共 %d 条\n\n" % (title, src, len(items)))
        for c in items:
            t.insert("end", "  %s   %s\n" % (c.get("date", ""), c.get("title", "")))
            if c.get("url"):
                t.insert("end", "        %s\n" % c["url"])
        if kind == "sl" and (d or {}).get("latest"):
            latest = (d["latest"].get("latest") or {})
            t.insert("end", "\n【版本标注】\n  最新二进制：%s\n  下载地址：%s\n" % (
                latest.get("label", ""), latest.get("url", "")))
            sr = (d.get("latest") or {}).get("source_rev", "")
            if sr:
                t.insert("end", "  源码最新 revision：r%s（官方二进制通常滞后于源码）\n" % sr)
        if kind == "lms":
            for c in ((d or {}).get("release") or {}).get("channels", []):
                t.insert("end", "  %-22s %-10s r%-12s %s\n" % (
                    c["label"], c["version"], c.get("revision", ""), c.get("url", "")))
        t.configure(state="disabled")

    def _do_upgrade(self):
        d = self.sl_data or {}
        item = (d.get("latest") or {}).get("latest") or {}
        if not item.get("url"):
            messagebox.showinfo("无法自动升级",
                "当前未取得二进制下载地址（版本源可能降级）。\n"
                "可点击「打开 SourceForge 下载页」手动下载，或在「设备」页指定新二进制路径。")
            return
        if not messagebox.askyesno("确认升级 Squeezelite",
                "将下载并替换：\n\n  %s\n\n目标路径：%s\n\n"
                "旧版会自动备份到 %s，可随时回退。确认继续？" % (
                    item.get("label", ""), find_binary(self.cfg) or "（未找到）", BACKUP_DIR)):
            return
        def worker():
            cfg = dict(self.cfg)
            ok, msg = upgrade_squeezelite(cfg, item, self.tlog)
            self.q.put(("info" if ok else "error", msg))
            if ok:
                self.q.put(("log", "升级完成，正在复查本机版本"))
                v = sq_local_version(find_binary(cfg), self.tlog)
                if v:
                    self.q.put(("upgrade_sl", dict(d, local=v)))
        self._run_bg(worker, "升级 Squeezelite")

    def _open_url(self, url):
        try:
            import webbrowser
            webbrowser.open(url)
            self._log("已打开: %s" % url)
        except Exception as e:
            self._log("打开链接失败: %s" % e)

    def _load_cache_to_ui(self):
        try:
            if self.cache.get("sl"):
                self._fill_sl(self.cache["sl"])
            if self.cache.get("lms"):
                self._fill_lms(self.cache["lms"])
            if self.cache.get("sl") or self.cache.get("lms"):
                self._log("已载入上次检查结果缓存")
        except Exception as e:
            self._log("载入缓存失败: %s" % e)

    # ------------------------------------------------------------ 保存/关闭
    def _save_config(self):
        self.cfg["params"] = dict(self.values)
        self.cfg["host_name"] = self.host_var.get().strip()
        self.cfg["name_template"] = self.tpl_var.get().strip()
        self.cfg["device_short"] = self.short_var.get().strip()
        self.cfg["extra"] = self.extra_text.get("1.0", "end").strip()
        self.cfg["lms_host"] = self.lms_host_var.get().strip()
        self.cfg["lms_port"] = self.lms_port_var.get().strip() or "9000"
        if hasattr(self, "lms_user_var"):
            self.cfg["lms_user"] = self.lms_user_var.get().strip()
            self.cfg["lms_pass"] = self.lms_pass_var.get()
        self.cfg["binary"] = self.binpath_var.get().strip()
        if save_config(self.cfg):
            self.status_var.set("配置已保存")
            self._log("配置已保存: %s" % CONFIG_PATH)
        else:
            self.q.put(("error", "配置保存失败"))

    # ------------------------------------------------ Tab: 正在播放 (Now Playing)
    def _np_card(self, parent, bgkey="surface"):
        C = self.C
        fr = tk.Frame(parent, background=C[bgkey],
                      highlightbackground=C["border"],
                      highlightthickness=1, bd=0)
        fr._sq_bg = bgkey
        self.np_cards.append(fr)
        return fr

    def _np_label(self, parent, text, fg="text", size=10, bold=False):
        C = self.C
        l = tk.Label(parent, text=text, background=C["surface"],
                     foreground=C[fg],
                     font=(self.fam, size, "bold") if bold else (self.fam, size))
        l._sq_bg = "surface"
        l._sq_fg = fg
        return l

    def _build_tab_now(self):
        f = self.tab_now
        C = self.C
        self._np_alive = True
        self.np_busy = False
        self._np_pl_busy = False
        self._np_pl_last = 0.0
        self._np_last_poll = 0.0
        self._np_fail = 0
        self.np_players = []
        self.np_player = None
        self.np_track_key = ""
        self.np_lyrics = ""
        self.np_lyrics_src = ""
        self._np_src_text = "歌词：等待 LMS"
        self.np_lrc = {"timed": False, "lines": [], "meta": {}}
        self.np_timed = False
        self.np_mode = "stop"
        self.np_time = 0.0
        self.np_time_at = 0.0
        self.np_cover_key = ""
        self.np_photo = None
        self.np_cur_line = -1
        self.np_view = "lyrics"
        self.np_detail = {}
        self.sl_output = getattr(self, "sl_output", {})
        self.np_bio_key = ""
        self.np_bio_cache = ("", "", "")
        self.np_audio_data = None
        self.np_cards = []
        self.focus_win = None

        bar = ttk.Frame(f, padding=(10, 8))
        bar.pack(fill="x")
        ttk.Label(bar, text="播放器").pack(side="left")
        self.np_player_var = tk.StringVar(value="（未连接）")
        self.np_player_cb = ttk.Combobox(bar, textvariable=self.np_player_var,
                                         state="readonly", width=34, values=[])
        self.np_player_cb.pack(side="left", padx=5)
        self.np_player_cb.bind("<<ComboboxSelected>>", lambda e: self._np_on_pick())
        ttk.Button(bar, text="刷新播放器", style="Tool.TButton",
                   command=lambda: self._np_refresh_players(True)
                   ).pack(side="left", padx=3)
        self.np_auto_var = tk.BooleanVar(value=bool(self.cfg.get("np_auto", True)))
        ttk.Checkbutton(bar, text="自动跟随", variable=self.np_auto_var,
                        command=self._np_on_auto).pack(side="left", padx=(14, 3))
        ttk.Label(bar, text="间隔(秒)").pack(side="left", padx=(10, 2))
        self.np_int_var = tk.StringVar(value=str(self.cfg.get("np_interval", "2")))
        icb = ttk.Combobox(bar, textvariable=self.np_int_var, state="readonly",
                           width=5, values=["1", "2", "3", "5", "10"])
        icb.pack(side="left")
        icb.bind("<<ComboboxSelected>>", lambda e: self._np_on_interval())
        self.np_state_lbl = ttk.Label(bar, text="● 未连接", style="Status.TLabel")
        self.np_state_lbl.pack(side="right", padx=6)

        body = ttk.Frame(f, padding=(10, 4))
        body.pack(fill="both", expand=True)

        # ---------------- 左：封面 + 控制（卡片） ----------------
        left = self._np_card(body)
        left.configure(width=320)
        left.pack(side="left", fill="y", padx=(0, 14))
        left.pack_propagate(False)
        lin = tk.Frame(left, background=C["surface"], padx=14, pady=14)
        lin._sq_bg = "surface"
        lin.pack(fill="both", expand=True)

        cover_box = tk.Frame(lin, background=C["surface2"],
                             highlightbackground=C["border"],
                             highlightthickness=1, bd=0,
                             width=290, height=290)
        cover_box.pack(pady=(0, 12))
        cover_box.pack_propagate(False)
        self.np_cover_box = cover_box
        self.np_cover_lbl = tk.Label(cover_box, text="无封面",
                                     anchor="center", justify="center",
                                     background=C["surface2"],
                                     foreground=C["text3"])
        self.np_cover_lbl._sq_bg = "surface2"
        self.np_cover_lbl._sq_fg = "text3"
        self.np_cover_lbl.pack(fill="both", expand=True)

        ctl = tk.Frame(lin, background=C["surface"])
        ctl._sq_bg = "surface"
        ctl.pack(fill="x", pady=(0, 8))
        for i in range(3):
            # v1.6.0 设计映射 §四：uniform 保证三列等宽，防止「下一首」被挤出画面
            ctl.columnconfigure(i, weight=1, uniform="transport")
        ttk.Button(ctl, text="◀ 上一首", style="Tool.TButton",
                   command=lambda: self._np_cmd(["playlist", "index", "-1"])
                   ).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ttk.Button(ctl, text="播放 / 暂停", style="Accent.TButton",
                   command=self._np_toggle
                   ).grid(row=0, column=1, sticky="ew", padx=3)
        ttk.Button(ctl, text="下一首 ▶", style="Tool.TButton",
                   command=lambda: self._np_cmd(["playlist", "index", "+1"])
                   ).grid(row=0, column=2, sticky="ew", padx=(3, 0))
        for text, cmd in (("立即刷新", self._np_force_poll),
                          ("⛶ 进入专注大屏", self._focus_open),
                          ("重新搜索在线歌词", self._np_search_lyrics),
                          ("手动载入本地 LRC…", self._np_load_local_lrc)):
            ttk.Button(lin, text=text, style="Tool.TButton",
                       command=cmd).pack(fill="x", pady=(4, 0))

        # ---------------- 右：曲目 + 音频链路 + 三视图 ----------------
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)
        self.np_title = ttk.Label(right, text="—", style="Hero.TLabel",
                                  anchor="w", wraplength=420, justify="left")
        self.np_title.pack(fill="x")
        self.np_artist = ttk.Label(right, text="", style="Subtitle.TLabel", anchor="w")
        self.np_artist.pack(fill="x", pady=(2, 0))
        self.np_album = ttk.Label(right, text="", style="Caption.TLabel", anchor="w")
        self.np_album.pack(fill="x", pady=(2, 0))
        self.np_prog = ttk.Progressbar(right, mode="determinate", maximum=100, value=0)
        self.np_prog.pack(fill="x", pady=(8, 2))
        self.np_meta = ttk.Label(right, text="", style="Caption.TLabel", anchor="w")
        self.np_meta.pack(fill="x")

        ac = self._np_card(right)
        ac.pack(fill="x", pady=(10, 6))
        ain = tk.Frame(ac, background=C["surface"], padx=12, pady=9)
        ain._sq_bg = "surface"
        ain.pack(fill="x")
        ahdr = tk.Frame(ain, background=C["surface"])
        ahdr._sq_bg = "surface"
        ahdr.pack(fill="x")
        self._np_label(ahdr, "音频链路", "text2", 11, True).pack(side="left")  # overline
        self.np_audio_verdict = self._np_label(ahdr, "等待曲目…", "text2", 11, True)
        self.np_audio_verdict.pack(side="right")
        self.np_audio_spec = self._np_label(ain, "—", "text", 12)
        self.np_audio_spec.pack(fill="x", pady=(7, 2))
        self.np_audio_out = self._np_label(ain, "实际解码：—", "text2", 9)
        self.np_audio_out.pack(fill="x")
        self.np_audio_note = self._np_label(ain, "", "text3", 9)
        self.np_audio_note.configure(anchor="w", justify="left", wraplength=640)
        self.np_audio_note.pack(fill="x", pady=(3, 0))

        vbar = ttk.Frame(right)
        vbar.pack(fill="x", pady=(8, 4))
        self.np_view_var = tk.StringVar(value="lyrics")
        for key, text in (("lyrics", "歌词"), ("detail", "专辑详情"),
                          ("bio", "歌手 / 专辑简介")):
            ttk.Radiobutton(vbar, text=text, value=key,
                            variable=self.np_view_var,
                            command=lambda k=key: self._np_switch_view(k)
                            ).pack(side="left", padx=(0, 12))
        ttk.Button(vbar, text="⛶ 专注大屏", style="Tool.TButton",
                   command=self._focus_open).pack(side="right")
        self.np_src_lbl = ttk.Label(right, text=self._np_src_text,
                                    style="Overline.TLabel", anchor="w")
        self.np_src_lbl.pack(fill="x", pady=(2, 3))

        self.np_view_host = ttk.Frame(right)
        self.np_view_host.pack(fill="both", expand=True)
        self.np_view_lyrics = ttk.Frame(self.np_view_host)
        self.np_lyr_text = tk.Text(self.np_view_lyrics, height=12, wrap="word",
                                   font=self.ui_font, **self._text_opts(False))
        self.np_lyr_text.pack(fill="both", expand=True)
        self.np_lyr_text.configure(state="disabled")
        self._attach_wheel(self.np_lyr_text, self.np_lyr_text)

        self.np_view_detail = ttk.Frame(self.np_view_host)
        self.np_detail_text = tk.Text(self.np_view_detail, height=12, wrap="word",
                                      font=self.ui_font, tabs=(112,),
                                      **self._text_opts(False))
        self.np_detail_text.pack(fill="both", expand=True)
        self.np_detail_text.configure(state="disabled")
        self._attach_wheel(self.np_detail_text, self.np_detail_text)
        self.np_detail_text.insert("1.0", "（等待曲目信息）")

        self.np_view_bio = ttk.Frame(self.np_view_host)
        self.np_bio_text = tk.Text(self.np_view_bio, height=11, wrap="word",
                                   font=self.small_font, **self._text_opts(False))
        self.np_bio_text.pack(fill="both", expand=True)
        self.np_bio_text.configure(state="disabled")
        self._attach_wheel(self.np_bio_text, self.np_bio_text)
        self._np_bio_tags()
        ttk.Button(self.np_view_bio, text="重新获取简介", style="Tool.TButton",
                   command=lambda: self._np_bio_load(True)
                   ).pack(anchor="e", pady=(4, 0))

        self._np_switch_view("lyrics")
        self._np_apply_lyric_tags()
        self._np_after_theme()
        self._np_set_cover_placeholder("无封面")
        self.after(400, self._np_refresh_players)

    def _np_apply_lyric_tags(self):
        C = self.C
        try:
            self.np_lyr_text.tag_configure("cur", background=C["sel"],
                                           foreground=C["sel_text"])
            self.np_lyr_text.tag_configure("dim", foreground=C["text3"])
        except Exception:
            pass

    def _np_set_cover_placeholder(self, msg):
        C = self.C
        try:
            self.np_cover_lbl.configure(text=msg, image="",
                                        background=C["surface2"],
                                        foreground=C["text3"])
        except Exception:
            pass

    def _np_show_lyrics(self, text, src_label=""):
        try:
            self.np_lyr_text.configure(state="normal")
            self.np_lyr_text.delete("1.0", "end")
            self.np_lyr_text.insert("1.0", text or "（暂无歌词）")
            self.np_lyr_text.configure(state="disabled")
        except Exception:
            pass
        if src_label:
            self._np_src_text = src_label
            if self.np_view == "lyrics":
                try:
                    self.np_src_lbl.configure(text=src_label)
                except Exception:
                    pass

    def _np_highlight(self, pos, force=False):
        if not self.np_timed:
            return
        lines = self.np_lrc["lines"]
        if not lines:
            return
        idx = 0
        for i, (t, _) in enumerate(lines):
            if t <= pos + 0.15:
                idx = i
            else:
                break
        if idx == self.np_cur_line and not force:
            return
        self.np_cur_line = idx
        try:
            self.np_lyr_text.tag_remove("cur", "1.0", "end")
            self.np_lyr_text.tag_add("cur", "%d.0" % (idx + 1), "%d.end" % (idx + 1))
            self.np_lyr_text.see("%d.0" % (idx + 1))
        except Exception:
            pass

    def _np_render(self, d):
        st = d.get("status") or {}
        tr = st.get("track") or {}
        self.np_mode = st.get("mode") or "stop"
        self.np_title.configure(text=tr.get("title") or "—")
        self.np_artist.configure(text=tr.get("artist") or "未知艺术家")
        self.np_album.configure(text=tr.get("album") or "未知专辑")
        self._np_render_detail(tr)
        self._np_render_audio(tr, st)
        dur, pos = st.get("duration") or 0.0, st.get("time") or 0.0
        self.np_prog.configure(value=(min(100.0, pos / dur * 100.0) if dur > 0 else 0))
        label = {"play": "播放中", "pause": "已暂停", "stop": "已停止"}.get(
            self.np_mode, self.np_mode)
        self.np_meta.configure(text="%s / %s   ·   %s   ·   队列 %d/%d" % (
            fmt_sec(pos), fmt_sec(dur), label, st["index"] + 1, st["count"]))
        pname = st.get("player_name") or (self.np_player or {}).get("name", "")
        self.np_state_lbl.configure(text="● 已连接 · %s" % pname)
        self.np_time = pos
        self.np_time_at = time.monotonic()
        key = "%s|%s" % (tr.get("id", ""), tr.get("title", ""))
        if key != self.np_track_key:
            self.np_track_key = key
            self.np_lyrics = ""
            self.np_lyrics_src = ""
            self.np_lrc = {"timed": False, "lines": [], "meta": {}}
            self.np_timed = False
            self.np_cur_line = -1
            self.np_cover_key = ""
            self._np_set_cover_placeholder("载入封面…")
            self._np_show_lyrics("", "歌词：正在从 LMS 获取…")
            self._np_async_extras(tr, tr.get("coverid", ""),
                                  tr.get("artwork_url", ""))
        self._np_highlight(pos, force=True)
        if self.np_view == "bio":
            self._np_bio_load()
        if self.focus_win is not None:
            self._focus_update()

    def _np_async_extras(self, track, coverid, artwork_url):
        key = self.np_track_key
        pid = (self.np_player or {}).get("id", "")
        cfg = dict(self.cfg)
        pad = self.C["surface2"]

        def worker():
            try:
                lyr, src = np_lyrics_resolve(cfg, track, pid)
                self.q.put(("np_lyrics", {"key": key, "lyrics": lyr, "src": src}))
            except Exception:
                self.q.put(("np_lyrics", {"key": key, "lyrics": "", "src": ""}))
            try:
                url = np_cover_url(cfg, coverid, artwork_url)
                if url:
                    ch = {}
                    try:
                        if url.startswith(lms_base(cfg)):
                            ch = lms_auth_headers(cfg)
                    except Exception:
                        pass
                    data = http_request(url, headers=ch or None, timeout=8)
                    png = decode_cover_png(data, 280, square=True,
                                          pad_color=pad)
                    self.q.put(("np_cover", {"key": key, "url": url, "png": png}))
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _np_on_lyrics(self, d):
        if d.get("key") != self.np_track_key:
            return
        lyr = d.get("lyrics") or ""
        self.np_lyrics = lyr
        self.np_lyrics_src = d.get("src") or ""
        self.np_lrc = parse_lrc(lyr)
        self.np_timed = bool(lyr) and self.np_lrc["timed"]
        self.np_cur_line = -1
        if not lyr:
            self._np_show_lyrics(
                "", "歌词：LMS 与在线歌词库均未找到，可点「重新搜索在线歌词」或「手动载入本地 LRC…」")
        else:
            lines = [x for _, x in self.np_lrc["lines"]]
            self._np_show_lyrics(
                "\n".join(lines) if lines else lyr,
                "歌词来源：%s · %s" % (self.np_lyrics_src,
                                  "时间轴同步" if self.np_timed else "纯文本"))
        self._np_highlight(self.np_time, force=True)

    def _np_on_cover(self, d):
        if d.get("key") != self.np_track_key:
            return
        png = d.get("png")
        if not png:
            self._np_set_cover_placeholder("封面不可用")
            return
        try:
            import base64
            self.np_photo = tk.PhotoImage(data=base64.b64encode(png).decode("ascii"))
            self.np_cover_lbl.configure(image=self.np_photo, text="",
                                        background=self.C["surface"])
        except Exception as e:
            self._np_set_cover_placeholder("封面加载失败")
            self._log("Now Playing 封面: %s" % str(e)[:110])

    def _np_on_error(self, msg):
        self._np_fail += 1
        is_auth = ("401" in msg) or ("Unauthorized" in msg)
        try:
            self.np_state_lbl.configure(
                text="● LMS 需要密码" if is_auth else "● 连接失败")
        except Exception:
            pass
        if self._np_fail in (1, 2) or self._np_fail % 15 == 0:
            self._log("Now Playing: %s" % msg)
            if is_auth:
                self._log("  → LMS 启用了密码保护，请在「升级与更新」页填写用户名/密码，再点「刷新播放器」")

    def _np_refresh_players(self, force=False):
        if not (self.cfg.get("lms_host") or "").strip():
            self._np_on_error("未填写 LMS 服务器地址（在「升级与更新」页设置）")
            return
        if getattr(self, "_np_pl_busy", False):
            return
        now = time.monotonic()
        if (not force and getattr(self, "_np_pl_last", 0.0)
                and now - self._np_pl_last < 8):
            return
        self._np_pl_last = now
        self._np_pl_busy = True

        def worker():
            try:
                self.q.put(("np_players", np_players(dict(self.cfg))))
            except Exception as e:
                self.q.put(("np_error", "获取播放器列表失败: " + str(e)[:120]))
            finally:
                self._np_pl_busy = False
        threading.Thread(target=worker, daemon=True).start()

    def _np_fill_players(self, ps):
        self.np_players = ps or []
        names = ["%s  [%s]" % (p["name"] or p["id"], p["id"][-8:] or p["id"])
                 for p in self.np_players]
        try:
            self.np_player_cb.configure(values=names or ["（无播放器）"])
        except Exception:
            pass
        pick = np_pick_player(self.cfg, self.np_players,
                              self.cfg.get("np_playerid", ""))
        if pick:
            self._np_set_player(pick)
        elif self.np_players:
            self._np_set_player(self.np_players[0])
        else:
            self.np_player = None
            self.np_player_var.set("（无播放器）")
            self._np_on_error("LMS 未报告任何播放器")

    def _np_set_player(self, p):
        self.np_player = p
        self.cfg["np_playerid"] = p["id"]
        try:
            self.np_player_var.set("%s  [%s]" % (
                p["name"] or p["id"], p["id"][-8:] or p["id"]))
            save_config(self.cfg)
        except Exception:
            pass
        self._log("Now Playing: 选定播放器 %s (%s)" % (p["name"], p["id"]))
        self._np_last_poll = 0.0

    def _np_on_pick(self):
        try:
            i = self.np_player_cb.current()
            if 0 <= i < len(self.np_players):
                self._np_set_player(self.np_players[i])
        except Exception:
            pass

    def _np_on_auto(self):
        self.cfg["np_auto"] = bool(self.np_auto_var.get())
        try:
            save_config(self.cfg)
        except Exception:
            pass

    def _np_on_interval(self):
        self.cfg["np_interval"] = self.np_int_var.get()
        try:
            save_config(self.cfg)
        except Exception:
            pass

    def _np_force_poll(self):
        self._np_last_poll = 0.0
        if not self.np_busy:
            self._np_poll_once()

    def _np_toggle(self):
        self._np_cmd(["pause"] if self.np_mode == "play" else ["play"])

    def _np_cmd(self, cmd):
        if not self.np_player:
            messagebox.showinfo(APP_NAME, "请先在下拉框中选择播放器")
            return
        pid = self.np_player["id"]
        cfg = dict(self.cfg)

        def worker():
            try:
                lms_rpc(cfg, cmd, pid, _id=20)
                self._np_last_poll = 0.0
            except Exception as e:
                self.q.put(("np_error", "控制命令失败: " + str(e)[:120]))
        threading.Thread(target=worker, daemon=True).start()

    def _np_load_local_lrc(self):
        p = filedialog.askopenfilename(
            title="选择 LRC 歌词",
            filetypes=[("LRC 歌词", "*.lrc"), ("文本", "*.txt"), ("全部", "*")])
        if not p:
            return
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                txt = f.read()
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e))
            return
        self.np_lyrics = txt
        self.np_lyrics_src = "本地 LRC（手动）"
        self.np_lrc = parse_lrc(txt)
        self.np_timed = self.np_lrc["timed"]
        self.np_cur_line = -1
        lines = [x for _, x in self.np_lrc["lines"]]
        self._np_show_lyrics(
            "\n".join(lines) if lines else txt,
            "歌词来源：本地 LRC · %s" % ("时间轴同步" if self.np_timed else "纯文本"))
        self._np_highlight(self.np_time, force=True)

    def _np_poll_once(self):
        if not (self.cfg.get("lms_host") or "").strip():
            self._np_on_error("未填写 LMS 服务器地址（在「升级与更新」页设置）")
            return
        if not self.np_player:
            self._np_refresh_players()
            return
        self.np_busy = True
        pid = self.np_player["id"]
        cfg = dict(self.cfg)

        def worker():
            try:
                st = np_status(cfg, pid)
                self.q.put(("np_update", {"status": st}))
                self._np_fail = 0
            except Exception as e:
                self.q.put(("np_error", str(e)[:160]))
            finally:
                self.np_busy = False
        threading.Thread(target=worker, daemon=True).start()

    def _np_tick(self):
        if not getattr(self, "_np_alive", False):
            return
        now = time.monotonic()
        try:
            if self.np_timed and self.np_time_at:
                self._np_highlight(self.np_time + (now - self.np_time_at))
            interval = max(1, min(15, int(float(self.cfg.get("np_interval", "2") or 2))))
            if (self.cfg.get("np_auto", True) and not self.np_busy
                    and (now - self._np_last_poll) >= interval):
                self._np_last_poll = now
                self._np_poll_once()
        except Exception as e:
            self._log("Now Playing 轮询异常: %s" % str(e)[:110])
        if getattr(self, "focus_win", None) is not None:
            try:
                self._focus_update()
            except Exception:
                pass
        self.after(500, self._np_tick)

    def _np_switch_view(self, name):
        self.np_view = name if name in ("lyrics", "detail", "bio") else "lyrics"
        for fr in (self.np_view_lyrics, self.np_view_detail, self.np_view_bio):
            try:
                fr.pack_forget()
            except Exception:
                pass
        target = {"lyrics": self.np_view_lyrics,
                  "detail": self.np_view_detail,
                  "bio": self.np_view_bio}[self.np_view]
        target.pack(fill="both", expand=True)
        try:
            self.np_view_var.set(self.np_view)
        except Exception:
            pass
        try:
            if self.np_view == "lyrics":
                self.np_src_lbl.configure(text=self._np_src_text)
            elif self.np_view == "detail":
                self.np_src_lbl.configure(text="专辑详情 · 由 LMS 标签提供")
            else:
                self.np_src_lbl.configure(
                    text="歌手 / 专辑简介 · LMS（MAI）+ 维基百科兜底")
        except Exception:
            pass
        if self.np_view == "bio":
            self._np_bio_load()

    def _np_after_theme(self):
        C = self.C
        try:
            for c in getattr(self, "np_cards", ()):
                c.configure(highlightbackground=C["border"])
            self.np_cover_box.configure(highlightbackground=C["border"])
            self.np_cover_lbl.configure(background=C["surface2"],
                                        foreground=C["text3"])
            self.np_lyr_text.configure(**self._text_opts(False))
            self.np_detail_text.configure(**self._text_opts(False))
            self.np_bio_text.configure(**self._text_opts(False))
            self._np_apply_lyric_tags()
            self._np_bio_tags()
            if self.np_audio_data:
                self._np_render_audio(*self.np_audio_data)
            if self.focus_win is not None:
                self._focus_theme()
        except Exception:
            pass

    def _np_render_detail(self, tr):
        self.np_detail = dict(tr or {})
        try:
            self.np_detail_text.configure(state="normal")
            self.np_detail_text.delete("1.0", "end")
            self.np_detail_text.insert("1.0", detail_lines(self.np_detail))
            self.np_detail_text.configure(state="disabled")
        except Exception:
            pass

    # ------------------------------------------------ 音频链路 / 直通判定
    def _np_render_audio(self, tr, st):
        spec = audio_spec(tr)
        sl = getattr(self, "sl_output", {}) or {}
        proc = getattr(self, "proc", None)
        owned = bool(proc and proc.poll() is None)
        level, title, note = audio_link_verdict(spec, st, sl, owned)
        self.np_audio_data = (dict(tr), dict(st))
        C = self.C
        color = {"ok": "ok", "warn": "warn",
                 "unknown": "text2"}.get(level, "text2")
        mark = {"ok": "✓ ", "warn": "⚠ "}.get(level, "◇ ")
        try:
            self.np_audio_verdict._sq_fg = color
            self.np_audio_verdict.configure(text=mark + title,
                                            foreground=C[color])
            self.np_audio_spec.configure(
                text="%s   ·   %s   ·   %s   ·   %s" % (
                    spec["format"], spec["rate"], spec["bits"],
                    spec["bitrate"]))
            out = dict(sl or {})
            if out.get("rate"):
                txt = "实际解码：%s%s" % (
                    (out.get("format") + " · ") if out.get("format") else "",
                    fmt_sl_rate(out["rate"]))
                if out.get("note") and not out.get("converted"):
                    txt += "（%s）" % out["note"]
            else:
                txt = "实际解码：未读取到 squeezelite 输出日志"
            if not owned:
                txt += "   ·   播放器未由本 APP 启动"
            self.np_audio_out.configure(text=txt)
            self.np_audio_note.configure(text=note)
        except Exception:
            pass

    # ------------------------------------------------ 歌手 / 专辑简介
    def _np_bio_tags(self):
        C = self.C
        t = self.np_bio_text
        try:
            t.tag_configure("h", font=(self.fam, 12, "bold"),
                            foreground=C["primary"], spacing1=8, spacing3=4)
            t.tag_configure("b", font=self.ui_font, foreground=C["text"],
                            spacing1=2)
            t.tag_configure("m", font=self.small_font, foreground=C["text3"])
        except Exception:
            pass

    def _np_bio_show(self, msg, tags=("b",)):
        t = self.np_bio_text
        try:
            t.configure(state="normal")
            t.delete("1.0", "end")
            t.insert("1.0", msg, tags)
            t.configure(state="disabled")
        except Exception:
            pass

    def _np_bio_load(self, force=False):
        tr = dict(self.np_detail or {})
        artist = str(tr.get("artist") or "").strip()
        album = str(tr.get("album") or "").strip()
        if not (artist or album):
            self._np_bio_show("（等待曲目信息）", ("m",))
            return
        key = "%s|%s" % (artist, album)
        if not force and key == self.np_bio_key and any(self.np_bio_cache[:2]):
            self._np_render_bio(tr, *self.np_bio_cache)
            return
        cfg = dict(self.cfg)
        self._np_bio_show("正在获取歌手 / 专辑简介…", ("m",))

        def worker():
            try:
                a, b, s = bio_fetch(cfg, artist, album, force)
                self.q.put(("np_bio", {"key": key, "artist": a,
                                       "album": b, "src": s}))
            except Exception:
                self.q.put(("np_bio", {"key": key, "artist": "",
                                       "album": "", "src": "获取失败"}))
        threading.Thread(target=worker, daemon=True).start()

    def _np_on_bio(self, d):
        tr = dict(self.np_detail or {})
        key = "%s|%s" % (str(tr.get("artist") or "").strip(),
                         str(tr.get("album") or "").strip())
        if d.get("key") != key:
            return
        self.np_bio_key = key
        self.np_bio_cache = (d.get("artist") or "", d.get("album") or "",
                             d.get("src") or "")
        self._np_render_bio(tr, *self.np_bio_cache)

    def _np_render_bio(self, tr, a_txt, b_txt, src):
        t = self.np_bio_text
        artist = str(tr.get("artist") or "未知艺术家").strip()
        album = str(tr.get("album") or "未知专辑").strip()
        try:
            t.configure(state="normal")
            t.delete("1.0", "end")
            t.insert("end", "歌手 · %s\n" % artist, "h")
            t.insert("end", (str(a_txt).strip() or "（暂无在线简介）") + "\n\n", "b")
            t.insert("end", "专辑 · %s\n" % album, "h")
            t.insert("end", (str(b_txt).strip() or "（暂无在线简介）") + "\n\n", "b")
            t.insert("end", "LMS 专辑信息\n", "h")
            meta = []
            for k, label in (("year", "年份"), ("genre", "流派"),
                             ("composer", "作曲"), ("tracknum", "音轨"),
                             ("duration", "时长")):
                v = tr.get(k)
                if v and str(v) not in ("0", "-1"):
                    meta.append("%s %s" % (
                        label, fmt_sec(v) if k == "duration" else v))
            t.insert("end", ("  ·  ".join(meta) if meta else
                             "（LMS 未返回更多标签）") + "\n\n", "b")
            t.insert("end", "简介来源：%s\n" % (src or "—"), "m")
            t.insert("end", "歌手简介优先取自 LMS 的 Music & Artist Information 插件，"
                            "未命中时回退维基百科；专辑信息始终由 LMS 标签提供。\n"
                            "本 APP 不做真实 FFT：PCM 由 LMS 经 Slimproto 直送 "
                            "squeezelite，不经过本 APP，且 macOS 无原生回环采集。\n", "m")
            t.configure(state="disabled")
        except Exception:
            pass

    # ------------------------------------------------ 专注大屏模式
    def _focus_label(self, parent, text, fg="text", size=12, bold=False):
        C = self.C
        l = tk.Label(parent, text=text, background=C["bg"], foreground=C[fg],
                     font=(self.fam, size, "bold") if bold else (self.fam, size),
                     anchor="w")
        l._sq_bg = "bg"
        l._sq_fg = fg
        return l

    def _focus_open(self):
        win = getattr(self, "focus_win", None)
        if win is not None:
            try:
                win.lift()
                win.focus_force()
                return
            except Exception:
                self.focus_win = None
        C = self.C
        win = tk.Toplevel(self)
        self.focus_win = win
        self.focus_photo = None
        win.configure(background=C["bg"])
        try:
            win.attributes("-fullscreen", True)
        except Exception:
            pass
        try:
            win.attributes("-topmost", True)
        except Exception:
            pass
        win.bind("<Escape>", lambda e: self._focus_close())
        win.bind("<Motion>", lambda e: self._focus_motion())

        wrap = tk.Frame(win, background=C["bg"])
        wrap._sq_bg = "bg"
        wrap.pack(fill="both", expand=True, padx=70, pady=44)

        top = tk.Frame(wrap, background=C["bg"])
        top._sq_bg = "bg"
        top.pack(fill="x")
        self.focus_hint = self._focus_label(
            top, "专注模式 · 移动鼠标显示退出按钮 · ESC 退出", "text3", 10)
        self.focus_hint.pack(side="left")
        self.focus_exit = tk.Button(
            top, text="✕  退出专注模式", command=self._focus_close,
            relief="flat", bd=0, background=C["surface"],
            foreground=C["text"], activebackground=C["primary_dark"],
            activeforeground=C["on_app_bar"], font=(self.fam, 11, "bold"),
            padx=18, pady=8, cursor="hand2")
        self.focus_exit._sq_bg = "surface"
        self.focus_exit._sq_fg = "text"
        self.focus_exit.pack(side="right")

        main = tk.Frame(wrap, background=C["bg"])
        main._sq_bg = "bg"
        main.pack(fill="both", expand=True, pady=28)
        cover = tk.Frame(main, background=C["surface2"], width=420, height=420,
                         highlightbackground=C["border"], highlightthickness=1)
        cover._sq_bg = "surface2"
        cover.pack(side="left", padx=(0, 48))
        cover.pack_propagate(False)
        self.focus_cover_box = cover
        self.focus_cover = tk.Label(cover, text="无封面", anchor="center",
                                    justify="center", background=C["surface2"],
                                    foreground=C["text3"])
        self.focus_cover._sq_bg = "surface2"
        self.focus_cover._sq_fg = "text3"
        self.focus_cover.pack(fill="both", expand=True)

        info = tk.Frame(main, background=C["bg"])
        info._sq_bg = "bg"
        info.pack(side="left", fill="both", expand=True)
        self.focus_title = self._focus_label(info, "—", "text", 56, True)  # heroFocus
        self.focus_title.configure(wraplength=620, justify="left")
        self.focus_title.pack(anchor="w", pady=(30, 8))
        self.focus_artist = self._focus_label(info, "", "text2", 18)
        self.focus_artist.configure(wraplength=620, justify="left")
        self.focus_artist.pack(anchor="w")
        self.focus_album = self._focus_label(info, "", "text3", 12)
        self.focus_album.configure(wraplength=620, justify="left")
        self.focus_album.pack(anchor="w", pady=(4, 24))
        self.focus_lyric = self._focus_label(info, "", "primary", 20)
        self.focus_lyric.configure(wraplength=620, justify="center")
        self.focus_lyric.pack(fill="both", expand=True, pady=10)

        bottom = tk.Frame(wrap, background=C["bg"])
        bottom._sq_bg = "bg"
        bottom.pack(fill="x")
        self.focus_prog = ttk.Progressbar(bottom, mode="determinate", maximum=100)
        self.focus_prog.pack(fill="x", pady=(0, 6))
        brow = tk.Frame(bottom, background=C["bg"])
        brow._sq_bg = "bg"
        brow.pack(fill="x")
        ttk.Button(brow, text="◀ 上一首", style="Tool.TButton",
                   command=lambda: self._np_cmd(["playlist", "index", "-1"])
                   ).pack(side="left", padx=3)
        ttk.Button(brow, text="播放 / 暂停", style="Accent.TButton",
                   command=self._np_toggle).pack(side="left", padx=3)
        ttk.Button(brow, text="下一首 ▶", style="Tool.TButton",
                   command=lambda: self._np_cmd(["playlist", "index", "+1"])
                   ).pack(side="left", padx=3)
        self.focus_time = self._focus_label(brow, "0:00 / 0:00", "text2", 11)
        self.focus_time.pack(side="right")

        self._focus_last_motion = time.monotonic()
        self.after(500, self._focus_hide_tick)
        self._focus_update()
        self._focus_cover_async()

    def _focus_motion(self):
        self._focus_last_motion = time.monotonic()
        try:
            if self.focus_exit.winfo_manager() != "pack":
                self.focus_exit.pack(side="right")
        except Exception:
            pass

    def _focus_hide_tick(self):
        if getattr(self, "focus_win", None) is None:
            return
        try:
            if (time.monotonic() - getattr(self, "_focus_last_motion", 0)) > 3.0:
                if self.focus_exit.winfo_manager() == "pack":
                    self.focus_exit.pack_forget()
        except Exception:
            pass
        self.after(500, self._focus_hide_tick)

    def _focus_close(self):
        win = getattr(self, "focus_win", None)
        self.focus_win = None
        self.focus_photo = None
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass
        try:
            self.focus_force()
        except Exception:
            pass

    def _focus_theme(self):
        win = getattr(self, "focus_win", None)
        if win is None:
            return
        try:
            self._retheme_tk(win)
            C = self.C
            self.focus_cover_box.configure(highlightbackground=C["border"])
            self.focus_exit.configure(activebackground=C["primary_dark"],
                                      activeforeground=C["on_primary"],
                                      background=C["surface"],
                                      foreground=C["text"])
        except Exception:
            pass

    def _focus_cover_async(self):
        tr = dict(self.np_detail or {})
        cid = ""
        for k in ("coverid", "artwork_track_id", "artwork_url"):
            v = str(tr.get(k) or "").strip()
            if v and v not in ("0", "-1"):
                cid = v
                break
        if not cid:
            return
        cfg = dict(self.cfg)
        pad = self.C["surface2"]

        def worker():
            try:
                is_url = cid.startswith("http")
                url = np_cover_url(cfg, "" if is_url else cid,
                                   cid if is_url else "")
                if not url:
                    return
                ch = {}
                try:
                    if url.startswith(lms_base(cfg)):
                        ch = lms_auth_headers(cfg)
                except Exception:
                    pass
                data = http_request(url, headers=ch or None, timeout=8)
                png = decode_cover_png(data, 420, square=True, pad_color=pad)
                if png:
                    self.q.put(("focus_cover", png))
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _focus_on_cover(self, png):
        if getattr(self, "focus_win", None) is None:
            return
        try:
            import base64
            self.focus_photo = tk.PhotoImage(
                data=base64.b64encode(png).decode("ascii"))
            self.focus_cover.configure(image=self.focus_photo, text="",
                                       background=self.C["surface2"])
        except Exception:
            pass

    def _focus_update(self):
        if getattr(self, "focus_win", None) is None:
            return
        tr = dict(self.np_detail or {})
        try:
            self.focus_title.configure(text=tr.get("title") or "—")
            self.focus_artist.configure(text=tr.get("artist") or "未知艺术家")
            self.focus_album.configure(text=tr.get("album") or "")
            try:
                dur = float(tr.get("duration") or 0)
            except Exception:
                dur = 0.0
            pos = self.np_time
            if self.np_time_at:
                pos += time.monotonic() - self.np_time_at
            if dur > 0:
                self.focus_prog.configure(value=min(100.0, pos / dur * 100.0))
                self.focus_time.configure(
                    text="%s / %s" % (fmt_sec(pos), fmt_sec(dur)))
            txt = ""
            if self.np_timed and self.np_lrc["lines"]:
                i = max(0, self.np_cur_line)
                if i < len(self.np_lrc["lines"]):
                    txt = self.np_lrc["lines"][i][1]
            elif self.np_lyrics:
                txt = "♪  播放中"
            self.focus_lyric.configure(text=txt)
            if getattr(self, "focus_photo", None) is not None:
                self.focus_cover.configure(image=self.focus_photo, text="",
                                           background=self.C["surface2"])
            elif getattr(self, "np_photo", None) is not None:
                self.focus_cover.configure(image=self.np_photo, text="",
                                           background=self.C["surface2"])
        except Exception:
            pass

    def _np_search_lyrics(self):
        if not self.np_detail and not self.np_track_key:
            messagebox.showinfo(APP_NAME, "当前还没有曲目信息")
            return
        key = self.np_track_key
        tr = dict(self.np_detail)
        cfg = dict(self.cfg)
        pid = (self.np_player or {}).get("id", "")
        self._np_switch_view("lyrics")
        self._np_show_lyrics("", "歌词：正在重新搜索在线歌词…")

        def worker():
            try:
                lyr, src = np_lyrics_resolve(cfg, tr, pid, force=True)
                self.q.put(("np_lyrics", {"key": key, "lyrics": lyr, "src": src}))
            except Exception:
                self.q.put(("np_lyrics", {"key": key, "lyrics": "", "src": ""}))
        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------ Tab: 音乐库 (阶段 2)
    # ------------------------------------------------ Tab: 音乐库 (阶段 2)
    LIB_MODE_MAP = {"专辑": "albums", "艺术家": "artists", "曲目": "titles",
                    "流派": "genres", "播放列表": "playlists"}
    LIB_MODE_LABEL = {"albums": "专辑", "artists": "艺术家", "titles": "曲目",
                      "genres": "流派", "playlists": "播放列表"}

    def _lib_card(self, parent, bgkey="surface"):
        """带细边框的 Material 卡片容器，并登记以便换肤时刷新边框色。"""
        C = self.C
        f = tk.Frame(parent, background=C[bgkey],
                     highlightbackground=C["border"],
                     highlightthickness=1, bd=0)
        f._sq_bg = bgkey
        self.lib_cards.append(f)
        return f

    def _lib_label(self, parent, text, fgkey="text", size=10, bold=False):
        C = self.C
        l = tk.Label(parent, text=text, background=C["surface"],
                     foreground=C[fgkey],
                     font=(self.fam, size, "bold") if bold else (self.fam, size))
        l._sq_bg = "surface"
        l._sq_fg = fgkey
        return l

    def _lib_rule(self, parent, vertical=False):
        C = self.C
        r = tk.Frame(parent, background=C["border"],
                     width=1 if vertical else 0,
                     height=0 if vertical else 1)
        r._sq_bg = "border"
        return r

    def _build_tab_lib(self):
        f = self.tab_lib
        C = self.C
        self.lib_mode = "albums"
        self.lib_page = 0
        self.lib_pagesize = 50
        self.lib_total = 0
        self.lib_items = []
        self.lib_current = None
        self.lib_busy = False
        self.lib_req = 0
        self.lib_rowmap = {}
        self.lib_photo_refs = {}
        self.lib_cover_key = ""
        self.lib_photo = None
        self.lib_stack = []
        self.lib_drill = None
        self.lib_cards = []

        # ---------------- 工具卡片 ----------------
        tools = self._lib_card(f)
        tools.pack(fill="x", padx=12, pady=(10, 6))
        inner = tk.Frame(tools, background=C["surface"], padx=12, pady=9)
        inner._sq_bg = "surface"
        inner.pack(fill="x")

        self._lib_label(inner, "浏览", "text2", 9).pack(side="left")
        self.lib_mode_var = tk.StringVar(value="专辑")
        mcb = ttk.Combobox(inner, textvariable=self.lib_mode_var,
                           state="readonly", width=9,
                           values=["专辑", "艺术家", "曲目", "流派", "播放列表"])
        mcb.pack(side="left", padx=(5, 2))
        mcb.bind("<<ComboboxSelected>>", lambda e: self._lib_on_mode())

        self.lib_query_var = tk.StringVar()
        qe = ttk.Entry(inner, textvariable=self.lib_query_var, width=14)
        qe.pack(side="left", padx=(10, 3))
        qe.bind("<Return>", lambda e: self._lib_load(True))
        ttk.Button(inner, text="搜索", width=5, style="Tool.TButton",
                   command=lambda: self._lib_load(True)).pack(side="left", padx=2)
        ttk.Button(inner, text="刷新", width=5, style="Tool.TButton",
                   command=lambda: self._lib_load(True)).pack(side="left", padx=2)

        vr = self._lib_rule(inner, vertical=True)
        vr.pack(side="left", fill="y", padx=8, pady=2)

        self.lib_size_var = tk.StringVar(value="50")
        scb = ttk.Combobox(inner, textvariable=self.lib_size_var,
                           state="readonly", width=4,
                           values=["24", "50", "100"])
        scb.pack(side="left")
        scb.bind("<<ComboboxSelected>>", lambda e: self._lib_on_size())
        self.lib_page_lbl = self._lib_label(inner, "1 / 1 · 0 项", "text2", 9)
        self.lib_page_lbl.pack(side="left", padx=(8, 4))
        ttk.Button(inner, text="◀", width=3, style="Tool.TButton",
                   command=lambda: self._lib_page(-1)).pack(side="left", padx=1)
        ttk.Button(inner, text="▶", width=3, style="Tool.TButton",
                   command=lambda: self._lib_page(1)).pack(side="left", padx=1)

        sub = tk.Frame(tools, background=C["surface"], padx=12, pady=8)
        sub._sq_bg = "surface"
        sub.pack(fill="x")
        self.lib_state_lbl = self._lib_label(sub, "", "text2", 9)
        self.lib_state_lbl.pack(side="left")
        self._lib_label(sub, "双击专辑查看曲目 · 双击曲目直接播放",
                        "text3", 9).pack(side="right")

        # ---------------- 面包屑 / 下钻导航 ----------------
        crumb = tk.Frame(f, background=C["bg"])
        crumb._sq_bg = "bg"
        crumb.pack(fill="x", padx=12, pady=(2, 6))
        crumb.columnconfigure(2, weight=1)
        self.lib_back_btn = ttk.Button(crumb, text="← 返回",
                                       command=self._lib_back)
        self.lib_back_btn.grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.lib_crumb_lbl = tk.Label(crumb, text="", background=C["bg"],
                                      foreground=C["text2"],
                                      font=(self.fam, 10))
        self.lib_crumb_lbl._sq_bg = "bg"
        self.lib_crumb_lbl._sq_fg = "text2"
        self.lib_crumb_lbl.grid(row=0, column=1, sticky="w")
        self.lib_album_btn = ttk.Button(crumb, text="▶ 播放整张专辑",
                                        command=self._lib_play_album)
        self.lib_album_btn.grid(row=0, column=3, sticky="e", padx=(10, 0))

        # ---------------- 主体：列表 + 详情 ----------------
        body = ttk.Frame(f, padding=(12, 2, 12, 10))
        body.pack(fill="both", expand=True)

        lp = self._lib_card(body)
        lp.pack(side="left", fill="both", expand=True)
        lpin = tk.Frame(lp, background=C["surface"])
        lpin._sq_bg = "surface"
        lpin.pack(fill="both", expand=True, padx=1, pady=1)
        self.lib_tree = ttk.Treeview(
            lpin, columns=("name", "info"), show="tree headings",
            height=16, style="Item.Treeview")
        self.lib_tree.heading("#0", text="封面")
        self.lib_tree.column("#0", width=68, stretch=False, anchor="center")
        self.lib_tree.heading("name", text="名称")
        self.lib_tree.column("name", width=330, anchor="w", stretch=True)
        self.lib_tree.heading("info", text="信息")
        self.lib_tree.column("info", width=240, anchor="w", stretch=False)
        sb = ttk.Scrollbar(lpin, orient="vertical", command=self.lib_tree.yview)
        self.lib_tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(0, 1), pady=1)
        self.lib_tree.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        self._attach_wheel(self.lib_tree, self.lib_tree)
        self.lib_tree.bind("<<TreeviewSelect>>", lambda e: self._lib_on_select())
        self.lib_tree.bind("<Double-1>", self._lib_on_double)

        rp = self._lib_card(body)
        rp.pack(side="right", fill="y", padx=(12, 0))
        rp.configure(width=300)
        rp.pack_propagate(False)
        rpin = tk.Frame(rp, background=C["surface"], padx=12, pady=12)
        rpin._sq_bg = "surface"
        rpin.pack(fill="both", expand=True)

        cover_box = tk.Frame(rpin, background=C["surface2"],
                             highlightbackground=C["border"],
                             highlightthickness=1, bd=0,
                             width=272, height=272)
        cover_box.pack(pady=(0, 10))
        cover_box.pack_propagate(False)
        self.lib_cover_box = cover_box
        self.lib_cover_lbl = tk.Label(cover_box, text="无封面",
                                      anchor="center", justify="center",
                                      background=C["surface2"],
                                      foreground=C["text3"])
        self.lib_cover_lbl._sq_bg = "surface2"
        self.lib_cover_lbl._sq_fg = "text3"
        self.lib_cover_lbl.pack(fill="both", expand=True)

        self.lib_title_lbl = self._lib_label(rpin, "—", "text", 24, True)  # PageTitle
        self.lib_title_lbl.configure(anchor="w", justify="left", wraplength=272)
        self.lib_title_lbl.pack(fill="x")
        self.lib_sub_lbl = self._lib_label(rpin, "选择左侧条目查看详情", "text2", 17)  # Subtitle
        self.lib_sub_lbl.configure(anchor="w", justify="left", wraplength=272)
        self.lib_sub_lbl.pack(fill="x", pady=(2, 8))
        self._lib_rule(rpin).pack(fill="x", pady=(0, 8))

        self.lib_detail_text = tk.Text(
            rpin, height=9, wrap="word", font=self.small_font,
            tabs=(112,), **self._text_opts(False))
        self.lib_detail_text.configure(background=C["surface"])
        self.lib_detail_text.pack(fill="both", expand=True)
        self.lib_detail_text.configure(state="disabled")
        self._attach_wheel(self.lib_detail_text, self.lib_detail_text)
        self._lib_detail_tags()

        btns = tk.Frame(rpin, background=C["surface"])
        btns._sq_bg = "surface"
        btns.pack(fill="x", pady=(10, 0))
        self.lib_browse_btn = ttk.Button(btns, text="查看曲目",
                                         state="disabled",
                                         command=self._lib_browse_selected)
        self.lib_browse_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(btns, text="▶ 播放此项", style="Accent.TButton",
                   command=self._lib_play_selected).pack(
                       side="right", fill="x", expand=True, padx=(4, 0))

        self._lib_after_theme()
        self._lib_crumb()
        self.after(700, lambda: self._lib_load(True))

    def _lib_detail_tags(self):
        C = self.C
        t = self.lib_detail_text
        try:
            t.tag_configure("h", font=(self.fam, 12, "bold"),
                            foreground=C["text"], spacing3=6)
            t.tag_configure("s", font=(self.fam, 10),
                            foreground=C["text2"], spacing3=10)
            t.tag_configure("b", font=self.small_font,
                            foreground=C["text"], spacing1=2)
        except Exception:
            pass

    def _lib_after_theme(self):
        C = self.C
        try:
            for c in getattr(self, "lib_cards", ()):
                c.configure(highlightbackground=C["border"])
            self.lib_cover_box.configure(highlightbackground=C["border"])
            self.lib_cover_lbl.configure(background=C["surface2"],
                                         foreground=C["text3"])
            self.lib_detail_text.configure(
                background=C["surface"], foreground=C["text"],
                insertbackground=C["text"], selectbackground=C["sel"],
                selectforeground=C["sel_text"],
                highlightbackground=C["border"])
            self._lib_detail_tags()
            t = self.lib_tree
            t.tag_configure("odd", background=C["row_alt"],
                            foreground=C["text"])
            t.tag_configure("chosen", background=C["sel"],
                            foreground=C["sel_text"])
        except Exception:
            pass

    def _lib_set_cover_placeholder(self, msg):
        C = self.C
        try:
            self.lib_cover_lbl.configure(text=msg, image="",
                                         background=C["surface2"],
                                         foreground=C["text3"])
        except Exception:
            pass

    # ------------------------------------------------ 导航
    def _lib_effective(self):
        if self.lib_drill:
            return self.lib_drill["mode"], self.lib_drill["filters"]
        return self.LIB_MODE_MAP.get(self.lib_mode_var.get(), "albums"), []

    def _lib_crumb(self):
        d = self.lib_drill
        if d:
            self.lib_back_btn.grid()
            self.lib_crumb_lbl.configure(
                text="音乐库  ›  %s  ›  %s" % (d["parent"], d["name"]))
            if d.get("album_id"):
                self.lib_album_btn.grid()
            else:
                self.lib_album_btn.grid_remove()
        else:
            self.lib_back_btn.grid_remove()
            self.lib_album_btn.grid_remove()
            self.lib_crumb_lbl.configure(
                text="音乐库  ›  %s" % self.lib_mode_var.get())

    def _lib_enter(self, it):
        kind = it.get("_kind") or self.lib_mode
        if kind not in ("albums", "artists", "genres"):
            self._lib_play(it)
            return
        iid = str(it.get("id", ""))
        if not iid:
            return
        self.lib_stack.append({
            "drill": self.lib_drill, "page": self.lib_page,
            "mode_var": self.lib_mode_var.get(),
            "query": self.lib_query_var.get()})
        if kind == "albums":
            self.lib_drill = {
                "mode": "titles", "parent": "专辑",
                "name": it.get("_name", ""), "album_id": iid,
                "filters": ["album_id:" + iid, "sort:tracknum"]}
        else:
            key = "artist_id:" if kind == "artists" else "genre_id:"
            self.lib_drill = {
                "mode": "albums", "parent": self.LIB_MODE_LABEL.get(kind, ""),
                "name": it.get("_name", ""), "album_id": "",
                "filters": [key + iid]}
        self.lib_page = 0
        self.lib_query_var.set("")
        self.lib_mode_var.set(self.LIB_MODE_LABEL.get(self.lib_drill["mode"], "专辑"))
        self._lib_crumb()
        self._lib_load(True)

    def _lib_back(self):
        if not self.lib_stack:
            return
        st = self.lib_stack.pop()
        self.lib_drill = st["drill"]
        self.lib_page = st["page"]
        self.lib_query_var.set(st["query"])
        self.lib_mode_var.set(st["mode_var"])
        self._lib_crumb()
        self._lib_load(True)

    def _lib_on_double(self, e):
        iid = self.lib_tree.identify_row(e.y)
        if not iid:
            return
        self.lib_tree.selection_set(iid)
        it = self.lib_rowmap.get(iid)
        if not it:
            return
        kind = it.get("_kind") or self.lib_mode
        if kind in ("albums", "artists", "genres"):
            self._lib_enter(it)
        else:
            self._lib_play(it)
        return "break"

    def _lib_browse_selected(self):
        if self.lib_current:
            self._lib_enter(self.lib_current)

    def _lib_play_album(self):
        d = self.lib_drill or {}
        aid = d.get("album_id")
        if not aid:
            return
        self._lib_play({"id": aid, "_kind": "albums",
                        "_name": d.get("name", "整张专辑")})

    # ------------------------------------------------ 载入
    def _lib_on_mode(self):
        self.lib_stack = []
        self.lib_drill = None
        self.lib_page = 0
        self.lib_query_var.set("")
        self._lib_crumb()
        self._lib_load(True)

    def _lib_on_size(self):
        try:
            self.lib_pagesize = int(self.lib_size_var.get())
        except Exception:
            self.lib_pagesize = 50
        self.lib_page = 0
        self._lib_load(True)

    def _lib_page(self, delta):
        pages = max(1, (self.lib_total + self.lib_pagesize - 1) // self.lib_pagesize)
        new = max(0, min(pages - 1, self.lib_page + delta))
        if new == self.lib_page:
            return
        self.lib_page = new
        self._lib_load(True)

    def _lib_load(self, force=False):
        if self.lib_busy and not force:
            return
        if not (self.cfg.get("lms_host") or "").strip():
            try:
                self.lib_state_lbl.configure(text="请先在「升级与更新」页填写 LMS 地址")
            except Exception:
                pass
            return
        self.lib_busy = True
        self.lib_req += 1
        req = self.lib_req
        mode, filters = self._lib_effective()
        start = self.lib_page * self.lib_pagesize
        query = self.lib_query_var.get().strip()
        cfg = dict(self.cfg)
        try:
            self.lib_state_lbl.configure(text="正在载入…")
        except Exception:
            pass

        def worker():
            try:
                items, total = lib_browse(cfg, mode, start,
                                          self.lib_pagesize, query, filters)
                self.q.put(("lib_items", {"req": req, "items": items,
                                          "total": total, "mode": mode,
                                          "start": start, "query": query}))
            except Exception as e:
                self.q.put(("lib_error", str(e)[:150]))
            finally:
                self.lib_busy = False
        threading.Thread(target=worker, daemon=True).start()

    def _lib_on_items(self, d):
        if d.get("req") != self.lib_req:
            return
        self.lib_items = d.get("items") or []
        self.lib_total = int(d.get("total") or 0)
        self.lib_mode = d.get("mode") or "albums"
        pages = max(1, (self.lib_total + self.lib_pagesize - 1) // self.lib_pagesize)
        try:
            self.lib_page_lbl.configure(text="%d / %d 页 · %d 项" % (
                self.lib_page + 1, pages, self.lib_total))
            q = d.get("query") or ""
            self.lib_state_lbl.configure(
                text="本页 %d 项%s" % (len(self.lib_items),
                                    " · 搜索「%s」" % q if q else ""))
        except Exception:
            pass
        self._lib_fill_tree()
        self._lib_thumbs(self.lib_items)
        self.lib_current = None
        self._lib_set_cover_placeholder("选择条目查看封面")
        try:
            self.lib_title_lbl.configure(text="—")
            self.lib_sub_lbl.configure(text="选择左侧条目查看详情")
            self.lib_detail_text.configure(state="normal")
            self.lib_detail_text.delete("1.0", "end")
            self.lib_detail_text.configure(state="disabled")
            self.lib_browse_btn.configure(state="disabled", text="查看曲目")
        except Exception:
            pass

    # ------------------------------------------------ 列表
    def _lib_info(self, it):
        name = str(it.get("_name") or "").strip()
        kind = it.get("_kind") or self.lib_mode
        keys = {"albums": ("artist", "year", "tracks"),
                "titles": ("artist", "album", "duration"),
                "artists": ("albums", "tracks"),
                "genres": ("albums", "tracks"),
                "playlists": ("tracks",)}.get(kind, ())
        parts = []
        for k in keys:
            v = it.get(k)
            if not v or str(v) in ("0", "-1"):
                continue
            s = fmt_sec(v) if k == "duration" else str(v).strip()
            if not s or s == name or s in parts:
                continue
            parts.append(s)
            if len(parts) >= 2:
                break
        if not parts:
            return self.LIB_MODE_LABEL.get(kind, "")
        out = "  ·  ".join(parts)
        return out if len(out) <= 58 else out[:56] + "…"

    def _lib_fill_tree(self):
        t = self.lib_tree
        for i in t.get_children():
            t.delete(i)
        self.lib_rowmap = {}
        self.lib_photo_refs = {}
        for n, it in enumerate(self.lib_items):
            iid = "r%d" % n
            nm = str(it.get("_name") or "")
            tn = str(it.get("tracknum") or "")
            if it.get("_kind") == "titles" and tn.isdigit() and int(tn) > 0:
                nm = "%s.  %s" % (tn, nm)
            t.insert("", "end", iid=iid, text="",
                     values=(nm, self._lib_info(it)),
                     tags=("odd",) if n % 2 else ())
            self.lib_rowmap[iid] = it

    def _lib_render_detail(self, it):
        t = self.lib_detail_text
        d = dict(it)
        if str(d.get("title") or "") == str(it.get("_name") or ""):
            d.pop("title", None)
        sub = []
        for k in ("artist", "album", "year", "genre"):
            v = str(d.get(k) or "").strip()
            if v and v != str(it.get("_name") or "") and v not in sub:
                sub.append(v)
            if len(sub) >= 2:
                break
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.insert("end", str(it.get("_name") or "—") + "\n", "h")
        t.insert("end", ("  ·  ".join(sub) or self.LIB_MODE_LABEL.get(
            it.get("_kind") or self.lib_mode, "")) + "\n", "s")
        t.insert("end", detail_lines(d) + "\n", "b")
        t.configure(state="disabled")

    # ------------------------------------------------ 选中 / 封面
    def _lib_on_select(self):
        sel = self.lib_tree.selection()
        if not sel:
            return
        it = self.lib_rowmap.get(sel[0])
        if not it:
            return
        self.lib_current = it
        kind = it.get("_kind") or self.lib_mode
        try:
            self.lib_title_lbl.configure(text=str(it.get("_name") or "—"))
            self.lib_sub_lbl.configure(text=self._lib_info(it))
            self._lib_render_detail(it)
            if kind in ("albums", "artists", "genres"):
                self.lib_browse_btn.configure(
                    state="normal",
                    text="查看专辑" if kind != "albums" else "查看曲目")
            else:
                self.lib_browse_btn.configure(state="disabled", text="查看曲目")
        except Exception:
            pass
        cid = lib_cover_id(it)
        self.lib_cover_key = "%s|%s" % (it.get("id", ""), it.get("_name", ""))
        key = self.lib_cover_key
        self._lib_set_cover_placeholder("载入封面…")
        if not cid:
            self._lib_set_cover_placeholder("无封面")
            return
        cfg = dict(self.cfg)
        pad = self.C["surface2"]

        def worker():
            try:
                is_url = cid.startswith("http")
                url = np_cover_url(cfg, "" if is_url else cid,
                                   cid if is_url else "")
                if not url:
                    return
                ch = {}
                try:
                    if url.startswith(lms_base(cfg)):
                        ch = lms_auth_headers(cfg)
                except Exception:
                    pass
                data = http_request(url, headers=ch or None, timeout=8)
                self.q.put(("lib_cover", {"key": key,
                                          "png": decode_cover_png(
                                              data, 272, square=True,
                                              pad_color=pad)}))
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _lib_on_cover(self, d):
        if d.get("key") != self.lib_cover_key:
            return
        png = d.get("png")
        if not png:
            self._lib_set_cover_placeholder("封面不可用")
            return
        try:
            import base64
            self.lib_photo = tk.PhotoImage(
                data=base64.b64encode(png).decode("ascii"))
            self.lib_cover_lbl.configure(image=self.lib_photo, text="",
                                         background=self.C["surface2"])
        except Exception:
            self._lib_set_cover_placeholder("封面加载失败")

    def _lib_thumbs(self, items):
        req = self.lib_req
        cfg = dict(self.cfg)
        pad = self.C["surface2"]
        jobs = []
        for n, it in enumerate(items[:60]):
            cid = lib_cover_id(it)
            if cid:
                jobs.append(("r%d" % n, cid))
        if not jobs:
            return

        def work(pair):
            iid, cid = pair
            try:
                is_url = cid.startswith("http")
                url = np_cover_url(cfg, "" if is_url else cid,
                                   cid if is_url else "")
                ch = {}
                try:
                    if url.startswith(lms_base(cfg)):
                        ch = lms_auth_headers(cfg)
                except Exception:
                    pass
                data = http_request(url, headers=ch or None, timeout=5)
                png = decode_cover_png(data, 44, square=True,
                                       pad_color=pad)
                if png:
                    return (iid, png)
            except Exception:
                pass
            return None

        def runner():
            try:
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=6) as ex:
                    for r in ex.map(work, jobs):
                        if r:
                            self.q.put(("lib_thumb", {"req": req,
                                                     "iid": r[0], "png": r[1]}))
            except Exception:
                pass
        threading.Thread(target=runner, daemon=True).start()

    def _lib_on_thumb(self, d):
        if d.get("req") != self.lib_req:
            return
        iid = d.get("iid")
        try:
            if not self.lib_tree.exists(iid):
                return
            import base64
            ph = tk.PhotoImage(data=base64.b64encode(d["png"]).decode("ascii"))
            self.lib_photo_refs[iid] = ph
            self.lib_tree.item(iid, image=ph)
        except Exception:
            pass

    # ------------------------------------------------ 播放
    def _lib_play_selected(self):
        sel = self.lib_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "请先在列表中选择一项")
            return
        it = self.lib_rowmap.get(sel[0])
        if not it:
            return
        self._lib_play(it)

    def _lib_play(self, it):
        if not self.np_player:
            messagebox.showinfo(APP_NAME,
                                "请先在「正在播放」页选择播放器，再从此页点播")
            return
        pid = self.np_player["id"]
        cmd = lib_play_cmd(it.get("_kind") or self.lib_mode, it.get("id", ""))
        cfg = dict(self.cfg)
        name = it.get("_name", "")
        try:
            self.lib_state_lbl.configure(text="正在发送播放：%s" % name)
        except Exception:
            pass

        def worker():
            try:
                lms_rpc(cfg, cmd, pid, _id=31)
                self.q.put(("lib_played", "已点播：%s" % name))
                self._np_last_poll = 0.0
            except Exception as e:
                self.q.put(("lib_error", "点播失败：%s" % str(e)[:120]))
        threading.Thread(target=worker, daemon=True).start()

    def _lib_on_played(self, msg):
        try:
            self.lib_state_lbl.configure(text=msg)
        except Exception:
            pass
        self._log("音乐库：" + str(msg))

    def _lib_on_error(self, msg):
        try:
            self.lib_state_lbl.configure(text=str(msg)[:90])
        except Exception:
            pass
        self._log("音乐库错误：" + str(msg)[:160])

    def _apply_theme(self, name, save=False):
        if name not in THEMES:
            name = "light"
        self.theme_name = name
        if save:
            self.cfg["theme"] = name
            try:
                save_config(self.cfg)
            except Exception:
                pass
        self._init_style()
        self._retheme_tk(self)
        self._refresh_tree_tags()
        try:
            self._np_after_theme()
        except Exception:
            pass
        try:
            self._lib_after_theme()
        except Exception:
            pass
        try:
            self._theme_seg_update()
        except Exception:
            pass
        self._log("界面主题：%s（Lyrion Material）" % (
            "深色" if name == "dark" else "浅色"))

    def _theme_seg_update(self):
        """分段按钮：选中项反色胶囊，其余融入 app bar。ttk 样式自绘。"""
        cur = ("跟随系统" if self.theme_mode == "system" else
               ("深色" if self.theme_name == "dark" else "浅色"))
        for label, b in getattr(self, "theme_segs", {}).items():
            try:
                b.configure(style=("ThemeSegOn.TLabel" if label == cur
                                   else "ThemeSeg.TLabel"))
            except Exception:
                pass
        try:
            self.theme_mode_var.set(cur)
        except Exception:
            pass

    def _on_theme_choice(self, v):
        if v == "跟随系统":
            self.theme_mode = "system"
            self.cfg["theme_mode"] = "system"
            try:
                save_config(self.cfg)
            except Exception:
                pass
            self._theme_seg_update()
            self._log("界面主题：跟随系统")
            def once():
                try:
                    self.q.put(("sys_theme", system_dark_mode()))
                except Exception:
                    self.q.put(("sys_theme", None))
            threading.Thread(target=once, daemon=True).start()
        else:
            self.theme_mode = "manual"
            self.cfg["theme_mode"] = "manual"
            self._apply_theme("light" if v == "浅色" else "dark", save=True)

    def _sys_theme_loop(self):
        def worker():
            try:
                self.q.put(("sys_theme", system_dark_mode()))
            except Exception:
                self.q.put(("sys_theme", None))
        threading.Thread(target=worker, daemon=True).start()
        self.after(4000, self._sys_theme_loop)

    def _on_sys_theme(self, v):
        if getattr(self, "theme_mode", "manual") != "system" or v is None:
            return
        want = "dark" if v else "light"
        if want != self.theme_name:
            self._apply_theme(want, save=False)

    def _on_close(self):
        self._np_alive = False
        self._viz_alive = False
        try:
            self._save_config()
        except Exception:
            pass
        if self.proc and self.proc.poll() is None:
            if messagebox.askyesno(APP_NAME, "squeezelite 仍在运行，是否一并停止？"):
                self._stop_proc()
        self.destroy()


# ---------------------------------------------------------------- v1.3.0 helpers
LYRICS_CACHE_PATH = os.path.join(CONFIG_DIR, "lyrics_cache.json")

LIB_MODES = {
    "albums":    ("albums",    "albums_loop",    "album",    "专辑"),
    "artists":   ("artists",   "artists_loop",   "artist",   "艺术家"),
    "titles":    ("titles",    "titles_loop",    "title",    "曲目"),
    "genres":    ("genres",    "genres_loop",    "genre",    "流派"),
    "playlists": ("playlists", "playlists_loop", "playlist", "播放列表"),
}

def system_dark_mode():
    """返回 True=系统深色 / False=系统浅色 / None=无法判断。"""
    try:
        if IS_MAC:
            # defaults 无需「自动化」授权，优先使用；AppleScript 仅作兜底，
            # 避免每轮检测触发一次权限违例（-10004）。
            try:
                r = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3)
                if r.returncode == 0:
                    return "dark" in (r.stdout or b"").decode("utf-8", "replace").lower()
                return False
            except Exception:
                pass
            try:
                r = subprocess.run(
                    ["osascript", "-e",
                     'tell application "System Events" to tell appearance preferences to get dark mode'],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=4)
                v = (r.stdout or b"").decode("utf-8", "replace").strip().lower()
                if v in ("true", "false"):
                    return v == "true"
            except Exception:
                pass
        elif sys.platform.startswith("linux"):
            try:
                r = subprocess.run(
                    ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3)
                v = (r.stdout or b"").decode("utf-8", "replace").lower()
                if "dark" in v:
                    return True
                if "default" in v or "light" in v:
                    return False
            except Exception:
                pass
            th = (os.environ.get("GTK_THEME") or "").lower()
            if "dark" in th:
                return True
        elif sys.platform == "win32":
            try:
                r = subprocess.run(
                    ["reg", "query",
                     r"HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                     "/v", "AppsUseLightTheme"],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3)
                if r.returncode == 0 and "0x0" in (r.stdout or b"").decode("utf-8", "replace"):
                    return True
                if r.returncode == 0:
                    return False
            except Exception:
                pass
    except Exception:
        pass
    return None

def lyrics_cache_load():
    try:
        with open(LYRICS_CACHE_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}

def lyrics_cache_save(d):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        if len(d) > 400:
            for k in list(d.keys())[:len(d) - 400]:
                d.pop(k, None)
        with open(LYRICS_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.chmod(LYRICS_CACHE_PATH, 0o600)
    except Exception:
        pass

def lyrics_lrclib_candidates(title, artist, album="", duration=0, timeout=6):
    """返回 [(歌词文本, 来源), ...]；是否带时间轴由调用方判断。"""
    out = []
    p = {"track_name": title}
    if artist: p["artist_name"] = artist
    if album: p["album_name"] = album
    if duration > 0: p["duration"] = int(duration)
    u = "https://lrclib.net/api/get?" + urllib.parse.urlencode(p)
    try:
        d = json.loads(http_request(u, timeout=timeout).decode("utf-8", "replace"))
        syn = d.get("syncedLyrics") or ""
        plain = d.get("plainLyrics") or ""
        if syn:
            out.append((syn, "LRCLIB（在线同步歌词）"))
        if plain and plain != syn:
            out.append((plain, "LRCLIB（在线纯文本歌词）"))
    except Exception:
        pass
    p2 = {"track_name": title}
    if artist: p2["artist_name"] = artist
    u2 = "https://lrclib.net/api/search?" + urllib.parse.urlencode(p2)
    try:
        arr = json.loads(http_request(u2, timeout=timeout).decode("utf-8", "replace"))
        if isinstance(arr, list):
            for it in arr[:6]:
                if not isinstance(it, dict):
                    continue
                syn = it.get("syncedLyrics") or ""
                plain = it.get("plainLyrics") or ""
                if syn:
                    out.append((syn, "LRCLIB 搜索（同步）"))
                elif plain:
                    out.append((plain, "LRCLIB 搜索（纯文本）"))
    except Exception:
        pass
    return out

def lyrics_netease(title, artist, timeout=8):
    q = (str(title) + " " + str(artist)).strip()
    hdr = {"Referer": "https://music.163.com"}
    u = "https://music.163.com/api/search/get?" + urllib.parse.urlencode(
        {"s": q, "type": 1, "offset": 0, "limit": 5})
    d = json.loads(http_request(u, headers=hdr, timeout=timeout).decode("utf-8", "replace"))
    songs = ((d.get("result") or {}).get("songs") or [])
    if not songs:
        return "", ""
    sid = songs[0].get("id")
    if not sid:
        return "", ""
    u2 = "https://music.163.com/api/song/lyric?" + urllib.parse.urlencode(
        {"id": sid, "lv": 1, "kv": 1, "tv": -1})
    d2 = json.loads(http_request(u2, headers=hdr, timeout=timeout).decode("utf-8", "replace"))
    t = (d2.get("lrc") or {}).get("lyric") or ""
    return (t, "网易云音乐（在线）") if t else ("", "")

def lyrics_netease_candidates(title, artist="", timeout=8):
    """网易云音乐：返回 [(歌词, 来源标签), ...]（最多前 4 首匹配）。"""
    out = []
    q = (str(title) + " " + str(artist)).strip()
    hdr = {"Referer": "https://music.163.com"}
    try:
        u = "https://music.163.com/api/search/get?" + urllib.parse.urlencode(
            {"s": q, "type": 1, "offset": 0, "limit": 6})
        d = json.loads(http_request(u, headers=hdr, timeout=timeout).decode("utf-8", "replace"))
        songs = ((d.get("result") or {}).get("songs") or [])
        for s in songs[:4]:
            sid = s.get("id")
            if not sid:
                continue
            try:
                u2 = "https://music.163.com/api/song/lyric?" + urllib.parse.urlencode(
                    {"id": sid, "lv": 1, "kv": 1, "tv": -1})
                d2 = json.loads(http_request(u2, headers=hdr, timeout=timeout).decode("utf-8", "replace"))
                t = (d2.get("lrc") or {}).get("lyric") or ""
                if t:
                    nm = s.get("name") or ""
                    ars = ",".join(a.get("name", "") for a in (s.get("artists") or [])[:2])
                    label = "网易云音乐" + (" · " + nm + ("/" + ars if ars else "") if nm else "")
                    out.append((t, label))
            except Exception:
                continue
    except Exception:
        pass
    return out


def lyrics_qqmusic_candidates(title, artist="", timeout=8):
    """QQ 音乐：搜索 + 歌词接口，返回 [(歌词, 来源标签), ...]。"""
    out = []
    q = (str(title) + " " + str(artist)).strip()
    hdr = {"Referer": "https://y.qq.com/", "User-Agent": UA}
    try:
        u = "https://c.y.qq.com/soso/fcgi-bin/client_search_cp?" + urllib.parse.urlencode(
            {"w": q, "format": "json", "n": 8, "p": 1})
        d = json.loads(http_request(u, headers=hdr, timeout=timeout).decode("utf-8", "replace"))
        songs = ((d.get("data") or {}).get("song") or {}).get("list") or []
        for s in songs[:5]:
            mid = s.get("songmid")
            if not mid:
                continue
            try:
                u2 = "https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg?" + urllib.parse.urlencode(
                    {"songmid": mid, "format": "json", "nobase64": 1})
                d2 = json.loads(http_request(u2, headers=hdr, timeout=timeout).decode("utf-8", "replace"))
                t = d2.get("lyric") or ""
                if isinstance(t, dict):
                    t = ""
                if t:
                    nm = s.get("songname") or ""
                    sg = ",".join(x.get("name", "") for x in (s.get("singer") or [])[:2])
                    label = "QQ 音乐" + (" · " + nm + ("/" + sg if sg else "") if nm else "")
                    out.append((t, label))
            except Exception:
                continue
    except Exception:
        pass
    return out


def lyrics_kugou_candidates(title, artist="", duration=0, timeout=8):
    """酷狗音乐：搜索 + 歌词 candidates + download，返回 [(歌词, 来源标签), ...]。"""
    out = []
    q = (str(title) + " " + str(artist)).strip()
    try:
        u = "https://songsearch.kugou.com/song_search_v2?" + urllib.parse.urlencode(
            {"keyword": q, "page": 1, "pagesize": 8})
        d = json.loads(http_request(u, timeout=timeout).decode("utf-8", "replace"))
        lst = ((d.get("data") or {}).get("lists") or [])
        for s in lst[:5]:
            fh = s.get("FileHash")
            if not fh:
                continue
            try:
                p = {"ver": 1, "man": "yes", "client": "pc", "keyword": q, "hash": fh}
                dur = int(s.get("Duration") or 0)
                if dur:
                    p["duration"] = dur
                u2 = "https://lyrics.kugou.com/search?" + urllib.parse.urlencode(p)
                d2 = json.loads(http_request(u2, timeout=timeout).decode("utf-8", "replace"))
                for cd in (d2.get("candidates") or [])[:2]:
                    cid, ak = cd.get("id"), cd.get("accesskey")
                    if not cid or not ak:
                        continue
                    try:
                        u3 = "https://lyrics.kugou.com/download?" + urllib.parse.urlencode(
                            {"ver": 1, "client": "pc", "id": cid, "accesskey": ak,
                             "format": "lrc", "charset": "utf8"})
                        d3 = json.loads(http_request(u3, timeout=timeout).decode("utf-8", "replace"))
                        content = d3.get("content") or ""
                        if content:
                            try:
                                content = base64.b64decode(content).decode("utf-8", "replace")
                            except Exception:
                                pass
                            nm = s.get("SongName") or ""
                            label = "酷狗音乐" + (" · " + nm if nm else "")
                            out.append((content, label))
                    except Exception:
                        continue
            except Exception:
                continue
    except Exception:
        pass
    return out


def lyrics_collect(title, artist="", album="", duration=0):
    """汇总所有在线歌词源候选，供前端手动选择。
    返回 [{"source":..., "text":..., "timed":bool}, ...]，带时间轴的优先。"""
    title = str(title or "").strip()
    if not title:
        return []
    out = []
    seen = set()

    def add(text, source):
        text = (text or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        out.append({"source": source, "text": text,
                    "timed": bool(parse_lrc(text).get("timed"))})

    for fn, args in (
        (lyrics_netease_candidates, (title, artist)),
        (lyrics_qqmusic_candidates, (title, artist)),
        (lyrics_kugou_candidates, (title, artist, duration)),
        (lyrics_lrclib_candidates, (title, artist, album, duration)),
    ):
        try:
            for t, s in fn(*args):
                add(t, s)
        except Exception:
            pass
    out.sort(key=lambda x: (not x["timed"],))
    return out


LYRIC_CHOICE_PATH = os.path.join(CONFIG_DIR, "lyric_choices.json")


def lyric_choice_get(key):
    try:
        with open(LYRIC_CHOICE_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d.get(key) if isinstance(d, dict) else None
    except Exception:
        return None


def lyric_choice_set(key, source, text):
    try:
        d = {}
        if os.path.exists(LYRIC_CHOICE_PATH):
            with open(LYRIC_CHOICE_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict):
                d = {}
        d[key] = {"source": source, "text": text}
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(LYRIC_CHOICE_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.chmod(LYRIC_CHOICE_PATH, 0o600)
        return True
    except Exception:
        return False


def lyric_choice_clear(key):
    try:
        if not os.path.exists(LYRIC_CHOICE_PATH):
            return True
        with open(LYRIC_CHOICE_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and key in d:
            d.pop(key, None)
            with open(LYRIC_CHOICE_PATH, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
        return True
    except Exception:
        return False


def lyric_choice_key(track):
    t = str((track or {}).get("title") or "").strip()
    a = str((track or {}).get("artist") or "").strip()
    tid = str((track or {}).get("id") or "").strip()
    return (tid + "|" if tid else "") + t + "|" + a


def lyrics_online(title, artist="", album="", duration=0, force=False):
    """不依赖 LMS 插件与本地挂载：带时间轴歌词优先，结果本地缓存。"""
    title = str(title or "").strip()
    if not title:
        return "", ""
    key = "%s|%s|%s" % (title, str(artist or "").strip(), str(album or "").strip())
    cache = lyrics_cache_load()
    if not force and key in cache:
        v = cache[key]
        return v.get("text", ""), v.get("src", "")

    def save_ret(t, s):
        cache[key] = {"text": t, "src": s}
        lyrics_cache_save(cache)
        return t, s

    lr = []
    try:
        lr = lyrics_lrclib_candidates(title, artist, album, duration)
    except Exception:
        pass
    timed = next(((t, s) for t, s in lr if t and parse_lrc(t)["timed"]), None)
    if timed:
        return save_ret(timed[0], timed[1])

    ne = []
    try:
        t, s = lyrics_netease(title, artist)
        if t:
            ne.append((t, s))
    except Exception:
        pass
    timed2 = next(((t, s) for t, s in ne if t and parse_lrc(t)["timed"]), None)
    if timed2:
        return save_ret(timed2[0], timed2[1])

    any_ = next(((t, s) for t, s in lr + ne if t), None)
    if any_:
        return save_ret(any_[0], any_[1])
    cache[key] = {"text": "", "src": ""}
    lyrics_cache_save(cache)
    return "", ""

def np_lyrics_resolve(cfg, track, playerid="", force=False):
    """优先级：LMS 内嵌歌词 → LMS/MAI → 在线歌词（带时间轴优先）→ 空。

    MAI 的 musicartistinfo lyrics 实测多为纯文本、无时间轴，因此默认仍让带
    时间轴的在线 LRC 优先，以保留逐行同步高亮；MAI 作为「完全从 LMS 端取数」
    的来源在在线未命中或无时间轴时兜底。配置 lyrics_prefer_lms=true 可强制
    MAI 优先（此时会失去逐行高亮）。
    """
    lyr, src = np_lyrics_from_lms(cfg, track.get("id", ""), playerid)
    if lyr:
        return lyr, src
    mai, msrc = lms_mai_lyrics(cfg, track)
    if mai and (cfg.get("lyrics_prefer_lms") or parse_lrc(mai)["timed"]):
        return mai, msrc
    t, s = lyrics_online(track.get("title", ""), track.get("artist", ""),
                         track.get("album", ""), _to_float(track.get("duration")),
                         force=force)
    if t and parse_lrc(t)["timed"]:
        return t, s
    if mai:
        return mai, msrc
    if t:
        return t, s
    return "", ""

def lib_cover_id(it):
    """LMS 不同查询返回的封面标识字段名不同，统一取一个可用值。"""
    for k in ("coverid", "artwork_track_id", "artwork_url", "cover"):
        v = str(it.get(k) or "").strip()
        if v and v not in ("0", "-1"):
            return v
    return ""

def lib_browse(cfg, mode, start=0, count=50, query="", filters=None):
    """浏览 LMS 曲库；filters 用于下钻（album_id / artist_id / genre_id 等）。"""
    cmd, loopkey, namekey, label = LIB_MODES.get(mode, LIB_MODES["albums"])
    args = [cmd, int(start), int(count)]
    if mode == "albums":
        # a=艺术家 l=专辑 j=artwork_track_id（小写 j 才返回封面标识）
        args.append("tags:alj")
    elif mode == "titles":
        args.append("tags:alcKdtuIroj")  # j=artwork_track_id，让曲目也带封面标识
    for f in (filters or []):
        if f:
            args.append(str(f))
    if query:
        args.append("search:" + str(query).strip())
    r = lms_rpc(cfg, args, _id=30)
    items = []
    for it in (r.get(loopkey) or []):
        if not isinstance(it, dict):
            continue
        d = {k: ("" if v is None else str(v)) for k, v in it.items()}
        d["_kind"] = mode
        d["_name"] = (d.get(namekey) or d.get("title") or d.get("album")
                      or d.get("artist") or d.get("id") or "")
        items.append(d)
    try:
        total = int(r.get("count") or len(items))
    except Exception:
        total = len(items)
    return items, total

def lib_play_cmd(mode, item_id):
    k = {"albums": "album_id", "artists": "artist_id", "titles": "track_id",
         "genres": "genre_id", "playlists": "playlist_id"}.get(mode, "album_id")
    return ["playlistcontrol", "cmd:load", "%s:%s" % (k, item_id)]

DETAIL_LABELS = {
    "title": "曲名", "artist": "艺术家", "albumartist": "专辑艺术家",
    "album": "专辑", "genre": "流派", "year": "年份",
    "tracknum": "音轨号", "disc": "碟号", "duration": "时长",
    "bitrate": "比特率", "samplerate": "采样率", "samplesize": "位深",
    "type": "文件格式", "filesize": "文件大小", "url": "文件路径",
    "comment": "注释", "composer": "作曲", "conductor": "指挥",
    "bpm": "BPM", "rating": "评分", "playcount": "播放次数",
}
DETAIL_ORDER = ["title", "artist", "albumartist", "album", "genre", "year",
                "tracknum", "disc", "duration", "bitrate", "samplerate",
                "samplesize", "type", "filesize", "url", "comment",
                "composer", "conductor", "bpm"]
DETAIL_SKIP = {"id", "coverid", "artwork_url", "artwork_track_id",
               "favorites_title", "favorites_url", "performance",
               "_kind", "_name"}

def detail_value(k, v):
    s = str(v)
    if k == "duration":
        return "%s（%s 秒）" % (fmt_sec(s), s)
    if k == "bitrate" and s.replace(".", "", 1).isdigit():
        return s + " kbps"
    if k == "samplerate" and s.replace(".", "", 1).isdigit():
        return s + " Hz"
    if k == "samplesize" and s.isdigit():
        return s + " bit"
    if k == "filesize" and s.isdigit():
        n = int(s)
        return "%.1f MB" % (n / 1048576.0) if n > 1048576 else "%d KB" % (n // 1024)
    if k in ("url", "file") and s:
        try:
            s = urllib.parse.unquote(s)
        except Exception:
            pass
        for pre in ("file://", "http://", "https://"):
            if s.startswith(pre):
                s = s[len(pre):]
                break
        parts = [x for x in s.replace("\\", "/").split("/") if x]
        if len(parts) > 2:
            s = "…/" + "/".join(parts[-2:])
        return s
    return s

def detail_lines(track):
    """把 status / songinfo 返回的字段转成「标签：值」文本；未知字段也展示。"""
    t = track or {}
    out, used = [], set()
    for k in DETAIL_ORDER:
        v = t.get(k)
        if v in (None, "", "0") or k in used:
            continue
        used.add(k)
        out.append("%s：\t%s" % (DETAIL_LABELS.get(k, k), detail_value(k, v)))
    for k in sorted(t.keys()):
        if k in used or k in DETAIL_SKIP or k.startswith("_"):
            continue
        v = t.get(k)
        if v in (None, "", "0"):
            continue
        out.append("%s：\t%s" % (k, str(v)))
    return "\n".join(out) if out else "（暂无详情，LMS 未返回更多标签）"

# ---------------------------------------------------------------- v1.5.0 helpers
BIO_CACHE_PATH = os.path.join(CONFIG_DIR, "bio_cache.json")
_WIKI_UA = "SqueezeliteGUI/1.5 (local desktop application)"

AUDIO_FORMAT_MAP = (
    (".dsf", "DSD (DSF)"), (".dff", "DSD (DFF)"), (".dsd", "DSD"),
    (".iso", "SACD ISO (DSD)"), (".flac", "FLAC"), (".wav", "WAV / PCM"),
    (".aiff", "AIFF / PCM"), (".aif", "AIFF / PCM"), (".pcm", "PCM"),
    (".alac", "ALAC"), (".m4a", "AAC / ALAC"), (".aac", "AAC"),
    (".mp3", "MP3"), (".ogg", "Ogg Vorbis"), (".opus", "Opus"),
    (".ape", "Monkey's Audio"), (".wv", "WavPack"), (".mpc", "Musepack"),
)
_DSD_EXT = (".dsf", ".dff", ".dsd", ".iso")

# LMS 的 type 字段（如 flc / mp3 / dsf）。url 被 LMS 重写或无扩展名时兜底。
LMS_TYPE_MAP = {
    "flc": "FLAC", "flac": "FLAC",
    "wav": "WAV / PCM", "aif": "AIFF / PCM", "aiff": "AIFF / PCM",
    "pcm": "PCM", "mp3": "MP3", "ogg": "Ogg Vorbis", "oga": "Ogg Vorbis",
    "opus": "Opus", "mp4": "AAC / ALAC", "m4a": "AAC / ALAC",
    "aac": "AAC", "alc": "ALAC", "alac": "ALAC",
    "dsf": "DSD (DSF)", "dff": "DSD (DFF)", "dsd": "DSD",
    "sacd": "SACD ISO (DSD)", "ape": "Monkey's Audio",
    "wv": "WavPack", "wvp": "WavPack", "mpc": "Musepack", "wma": "WMA",
}


def _int_or_zero(v):
    try:
        return int(float(v))
    except Exception:
        return 0


def audio_spec(track):
    """从 LMS status 标签解析【源文件】音频规格（不是实际解码输出）。"""
    t = track or {}
    url = str(t.get("url") or "")
    path = url.split("#")[0].split("?")[0]
    try:
        path = urllib.parse.unquote(path)
    except Exception:
        pass
    ext = os.path.splitext(path)[1].lower()
    typ = str(t.get("type") or "").strip().lower()
    fmt = ""
    for e, label in AUDIO_FORMAT_MAP:
        if ext == e:
            fmt = label
            break
    if not fmt:
        # url 被 LMS 重写或没有扩展名时，用 LMS 的 type 字段兜底
        fmt = LMS_TYPE_MAP.get(typ, "")
    if not fmt:
        fmt = ((ext.lstrip(".").upper() + "（未知）") if ext else
               (typ.upper() + "（LMS）" if typ else "未知格式"))
    is_dsd = (ext in _DSD_EXT or fmt.startswith("DSD") or "SACD" in fmt
              or typ in ("dsf", "dff", "dsd", "sacd"))
    sr = _int_or_zero(t.get("samplerate"))
    if sr and is_dsd:
        dsd_n = max(64, int(round(sr / 2822400.0)) * 64)
        rate = "DSD%d · %.4f MHz" % (dsd_n, sr / 1000000.0)
    elif sr:
        rate = "%.1f kHz" % (sr / 1000.0)
    else:
        rate = "—"
    if is_dsd:
        bits = "1 bit"
    else:
        ss = str(t.get("samplesize") or "").strip()
        bits = (ss if ss.lower().endswith("bit") else ss + " bit") if ss else "—"
    size = _int_or_zero(t.get("filesize"))
    try:
        dur = float(t.get("duration") or 0)
    except Exception:
        dur = 0.0
    kbps = int(size * 8 / dur / 1000) if size > 0 and dur > 1 else 0
    rep_rate = str(t.get("bitrate") or "").strip()
    if rep_rate and rep_rate not in ("0", "-1", "0kbps", "0 kbps"):
        # LMS 报告值优先（如 "815kbps VBR"），比按文件大小推算更准确
        bitrate = rep_rate
    elif kbps >= 1000:
        bitrate = "%.2f Mbps" % (kbps / 1000.0)
    elif kbps:
        bitrate = "%d kbps" % kbps
    else:
        bitrate = "—"
    return {"format": fmt, "rate": rate, "rate_hz": sr, "bits": bits,
            "bitrate": bitrate, "is_dsd": is_dsd, "ext": ext,
            "filesize": size, "duration": dur}


def parse_sl_output(line, state=None):
    """解析 squeezelite -d output=info 日志，得到【实际解码/输出】状态。"""
    s = dict(state or {})
    s.setdefault("rate", 0)
    s.setdefault("dsd", 0)
    s.setdefault("format", "")
    s.setdefault("converted", False)
    s.setdefault("note", "")
    low = str(line)
    m = re.search(
        r"DSD[ ]*([0-9]+)[ ]+stream,[ ]*format:[ ]*([^,]+),[ ]*rate:[ ]*([0-9]+)[ ]*Hz",
        low, re.I)
    if m:
        s["dsd"] = int(m.group(1))
        s["format"] = "DSD" + m.group(1)
        s["rate"] = int(m.group(3))
        s["converted"] = False
        s["note"] = m.group(2).strip()
        return s, True
    m = re.search(r"track start sample rate:[ ]*([0-9]+)", low, re.I)
    if m:
        s["rate"] = int(m.group(1))
        s["dsd"] = 0
        s["format"] = "PCM"
        s["converted"] = False
        return s, True
    m = re.search(r"sample rate:[ ]*([0-9]+)", low, re.I)
    if m:
        s["rate"] = int(m.group(1))
        return s, True
    if "converting to PCM" in low:
        s["converted"] = True
        s["note"] = "设备不支持该 DSD 速率，已转换为 PCM"
        return s, True
    if "not supported" in low and "sample rate" in low:
        s["converted"] = True
        s["note"] = "采样率不受输出设备支持"
        return s, True
    if "rates differ" in low:
        s["converted"] = True
        s["note"] = "相邻曲目采样率不同，已跳过淡入淡出"
        return s, True
    return s, False


def fmt_sl_rate(hz):
    hz = int(hz or 0)
    if not hz:
        return "—"
    if hz >= 1000000:
        return "%.4f MHz" % (hz / 1000000.0)
    return "%.1f kHz" % (hz / 1000.0)


def audio_link_verdict(spec, st, sl, app_owned):
    """直通判定，返回 (等级, 标题, 说明)；等级 ok / warn / unknown。"""
    src_rate = int(spec.get("rate_hz") or 0)
    try:
        vol = int(float(st.get("volume")))
    except Exception:
        vol = 100
    rate = st.get("rate", 1)
    out = dict(sl or {})
    out_rate = int(out.get("rate") or 0)
    converted = bool(out.get("converted"))
    if converted:
        return ("warn", "已转码 / 重采样",
                out.get("note") or "squeezelite 输出日志显示格式或采样率发生了变化")
    if out_rate and src_rate and out_rate != src_rate:
        return ("warn", "已重采样",
                "源 %s → 实际输出 %s" % (fmt_sl_rate(src_rate), fmt_sl_rate(out_rate)))
    if out_rate and src_rate and out_rate == src_rate:
        same = "输出采样率与源文件一致（%s）" % fmt_sl_rate(out_rate)
    elif out_rate:
        same = "实际输出采样率 %s" % fmt_sl_rate(out_rate)
    else:
        same = "未读到 squeezelite 实际输出采样率"
    if vol != 100:
        _clr = ("输出采样率与源文件一致，未发现转码；"
                if out_rate and src_rate and out_rate == src_rate else "")
        return ("warn", "数字音量介入",
                _clr + "LMS 音量为 %s（非 100），会改动 PCM 数据，非 bit-perfect" % vol)
    try:
        rate_f = float(rate)
    except Exception:
        rate_f = 1.0
    if rate_f != 1.0:
        return ("warn", "非 1 倍速播放", "播放速率 %s，非正常直通" % rate)
    if out_rate and src_rate and out_rate == src_rate:
        return ("ok", "完美直通（bit-perfect）",
                "%s · 音量 100 · 1 倍速（依据 squeezelite 输出日志）" % same)
    if out_rate:
        return ("ok", "未发现转码迹象",
                "%s · 音量 100 · 1 倍速（源采样率未由 LMS 报告）" % same)
    return ("unknown", "待确认（以播放器输出为准）",
            "%s；%s" % (same,
              "播放器未开启 output 日志时，仅能显示 LMS 提供的源文件规格"
              if app_owned else
              "播放器未由本 APP 启动，无法读取 squeezelite 实际输出"))


def bio_cache_load():
    try:
        with open(BIO_CACHE_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def bio_cache_save(d):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = BIO_CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, BIO_CACHE_PATH)
        try:
            os.chmod(BIO_CACHE_PATH, 0o600)
        except Exception:
            pass
    except Exception:
        pass


def wiki_extract(title, lang="zh"):
    if not title:
        return ""
    host = "zh.wikipedia.org" if lang == "zh" else "en.wikipedia.org"
    q = urllib.parse.urlencode({
        "action": "query", "prop": "extracts", "exintro": "1",
        "explaintext": "1", "format": "json", "redirects": "1",
        "titles": title})
    url = "https://%s/w/api.php?%s" % (host, q)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _WIKI_UA})
        with urllib.request.urlopen(req, timeout=7) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        pages = ((d.get("query") or {}).get("pages") or {})
        for pg in pages.values():
            txt = str(pg.get("extract") or "").strip()
            if len(txt) >= 40:
                return txt
    except Exception:
        pass
    return ""


# v1.5.1：MAI 插件命令可用性缓存。插件未安装时 LMS 会断开连接，
# 一旦探测到断连就不再重复发起，避免每切一首歌都重试。
_MAI_STATE = {"checked": False, "ok": False}


def mai_rpc(cfg, args, timeout=6, _id=45):
    """调用 LMS 端 Music & Artist Information 插件的 CLI：musicartistinfo <子命令>。

    正确命令是 musicartistinfo biography / albumreview / lyrics / artistphoto…
    （旧版误用 artistinfo / albuminfo，LMS 不认识该命令会直接断连）。
    插件未安装、命令失败或 LMS 断连一律返回空字典，由调用方自动降级。
    """
    if cfg.get("bio_lms_plugin") is False:
        return {}
    if _MAI_STATE["checked"] and not _MAI_STATE["ok"]:
        return {}
    try:
        r = lms_rpc(cfg, ["musicartistinfo"] + [str(a) for a in args],
                    timeout=timeout, _id=_id)
    except Exception:
        _MAI_STATE.update(checked=True, ok=False)
        return {}
    _MAI_STATE.update(checked=True, ok=True)
    return r if isinstance(r, dict) else {}


def _mai_text(s):
    """MAI 返回的长文本可能夹带 HTML 标签 / 实体，统一清洗为纯文本。"""
    s = str(s or "")
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = html.unescape(s).replace("\u00a0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n[ \t]*\n[ \t]*\n+", "\n\n", s)
    return s.strip()


def lms_plugin_bio(cfg, kind, name, extra=""):
    """从 LMS 的 Music & Artist Information 插件取歌手简介 / 专辑评论。

    kind="artist" -> musicartistinfo biography artist:<name>
    kind="album"  -> musicartistinfo albumreview artist:<extra> album:<name>
    未命中或插件不可用时返回空串，交由 bio_fetch 回退维基百科。
    """
    name = str(name or "").strip()
    if not name:
        return ""
    if kind == "artist":
        r = mai_rpc(cfg, ["biography", "artist:" + name], timeout=6)
        txt = _mai_text(r.get("biography"))
    else:
        artist = str(extra or "").strip()
        args = ["albumreview"]
        if artist:
            args.append("artist:" + artist)
        args.append("album:" + name)
        r = mai_rpc(cfg, args, timeout=6)
        txt = _mai_text(r.get("albumreview"))
    return txt if len(txt) >= 40 else ""


def lms_mai_lyrics(cfg, track):
    """从 LMS 端 MAI 插件取歌词（实测多为纯文本，无 [mm:ss.xx] 时间轴）。"""
    t = track or {}
    tid = str(t.get("id") or "").strip()
    url = str(t.get("url") or "").strip()
    title = str(t.get("title") or "").strip()
    artist = str(t.get("artist") or "").strip()
    cmds = []
    if tid:
        cmds.append(["lyrics", "track_id:" + tid])
    if url:
        cmds.append(["lyrics", "url:" + url])
    if title:
        cmds.append(["lyrics", "artist:" + artist, "title:" + title])
    for args in cmds:
        r = mai_rpc(cfg, args, timeout=5, _id=46)
        txt = _mai_text(r.get("lyrics"))
        if txt:
            return txt, "LMS · Music & Artist Information"
    return "", ""


def bio_fetch(cfg, artist, album="", force=False):
    """返回 (artist_text, album_text, src_label)；结果带本地缓存。"""
    artist = str(artist or "").strip()
    album = str(album or "").strip()
    key = "%s|%s" % (artist, album)
    cache = bio_cache_load()
    if not force and key in cache:
        v = cache[key]
        return v.get("artist", ""), v.get("album", ""), v.get("src", "")
    a_txt = lms_plugin_bio(cfg, "artist", artist)
    b_txt = lms_plugin_bio(cfg, "album", album, artist)
    a_src = "LMS · Music & Artist Information" if a_txt else ""
    b_src = "LMS · Music & Artist Information" if b_txt else ""
    if not a_txt:
        for lang in ("zh", "en"):
            a_txt = wiki_extract(artist, lang)
            if a_txt:
                a_src = "维基百科（%s）" % ("中文" if lang == "zh" else "英文")
                break
    if not b_txt and album:
        for lang in ("zh", "en"):
            b_txt = wiki_extract(album, lang)
            if b_txt:
                b_src = "维基百科（%s）" % ("中文" if lang == "zh" else "英文")
                break
    src = " · ".join(x for x in (a_src, b_src) if x) or "暂无在线简介"
    cache[key] = {"artist": a_txt[:2000], "album": b_txt[:2000], "src": src}
    if len(cache) > 300:
        for k in list(cache.keys())[:-300]:
            cache.pop(k, None)
    bio_cache_save(cache)
    return cache[key]["artist"], cache[key]["album"], src


HELP_TEXT = """Squeezelite GUI · 使用说明
界面：顶栏右侧「浅色 / 深色 / 跟随系统」分段按钮可直接切换主题，
跟随系统会自动检测 macOS / Linux / Windows 的明暗外观并实时切换
（Lyrion Material 风格）；
参数配置页、设备列表、版本列表、音乐库均支持鼠标滚轮上下滚动。

【正在播放】（v1.3.0 起，v1.5.0 增强）
  先在「升级与更新」页填好 LMS 服务器地址；若 LMS 启用了密码保护
  （Basic Auth），还需在同一页填写用户名/密码，仅设置密码时用户名留空。
  曲目信息、专辑封面来自 LMS；本页不读本机音乐目录、不依赖任何挂载点。
  歌词优先级：LMS 内嵌歌词（songinfo tags:w）→ LMS 端 Music & Artist
  Information 插件（musicartistinfo lyrics）→ 在线歌词库（LRCLIB / 网易云，
  带本地缓存）→ 手动载入本地 LRC。带 [mm:ss.xx] 时间轴的歌词会随播放
  进度逐行高亮；插件歌词实测多为纯文本无时间轴，故默认仍优先带时间轴的
  在线 LRC，插件歌词作为不走公网的兜底。若希望完全从 LMS 取歌词，
  可在 config.json 设 lyrics_prefer_lms: true（会失去逐行高亮）。
  右侧可切换「歌词 / 专辑详情 / 歌手 / 专辑简介」三个视图：
    · 歌词：LRC 时间轴随播放进度逐行高亮；「重新搜索在线歌词」忽略缓存重试；
    · 专辑详情：LMS 返回的流派、年份、音轨号、比特率、采样率、路径等全部标签；
    · 歌手 / 专辑简介：专辑元信息始终取自 LMS 标签；歌手简介优先取自 LMS 的
      Music & Artist Information 插件（musicartistinfo biography），专辑评论
      取自 musicartistinfo albumreview，任一未命中时回退维基百科中 / 英文 API。
      结果缓存在 ~/.squeezelite_gui/bio_cache.json，可点「重新获取简介」强制
      刷新。插件命令失败或未安装时自动降级，不会断连；如需彻底跳过插件，
      在 config.json 设 bio_lms_plugin: false。
  本架构无法提供真实 FFT 频谱：PCM 由 LMS 经 Slimproto(3483) 直送
  squeezelite，不经过本 APP，macOS 也无原生回环采集设备；因此已移除
  原有的装饰性节奏动画视图，改为上述简介视图。
  遥控端（手机 / 网页）发起播放后，本页会自动更新，无需在此点播。

【音频链路 / 完美直通判定】（v1.5.0）
  正在播放页顶部「音频链路」卡片显示当前曲目的源格式（FLAC / WAV /
  DSD / PCM / MP3 / AAC 等）、采样率、位深与码率，取自 LMS 的
  status / songinfo 标签；DSD 另按 DSF / DFF 后缀与 DSD 速率标注。
  请求已按真实 LMS 补齐 I(位深) / r(码率) / o(格式类型) 标签，
  位深与码率优先用 LMS 报告值，缺失时才按文件大小与时长推算。
  通过本 APP「▶ 启动」播放器时会自动追加 -d output=info，从 squeezelite
  日志解析实际输出采样率、DSD 封装（DoP / native）与「converting to
  PCM」等转换提示；再结合源 / 输出采样率、LMS 音量与播放速率，给出
  「完美直通（bit-perfect）/ 未发现转码迹象 / 已转码 / 已重采样 /
  数字音量介入 / 非 1 倍速 / 待确认」判定。
  若播放器并非由本 APP 启动（独立遥控端或外部 squeezelite 进程），
  无法读取其输出日志，卡片只显示 LMS 提供的源文件规格并标注「待确认」。
  要真正做到 bit-perfect，LMS 端还需关闭该播放器的「音量固定 /
  比特率限制 / 转码」，并使用无损音源。

【专注大屏】（v1.5.0）
  点正在播放页「⛶ 进入专注大屏」或视图栏「⛶ 专注大屏」进入全屏：
  大尺寸正方形封面、大字歌词、曲目信息与播放进度 / 控制。按 ESC 退出；
  移动鼠标会浮出「✕ 退出专注模式」按钮，静止约 3 秒后自动隐藏；
  大屏配色随主窗口的浅色 / 深色 / 跟随系统主题同步刷新。

【音乐库】（v1.4.0 起，v1.5.0 统一封面）
  可按专辑 / 艺术家 / 曲目 / 流派 / 播放列表分页浏览，输入关键词后
  回车或点「搜索」走 LMS 的 search: 过滤；列表带封面缩略图，
  选中一项右侧卡片显示大封面、标题与 LMS 返回的全部标签。
  双击专辑 / 艺术家 / 流派（或点「查看曲目」）进入下一级浏览，
  顶部面包屑「← 返回」逐级回退；专辑内「▶ 播放整张专辑」可整张点播。
  曲目双击、或选中后点「▶ 播放此项」，通过
  playlistcontrol cmd:load 发送到当前播放器（需先在「正在播放」页选定）。
  所有请求自动携带 LMS 的用户名/密码。
  v1.5.0 起专辑与曲目封面缩略图、详情大封面统一按正方形等比缩放后
  居中补边输出，不再出现大小不一或变形。

================================================================================

【快速开始】
  1. 「设备与名称」：程序启动会自动扫描音频输出设备，选中一个即自动生成 LMS 端显示名。
     找不到设备时：点「指定 squeezelite 路径」或到「升级与更新」页安装；也可手动添加 -o 名。
  2. 「参数配置」：每个参数都有下拉预设、文本框（可填自定义值）、? 详细说明与 ★ 最优音质推荐。
     点击顶部「一键应用最优音质方案」即可套用 bit-perfect 配置。
  3. 「启动控制」：确认命令无误后点「▶ 启动」，运行日志实时显示；可保存 .command 或安装 LaunchAgent。
  4. 「升级与更新」：填 LMS 服务器地址 → 点「检查更新」，即可看到客户端/服务端版本与升级内容。

【播放器命名规则】
  本机名称 + 音频设备简称，模板默认 "{host} - {short}"，可自定义变量。
  简称自动生成：Built-in Output → BuiltIn，USB Audio DAC → USBDac，HDMI → HDMI …
  该名称通过 -n 传给 squeezelite，LMS「播放器」列表即显示为此名。
  注意 -n 与 -N（允许服务端改名）互斥，请勿同时启用。

【最优音质 / bit-perfect 要点】
  · -a 100:0   macOS 专有：Pro Mode 独占设备，绕过 CoreAudio 混音与采样率转换（最关键）
  · -r 44100-384000  声明全采样率，避免 LMS 端重采样
  · 不启用 -u/-R（SoX 重采样）、-v（可视化）、-W（忽略服务端参数）
  · -b 8192:8192  大缓冲抗网络抖动（不改变音频数据）
  · -C 不设置  设备常开，避免反复重新协商时钟
  · 还必须在 LMS 服务端关闭该播放器的「音量固定 / 比特率限制 / 转码」，并使用无损音源

【升级内容 / 数据来源（均可在配置里自定义 URL，失败自动降级）】
  参数说明     https://ralph-irving.github.io/squeezelite.html   （官方 manpage 2025-10-10）
  LMS 版本库   https://lyrion.org/lms-server-repository/servers.json
                 latest=正式版 / 9.1.2=稳定夜版 / 9.2.0=开发版，含 macOS .dmg 直链与 revision
  LMS 当前版本 JSON-RPC  POST http://<host>:9000/jsonrpc.js
                 {"id":1,"method":"slim.request","params":[0,["version","?"]]}
  Squeezelite   https://sourceforge.net/projects/lmsclients/files/squeezelite/osx/{m1,intel}/
                 文件名含版本+revision，如 squeezelite-2.0.0.1465-osx-intel.tar.gz
                 升级前会自动备份旧二进制到 ~/.squeezelite_gui/backups/
  升级内容     GitHub commits Atom feed（无需 API 令牌、可达性最好）：
                 https://github.com/ralph-irving/squeezelite/commits/master.atom
                 https://github.com/LMS-Community/slimserver/commits/public/9.1.atom
                 若 api.github.com 可达则自动改用 API 获取更完整的提交信息
  Homebrew     macOS 第三方 tap：brew install tsirysndr/tap/squeezelite
                 （homebrew-core 无 squeezelite 官方 formula）

【常见问题】
  · 找不到设备：确认 squeezelite 已安装且有执行权限；macOS 上会额外用
    system_profiler SPAudioDataType -json 枚举设备作为补充。
  · 启动报「URL/设备名含空格」：本工具用参数数组传参，不会做 shell 拼接，空格安全。
  · Pro Mode 下其它 App 没声音：这是独占（hog mode）的正常表现，改 -a 100:1 可共享但音质有损。
  · api.github.com 403：工具会自动降级到 Atom feed 与 SourceForge，不影响升级提示。
  · LMS 检查失败：确认地址/端口（默认 9000）以及 LMS 的 JSON-RPC 接口可访问。
  · 本工具只提示并下载 LMS 安装包，不自动替换服务端（服务端可能在另一台机器）。

【文件位置】
  配置   ~/.squeezelite_gui/config.json
  缓存   ~/.squeezelite_gui/update_cache.json
  备份   ~/.squeezelite_gui/backups/
  自启   ~/Library/LaunchAgents/com.squeezelite.gui.plist
"""


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
