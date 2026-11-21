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
- **Lyrion Material 风格界面**：浅色 / 深色 / 跟随系统三态（顶栏下拉），
  配色取自官方 Lyrion Material Skin；跟随系统会自动检测 macOS / Linux /
  Windows 的明暗外观并实时切换。
- **原创应用图标**：`assets/logo.svg` + `assets/app.icns`（Material 圆角方形 +
  浮动操作按钮 + 声波弧线），非 Apple 系统资源，可随应用分发
- 配置保存在 `~/.squeezelite_gui/`，升级前自动备份旧二进制
- **「正在播放」看板**（v1.3.0）：跟随 LMS 播放器状态，展示大尺寸专辑
  封面、曲目信息、进度与「歌词 / 专辑详情 / 可视化」三视图；歌词优先取
  LMS 内嵌歌词，未命中时自动走在线歌词库（LRCLIB / 网易云，带缓存），
  不依赖 LMS 插件、本地音乐目录或挂载点，支持 LRC 时间轴逐行同步
- **音乐库（阶段 2）**（v1.3.0，v1.4.0 增强）：分页浏览专辑 / 艺术家 /
  曲目 / 流派 / 播放列表、关键词搜索、封面缩略图与详情；v1.4.0 起支持
  双击专辑下钻浏览曲目、面包屑返回、播放整张专辑，可点播到当前播放器
- **主题分段按钮**（v1.4.0）：顶栏「浅色 / 深色 / 跟随系统」高对比自绘
  控件，取代深色主题下不可读的下拉框

## 正在播放与歌词来源

在「升级与更新」页填好 LMS 服务器地址后，打开「正在播放」页会自动列出
LMS 上的播放器；选中后即开始跟随其状态。本页只读写 LMS 的 JSON-RPC 接口
（`serverstatus` / `status` / `songinfo` / `playlist`），音频仍由 squeezelite
通过 Slimproto 输出，两条通道互不影响 —— 因此即使未点「启动」，只要 LMS
在线，本页也能显示其他遥控端发起的播放。

歌词按「LMS 内嵌歌词 → 在线歌词库 → 手动载入本地 LRC」的顺序获取：
先试 `songinfo ... tags:w`（LMS 扫描入库的内嵌歌词）与 `status tags:w`，
未命中则自动查询在线歌词库（LRCLIB / 网易云，结果带本地缓存），仍无结果时
可用「手动载入本地 LRC…」临时补充；点「重新搜索在线歌词」可忽略缓存重试。
在线歌词由本 APP 直接访问公网，不需要 LMS 安装任何插件，也不依赖本机挂载
音乐目录，因此 LMS 部署在独立服务器、曲库路径无法访问时同样可用。
带 `[mm:ss.xx]` 时间轴的歌词会随播放进度逐行高亮。

右侧可切换「歌词 / 专辑详情 / 可视化」三个视图：专辑详情展示 LMS 返回的
流派、年份、音轨号、比特率、采样率、文件路径等全部标签；可视化为装饰性
节奏动画（音频由 squeezelite 输出，本 APP 不采集 PCM，非真实 FFT 频谱）。
专辑封面固定按 280 px 显示，缩略图按 48 px 加载。

专辑封面请求 LMS 的 `/music/<coverid>/cover_300x300.jpg` 或 `artwork_url`，
解码为 PNG 后显示。解码按「LMS 已返回 PNG → macOS `sips` → Pillow →
ffmpeg」逐级降级，全部为可选路径：`.app` 内置运行时不依赖 Pillow，最差
情况仅显示文字占位符，不影响其他功能。

LMS 若启用密码保护，直接在「升级与更新」页 B 区填写用户名 / 密码即可
（密码掩码显示；仅设置密码时用户名留空）。也可手工写入
`~/.squeezelite_gui/config.json` 的 `lms_user` / `lms_pass`，文件权限 600。
服务端版本检测、正在播放与专辑封面请求都会自动携带该凭据。

## 歌词来源（无需 LMS 插件）

歌词获取顺序：① LMS 内嵌歌词 `songinfo ... tags:w`；② 在线歌词库
**LRCLIB**（`https://lrclib.net/api/get`，与 LMS 的 Music & Artist Information
插件同源）与网易云音乐备用源；③ 页面上的「手动载入本地 LRC…」兜底。
在线歌词由本 APP 直接访问公网，**不需要在 LMS 安装任何插件**，也不需要
本机挂载音乐目录 —— 因此 LMS 部署在独立服务器、曲库路径不可访问时同样可用。
结果缓存在 `~/.squeezelite_gui/lyrics_cache.json`（权限 600），点
「重新搜索在线歌词」可忽略缓存重试。带 `[mm:ss.xx]` 时间轴的歌词会随
`status.time` 逐行高亮。

注意：LMS 的 `songinfo tags:w` 只返回它扫描入库的**内嵌**歌词，默认不会读取
同目录的独立 `.lrc` 文件。若确实希望由 LMS 端提供，需要在 LMS 插件管理里
添加第三方插件仓库并安装 Music & Artist Information（支持同名 `.lrc`），
但这不是本 APP 正常工作的前提。

## 音乐库（阶段 2）

在「音乐库」页选择浏览维度、输入关键词回车即可走 LMS 的 `search:` 过滤；
列表带异步加载的封面缩略图，选中一项后右侧卡片显示大封面、标题与 LMS
返回的全部标签（文件路径已做 URL 解码，不再显示一长串 `%XX`）。

**下钻浏览**：双击专辑（或点「查看曲目」）进入该专辑的曲目列表，
请求为 `titles ... album_id:<id> sort:tracknum`，按音轨号排序并显示音轨号；
艺术家 / 流派可下钻到其专辑列表；顶部面包屑「← 返回」逐级回退，
专辑内「▶ 播放整张专辑」可整张点播。曲目双击或「▶ 播放此项」通过
`playlistcontrol cmd:load <album_id|artist_id|track_id|genre_id|playlist_id>`
发送到「正在播放」页选定的播放器。

所有浏览、封面与点播请求都会自动携带「升级与更新」页填写的 LMS 凭据。

可视化视图是**装饰性节奏动画**：音频通道是 squeezelite ↔ LMS 的 Slimproto
(3483)，PCM 数据不经过本 APP，因此无法做真实 FFT 频谱；该视图仅随播放
状态生成动态柱，界面上已明确标注。

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
