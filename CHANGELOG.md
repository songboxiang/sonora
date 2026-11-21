# Changelog

本项目遵循语义化版本：发布时同步更新 `squeezelite_gui.py` 中的 `VERSION`
常量，并打附注标签 `vX.Y.Z`。

## v1.5.0 (2026-11-22) — 音频链路直通判定、简介视图、专注大屏与 UI 收敛

- **修复「下一曲」被挤出画面**：正在播放页左卡片的播放控制区由 `pack`
  改为三列等宽 `grid`（上一首 / 播放暂停 / 下一首），窄窗口下不再溢出。
- **封面统一为正方形**：`decode_cover_png()` 新增 `square=True`，等比缩放后
  居中补边（不变形），依次用 `sips -p` / Pillow / ffmpeg `scale+pad`；
  正在播放 280 px、专注大屏 420 px、音乐库详情 272 px、列表缩略图 44 px
  全部走同一路径，修复专辑与曲目封面有大有小的问题。
- **主题分段控件重做**：由 macOS Aqua 下背景色不可靠的 `tk.Button` 改为
  `ttk.Label` + `ThemeSeg.TLabel` / `ThemeSegOn.TLabel` 自绘样式，选中项
  反色胶囊、未选中项融入 app bar，浅色 / 深色 / 跟随系统三态均清晰可读。
- **音频链路 / 完美直通判定**（新增）：`audio_spec()` 从 LMS `status` /
  `songinfo` 标签提取源格式（FLAC / WAV / DSD / PCM / MP3 / AAC）、采样率、
  位深与码率；按真实 LMS 9.1.1 抽样补齐 `I`(位深) / `r`(码率) /
  `o`(格式类型) 三个 tag（原有 `T` / `f` 对应采样率 / 文件大小），
  位深与码率优先采用 LMS 报告值，缺失时才按文件大小与时长推算，
  并支持用 LMS `type` 在 url 被重写时兜底判定格式；
  `_start_proc()` 自动追加 `-d output=info`，
  `parse_sl_output()` 从 squeezelite 日志解析实际输出采样率、DSD 封装与
  「converting to PCM」；`audio_link_verdict()` 结合源 / 输出采样率、LMS
  音量与播放速率，给出「完美直通 / 未发现转码迹象 / 已转码 / 已重采样 /
  数字音量介入 / 非 1 倍速 / 待确认」判定。播放器非本 APP 启动时明确标注
  无法读取输出日志，仅显示 LMS 源文件规格。
- **可视化页改为「歌手 / 专辑简介」**：真实 FFT 在本架构不可行（PCM 由 LMS
  经 Slimproto 直送 squeezelite，不经过本 APP；macOS 无原生回环采集），
  因此移除装饰性节奏动画与 `np_viz_canvas` / `viz_frame()` 死代码。新视图
  用 LMS 标签展示专辑元信息，长篇简介取自维基百科中 / 英文 API；若 LMS
  启用 Music & Artist Information 类插件，可设 `bio_lms_plugin=true` 改用
  `artistinfo` / `albuminfo`（默认关闭，未装插件会断连）。结果缓存于
  `~/.squeezelite_gui/bio_cache.json`（权限 600，上限 300 条），页面提供
  「重新获取简介」。
- **专注大屏模式**（新增）：`tk.Toplevel` 全屏，420 px 正方形大封面、大字
  歌词、曲目信息、进度与控制；`ESC` 退出，`<Motion>` 浮出「✕ 退出专注
  模式」按钮，静止约 3 秒自动隐藏；配色随主窗口明暗主题同步刷新。
- **UI 风格收敛**：新增 `Hero.TLabel` / `Muted.TLabel` / `Ok.TLabel` /
  `Warn.TLabel` / `Card.TFrame` 与细进度条，卡片细边框、字号层级、分隔线
  与状态色统一，向 Lyrion Material / Audirvana 播放器看齐。
- 仍为纯标准库 tkinter 单文件，未引入新依赖；新增缓存文件仅
  `bio_cache.json`。

## v1.4.0 (2026-11-22) — 主题控件、专辑下钻、音乐库卡片式重排

- **修复顶栏主题选择器对比度**：原 `ttk.Combobox` 在深色 app bar 上被系统
  渲染成浅色底 + 浅色字，几乎无法辨认。改为自绘 Material
  「浅色 / 深色 / 跟随系统」分段按钮：选中项为反色胶囊（高对比），
  未选中项融入 app bar；跟随系统仍每 4 秒轮询并实时切换。
- **音乐库支持专辑下钻**：双击专辑（或点「查看曲目」）进入该专辑曲目列表，
  使用 `titles ... album_id:<id> sort:tracknum` 按音轨号排序；艺术家 / 流派
  可下钻到专辑列表；面包屑「← 返回」逐级回退，专辑内提供
  「▶ 播放整张专辑」。曲目双击仍为直接播放。
- **封面字段修正**：专辑列表改用 `tags:alj`，LMS 才返回
  `artwork_track_id`；统一 `coverid` / `artwork_track_id` / `artwork_url`
  取值，专辑与曲目列表缩略图都能正常显示。
- **列表与详情重排**：音乐库列表专用行高 54px（缩略图 44px），名称列不再
  与「信息」列重复显示同名专辑；曲目前加音轨号；详情改为标题 / 副标题 /
  制表位对齐字段，文件路径 URL 解码后只显示末尾两级，避免长串撑满版面。
- **界面美化**：顶栏加分隔线；Notebook 改卡片式选中态；工具栏拆成
  「操作行 + 状态 / 提示行」并加入紧凑按钮样式；列表与详情放进带细边框的
  Material 卡片；卡片边框、文字、详情文本配色随明暗主题同步刷新。
- 仍为纯标准库 tkinter 单文件，未引入新依赖。

## v1.3.0 (2026-11-22) — 在线歌词、大封面、跟随系统、音乐库（阶段 2）

- **歌词不再依赖 LMS 插件或本地挂载**：新增在线歌词源 LRCLIB
  （`/api/get` 精确匹配 + `/api/search` 兜底，返回带时间轴的 `syncedLyrics`）
  与网易云音乐备用源，结果缓存到 `~/.squeezelite_gui/lyrics_cache.json`。
  获取优先级：LMS 内嵌歌词 `songinfo tags:w` → 在线歌词 → 手动载入本地 LRC；
  「重新搜索在线歌词」可忽略缓存重试。LMS 端无需安装任何插件。
  在线歌词按「带时间轴优先」挑选：LRCLIB 同步歌词 → 网易云 LRC → 任意
  纯文本；例如 LRCLIB 把《月光》标为 instrumental 且无歌词时，会自动改用
  网易云返回的带时间轴 LRC，保证逐行同步可用。
  macOS 跟随系统以 `defaults read -g AppleInterfaceStyle` 为首选
  （无需「自动化」授权），AppleScript 仅作兜底，避免权限违例 -10004。
- **修复专辑封面过小**：原 `tk.Label(width=30, height=14)` 在含图片时按
  **像素**解释，把 300px 封面压成 30×14。改为 280×280 固定容器 + 自适应
  Label，封面按 280px 解码；新增「专辑详情 / 可视化」视图，与歌词三向切换。
- **专辑详情**：`status` 请求扩展 tags，展示流派、年份、音轨号、比特率、
  采样率、位深、文件格式、文件大小、文件路径等 LMS 返回的全部标签。
- **可视化**：Canvas 绘制 32 条动态柱，随播放状态起伏。明确标注为装饰性
  节奏动画 —— 音频由 squeezelite 输出，本 APP 不采集 PCM，非真实 FFT 频谱。
- **主题跟随系统**：顶栏新增「浅色 / 深色 / 跟随系统」下拉，跟随系统通过
  macOS AppleScript `appearance preferences` + `defaults`、Linux
  `gsettings`、Windows 注册表检测，后台每 4 秒轮询并自动切换；手动切换
  会自动切回手动模式。切主题时歌词高亮、可视化配色、音乐库行色同步刷新。
- **音乐库（阶段 2）**：第 7 个标签页，支持专辑 / 艺术家 / 曲目 / 流派 /
  播放列表分页浏览与 `search:` 关键词过滤；Treeview 带异步封面缩略图，
  选中显示大封面与详情，点「播放此项」或双击通过 `playlistcontrol cmd:load`
  发送到当前播放器。所有请求自动携带 LMS Basic Auth 凭据。
- 文档：README 功能与歌词/音乐库章节、应用内帮助同步更新。

## v1.2.1 (2026-11-22) — 修复 LMS 密码保护下无法连接

- 修复 LMS 启用 Basic Auth 时「正在播放」页完全空白：抽出统一的
  `lms_auth_headers(cfg)`，让 `lms_rpc`、`lms_current` 与专辑封面 GET
  三处请求全部携带 `Authorization` 头（此前封面与版本检测未带）。
- 支持「仅设置密码、用户名留空」的 LMS 安全配置（此前要求用户名非空
  才发送凭据）。
- 「升级与更新」页 B 区新增用户名 / 密码输入框（密码掩码显示），实时写回
  配置并在退出时持久化；配置文件权限保持 600。
- 401 时状态栏显示「● LMS 需要密码」，日志给出修复指引，版本检测失败
  也返回可读提示，不再只显示笼统的「连接失败」。
- 结果：服务端版本检测、播放器列表、曲目信息、歌词、专辑封面现在都可在
  受密码保护的 LMS 上正常工作。

## v1.2.0 (2026-11-22) — 阶段 1：正在播放

- 新增第 6 个标签页「正在播放」(Now Playing)：通过 LMS JSON-RPC
  `serverstatus` / `status` 获取播放器状态，显示曲名、艺术家、专辑、
  进度条、播放状态、队列位置与专辑封面；遥控端（手机 / 网页）发起播放后
  本页自动跟随，无需在本 APP 内点播。
- **歌词全部从 LMS 服务端获取**：优先 `songinfo 0 100 track_id:X tags:w`
  （LMS 扫描曲库时入库的内嵌歌词），失败回落 `status tags:w`。不读取本机
  音乐目录、不依赖任何挂载点，适配 LMS 部署在独立服务器的场景。
- LRC 时间轴解析与逐行同步高亮：支持 `[mm:ss.xx]`、多时间戳与
  `[ti:]/[ar:]/[al:]` 元数据，按 `status.time` 配合本地时钟平滑推进。
  LMS 无内嵌歌词时可用「手动载入本地 LRC…」临时补充。
- 封面多级解码：LMS 已返回 PNG 时直接用；JPEG 依次尝试 macOS `sips`、
  Pillow（若已安装）、ffmpeg，全部不可用则显示文字占位符。保持单文件与
  零强制第三方依赖，`.app` 内置运行时无需 Pillow。
- 播放器自动定位：按已保存的 playerid、本机显示名、主机名、squeezelite
  模型依次匹配，也可在下拉框手动选择；支持上一首 / 播放暂停 / 下一首。
- 可选 Basic Auth（`lms_user` / `lms_pass`），配置文件权限收紧为 600。
- 500ms UI 节拍 + 可配置 1/2/3/5/10 秒网络轮询间隔；所有网络操作在后台
  线程执行，复用现有 `Queue + after()` 泵，不阻塞界面。

## v1.1.0 (2026-11-21)

- 界面重做为 **Lyrion Material Skin** 风格：亮 / 暗双主题（顶栏一键切换，
  偏好写入 `~/.squeezelite_gui/config.json`）；Material 顶栏、主色标签页、
  卡片式分组、统一按钮 / 输入框 / 滚动条 / Treeview / 文本框配色。
  色值取自官方 `lyrion.css` / `light.css` / `dark-lyrion.css`。
- 修复参数配置页**只能用滚动条拖拽翻页**：新增跨平台滚轮支持
  （macOS/Windows `<MouseWheel>`、X11 `<Button-4>/<Button-5>`），递归绑定到
  参数区 255 个控件，并固定 40px 滚动步长；设备表与版本表同样支持滚轮。
- 新增**原创应用图标**：`assets/logo.svg`、`assets/logo-1024.png`、
  `assets/app.icns`（7 种尺寸），由 `assets/make_icon.py` 生成；
  `build_app.sh` 默认捆绑该图标，彻底移除对 Apple 系统图标的复制。
- 全部硬编码颜色改为主题变量，切换主题时 ttk 与 tk 原生控件同步刷新。

## v1.0.1 (2026-11-21)

- 修复 macOS 系统自带 Tk 8.5 导致的窗口内容全白：构建产物改用内置
  Python 3.13 / Tk 9 运行时，并增加 Tk < 8.6 的重绘兜底与版本日志。
- `find_binary()` 支持 `.app` 内置 squeezelite，联网升级可就地替换，
  旧版备份到 `~/.squeezelite_gui/backups/`。
- 移除对 macOS 系统图标（CoreTypes.bundle）的复制，避免再分发 Apple
  专有资源；改为可选自备原创 `app.icns`。
- 新增开源发布文件：`LICENSE`(MIT)、`THIRD_PARTY_NOTICES.md`、
  `README.md`、`.gitignore`、`CHANGELOG.md`。
- `Squeezelite-GUI.command` 改为要求 Tk >= 8.6，避免回落到系统 Tk 8.5。

## v1.0.0 (2026-11-21)

- 首个版本：启动自动扫描音频输出设备并手选；27 项参数下拉 / 效果说明 /
  最优音质推荐 / 自定义范围；播放器名 = 本机名 + 设备简称（`-n`）；
  联网升级 Squeezelite、检查 LMS 服务端更新并标注升级内容。
