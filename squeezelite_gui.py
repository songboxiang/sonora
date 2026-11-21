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

数据来源（均可自定义/降级）：
  - 参数说明：官方 manpage https://ralph-irving.github.io/squeezelite.html (2025-10-10)
  - LMS 版本库：https://lyrion.org/lms-server-repository/servers.json
  - LMS 当前版本：JSON-RPC  POST /jsonrpc.js  {"params":[0,["version","?"]]}
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

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext, font as tkfont

VERSION = "1.1.0"
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
    "light": {
        "primary": "#589e81", "primary_dark": "#3f7a61", "on_primary": "#ffffff",
        "app_bar": "#589e81", "on_app_bar": "#ffffff", "accent": "#6cac92",
        "bg": "#fafafa", "surface": "#ffffff", "surface2": "#f1f5f3",
        "border": "#dfe6e3", "divider": "#e8eeeb",
        "text": "#1f2926", "text2": "#5f6b67", "text3": "#8a9792",
        "link": "#0a5ca8", "ok": "#2e7d5b", "warn": "#9a6410", "err": "#c0392b",
        "sel": "#dcefe7", "sel_text": "#12352a", "row_alt": "#f4f8f6",
        "scroll": "#c2cdc9", "scroll_active": "#589e81",
        "terminal_bg": "#12211f", "terminal_fg": "#dceae5", "code_bg": "#f1f5f3",
    },
    "dark": {
        "primary": "#589e81", "primary_dark": "#6cac92", "on_primary": "#ffffff",
        "app_bar": "#0d292d", "on_app_bar": "#e3fdc4", "accent": "#e3fdc4",
        "bg": "#081f22", "surface": "#0d292d", "surface2": "#123338",
        "border": "#20454a", "divider": "#1a3b3f",
        "text": "#e6f0ec", "text2": "#9fb4ae", "text3": "#78918a",
        "link": "#8fd0b4", "ok": "#8fd6ae", "warn": "#e0be6a", "err": "#ef8f80",
        "sel": "#1d4d47", "sel_text": "#e3fdc4", "row_alt": "#103035",
        "scroll": "#2b5054", "scroll_active": "#6cac92",
        "terminal_bg": "#06171a", "terminal_fg": "#d5e8e1", "code_bg": "#0d292d",
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
    "install_method": "auto",
    "brew_formula": "tsirysndr/tap/squeezelite",
    "sources": {},
    "auto_scan": True,
    "auto_upgrade_check": False,
    "audio_preset": "best",
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
        ("127.0.0.1:9000", "本机 127.0.0.1:9000", "LMS 与播放器在同一台 Mac 时使用，连接最稳"),
        ("{LMS_HOST}", "使用「升级」页填写的服务器地址", "自动填入 LMS 主机:端口，避免两处重复维护"),
     ],
     "effect":"决定播放器连接哪台 LMS；留空则由 squeezelite 自动发现。",
     "detail":"格式 host[:port]，端口默认 9000。自动发现依赖 UDP 3483，跨 VLAN/路由器时通常无效，此时必须手动指定。",
     "range":"IP / 主机名 [ :端口 ]，如 192.168.1.10:9000；留空=自动发现"},

    {"key":"name","flag":"-n","name":"播放器名称 (-n)","group":"连接","platform":"all","kind":"text",
     "default":"","recommend":"",
     "options":[("", "由「设备与名称」页自动生成", "自动使用『本机名称 + 音频设备简称』，切换设备时自动更新")],
     "effect":"LMS 服务端「播放器」列表里显示的名字；本工具按所选设备自动生成。",
     "detail":"与 -N（允许服务端改名）互斥。名称会随所选输出设备变化，例如 Song-Mac - USBDAC，便于在多房间/多设备环境辨认。",
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
    """把 9.1.1 / 2.0.0.1465 / 9.1.2 - 1792854063 转成可比较元组。"""
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
    port = (cfg.get("lms_port") or "9000").strip()
    if host and not re.search(r":\d+$", host):
        host = host + ":" + port
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

def build_argv(cfg, values):
    binary = find_binary(cfg) or "squeezelite"
    argv = [binary]
    for p in PARAMS:
        v = values.get(p["key"], p.get("default", ""))
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

def lms_current(cfg, log=None):
    host = (cfg.get("lms_host") or "").strip()
    port = (cfg.get("lms_port") or "9000").strip()
    if not host:
        return {"ok": False, "error": "未填写 LMS 服务器地址（在「升级与更新」页设置）"}
    base = host if host.startswith("http") else "http://" + host
    if not re.search(r":\d+(?:/|$)", base):
        base = base.rstrip("/") + ":" + port
    url = base.rstrip("/") + "/jsonrpc.js"
    payload = json.dumps({"id": 1, "method": "slim.request",
                          "params": [0, ["version", "?"]]}).encode("utf-8")
    try:
        raw = http_request(url, data=payload,
                           headers={"Content-Type": "application/json"},
                           timeout=8, log=log)
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
            d = json.loads(http_request(url, data=p2,
                                        headers={"Content-Type": "application/json"},
                                        timeout=8).decode("utf-8", "replace"))
            v = (d.get("result", {}) or {}).get("version")
            if v:
                return {"ok": True, "version": str(v), "url": url, "raw": d.get("result", {})}
        except Exception:
            pass
        return {"ok": False, "error": str(e)[:150], "url": url}

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


class App(tk.Tk):
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
        self._terminal_texts = []
        self.title("%s  v%s" % (APP_NAME, VERSION))
        self.geometry("1200x820")
        self.minsize(1020, 680)
        self._init_style()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(120, self._pump)
        self._log("已启动 %s v%s | 平台 %s %s | Python %s | Tk %s" % (
            APP_NAME, VERSION, sys.platform, platform.machine(),
            platform.python_version(), tk.TkVersion))
        self._log("配置文件: %s" % CONFIG_PATH)
        self._refresh_preview()
        self._mac_render_fix()
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
    def _toggle_theme(self):
        self.theme_name = "dark" if self.theme_name == "light" else "light"
        self.cfg["theme"] = self.theme_name
        try:
            save_config(self.cfg)
        except Exception:
            pass
        self._init_style()
        self._retheme_tk(self)
        self._refresh_tree_tags()
        try:
            C = self.C
            self.theme_btn.configure(
                text="切换浅色" if self.theme_name == "dark" else "切换深色",
                background=C["app_bar"], foreground=C["on_app_bar"],
                activebackground=C["primary_dark"],
                activeforeground=C["on_app_bar"])
        except Exception:
            pass
        self._log("界面主题：%s（Lyrion Material）" % (
            "深色" if self.theme_name == "dark" else "浅色"))

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
        for t in (getattr(self, "dev_tree", None), getattr(self, "lms_tree", None)):
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
        C = self.C
        app_bar = getattr(self, "app_bar", None)
        try:
            cls = w.winfo_class()
            if cls == "Frame":
                w.configure(background=C["app_bar"] if w is app_bar else C["bg"])
            elif cls == "Label":
                bar = (w.master is app_bar)
                w.configure(background=C["app_bar"] if bar else C["bg"],
                            foreground=C["on_app_bar"] if bar else C["text"])
            elif cls == "Button":
                bar = (w.master is app_bar)
                w.configure(background=C["app_bar"] if bar else C["surface"],
                            foreground=C["on_app_bar"] if bar else C["text"],
                            activebackground=C["primary_dark"],
                            activeforeground=C["on_app_bar"],
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
        self.ui_font = (fam, 11)
        self.small_font = (fam, 9)
        self.bold_font = (fam, 11, "bold")
        self.head_font = (fam, 10, "bold")
        self.title_font = (fam, 14, "bold")
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
                        font=(fam, 10), padding=(11, 6), relief="flat",
                        borderwidth=1)
        style.map("TButton",
                  background=[("pressed", C["sel"]), ("active", C["surface2"]),
                              ("disabled", C["bg"])],
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
        style.map("TCombobox", fieldbackground=[("readonly", C["surface"])],
                  bordercolor=[("focus", C["primary"])],
                  foreground=[("disabled", C["text3"])])
        self.option_add("*TCombobox*Listbox.background", C["surface"])
        self.option_add("*TCombobox*Listbox.foreground", C["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", C["primary"])
        self.option_add("*TCombobox*Listbox.selectForeground", C["on_primary"])
        style.configure("TNotebook", background=C["bg"],
                        bordercolor=C["border"], tabmargins=(8, 8, 8, 0),
                        relief="flat")
        style.configure("TNotebook.Tab", background=C["bg"],
                        foreground=C["text2"], padding=(20, 10),
                        font=self.head_font, borderwidth=0, relief="flat")
        style.map("TNotebook.Tab",
                  background=[("selected", C["primary"]),
                              ("active", C["surface2"])],
                  foreground=[("selected", C["on_primary"]),
                              ("active", C["text"])])
        style.configure("Treeview", background=C["surface"],
                        fieldbackground=C["surface"], foreground=C["text"],
                        font=self.ui_font, rowheight=30,
                        bordercolor=C["divider"], relief="flat", borderwidth=0)
        style.configure("Treeview.Heading", background=C["surface2"],
                        foreground=C["text2"], font=self.head_font,
                        padding=(8, 9), relief="flat",
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
        style.configure("TProgressbar", background=C["primary"],
                        troughcolor=C["surface2"], bordercolor=C["surface2"],
                        lightcolor=C["primary"], darkcolor=C["primary"],
                        relief="flat")
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
        style.configure("Rec.TLabel", background=C["bg"],
                        foreground=C["ok"], font=self.small_font)
        style.configure("AppBar.TLabel", background=C["app_bar"],
                        foreground=C["on_app_bar"])
        self.configure(background=C["bg"])

    # ------------------------------------------------------------ 主框架
    def _build_ui(self):
        C = self.C
        self.app_bar = tk.Frame(self, background=C["app_bar"], height=60)
        self.app_bar.pack(fill="x")
        self.app_bar.pack_propagate(False)
        tk.Label(self.app_bar, text="Squeezelite", background=C["app_bar"],
                 foreground=C["on_app_bar"], font=(self.fam, 17, "bold")
                 ).pack(side="left", padx=(20, 8))
        tk.Label(self.app_bar, text="LMS Material 控制台",
                 background=C["app_bar"], foreground=C["on_app_bar"],
                 font=(self.fam, 10)).pack(side="left")
        self.theme_btn = tk.Button(
            self.app_bar,
            text="切换浅色" if self.theme_name == "dark" else "切换深色",
            command=self._toggle_theme, relief="flat", bd=0,
            background=C["app_bar"], foreground=C["on_app_bar"],
            activebackground=C["primary_dark"],
            activeforeground=C["on_app_bar"],
            font=(self.fam, 10), padx=14, pady=4, cursor="hand2")
        self.theme_btn.pack(side="right", padx=(6, 16))
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
        for f, t in [(self.tab_devices, "设备与名称"), (self.tab_params, "参数配置"),
                     (self.tab_launch, "启动控制"), (self.tab_update, "升级与更新"),
                     (self.tab_help, "日志 / 帮助")]:
            self.nb.add(f, text="  " + t + "  ")
        self._build_tab_params()   # 参数控件需先建立：设备页的命名会写入 -n
        self._build_tab_devices()
        self._build_tab_launch()
        self._build_tab_update()
        self._build_tab_help()
        self._refresh_tree_tags()

        foot = ttk.Frame(self, padding=(14, 8))
        foot.pack(fill="x")
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(foot, textvariable=self.status_var,
                  style="Hint.TLabel").pack(side="left")
        self.pbar = ttk.Progressbar(foot, mode="indeterminate", length=110)
        self.pbar.pack(side="left", padx=10)
        ttk.Button(foot, text="保存配置", style="Accent.TButton",
                   command=self._save_config).pack(side="right", padx=3)
        ttk.Button(foot, text="退出", command=self._on_close).pack(side="right", padx=3)
        ttk.Button(foot, text="重新生成命令", command=self._refresh_preview).pack(side="right", padx=3)

    # ------------------------------------------------------------ 日志/队列
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
                elif kind == "proc_exit":
                    self._on_proc_exit(data)
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
        self.validate_lbl = ttk.Label(bottom, text="", style="Hint.TLabel")
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
            self.validate_lbl.configure(text="⚠ 发现 %d 处问题" % len(problems), foreground=self.C["err"])
        else:
            self.validate_lbl.configure(text="✓ 全部参数取值合法", foreground=self.C["ok"])
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
                    self.validate_lbl.configure(text="⚠ " + "；".join(problems[:3]),
                                                foreground=self.C["err"])
                else:
                    self.validate_lbl.configure(text="✓ 全部参数合法 · 共 %d 个参数项" % len(argv),
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
        self.cfg["binary"] = self.binpath_var.get().strip()
        if save_config(self.cfg):
            self.status_var.set("配置已保存")
            self._log("配置已保存: %s" % CONFIG_PATH)
        else:
            self.q.put(("error", "配置保存失败"))

    def _on_close(self):
        try:
            self._save_config()
        except Exception:
            pass
        if self.proc and self.proc.poll() is None:
            if messagebox.askyesno(APP_NAME, "squeezelite 仍在运行，是否一并停止？"):
                self._stop_proc()
        self.destroy()


HELP_TEXT = """Squeezelite GUI · 使用说明
界面：顶栏可一键切换亮色 / 深色（Lyrion Material 风格）；
参数配置页、设备列表、版本列表均支持鼠标滚轮上下滚动。

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
