# Squeezelite GUI（macOS）

一个零第三方依赖的 macOS 图形化控制台，用于配置、启动与升级
[Squeezelite](https://github.com/ralph-irving/squeezelite) 播放器，
并查询 Lyrion Media Server (LMS) 服务端版本更新。

> **非官方项目**，与 Lyrion / Squeezelite / Logitech 无隶属或背书关系。

## 功能

- 启动自动扫描音频输出设备并手动选择
- 27 项参数：下拉选项、可选参数、逐项效果说明、最优音质推荐，
  并支持自定义值与范围校验
- 播放器显示名 = 本机名称 + 音频设备简称（通过 `-n` 传给 LMS 服务端）
- 联网升级 Squeezelite（SourceForge 官方 macOS 二进制 / Homebrew），
  检查 LMS 服务端版本更新并提示，标注升级内容（GitHub commit 日志）
- 配置保存在 `~/.squeezelite_gui/`，升级前自动备份旧二进制

## 仓库内容（仅源码，不含任何二进制）

| 文件 | 说明 |
| --- | --- |
| `squeezelite_gui.py` | GUI 主程序，tkinter 单文件、仅 Python 标准库 |
| `build_app.sh` | macOS 一键封装脚本，生成自包含 `.app` |
| `Squeezelite-GUI.command` | macOS 双击启动脚本 |
| `LICENSE` | 原创代码许可（MIT） |
| `THIRD_PARTY_NOTICES.md` | 第三方组件许可与分发义务 |

**本仓库不提供、也不包含** squeezelite 可执行文件、Python 运行时、
Tcl/Tk 或任何 `.app` 构建产物。请自行从官方渠道获取 squeezelite，
或从本机已有二进制构建。

## 在本机构建自包含 .app

前置：macOS（Apple Silicon / Intel）、一份 squeezelite 可执行文件、
带 tkinter 且 Tk ≥ 8.6 的 Python 3。

```bash
git clone <your-repo-url>
cd squeezelite-gui
SL_BIN=/path/to/squeezelite bash build_app.sh
```

脚本生成 `~/Applications/Squeezelite GUI.app`，内置 Python/Tk 运行时、
GUI 与 squeezelite，双击即用。旧同名应用会被改名隔离备份而非删除。
可选：在仓库目录放一份**原创** `app.icns`，构建时自动作为应用图标
（脚本不会从 macOS 系统目录复制任何图标）。

> 使用系统自带 `/usr/bin/python3`（Python 3.9 + Tk 8.5）会出现窗口
> 内容全白 —— 该 Tk 已被 macOS 弃用。请改用 `.app` 内置运行时或
> 安装带 Tk 8.6+ 的 Python。

## 许可

本仓库原创代码采用 **MIT**（见 `LICENSE`，版权人可改为您的名字）。
第三方组件各有其许可，其中 **Squeezelite 为 GPL-3.0-or-later**；
**分发构建产物时必须履行相应义务**，详见 `THIRD_PARTY_NOTICES.md`。

本 GUI 与 squeezelite 仅为命令行调用关系（mere aggregation），因此
原创代码可以选择 MIT；若您希望与上游保持一致，也可改用 GPLv3。

## 免责

按「现状」提供，不保证适配所有音频设备。参数效果说明依据官方 manpage
整理，使用前请自行核对。详见 `LICENSE` 的免责条款。
