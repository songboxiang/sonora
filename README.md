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
- **Lyrion Material 风格界面**：亮 / 暗双主题（顶栏一键切换），配色取自
  LMS Material Skin 官方 Lyrion 色板；参数页支持鼠标滚轮滚动
- **原创应用图标**：`assets/logo.svg` + `assets/app.icns`（Material 圆角方形 +
  浮动操作按钮 + 声波弧线），非 Apple 系统资源，可随应用分发
- 配置保存在 `~/.squeezelite_gui/`，升级前自动备份旧二进制
- **「正在播放」看板**（v1.2.0）：自动跟随 LMS 播放器状态，显示曲目信息、
  专辑封面与歌词；歌词由 LMS 服务端提供（`songinfo tags:w`），不依赖本地
  音乐目录或挂载点，支持 LRC 时间轴逐行同步

## 正在播放与歌词来源

在「升级与更新」页填好 LMS 服务器地址后，打开「正在播放」页会自动列出
LMS 上的播放器；选中后即开始跟随其状态。本页只读写 LMS 的 JSON-RPC 接口
（`serverstatus` / `status` / `songinfo` / `playlist`），音频仍由 squeezelite
通过 Slimproto 输出，两条通道互不影响 —— 因此即使未点「启动」，只要 LMS
在线，本页也能显示其他遥控端发起的播放。

歌词**完全从 LMS 端获取**：优先 `songinfo ... tags:w`（LMS 扫描曲目时入库的
内嵌歌词），失败回落 `status tags:w`。因此 LMS 部署在独立服务器、曲库路径
无法从本机访问时同样可用。若曲库中没有内嵌歌词，可用「手动载入本地 LRC…」
按钮临时补充；带 `[mm:ss.xx]` 时间轴的歌词会随播放进度逐行高亮。

专辑封面请求 LMS 的 `/music/<coverid>/cover_300x300.jpg` 或 `artwork_url`，
解码为 PNG 后显示。解码按「LMS 已返回 PNG → macOS `sips` → Pillow →
ffmpeg」逐级降级，全部为可选路径：`.app` 内置运行时不依赖 Pillow，最差
情况仅显示文字占位符，不影响其他功能。

LMS 若启用密码保护，可在 `~/.squeezelite_gui/config.json` 中填写
`lms_user` / `lms_pass`（可选，文件权限 600）。

## 仓库内容（仅源码，不含任何二进制）

| 文件 | 说明 |
| --- | --- |
| `squeezelite_gui.py` | GUI 主程序，tkinter 单文件、仅 Python 标准库 |
| `build_app.sh` | macOS 一键封装脚本，生成自包含 `.app` |
| `Squeezelite-GUI.command` | macOS 双击启动脚本 |
| `assets/logo.svg` | 原创图标矢量源（Lyrion Material 风格） |
| `assets/app.icns` | 由 `assets/make_icon.py` 生成的 macOS 应用图标 |
| `assets/make_icon.py` | 图标生成脚本（仅设计阶段需要 Pillow） |
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
默认使用仓库内 `assets/app.icns`（本项目原创 logo）。脚本不会从 macOS
系统目录复制任何 Apple 图标；如需换图标，可替换 `assets/app.icns` 或在
仓库根目录另放一份自备原创 `app.icns`。

> 使用系统自带 `/usr/bin/python3`（Python 3.9 + Tk 8.5）会出现窗口
> 内容全白 —— 该 Tk 已被 macOS 弃用。请改用 `.app` 内置运行时或
> 安装带 Tk 8.6+ 的 Python。

## 许可

本仓库原创代码采用 **MIT**（见 `LICENSE`，版权人可改为您的名字）。
第三方组件各有其许可，其中 **Squeezelite 为 GPL-3.0-or-later**；
**分发构建产物时必须履行相应义务**，详见 `THIRD_PARTY_NOTICES.md`。

本 GUI 与 squeezelite 仅为命令行调用关系（mere aggregation），因此
原创代码可以选择 MIT；若您希望与上游保持一致，也可改用 GPLv3。
`assets/` 下的图标、SVG 与生成脚本同样属原创代码，随 MIT 许可授予。

## 免责

按「现状」提供，不保证适配所有音频设备。参数效果说明依据官方 manpage
整理，使用前请自行核对。详见 `LICENSE` 的免责条款。
