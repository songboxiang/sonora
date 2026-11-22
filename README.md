# Squeezelite GUI（macOS）


> 🆕 **v2.0.0 大版本（Sonora 颂诺 · Web 版）已发布**：全新 pywebview 渲染层，
> 见 [`sonora-web/`](sonora-web/)（[运行说明](sonora-web/README.md) /
> [更新日志](sonora-web/CHANGELOG.md)）。下方为经典 Tk 版 v1.x 说明。

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
- **Lyrion Material 风格界面**：浅色 / 深色 / 跟随系统三态（顶栏分段
  按钮，v1.5.0 重做为三态均高对比可读的 `ttk` 自绘控件），配色取自
  官方 Lyrion Material Skin 并参考 Audirvana 播放器的字号层级与留白；
  跟随系统会自动检测 macOS / Linux / Windows 的明暗外观并实时切换。
- **原创应用图标**：`assets/logo.svg` + `assets/app.icns`（Material 圆角方形 +
  浮动操作按钮 + 声波弧线），非 Apple 系统资源，可随应用分发
- 配置保存在 `~/.squeezelite_gui/`，升级前自动备份旧二进制
- **「正在播放」看板**（v1.3.0 起，v1.5.1 增强）：跟随 LMS 播放器状态，
  展示大尺寸正方形专辑封面、曲目信息、进度，以及「歌词 / 专辑详情 /
  歌手 / 专辑简介」三视图；歌词与歌手简介优先从 LMS 端获取
  （`songinfo tags:w` + Music & Artist Information 插件），未命中时才走
  在线歌词库 / 维基百科，支持 LRC 时间轴逐行同步
- **LMS 端数据直连**（v1.5.1）：修正 MAI 插件 CLI 命令为
  `musicartistinfo biography / albumreview / lyrics`，歌手简介、专辑评论与
  歌词默认优先取自 LMS；插件未装 / 命令失败自动降级到维基百科与在线歌词，
  不会断连。插件清单与安装步骤见 `docs/LMS_PLUGINS.md`
- **音频链路 / 完美直通判定**（v1.5.0）：显示源格式（FLAC / WAV / DSD /
  PCM 等）、采样率、位深与码率；通过本 APP 启动时自动追加
  `-d output=info`，从 squeezelite 日志解析实际解码输出，结合 LMS 音量
  与播放速率判定是否未经转码 / 重采样的 bit-perfect 直通
- **专注大屏**（v1.5.0）：全屏大封面 + 大字歌词 + 进度控制，ESC 退出，
  移动鼠标浮出退出按钮（静止约 3 秒自动隐藏），配色随主题同步
- **音乐库（阶段 2）**（v1.3.0，v1.4.0 / v1.5.0 增强）：分页浏览专辑 /
  艺术家 / 曲目 / 流派 / 播放列表、关键词搜索、封面缩略图与详情；支持
  双击专辑下钻浏览曲目、面包屑返回、播放整张专辑，可点播到当前播放器；
  v1.5.0 起专辑与曲目封面统一为正方形
- **主题分段按钮**（v1.4.0，v1.5.0 重做）：顶栏「浅色 / 深色 / 跟随系统」
  三态全部可读的 `ttk` 自绘分段控件，选中项反色胶囊、未选中项融入
  app bar，取代系统渲染下不可读的下拉框与 `tk.Button`
- **Lyrion Material / Audirvana 风格收敛**（v1.5.0）：标题 / 副标题 /
  正文三级字号与高对比文字、卡片细边框、进度细条、统一按钮与状态色
- **设计交接规范**（v1.5.1）：`docs/UI_DESIGN_BRIEF.md` 写明把 UI
  交给设计类模型时应提供的标准、必须输出的交付物与到 tkinter 的映射；
  v1.6.0 实际落地所用的一整套设计交付物已归档在 `docs/design/`
  （`design-tokens.json` / `mapping.md` / `components.md` / `states.md` /
  `screens/` 五张设计稿），令牌到代码的精确映射见 `docs/design/mapping.md`
- **设计交付包落地**（v1.6.0）：按完整设计交付物（设计令牌映射表 / 组件清单
  / 五张设计稿）全量替换浅深两套配色与字号层级 —— 主色改为满足 WCAG AA
  的可交互绿，Lyrion 原色仅作装饰；曲名 42 / 专注 56 / 标题 24 / 副标题 17 /
  元数据 12 / 角标 10 六级字号；新增 11 个组件样式（徽章 / 状态 / 危险按钮 /
  列表项等），进度条加厚 8px，顶栏精简至 48px，播放三列等宽防溢出。
  令牌到代码的映射见 `docs/UI_DESIGN_BRIEF.md`。

## 正在播放、歌词与音频链路

在「升级与更新」页填好 LMS 服务器地址后，打开「正在播放」页会自动列出
LMS 上的播放器；选中后即开始跟随其状态。本页只读写 LMS 的 JSON-RPC 接口
（`serverstatus` / `status` / `songinfo` / `playlist`），音频仍由 squeezelite
通过 Slimproto 输出，两条通道互不影响 —— 因此即使未点「启动」，只要 LMS
在线，本页也能显示其他遥控端发起的播放。

歌词按「LMS 内嵌歌词 → LMS/MAI 插件歌词 → 在线歌词库 → 手动 LRC」获取：
先试 `songinfo ... tags:w`（LMS 扫描入库的内嵌歌词）与 `status tags:w`；
未命中则调 LMS 的 Music & Artist Information 插件 `musicartistinfo lyrics
track_id:<id>`；再未命中才查询在线歌词库（LRCLIB / 网易云，带本地缓存），
仍无结果时可用「手动载入本地 LRC…」补充。插件歌词实测多为**纯文本、无
时间轴**，因此默认仍让带 `[mm:ss.xx]` 时间轴的在线 LRC 优先以保留逐行
高亮；若要完全从 LMS 端取歌词，可在 `config.json` 设
`lyrics_prefer_lms: true`（会失去逐行高亮）。点「重新搜索在线歌词」可忽略
缓存重试。所有路径都不依赖本机挂载音乐目录，LMS 部署在独立服务器同样可用。

右侧可切换「歌词 / 专辑详情 / 歌手 / 专辑简介」三个视图：专辑详情展示
LMS 返回的流派、年份、音轨号、比特率、采样率、文件路径等全部标签；
简介视图把 LMS 标签提供的专辑元信息，与**歌手简介 / 专辑评论**合并展示：
长篇内容默认优先取自 LMS 的 Music & Artist Information 插件
（`musicartistinfo biography` / `albumreview`），任一未命中时自动回退
维基百科中 / 英文 API；结果缓存在 `~/.squeezelite_gui/bio_cache.json`
（权限 600，上限 300 条）。插件命令不存在或未安装时自动降级、不会断连；
如需彻底跳过插件，在 `config.json` 设 `bio_lms_plugin: false`。
插件清单与安装步骤见 `docs/LMS_PLUGINS.md`。

**不再提供可视化视图**：真实 FFT 在本架构不可行 —— PCM 由 LMS 经
Slimproto 直送 squeezelite，不经过本 APP，macOS 也没有原生回环采集设备；
原先的装饰性节奏动画已移除，该页改为上述简介视图。

**音频链路 / 完美直通**：新增卡片显示源格式、采样率、位深、码率，以及
squeezelite 实际输出。通过本 APP「▶ 启动」时自动追加 `-d output=info`，
解析 `track start sample rate`、`DSD… stream`、`converting to PCM` 等日志；
结合源 / 输出采样率、LMS 音量与播放速率给出「完美直通 / 未发现转码迹象 /
已转码 / 已重采样 / 数字音量介入 / 待确认」判定。播放器若由外部启动则
无输出日志，卡片标注「待确认」并仅显示 LMS 源文件规格。

源规格取自 LMS `status` 的 `tags:...Iro`：`I` = 位深、
`r` = 码率、`T` = 采样率、`f` = 文件大小、`o` = 格式类型；这三个标签
按真实 LMS 9.1.1 抽样补齐，位深与码率不再只能显示「—」或靠推算。
url 被 LMS 重写时，还会用 `type`（如 `flc` / `mp3` / `dsf`）兜底判定格式。

专辑封面按正方形等比缩放后居中补边输出：正在播放页 280 px、专注大屏
420 px、音乐库详情 272 px、列表缩略图 44 px，不再出现大小不一或变形。

专辑封面请求 LMS 的 `/music/<coverid>/cover_300x300.jpg` 或 `artwork_url`，
解码为 PNG 后显示。解码按「LMS 已返回 PNG → macOS `sips` → Pillow →
ffmpeg」逐级降级，全部为可选路径：`.app` 内置运行时不依赖 Pillow，最差
情况仅显示文字占位符，不影响其他功能。

LMS 若启用密码保护，直接在「升级与更新」页 B 区填写用户名 / 密码即可
（密码掩码显示；仅设置密码时用户名留空）。也可手工写入
`~/.squeezelite_gui/config.json` 的 `lms_user` / `lms_pass`，文件权限 600。
服务端版本检测、正在播放与专辑封面请求都会自动携带该凭据。

## 歌词来源与 LMS 插件

歌词获取顺序：① LMS 内嵌歌词 `songinfo ... tags:w`；② LMS 端
Music & Artist Information 插件 `musicartistinfo lyrics`；③ 在线歌词库
**LRCLIB**（`https://lrclib.net/api/get`，与 MAI 插件同源）与网易云音乐备用
源；④ 页面上的「手动载入本地 LRC…」兜底。带 `[mm:ss.xx]` 时间轴的歌词会随
`status.time` 逐行高亮；插件歌词多为纯文本，默认让带时间轴的在线 LRC 优先，
可用 `lyrics_prefer_lms: true` 改为完全从 LMS 取。结果缓存在
`~/.squeezelite_gui/lyrics_cache.json`（权限 600），点「重新搜索在线歌词」
可忽略缓存重试。所有路径都不需要本机挂载音乐目录。

**LMS 端插件**：`songinfo tags:w` 只返回扫描入库的**内嵌**歌词，不会读取同目录
独立 `.lrc`。若希望歌词、歌手简介、专辑评论都由 LMS 提供，需在 LMS
「设置 → 插件」启用 **Music & Artist Information**（LMS 9.x 默认仓库已包含，
通常无需添加第三方仓库）。本 APP 会自动探测插件命令，未安装时静默降级到
在线歌词与维基百科，不影响使用。完整清单、CLI 命令与验证方法见
`docs/LMS_PLUGINS.md`。

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

**封面统一为正方形**：列表缩略图与详情大封面均走
`decode_cover_png(..., square=True)`，等比缩放后居中补边（不变形），
依次尝试 LMS 已返回 PNG → macOS `sips -p` → Pillow → ffmpeg `scale+pad`。
音乐库行高 54 px / 封面列 68 px，缩略图 44 px，专辑与曲目显示尺寸一致。

**关于真实 FFT**：音频通道是 squeezelite ↔ LMS 的 Slimproto(3483)，PCM
数据不经过本 APP，macOS 亦无原生回环采集，因此无法做真实 FFT 频谱；
本版本已移除装饰性动画，改为「歌手 / 专辑简介」视图，并在页面内说明原因。

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
