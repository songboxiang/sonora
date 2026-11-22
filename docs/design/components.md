# 组件规格 / Component Specifications

> 适用：Squeezelite GUI (tkinter/ttk)。所有色值取自 `design-tokens.json`。
> 五态 = 默认 default / 悬停 hover / 按下 pressed / 选中 selected / 禁用 disabled。
> Tk 无圆角容器（radius=0）、无阴影、无渐变、无 RGBA；边框为 1px 纯色细线。
> 中英双语标注：中文为主，英文小字注释。

---

## 通用色值对照 / Palette Reference

| 令牌 Token | 浅色 Light | 深色 Dark | 用途 |
|---|---|---|---|
| background | `#FAFAFA` | `#081F22` | 窗口底色 |
| card | `#FFFFFF` | `#0D292D` | 卡片底 |
| cardBorder | `#E0E7E3` | `#22444A` | 细边框 |
| textPrimary | `#1B2A26` | `#EAF3EF` | 主文字 |
| textSecondary | `#53655E` | `#A6BDB6` | 次文字 |
| primary | `#2F6B52` | `#7CC7A6` | 可交互主色 |
| onPrimary | `#FFFFFF` | `#081F22` | 主色上文字 |
| selected | `#E2F0EA` | `#17453E` | 选中底 |
| hover | `#EEF5F1` | `#153A3C` | 悬停底 |
| disabled | `#8E9B95` | `#6E8984` | 禁用 |
| divider | `#E4EAE7` | `#22444A` | 分隔线 |
| success / warning / error | `#3E7D62` / `#9A6100` / `#B5352B` | `#7CC7A6` / `#E9B15C` / `#F0857A` | 状态色 |

---

## 1. 顶栏 + 主题分段控件 / Topbar & Theme Segmented Control

**ttk.Style**：`Top.TFrame`（顶栏容器，需新增）、`ThemeSeg.TLabel` / `ThemeSegOn.TLabel`（已有）

| 属性 | 值 |
|---|---|
| 尺寸 Size | 高 48px；分段按钮 64×32，间距 4px |
| padding | 左右 `lg`(20px)，上下 `sm`(8px) |

五态（分段按钮 Segment）：

| 态 | 前景 fg | 背景 bg | 边框 border |
|---|---|---|---|
| 默认 default | textSecondary | topbar | cardBorder |
| 悬停 hover | textPrimary | hover | cardBorder |
| 按下 pressed | onPrimary | primary | primary |
| 选中 selected（ThemeSegOn） | primary `#2F6B52` / `#7CC7A6` | selected `#E2F0EA` / `#17453E` | primary 1px |
| 禁用 disabled | disabled | card | cardBorder |

> **已知问题修复**：旧版「只有选中项可读」→ 未选中项一律用 textSecondary（浅 5.93:1 / 深 8.60:1），保证可读。
> 中文文案示例：`浅色 Light` / `深色 Dark` / `跟随系统 Auto`

---

## 2. ttk.Notebook 标签 / Tab

**ttk.Style**：`TNotebook` / `TNotebook.Tab`（可复用系统样式，仅改色）

| 态 | 前景 | 背景 | 边框 |
|---|---|---|---|
| 默认 | textSecondary | background | — |
| 悬停 | textPrimary | hover | — |
| 选中 | primary | card | 底边 2px primary（选中指示条） |
| 禁用 | disabled | background | — |

中文文案示例：`正在播放 Now Playing` / `音乐库 Library` / `参数配置 Settings` / `音频设备 Audio Device` / `升级更新 Update` / `帮助 Help`

---

## 3. 卡片容器 / Card

**ttk.Style**：`Card.TFrame`（已有）

| 属性 | 值 |
|---|---|
| padding | `md`(12px) 内边距；卡片间距 `md` |
| 边框 | 1px cardBorder，radius=0 |

| 态 | 背景 | 边框 |
|---|---|---|
| 默认 | card | cardBorder |
| 悬停（可点击卡片） | hover | cardBorder |
| 选中 | selected | primary |
| 禁用 | card | disabled |

---

## 4. 按钮 / Button（主 / 次 / 危险）

**ttk.Style**：`Accent.TButton`（主）、`TButton`（次）、`Danger.TButton`（危险，需新增）

| 态 | 主按钮 Accent.TButton | 次按钮 TButton | 危险 Danger.TButton |
|---|---|---|---|
| 默认 | bg=primary, fg=onPrimary | bg=card, fg=textPrimary, bd=cardBorder | bg=card, fg=error, bd=error |
| 悬停 | bg=primary(加深5%) `#2A5F49`/`#6DB99A` | bg=hover | bg=`#FBEAE8`/`#3A1F1C` |
| 按下 | bg 同上, 内缩 1px | bg=selected | bg=error, fg=onPrimary(浅) |
| 选中 | — | bg=selected, fg=primary | — |
| 禁用 | bg=disabled, fg=background | fg=disabled | fg=disabled |

| 属性 | 值 |
|---|---|
| 尺寸 | 最小高 32px；padding 横向 `md`(12px) |
| 中文文案 | `播放 Play` / `暂停 Pause` / `上一曲 Prev` / `下一曲 Next` / `删除 Remove` |

> **已知问题修复**：「下一曲 Next」曾溢出窗口 → 三列播放控制区用等宽 `grid` + `uniform` 分组，按钮 `sticky='ew'`，不设固定宽。

---

## 5. 输入框 / Entry

**ttk.Style**：`TEntry`

| 态 | 前景 | 背景 | 边框 |
|---|---|---|---|
| 默认 | textPrimary | card | cardBorder |
| 悬停 | textPrimary | card | textSecondary |
| 聚焦（按下态对应） | textPrimary | card | primary 1px |
| 选中（选中文本） | onPrimary | primary（选中高亮） | — |
| 禁用 | disabled | hover | cardBorder |

中文文案示例（占位符）：`输入服务器地址 Server address`

---

## 6. 下拉 / Combobox

**ttk.Style**：`TCombobox`

五态同 Entry；下拉弹层背景 = card，列表项选中 = selected + primary 前景。

---

## 7. 进度条 / Progressbar（含拖拽定位）

**ttk.Style**：`TProgressbar`（`Horizontal.TProgressbar`）

| 态 | troughColor（底槽） | 填充色 |
|---|---|---|
| 默认 | progressTrack `#DCE5E0` / `#22444A` | progressFill = brandDecorative `#589E81` / `#6CAC92` |
| 悬停 | progressTrack | brandDecorative（拇指 hover 加深） |
| 按下/拖拽 | progressTrack | primary `#2F6B52` / `#7CC7A6` |
| 禁用 | divider | disabled |

> 填充用 Lyrion 品牌色（图形对比 3.04/6.47，满足图形 ≥3.0）。

---

## 8. Treeview 行 / Library Row

**ttk.Style**：`Treeview` / `Treeview.Heading` / `Item.Treeview`（行，需新增）

| 态 | 前景 | 背景 | 说明 |
|---|---|---|---|
| 默认 | textPrimary | card | 行高 56px |
| 悬停 | textPrimary | hover | — |
| 按下 | textPrimary | selected | — |
| 选中 | onPrimary（浅）/ textPrimary（深） | primary（浅 `#2F6B52`）/ selected（深 `#17453E`） | 选中行 |
| 禁用 | disabled | card | — |

> 封面列：44×44 正方形 PNG，统一裁切（`subsample`/`zoom` 保持正方形，禁止拉伸变形）。

---

## 9. 标签 / 徽章 / Badge

**ttk.Style**：`Ok.TLabel` / `Warn.TLabel` / `Error.TLabel`（已有）、`Badge.TLabel`（需新增）

| 态 | 前景 | 背景 |
|---|---|---|
| 默认（Ok） | success | transparent→用 card 实色 |
| 默认（Warn） | warning | card |
| 默认（Error） | error | card |
| 徽章 Badge | onPrimary | primary |

中文文案：`直通 Bit-perfect` / `已转码 Transcoded` / `需密码 Auth required`

---

## 10. 滚动条 / Scrollbar

**ttk.Style**：`TScrollbar`

| 态 | 滑块 | 底槽 |
|---|---|---|
| 默认 | cardBorder | background |
| 悬停 | textSecondary | background |
| 按下 | primary | background |
| 禁用 | disabled | background |

---

## 11. 状态提示 / Status Toast

**ttk.Style**：`Status.TLabel`（需新增）+ 1px 边框容器

| 态 | 前景 | 背景 | 边框 |
|---|---|---|---|
| 信息 Info | textPrimary | card | divider |
| 成功 Success | success | card | success |
| 警告 Warn | warning | card | warning |
| 错误 Error | error | card | error |

---

## 12. 模态弹窗 / Modal Dialog

**ttk.Style**：`Toplevel`（系统窗口）+ `Card.TFrame` 内容

| 态 | 前景 | 背景 |
|---|---|---|
| 标题 | textPrimary | topbar |
| 正文 | textPrimary | card |
| 遮罩 | 无 RGBA → 用纯色 background 覆盖，不透明 | — |

中文文案示例：`需要密码 Authentication required` / `服务器返回 401 Server returned 401`

---

## 13. 分隔线 / Separator

**ttk.Style**：`TSeparator`

1px divider，占满容器宽；无态变化。

---

## 14. 播放控制三列区 / Transport Controls

**ttk.Style**：`Tool.TButton`（已有，次按钮语义）

| 态 | 前景 | 背景 |
|---|---|---|
| 默认 | textPrimary | card |
| 悬停 | primary | hover |
| 按下 | onPrimary | primary |
| 选中 | primary | selected |
| 禁用 | disabled | card |

布局：三列等宽 `grid`，列权重 `uniform='transport'`，图标 24px PNG + 中文小字，禁止固定宽度（防溢出）。
