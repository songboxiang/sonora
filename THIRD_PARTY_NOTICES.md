# 第三方组件与许可声明 / Third-Party Notices

本仓库**只含原创源码**，不含任何第三方二进制。但 `build_app.sh` 在本机
生成的 `Squeezelite GUI.app` 会捆绑下列组件。**只使用源码、不分发构建产物
时，以下分发义务不适用于您**；若把 `.app` 上传或分发给他人，必须履行
对应义务。

## 1. Squeezelite —— GPL-3.0-or-later（最需要注意）

- 本机二进制：`Squeezelite 2.0.0-1584`（arm64），来自官方 SourceForge
  <https://sourceforge.net/projects/lmsclients/files/squeezelite/osx/m1/>
- 许可：GNU General Public License v3 或更高版本；
  Copyright 2012-2015 Adrian Smith, 2015-2026 Ralph Irving。
  执行 `squeezelite -t` 会输出完整许可声明。
- 源码：<https://github.com/ralph-irving/squeezelite>；
  捆绑的第三方库源码与补丁：
  <https://sourceforge.net/projects/lmsclients/files/source/>
- 内含的独立许可组件：FFmpeg 库（LGPL-2.1）、OpenSSL（GPLv3 §7 附加
  许可）、dsd2pcm（© 2009, 2011 Sebastian Gesemann，自有许可）、
  Daphile full dsd patch（© 2013-2017 Daphile，自有许可）、
  `-W` 服务端上采样补丁（© 2015 Marco Curti，自有许可）。
- **分发二进制时的义务（GPLv3 §6）**：随附 GPLv3 许可证全文；提供
  Corresponding Source（源码，或明确且至少三年有效的书面获取要约，
  并须与所分发二进制版本精确对应）；保留全部版权与免责声明；不得对
  接收者行使 GPL 所赋权利施加额外限制。
- 本 GUI 通过命令行以 `subprocess` 调用**独立的** squeezelite 进程，
  属于 GPL FAQ 所述 "mere aggregation"（同一介质上的独立程序），不会
  因此使本仓库原创代码自动变为 GPL；但整个 bundle 中的 squeezelite
  部分仍必须满足上述义务，且不可把整个 `.app` 声明为纯 MIT 并限制
  接收者权利。

## 2. CPython 3.13 —— PSF License v2

- 来源：本机 Python 3.13.12 运行时（python-build-standalone 构建），
  由 `build_app.sh` 复制到 `.app/Contents/Resources/python`。
- 许可：Python Software Foundation License Version 2（BSD 类、GPL 兼容）。
  允许再分发（含二进制与商业用途），须保留 PSF 许可协议与版权声明
  `Copyright © 2001 Python Software Foundation; All Rights Reserved`；
  若修改了 Python 本身并分发，需附变更摘要；不得使用 PSF 商标背书。
- 完整许可文本随运行时提供：`python/lib/python3.13/LICENSE.txt`。
  该发行版还内含 OpenSSL、libffi、zlib、xz、bzip2、SQLite、expat、
  ncurses/readline 等库，各自许可见该 LICENSE.txt 与
  python-build-standalone 项目的许可清单；分发 `.app` 时须一并保留。

## 3. Tcl/Tk 9 —— Tcl/Tk License（BSD 风格）

- 来源：随上述 Python 运行时复制（`python/lib/tcl9.0`、`tk9.0`）。
- 许可：Copyright © Regents of the University of California,
  Sun Microsystems, Inc., Scriptics Corporation 及其他贡献者。
  允许为任何目的使用、复制、修改、分发，**须在所有副本中保留现有
  版权声明，并在任何分发中原样包含该许可文本**（`license.terms`）。
  修改部分可由修改者另行许可，但需在文件首页明确标示。

## 4. 随运行时附带的 Python 第三方包

`site-packages` 内含 requests、urllib3、certifi、charset_normalizer、
idna、flask、jinja2、click、werkzeug、markupsafe、itsdangerous、
blinker、PyYAML、pip 等（版本见各 `.dist-info/METADATA`）。许可涵盖
Apache-2.0、MIT、MPL-2.0、BSD-3-Clause、ISC 等宽松许可。分发 `.app`
时应保留各包 `.dist-info` 内的 LICENSE / METADATA 许可声明。

## 5. 应用图标与 UI 配色 —— 本项目原创

`assets/logo.svg` 与 `assets/app.icns` 是本项目原创设计的图标
（Material 圆角方形 + 浮动操作按钮 + 声波弧线），由 `assets/make_icon.py`
生成，随 MIT 许可一并授予，**不含任何 Apple 系统资源**。
`make_icon.py` 仅在设计阶段需要 Pillow；最终用户只需现成的 `.icns`。

早期 `build_app.sh` 曾从 macOS `CoreTypes.bundle` 复制 Apple 通用应用图标，
该系统资源受 macOS SLA 约束、不可再分发，现已彻底移除。

界面配色参考 LMS Material Skin 的官方 Lyrion 色板
（`css/colors/lyrion.css`、`css/themes/light.css`、`css/themes/dark-lyrion.css`，
MIT 许可）。色值属于事实性数据，本项目仅借用配色与视觉语言，未复制其
代码、图标或文案；GUI 代码与图标均为原创。

## 6. 外部数据、文档与商标

- 参数说明依据官方 manpage
  <https://ralph-irving.github.io/squeezelite.html>，仅引用参数名、
  取值与作用等事实性信息，未复制原文段落。
- LMS 版本数据来自 lyrion.org / lms-server-repository 与 LMS JSON-RPC；
  Squeezelite 发布信息来自 SourceForge 与 GitHub。这些均为运行时联网
  读取的数据，不随本仓库分发。
- Lyrion / Squeezelite / Logitech 等名称与商标归各自权利人所有。本项目
  为**非官方**第三方工具，与上述项目无隶属、授权或背书关系。
