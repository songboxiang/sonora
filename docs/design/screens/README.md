# 屏幕设计稿 / Screens

> 5 张高保真线框稿，全部导出为 **1120 × 760 PNG**（APP 最小窗口尺寸）。
> 遵循 tkinter/ttk 硬约束：纯色、1px 细边框、圆角=0、无阴影/渐变/半透明。
> 文案中英双语（中文为主 + 英文小字注释）。封面为占位块（待用 PNG 资源替换）。
> **v1.1 风格强化**：向 LMS Material 皮肤 + Audirvana 靠拢——英文/数字改 Roboto 字形、曲名放大（播放页 42px / 专注页 56px）、进度条加厚至 8px、卡片去边框改 surface 浅底、深色封面占位改深底。

| 文件 File | 页面 Screen | 主题 Theme | 尺寸 Size |
|---|---|---|---|
| `01-now-playing-light.png` | 正在播放 Now Playing | 浅色 Light | 1120×760 |
| `02-now-playing-dark.png` | 正在播放 Now Playing | 深色 Dark | 1120×760 |
| `03-library-light.png` | 音乐库 Library | 浅色 Light | 1120×760 |
| `04-focus-mode.png` | 专注大屏 Focus Mode | 深色（全屏）Dark | 1120×760 |
| `05-settings-light.png` | 参数配置 Settings | 浅色 Light | 1120×760 |

---

## 通用布局基准 / Global Layout Baseline

- **顶栏 Topbar**：y=0，高 48px，底=topbar 色，1px 分隔线。
- **标签栏 Tabs**：y=48，高 40px；选中项底部 3px primary 指示条（Material 下划线）；1px 分隔线在 y=87。
- **内容区 Content**：y=88 起，高 672px。
- **主题分段 ThemeSeg**：右上角 280×32，三段各约 90px；选中项 selected 底 + primary 1px 边框。
- **页边距**：左右 20–32px（`lg`）。
- **卡片间距**：12px（`md`）；卡片内边距 12px；1px cardBorder，radius=0。
- **字体**：Noto Sans SC（画布预览）；落地用系统字体（macOS PingFang SC / Linux Noto Sans CJK SC）。

## 01 / 02 正在播放 Now Playing

- 左区 660px + 右区 460px 分栏。
- 大封面 **272×272**（x=32, y=116 相对内容区），正方形。
- 曲名 hero **42px bold**（Audirvana 大字层级，v1.1 由 40 放大）；副标题 18px；英文元数据 14px Roboto。
- 进度条：宽 596px，高 **8px**（v1.1 由 6 加厚），填充色用 Lyrion 品牌色 `#589E81`/`#6CAC92`。
- 音频链路卡：v1.1 去边框改 surface 浅底（浅 `#F5F8F6` / 深 `#0F2C2F`），Material 以面而非线分区。
- 深色封面占位：v1.1 由白底图改深底 `#12332F` + 1px 边框 + 居中浅灰标注，消除深底白斑。
- 播放控制三列区：宽 596px，三按钮各 150px，列间距 33px，等宽分布（对应 Tk `uniform` 网格），「下一曲」不溢出。
- 音频链路卡片：596×150，含 bit-perfect（success）与已转码（warning）双徽章。
- 右区：视图切换（歌词/专辑详情/歌手简介）36px 高 + 歌词卡 428×440（行高：普通 14px / 高亮 17px bold）+ 状态栏 428×120（含音量条）。
- 深浅差异：背景 `#FAFAFA`↔`#081F22`，卡片 `#FFFFFF`↔`#0D292D`，主文字 `#1B2A26`↔`#EAF3EF`，主色 `#2F6B52`↔`#7CC7A6`。

## 03 音乐库 Library

- 面包屑（y=100）→ 工具栏行1（y=132, 36px）→ 工具栏行2（y=172, 32px）→ 表头（y=212, 32px）→ 列表行（每行 **56px**，5 行示例）。
- 工具栏两行布局：行1 搜索/筛选/排序/视图；行2 艺术家/专辑/曲目筛选 + 计数。
- Treeview 列表宽 700px：44×44 正方形封面列 + 标题 + 艺术家 + 时长列；选中行 selected 底 + primary 曲名；窄窗口下图片段有横向滚动条。
- 右侧详情卡 364×520：280×280 详情封面 + 曲名 24px + 元数据 + 「加入播放」主按钮。
- 底部状态 "显示 5 / 1,248 首"。

## 04 专注大屏 Focus Mode

- 全屏深色 `#081F22`；420×420 大封面居中（x=350, y=110）。
- 曲名 **56px bold 居中**（v1.1 由 40 放大，Audirvana 沉浸大字）+ 歌手 19px 居中 + 进度条 800×8 + 时间 + 操作提示。
- 退出按钮右上角 80×36（primary 底）：鼠标移动显示、静止 3 秒隐藏、ESC 退出。
- 封面/文字全部居中对齐（`textAlignHorizontal: CENTER`）。

## 05 参数配置 Settings

- 左侧分组导航 200×590（服务器/播放/音频/歌词/界面/高级/关于），选中项 selected 底 + primary 文字。
- 右侧表单 856×590：小节标题 17px + 参数行（标签 250px + 控件 400px）。
- 控件类型覆盖：输入框、下拉、开关（开=primary／关=divider）、密码掩码。
- 「还有 18 项参数·向下滚动」提示体现 27 项可滚动；底部重置/保存按钮。
- 开关滑块：开 x=26 / 关 x=3（26px 轨道内）。

---

## 落地注意 / Handoff Notes

1. PNG 为预览稿，尺寸标注见上；落地时按 `mapping.md` 把令牌映射到 `C[]` 与 `ttk.Style`。
2. 封面占位块替换为 `icons-assets.md` 定义的正方形 PNG（44/272/280/420）。
3. 播放控制等宽列、工具栏两行、封面正方形是三条易回归失败的约束，见 `checklist.md`。
