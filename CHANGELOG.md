# Changelog

本项目遵循语义化版本：发布时同步更新 `squeezelite_gui.py` 中的 `VERSION`
常量，并打附注标签 `vX.Y.Z`。

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
