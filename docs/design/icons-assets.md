# 图标与资源清单 / Icons & Assets

> 约束：图标只能是 PNG（`tk.PhotoImage`）。矢量需导出 PNG。
> 导出要求：透明背景（Tk 支持 PNG alpha 作为图标，但**界面表面**不得用半透明）；不含文字；无抗锯齿白边；浅深两套分别导出。
> 生成方式：纯 Python `assets/make_icon.py`（Pillow 不引入；用标准库或预生成），不引用第三方图标库（许可风险）。
> 中英双语：图标语义中英对照。

---

## 图标清单 / Icon Inventory

| 名称 Name | 语义 Meaning | 尺寸 px | 浅色文件 Light | 深色文件 Dark | 用途 |
|---|---|---|---|---|---|
| `play` | 播放 Play | 16/24/32 | `play_l.png` | `play_d.png` | 播放控制、工具栏 |
| `pause` | 暂停 Pause | 16/24/32 | `pause_l.png` | `pause_d.png` | 播放控制 |
| `prev` | 上一曲 Previous | 16/24/32 | `prev_l.png` | `prev_d.png` | 播放控制 |
| `next` | 下一曲 Next | 16/24/32 | `next_l.png` | `next_d.png` | 播放控制 |
| `stop` | 停止 Stop | 24 | `stop_l.png` | `stop_d.png` | 播放控制 |
| `shuffle` | 随机 Shuffle | 24 | `shuffle_l.png` | `shuffle_d.png` | 播放模式 |
| `repeat` | 循环 Repeat | 24 | `repeat_l.png` | `repeat_d.png` | 播放模式 |
| `volume` | 音量 Volume | 16/24 | `volume_l.png` | `volume_d.png` | 音量条 |
| `cover_placeholder` | 无封面占位 | 44/272/280/420 | `cover_l.png` | `cover_d.png` | 无封面时 |
| `folder` | 文件夹/下钻 Folder | 16 | `folder_l.png` | `folder_d.png` | Treeview |
| `artist` | 歌手 Artist | 16 | `artist_l.png` | `artist_d.png` | 音乐库 |
| `album` | 专辑 Album | 16 | `album_l.png` | `album_d.png` | 音乐库 |
| `settings` | 设置 Settings | 24 | `settings_l.png` | `settings_d.png` | Notebook 标签 |
| `update` | 升级 Update | 24 | `update_l.png` | `update_d.png` | Notebook 标签 |
| `help` | 帮助 Help | 24 | `help_l.png` | `help_d.png` | Notebook 标签 |
| `audio_device` | 音频设备 Audio device | 24 | `audio_l.png` | `audio_d.png` | Notebook 标签 |
| `focus` | 专注模式 Focus mode | 24 | `focus_l.png` | `focus_d.png` | 工具栏 |
| `exit` | 退出 Exit | 24 | `exit_l.png` | `exit_d.png` | 专注大屏浮出按钮 |
| `check` | 成功 Check | 16 | `check_l.png` | `check_d.png` | 状态徽章 |
| `warning` | 警告 Warning | 16 | `warning_l.png` | `warning_d.png` | 状态徽章 |

---

## 导出规范 / Export Spec

- 背景：透明（RGBA 仅用于图标本身，非界面表面）。
- 着色：浅色版用浅色板前景色（如 `#1B2A26`），深色版用深色板前景色（如 `#EAF3EF`）；主色图标用 primary `#2F6B52` / `#7CC7A6`。
- 抗锯齿：导出后检查边缘无白边；1px 描边对齐像素网格。
- 命名：`<name>_<l|d>_<size>.png`，例：`play_l_24.png`。

---

## Logo / App 图标规格 / App Icon Spec

| 项 | 规格 |
|---|---|
| 源图 | 1024×1024 PNG，纯色背景 + 音符/波形主形 |
| macOS ICNS | 7 尺寸：16, 32, 128, 256, 512 (+ 1024)，打包为 `.icns` |
| 浅/深 | App 图标单一版本即可（不随主题）；界面内 logo 用浅深两套 |
| 生成 | `assets/make_icon.py` 纯 Python 生成，输出 `assets/appicon.icns` |

> 中英标注示例：界面内 logo 下方小字 `Squeezelite GUI · 高保真播放器 / Hi-Res Player`
