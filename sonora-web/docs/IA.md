# Squeezelite GUI Web 版 — 信息架构与 Bridge API 契约（阶段 0）

> 状态：v0.1 / 2026-11-22
> 依据：现有 `/opt/squeezelite-gui/squeezelite_gui.py` v1.6.0 真实代码结构
> + `docs/design/` 设计交付物（design-tokens.json / mapping.md / 5 张设计稿）
> 目标：pywebview 渲染层替换，**逻辑层尽量原样复用，前端按此规格实现**。

---

## 0. 架构分层与复用边界

```
前端 web/  (HTML/CSS/JS, 无框架或轻量)            新建
  页面 = 视图；只发 API 请求 + 渲染返回结果
pywebview 窗口 + JS API bridge                   新建（薄）
  window.api.<method>(args) -> Promise<JSON>
backend/  (从 squeezelite_gui.py 抽取的纯逻辑)     复用为主
  lms_rpc / np_status / np_lyrics_resolve /
  lib_browse / bio_fetch / audio_spec / 配置缓存 …
squeezelite helper (外部进程, GPLv3, 独立聚合)     不变
```

**可原样复用**（顶层纯函数，约 70 个，cfg 入参 + 返回 dict/tuple）：
`lms_rpc` `lms_auth_headers` `lms_current` `np_players` `np_pick_player`
`np_status` `np_lyrics_from_lms` `parse_lrc` `np_cover_url` `decode_cover_png`
`np_lyrics_resolve` `lyrics_online` `lib_browse` `lib_play_cmd` `detail_lines`
`audio_spec` `parse_sl_output` `audio_link_verdict` `bio_fetch` `mai_rpc`
`lms_plugin_bio` `lms_mai_lyrics` `load_config` `save_config` `scan_devices`
`build_argv` `validate_all` `preview_cmd` `find_binary` `system_dark_mode` 等。

**需重写为 bridge API**（现有 App 方法把逻辑与 Tk 控件混在一起）：
所有 `_np_*` / `_lib_*` / `_focus_*` 编排方法 → 拆成「返回数据的 API」+「前端渲染」。

**通信模式**：
- 请求-响应：`window.api.xxx()` → Python 同步/异步函数 → JSON 返回（Promise）。
- 服务端推送：Python 后台线程轮询 LMS → 调 JS 回调 `window.onPush(event)` 推送
  `np:update` / `proc:log` / `theme:change` 等事件。
  阶段 1 可先用前端 `setInterval` 调 `api.getStatus()` 轮询，降低 bridge 复杂度。

---

## 1. 页面清单（7 页，沿用现有功能域，重排信息层级）

| # | 页面 id | 名称 | 核心内容 | 主要数据来源 |
|---|---|---|---|---|
| 1 | `devices` | 设备与启动 | 音频设备列表、播放器名称、启动/停止、实时日志 | `scan_devices` / `build_argv` / helper 进程 |
| 2 | `params` | 参数配置 | 27 项参数分组、下拉+说明+推荐、实时校验、命令预览 | `PARAMS` / `validate_all` / `preview_cmd` |
| 3 | `launch` | 启动脚本 | 命令行预览、复制、保存脚本、LaunchAgent 安装 | `build_argv` / `make_launch_agent` |
| 4 | `now` | 正在播放 | 大封面、曲名/歌手、进度、歌词、音频链路、简介、视图切换、专注入口 | `np_status` / `np_lyrics_resolve` / `bio_fetch` / `audio_spec` |
| 5 | `lib` | 音乐库 | 面包屑、模式切换、两行工具栏、分页列表、详情卡、封面缩略图 | `lib_browse` / `detail_lines` / `lib_cover_id` |
| 6 | `update` | 升级与更新 | LMS 服务器配置、squeezelite/LMS 版本检查、变更日志、升级、自动更新开关 | `sq_latest` / `lms_latest` / `changelog` / `upgrade_squeezelite` |
| 7 | `help` | 帮助 | 使用说明、数据来源、许可声明 | 静态内容 |

**全局组件**：顶栏（产品名/主题三态分段/连接状态）、底栏（状态/进度/退出）、
Toast 通知、专注大屏（全屏浮层，ESC 退出、鼠标静止 3s 隐藏）。

**导航调整**（相对 Tk 版）：
- 顶栏从 64px 精简到 48px，主题分段与连接状态常驻（设计稿）。
- 「正在播放」设为默认首页（Tk 版默认是设备页）——打开即见核心体验。
- 专注大屏作为全局浮层，不属于导航栈，任意页面可唤起。
- 音乐库详情从右侧固定卡改为可折叠侧栏，窄屏可隐藏。

---

## 2. 每页数据契约与状态机

### 2.4 正在播放 `now`（阶段 1 实现目标）

**状态**（前端需维护）：
```
playerId: string | null        # 当前播放器 id
status: {mode,time,duration,volume,rate,track:{...}} | null
view: "lyrics" | "bio" | "detail" | "audio"
cover: dataURL | null
lyrics: {text,source,timed} | null
bio: {artist,album,source} | null
pollInterval: number           # 秒, 默认 2, 范围 1-15
```

**流**：
1. `api.getPlayers()` → 选 playerId（优先配置里的 `np_playerid`，否则自动选在线）。
2. `api.getStatus(playerId)` → 渲染曲名/进度/音量；track.id 变化时清 cover/lyrics/bio。
3. 并行拉取：`api.getCover(track, 420)`、`api.getLyrics(track)`、
   `api.getBio(artist, album)`、`api.getAudio(track)`。
4. 定时轮询 `getStatus`；time 前进驱动歌词逐行高亮。
5. 播放控制：`api.playControl("play"|"pause"|"next"|"prev")`。

**降级**：LMS 未连接时显示空态 + 引导到「升级与更新」页填地址，不报错弹窗。

### 2.0 设备与启动 `devices`
- `api.scanDevices()` → `{devices, reasons, binary}`；`api.setDevice(index)`；
  `api.setPlayerName(name)`；`api.start()` / `api.stop()` / `api.restart()`；
  `api.getProcLog()` 或推送 `proc:log` 事件。

### 2.1 参数 `params`
- `api.getParams()` → 分组结构 + 当前值 + 说明/推荐/范围；
  `api.setParam(key,value)`；`api.validate()` → `{ok, problems[]}`；
  `api.previewCmd()` → 命令行字符串。

### 2.2 启动脚本 `launch`
- `api.getLaunchScript()` / `api.copyCmd()` / `api.saveScript()` / `api.installAgent()`。

### 2.3 升级 `update`
- `api.getVersions()` → `{slLocal,slLatest,lmsLocal,lmsLatest}`；
  `api.getChangelog(kind)`；`api.upgrade(kind)`；`api.setLms(host,port,user,pass)`；
  `api.testLms()` → `{ok,error}`。

### 2.5 音乐库 `lib`
- `api.libBrowse(mode,start,count,filters,query)` → `{items,total}`；
  `api.libInfo(item)` → 详情行；`api.libCover(item,size)` → dataURL；
  `api.libPlay(mode,itemId)`；面包屑用前端栈维护 filters（下钻/回退）。

### 2.6 帮助 `help`
- 静态文案 + 版本信息 `api.getMeta()`。

---

## 3. Bridge API 契约（统一规范）

**命名**：`window.api.<name>(...args) -> Promise<JSON>`，
Python 侧 `@api.expose` 注册；返回值必须 JSON-serializable（dict/list/str/int/bool/None）。
封面/图片用 data URL 字符串（`data:image/png;base64,...`）。

**错误**：Python 抛异常 → bridge 转为 `{ok:false, error:"消息"}`（不 reject，便于前端统一处理）；
成功返回 `{ok:true, data:...}` 或直接 data（阶段 1 采用直接 data + 全局 error 事件，简化）。

**阶段 1 必须实现的 API 清单**（最小闭环）：
```
getMeta()               -> {version, appName, platform}
getConfig()             -> config dict (前端只读展示用)
getPlayers()            -> [{id,name,connected}]
getStatus(playerId)     -> status dict (见 2.4)
getCover(track, size)   -> dataURL | null
getLyrics(track)        -> {text,source,timed}
getBio(artist, album)   -> {artist,album,source}
getAudio(track)         -> {spec, verdict, slState}
playControl(cmd)        -> {ok}
setTheme(name)          -> {ok}         # 前端自己换 CSS 变量，API 仅持久化
```

**阶段 2 补齐**：devices/params/launch/update/lib 全部 API + 进程日志推送。

---

## 4. 设计令牌 → CSS 映射（阶段 1 直接用）

`docs/design/design-tokens.json` v1.1 转成 `:root` CSS 变量：
- `--bg` / `--surface` / `--surface2` / `--card` / `--card-border` / `--topbar`
- `--text` / `--text2` / `--text3` / `--primary` / `--on-primary` / `--brand`
- `--divider` / `--hover` / `--selected` / `--error` / `--warn` / `--ok`
- `--prog-bg` / `--prog-fg` / `--cover-pad`
- 字号 `--fs-hero:42px` `--fs-hero-focus:56px` `--fs-title:24px`
  `--fs-subtitle:17px` `--fs-body:14px` `--fs-caption:12px` `--fs-overline:10px`
- `[data-theme="dark"]` 覆盖为深色令牌（值与 THEMES["dark"] 一致）。
- 圆角/阴影/毛玻璃是 Web 新增能力（Tk 无对应令牌）：
  `--radius:12px`、`--shadow:0 8px 32px rgba(0,0,0,.12)`、
  封面卡 `backdrop-filter: blur(24px) saturate(140%)`。

---

## 5. 阶段 1 验收标准

1. pywebview 窗口启动，加载 `web/index.html`，无空白。
2. 毛玻璃封面卡、圆角、阴影在 macOS WKWebView 下真实渲染（截图确认）。
3. 8 个 bridge API 全部可从 JS 调用并返回真实 LMS 数据（连 `192.168.1.100:9000`）。
4. 主题切换：前端换 CSS 变量 + API 持久化，刷新后保持。
5. 进度/歌词随时间轴更新，播放控制按钮生效。
6. 打包体积 < 60MB；ad-hoc 签名通过；本机可启动。
