# Changelog — Sonora 颂诺 Web 版

本文件记录 Web 版（pywebview 渲染层）的变更。Tk 版 v1.x 的变更见仓库根目录
`CHANGELOG.md`。发布时同步更新 `main.py` 的 `VERSION` 与 `backend/api.py`
的 bridge 标记，并打附注标签 `vX.Y.Z`。


## v2.0.13 (2026-11-23) — 真机四测：加歌假成功根治 + 专注漏边 + 发布脱敏

- **歌单加歌假成功（核心）**：`playlistAdd` 的 BridgeAPI 签名只接受 2 个参数，
  前端却传了 3 个（多传曲目 meta），pywebview 直接抛 TypeError；而 `apiCall`
  的 `.catch(()=>fallback)` 把异常吞掉并返回 `{ok:true}`，于是"添加成功"是假的，
  曲目根本没写进 playlists.json。现桥接签名补上 meta 参数，并给 `apiCall`
  加 `console.error` 日志——以后任何桥接参数不匹配都会在控制台暴露，不再静默假成功。
  真机验证：经 BridgeAPI 三参数调用，曲目正确写入本地歌单。
- **加入队列看不到结果**：`queueAdd` 命令本身在真机是生效的（实测 1→2 首），
  但若播放列表面板正停在某个命名列表视图，`loadQueue()` 被 `if(!S.plSource)`
  挡住不刷新，用户就以为没加上。现"加入当前队列"后强制切回"当前队列"视图、
  自动展开播放列面板并刷新，立即看到结果；fallback 从 `{ok:true}` 改为
  `{ok:false}`，失败不再误报成功。
- **专注模式顶部漏边**：macOS 原生白色标题栏覆盖在 WKWebView 顶部（约 28px），
  focus-top 那排圆形按钮上半截落在标题栏后被白色盖住，只露下半截，看着像漏边。
  新增 refine9.css，把 focus-top 下移到标题栏以下的安全区（padding-top:42px）
  并加同色顶部遮挡条。模拟标题栏截图验证按钮完整显示、无漏边。
- **发布隐私脱敏**：预览页 build_preview.py 注入的 `lms_host=192.168.199.2`、
  `host_name=Song-Mac`、LMS 版本 9.1.1 等真实环境快照，以及 docs/IA.md 里的
  真实 IP，全部替换为通用示例值；preview.html 重新生成并确认零残留。
  说明：app 运行时配置读自 `~/.squeezelite_gui/config.json`（用户家目录，
  不在 app 包内），别人首次启动只会得到空配置并走引导填自己的服务器，
  不会带入你的连接信息/收藏/歌单/缓存。

## v2.0.12 (2026-11-23) — 真机三测：播放列表/队列/转码判定/退出清理

- **播放列表本地持久化（核心）**：这台 LMS 的 `playlists` 查询恒返回 `{}`、
  `playlists new` 返回 ID 但列表里查不到——创建/加歌全是假成功。现改为
  本地 `~/.squeezelite_gui/playlists.json` 持久化：创建、删除、重命名、
  加歌、删歌、取曲目全部本地实现，创建后立即在下拉选中。真实 LMS 验证
  创建→加 3 首→列出→删除全流程通过。
- **整单载入队列（可测试切歌）**：新增 `playlistPlayAll`——把本地歌单清空队列后
  按序载入 LMS 并从指定曲播放。真实验证：3 首载入后 `playlist index +1` 正确
  从 4441 切到 4425。现在有歌单就能测试上一曲/下一曲/播完切歌。
- **队列加歌假成功修复**：`queueAdd` 发送命令后复核 getQueue 队列数量，
  未真正入队则返回 ok:false + 错误说明；右键 toast 依据真实结果，不再谎报成功。
- **转码/直通判定重做**：弃用依赖 squeezelite 输出日志的方案（真机无日志 →
  永远"待确认"）。改为依据 LMS status 的 `url`：`file://` = 源文件直送未转码；
  含 stream/transcode 或 type=pcm = 已转码。音量/倍速作为附注。
  真实验证当前 FLAC 曲目显示"未转码 · 源文件直送"（不再是待确认）。
  LED 显示完整中文结论，曲目信息面板增加"音频链路/判定依据"两行。
- **退出自动停引擎**：main.py 注册 `window.events.closing`/`closed` + `atexit`，
  点 X / Cmd+Q / 异常退出都会调用 stopEngine 停止 squeezelite（幂等防重复）。

## v2.0.11 (2026-11-23) — 真机三次反馈 6 项修复

- **音乐库播放列表随切歌更新**：`loadQueue()` 在抽屉打开时同步刷新抽屉曲目；
  命名列表按当前曲目 id 标记 ▶，不再需要手动刷新才识别当前播放。
- **工具条按钮区分**：「▤ 播放列表」改为带文字的独立按钮，与「▦ 视图切换」
  之间加视觉分隔线，避免两个图标挨太近误点（refine8.css）。
- **切歌跳闪根治**：移除 `applyTrackToAll()` 里 `buildPlaylist()` 与
  `loadQueue()` 对同一 `#playlistBox` 的双重写入；改为切歌时单一
  `refreshPlaylistPanel()`，并对队列/命名列表/抽屉渲染加内容签名去重，
  内容未变不重绘 DOM，杜绝闪一下或闪现其它列表样子。
- **封面模糊根治**：`playItem()` 不再把 96px 列表缩略图当主封面；
  `getCover()` 优先请求 LMS `cover_1000x1000.jpg` / 原始 `cover.jpg`，
  再回退 300x300，按 800px 解码，专注大屏封面清晰。
- **转码/直通可判定**：引擎日志读取器实时喂给 `parse_sl_output()`，
  `_AUDIO_STATE` 不再只声明不填充；LED 显示短标签（BIT-PERFECT /
  已转码 / 已重采样 / 待确认），完整说明放到悬浮提示。
- **歌词/音频信息延后根治**：`loadTrackExtras()` 改为四个数据源
  （音频/歌词/简介/封面）各自到位即单独刷新，用 requestAnimationFrame
  合并到同一帧，不再等最慢的简介或封面；保留按 id 与序号双重防串曲。

## v2.0.10 (2026-11-23) — 真机二测 9 项修复 + 2 个隐藏命令 bug

- **面板全部开启可滚动**：`.player-panels` 改为可纵向滚动 + 行高按内容，
  四个信息面板全开时不再被窗口底部裁切。
- **进度条拖拽反馈**：扩大点击热区（上下各 10px），拖拽时本地即时走时并抑制
  轮询回弹；后端 seek 保持标准 `seek <秒数>`。
- **上一曲/下一曲根治**：`playControl` 由 `playlist jump ±1` 改为 `playlist index ±1`
  ——真实 LMS 验证 jump 在短队列会回退开头，index 正常切歌（实测 index 0→1）。
- **播完自动下一曲**：依赖队列修复；队列有多首时 LMS 自然推进。
- **播放列表正在播放标识**：队列/曲库/专注三处列表当前曲目显示绿色闪烁 ▶ 及高亮。
- **音量感知曲线**：滑块线性 0-100 ↔ LMS 刻度用平方曲线映射，低音量段更细腻；
  静音恢复、状态回显统一换算。
- **收藏双心去除**：收藏列表名已含 ♥，下拉选项不再重复加 ♥ 前缀。
- **队列能加多首（核心）**：`queueAdd` 由 `playlist add <纯数字>` 改为
  `playlistcontrol cmd:add/insert track_id:N`——真实 LMS 验证生效（队列 12→13）。
- **app 图标生效**：打包时把新 icns 覆盖到 app 的 `Contents/Resources/Sonora.icns`。
- **隐藏 bug：移除队列项失败**：`queueRemove` 用 `playlist del` 会触发 LMS
  "Remote end closed"，真实验证正确的是 `playlist delete`（已修复）。

## v2.0.9 (2026-11-23) — 真机反馈 7 项修复

- **专注模式布局**：改为纵向 flex 三段布局，顶部控件 flex-wrap 防漏边穿帮；
  标题/meta 固定顶部、歌词区独立滚动（min-height:0），根治歌名被顶出裁切。
  新增 refine6.css。
- **mini 封面串图**：封面写入记录 `coverTrackId`，`coverOf()` 仅在当前曲目匹配时
  用全局封面；`loadTrackExtras` 加请求序号，异步回调乱序时丢弃旧结果，杜绝串封面。
- **信息/歌词刷新迟缓**：切歌立即清空旧歌词并显示"加载中"；轮询间隔 2s→1s；
  按 id 防串确保歌词/信息随切歌即时更新。
- **上一曲/下一曲控制失败**：根治 `playControl` 把命令字符串传给 `lms_rpc`（内部
  `list(cmd)` 拆成单字符）导致 LMS 断连 "Remote end closed" 的 bug，改为传列表。
- **收藏失败 + 列表无收藏入口**：收藏改为本地持久化（favorites.json），彻底绕开
  本 LMS 版本不可用的 playlists 查询/tracks 接口；`getPlaylists` 始终注入虚拟
  「♥ 收藏」列表，增删查即时生效，收藏带曲名元信息。
- **进度条拖拽 seek**：mini/播放器/专注三条进度条支持点击+拖拽，调用 setSeek 定位。
- **app 图标**：重做为明亮绿色渐变 + 白色播放键 + 声波弧线，构图完整不裁切，
  与 Tk 版图标风格一致。



## v2.0.8 (2026-11-23) — 播放器体验 7 项修复 + 歌词串曲根治

- **mini 播放器溃缩**：关闭不再是隐藏，而是缩成左下角封面小图标；点击图标恢复展开，
  切歌时保持当前展开/溃缩状态（新增 `setMiniFolded` + `.folded` 样式）。
- **元数据/封面同步**：`loadTrackExtras()` 在每次切歌统一刷新封面、音频、歌词，
  贯穿 mini / 主播放器 / 专注模式；曲目标签补 `j`(artwork_track_id)，
  下钻曲目也能带封面；音乐库缺封面的条目异步补缩略图，不再出现永久空封面。
- **分类切换不错乱**：切换专辑/艺术家/音乐/流派时重置面包屑与浏览缓存
  （`crumbs/browseItems/lastBrowse`），二级浏览下切分类不再串内容。
- **播放模式生效**：单曲循环 / 列表循环 / 随机点击后加 6 秒乐观锁
  （`modePendingUntil`），轮询期间不回写，杜绝自动弹回顺序播放。
- **音频信息恢复**：`getAudio()` 从 LMS 真实 status 标签
  （url/type/samplerate/samplesize/bitrate）解析格式/码率/位深与直通判定，
  不再依赖前端传入的精简曲目。
- **二级浏览不重复**：曲目视图改用 `dispCat`，标题/副标题按曲目真实字段渲染，
  不再重复显示所属专辑信息。
- **歌词正常获取 + 不串曲**：`getLyrics()` 优先用传入曲目、字段不足时用当前播放状态补全；
  修复内嵌歌词注入未校验曲目 id 的 bug——切歌时曾把上一首的歌词串给下一首，
  现仅在曲目 id 匹配或传入为空时注入，切歌/同曲补全双向验证通过。



## v2.0.7 (2026-11-22) — 根治「引擎进程卡 SYN_SENT 连不上 LMS」

- **真机确诊**：app 用 `subprocess.Popen`（fork）派生的 squeezelite 子进程 TCP 连接
  永远卡在 SYN_SENT（连不上 LMS:3483），而同一个二进制用 shell / posix_spawn
  启动则瞬间 ESTABLISHED。这是 PyInstaller/WKWebView 进程 fork 后网络栈的问题，
  与 -s 参数、认证、防火墙、代理、沙盒均无关（均已真机排除）。
- **根治方案**：macOS 上改用 `os.posix_spawn` + 临时日志文件 + tail 读取线程
  替代 Popen，彻底规避 fork 的 SYN_SENT bug；引擎守护线程改为 tail 日志模式，
  保留实时日志、退出检测与看门狗自动重启。
- **状态修复**：startEngine/stopEngine 返回值与 _engine_alive 全面适配 spawn_pid，
  用 waitpid(WNOHANG) 避免停止后僵尸进程误判为"仍在运行"。
- **端到端验证（真机）**：启动→SlimProto connected→`[注册验证] ✅ 播放器已在
  LMS 上线`→LMS players=1→停止→running=False，全部通过。

## v2.0.6 (2026-11-22) — 真机诊断后彻底修复引擎存活与注册可见性

- **真机实测结论**：手动用相同二进制+命令启动，播放器 2 秒内 `connected=1`；
  但 app 启动的引擎进程会退出，而 UI 因只看 Popen 对象仍显示"运行中"，
  这是用户看到"引擎已启动但 LMS 查不到"的真正原因。v2.0.5 的 -s 修复方向错误。
- **看门狗**：引擎意外退出时自动重启（最多 3 次），手动停止不会触发。
- **注册验证**：启动 3 秒后主动查 LMS，把"播放器是否真的上线"写入引擎日志（✅/⚠）。
- **SlimProto 日志**：引擎日志加 `all=info`，连接/HELO/set name 过程可见。

## v2.0.5 (2026-11-22) — 修复引擎启动未传 -s/-n/-o，squeezelite 未注册到 LMS

- **根因**：`server` / `name` / `output` 三个参数此前只在设备页与参数页回显，
  从未进入实际启动命令。未传 `-s` 时 squeezelite 只能靠 UDP 3483 自动发现，
  跨网段或远程 LMS 必然失败——进程能启动并打开音频设备，但 LMS 播放器列表
  里没有它，顶部徽标与「多端同播」自然都查不到（这两个页面读的是同一份
  LMS `serverstatus.players_loop`，并非摆设）。
- **修复**：`build_argv` 新增 `_link_values()` 统一联动：参数页留空时自动填入
  「升级与更新」页的 LMS 主机 + SlimProto 端口 3483 作为 `-s`（不是 HTTP 9000）、设备页生成的播放器名作为
  `-n`、选中的输出设备作为 `-o`；引擎启动、开机自启、参数预览共用同一份命令。
- **附带修复**：引擎页版本号原先把 `sq_local_version()` 返回的字典直接拼接，
  显示成 `squeezelite [object Object]`；现取其中的 version 字符串。
- **需要重启引擎**：旧进程是用旧命令启动的，升级后需先停止旧引擎（必要时
  `kill <PID>`），再启动新引擎，才会带 `-s` 注册到 LMS。

## v2.0.4 (2026-11-22) — 修复 PyInstaller 构建脚本中断

- **build_app.sh 构建修复**：在 `set -euo pipefail` 模式下直接引用未设置的
  `SQUEEZELITE_GUI_BINARY`，依赖安装完成后立即报 `unbound variable` 并中断。
  改为 `${SQUEEZELITE_GUI_BINARY:-}` 默认值后再遍历候选路径；未设置时继续
  自动查找本机 squeezelite，内置逻辑不受影响。
- 同步更新源码包与 .app 内 `Contents/Resources` 中的脚本副本。

## v2.0.3 (2026-11-22) — 内置 squeezelite + 真更新 + 系统级开机自启

- **内置二进制**：文本型 .app 首次启动自动探测本机 squeezelite 并复制到 app 内（`SQUEEZELITE_GUI_BINARY` 环境变量注入）；PyInstaller 版 build_app.sh 打包时内置二进制；main.py 兼容三种运行形态的资源定位。
- **一键更新**：新增 `upgradeSqueezelite` API，从版本源查最新版 → 下载解压/挂载 DMG → 备份旧版 → 就地替换 → 自动重启引擎；更新页新增「立即更新 squeezelite」按钮 + 实时日志。
- **系统级开机自启**：`setAutoStart` 从"只存配置"改为生成/卸载 macOS LaunchAgent（RunAtLoad+KeepAlive），开机后独立拉起 squeezelite 并注册到 LMS，不依赖 app 打开；新增 `getAutoStartStatus` 回显真实安装/加载状态。
- Bridge API 51 → 53 方法。

## v2.0.2 (2026-11-22) — 修复「能连服务器却放不了歌」根因：补齐播放器引擎启动

**核心修复**：Web 版此前只有「遥控端」能力，缺少 Tk 版最关键的「启动 squeezelite 播放器并注册到 LMS」环节，导致 LMS 上没有播放器在线——所有播放器级命令（播放下发/静音/音量/进度/封面）都被 LMS 断连。本版本补齐完整进程管理闭环。

- **引擎进程管理**：后端新增 `startEngine` / `stopEngine` / `engineStatus`（subprocess.Popen 真正启动 squeezelite，复用 build_argv/validate_all，守护线程读日志、检测退出码、维护运行/退出状态）。
- **启动控制页**：前端「启动引擎」按钮从假交互改为真实调用后端；新增引擎日志显示区；进页面回显真实运行状态（PID/运行时长/命令/日志）；支持开机自启。
- **连接状态增强**：顶部徽标检测在线播放器数，服务器已连但无播放器时显示「已连服务器·播放器未启动」并给出指引（警示色）。
- **静音兜底**：无播放器/状态读取失败时返回明确中文提示，不再笼统报「静音失败」。
- **封面兜底**：缩略图与大图抓取均增加多 URL 候选 + Basic Auth 认证头重试，LMS 启用密码保护时也能取到封面。
- Bridge API 48 → 51 方法。

## v2.0.1 (2026-11-22) — 真实环境测试 7 项问题修复

基于 macOS 真机手动测试反馈，修复 7 项问题：

1. **音量图标风格与静音**：emoji 🔊 换成与 UI 一致的 SVG 扬声器图标；
   音量控件新增一键静音/恢复按钮（后端记住静音前音量）。
2. **设备扫描**：无 squeezelite 时用 LMS 在线播放器 + 默认输出兜底，
   保证界面始终有可选项；coreaudio_device 等扫描结果正常显示。
3. **播放器命名**：设备页新增「本机名称 / 设备简称 / 名称模板」输入框，
   实时预览 LMS 显示名并保存到配置；saveDevice 扩展支持 host_name / name_template。
4. **参数页一键最优与帮助**：修复前端字段错误（options 而非 choices），
   渲染每个参数的下拉显示名、具体效果、详细说明、推荐值与取值范围；
   新增「★ 一键最优」按钮（后端 applyBestParams，保留设备/名称/LMS 联动项）。
5. **mini 播放器关闭**：新增关闭按钮（悬停显示），关闭后切歌会再次出现，
   不再遮挡后方内容。
6. **连接状态**：顶部徽标新增 getConnection API 实时轮询，正确显示
   「已连接 / 连接失败 / 未配置」（此前写死「未连接」）。
7. **播放下发与封面**：LMS JSON-RPC 增加瞬时断连重试（Remote end closed
   connection / reset / timeout 自动重试 2 次），修复点歌下发失败。

其他：Bridge API 45 → 48；版本号统一 2.0.1；新增 refine5.css 独立样式层。

## v2.0.0 (2026-11-22) — 大版本：pywebview 渲染层重构 + 完整交互

相对 Tk 版 v1.6.0 的大版本升级：渲染层从 Tk 换成 HTML/CSS（pywebview 6.x
+ 系统 WKWebView），Python 逻辑层原样复用 Tk 版纯函数。

### 视觉
- 高保真音响质感：毛玻璃 / 圆角 / 阴影 / 渐变 / 精细抗锯齿，独立 refine
  样式层（refine → refine4）可整体回退，不破坏基础样式。
- 大封面毛玻璃卡、42px 曲名、8px 进度条、LED 点阵规格屏、氛围取色背景、
  专注大屏模式；明暗主题切换。

### 音乐库与播放
- 四类库（专辑 / 艺术家 / 音乐 / 流派）、网格⇄列表、排序、搜索、首字母跳转、
  真实 LMS 封面缩略图。
- 下钻浏览、右键上下文菜单、曲目详情 / 歌手简介弹窗。
- mini 播放器 + 常规播放器 + 专注大屏；播放列表 / 歌词 / 简介侧栏。

### 播放列表与收藏
- 队列 + 命名播放列表管理；面板随内容自适应高度、鼠标拖拽缩放、双击复位。
- 音乐库就地播放列表抽屉：下拉切换队列 / 命名列表，新建 / 删除列表、刷新。
- 收藏体系：默认有且仅有固定「♥ 收藏」列表，收藏自动加入、取消收藏自动移除；
  收藏列表受系统保护（不可删除 / 不可重命名），心形状态四处同步。
- 播放模式（顺序 / 循环 / 单曲 / 随机）、音量控制、真实状态同步。

### 设置与桥接
- 服务器设置 / 播放器引擎 / 参数配置 / 升级更新 / 帮助全部落地。
- Bridge 45+ JS 可调用 API（`window.pywebview.api`），真实 LMS 双向数据互通。

### 交付
- `run_mac.command` macOS 一键启动脚本（自动建 venv、装依赖、启动窗口）。
- `build_preview.py` 离线预览生成器（mock 数据，无需 LMS 即可看界面交互）。
