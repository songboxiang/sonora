# Changelog

本项目遵循语义化版本：发布时同步更新 `squeezelite_gui.py` 中的 `VERSION`
常量，并打附注标签 `vX.Y.Z`。

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
