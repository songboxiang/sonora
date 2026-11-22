# 令牌映射 / Token → App Mapping（最关键）

> 把每个设计令牌 / 组件映射到 Squeezelite GUI 的具体落点：
> `C[...]` 色板键、`ttk.Style` 名、`_apply_theme()` 字典、具体方法。
> 无对应物的标注 **需新增**。已知现有样式：`Hero.TLabel` / `Muted.TLabel` / `Ok.TLabel` / `Warn.TLabel` / `Card.TFrame` / `ThemeSeg.TLabel` / `ThemeSegOn.TLabel` / `Tool.TButton` / `Accent.TButton`（取自 `squeezelite_gui.py`）。

---

## 一、颜色令牌 → C[] 色板 / 主题字典

| 设计令牌 Token | 浅色值 | 深色值 | C[] 键（落点） | _apply_theme 字典 | 备注 |
|---|---|---|---|---|---|
| background | `#FAFAFA` | `#081F22` | `C['bg']` | 浅/深两套 | 需确认现有键名，若无则新增 |
| topbar | `#FFFFFF` | `#0D292D` | `C['topbar']` | 浅/深两套 | 需新增 |
| card | `#FFFFFF` | `#0D292D` | `C['surface']` | 浅/深两套 | 已有 `surface` 概念，核对键名 |
| cardBorder | `#E0E7E3` | `#22444A` | `C['border']` | 浅/深两套 | 需新增 |
| textPrimary | `#1B2A26` | `#EAF3EF` | `C['fg']` | 浅/深两套 | 已有 `fg` |
| textSecondary | `#53655E` | `#A6BDB6` | `C['muted']` | 浅/深两套 | 对应 `Muted.TLabel` |
| primary | `#2F6B52` | `#7CC7A6` | `C['accent']` | 浅/深两套 | 可交互主色（加深版） |
| onPrimary | `#FFFFFF` | `#081F22` | `C['on_accent']` | 浅/深两套 | 需新增 |
| brandDecorative | `#589E81` | `#6CAC92` | `C['brand']` | 浅/深两套 | Lyrion 原色，进度条填充 |
| success | `#3E7D62` | `#7CC7A6` | `C['ok']` | 浅/深两套 | 对应 `Ok.TLabel` |
| warning | `#9A6100` | `#E9B15C` | `C['warn']` | 浅/深两套 | 对应 `Warn.TLabel` |
| error | `#B5352B` | `#F0857A` | `C['error']` | 浅/深两套 | 需新增 error 键 |
| selected | `#E2F0EA` | `#17453E` | `C['selected']` | 浅/深两套 | 对应 `ThemeSegOn.TLabel` |
| hover | `#EEF5F1` | `#153A3C` | `C['hover']` | 浅/深两套 | 需新增 |
| disabled | `#8E9B95` | `#6E8984` | `C['disabled']` | 浅/深两套 | 需新增 |
| divider | `#E4EAE7` | `#22444A` | `C['divider']` | 浅/深两套 | 需新增 |
| progressTrack | `#DCE5E0` | `#22444A` | `C['prog_bg']` | 浅/深两套 | 需新增 |
| progressFill | `#589E81` | `#6CAC92` | `C['prog_fg']` | 浅/深两套 | 需新增 |

---

## 二、字号层级 → ttk.Style

| 令牌 | px / 字重 | 落点 | 现有/新增 |
|---|---|---|---|
| hero | 42 bold | `Hero.TLabel` + `-font ('', 42, 'bold')` | 已有（v1.1 由 40 调至 42） |
| heroFocus | 56 bold | `HeroFocus.TLabel` + `-font ('', 56, 'bold')` | v1.1 新增（专注大屏曲名） |
| title | 24 bold | `Title.TLabel` | 需新增 |
| subtitle | 17 normal | `Subtitle.TLabel` | 需新增 |
| body | 14 normal | 默认 `TLabel` | 已有 |
| caption | 12 normal | `Caption.TLabel` | 需新增 |
| overline | 10 bold | `Overline.TLabel` | 需新增 |

> **字体基准（v1.1 风格强化）**：英文/数字（时间、时长、元数据、overline、AppName）基准字体为 **Roboto**（Material Design 官方字体）；中文及中英混排用 **Noto Sans SC**。Tk 不能内置字体文件，落地时统一回退系统 sans：macOS `-apple-system`/`PingFang SC`、Linux `Noto Sans CJK SC`；版式按上表 px 层级即可，不需要随附字体文件。

---

## 三、组件 → ttk.Style 落点

| 组件 | ttk.Style 名 | 现状 | 落点说明 |
|---|---|---|---|
| 顶栏 | `Top.TFrame` | 需新增 | 容器背景 = topbar |
| 主题分段（未选） | `ThemeSeg.TLabel` | 已有 | fg=muted（修复「只有选中可读」） |
| 主题分段（选中） | `ThemeSegOn.TLabel` | 已有 | fg=accent, bg=selected, bd=accent |
| Notebook | `TNotebook` / `TNotebook.Tab` | 系统默认 | 改 tab 色：选中 fg=accent, 底边 2px |
| 卡片 | `Card.TFrame` | 已有 | bg=card, bd=1px border |
| 主按钮 | `Accent.TButton` | 已有 | bg=accent, fg=on_accent |
| 次按钮 | `Tool.TButton` | 已有 | bg=card, fg=fg |
| 危险按钮 | `Danger.TButton` | 需新增 | fg=error, bd=error |
| 输入框 | `TEntry` | 系统默认 | fieldbackground=card, 聚焦 bd=accent |
| 下拉 | `TCombobox` | 系统默认 | 同 Entry |
| 进度条 | `Horizontal.TProgressbar` | 系统默认 | troughColor=prog_bg, background=prog_fg |
| Treeview 行 | `Item.Treeview` | 需新增 | 行高 56；选中 bg=accent(浅)/selected(深) |
| 状态标签 Ok | `Ok.TLabel` | 已有 | fg=ok |
| 状态标签 Warn | `Warn.TLabel` | 已有 | fg=warn |
| 状态标签 Error | `Error.TLabel` | 需新增 | fg=error |
| 徽章 | `Badge.TLabel` | 需新增 | bg=accent, fg=on_accent |
| 滚动条 | `TScrollbar` | 系统默认 | trough=background, 滑块=border |
| 状态提示 | `Status.TLabel` | 需新增 | 按 info/success/warn/error 配 fg/bd |
| 分隔线 | `TSeparator` | 系统默认 | 1px divider |
| 模态弹窗 | `Toplevel` + `Card.TFrame` | 系统默认 | 内容用卡片样式 |

---

## 四、方法级落点 / Method Hooks

| 变更 | 需同步修改的方法 | 说明 |
|---|---|---|
| 换肤整体刷新 | `_apply_theme()` | 浅/深字典灌入 C[]；`ttk.Style.configure` 全量更新 |
| 正在播放页换肤后 | `_np_after_theme()` | 刷新封面占位、进度条、歌词视图颜色 |
| 专注页换肤后 | `_focus_theme()` | 刷新专注大屏底色与退出按钮 |
| 封面正方形 | 封面加载函数（需新增统一裁切） | 44/272/280/420 统一裁切为正方形 |
| 工具列两行 | 音乐库布局函数 | `grid` 两行工具栏 |
| 三列控制不溢出 | 播放控制布局函数 | `uniform='transport'` + `sticky='ew'` |
| 专注 ESC/Motion/3s | 专注模式事件绑定 | `after(3000)` 隐藏，Motion 唤出，Esc 退出 |

---

## 五、需要新增的清单 / To-Create List

- `C[]` 键：`topbar`, `border`, `on_accent`, `brand`, `error`, `hover`, `disabled`, `divider`, `prog_bg`, `prog_fg`（若现有无对应）
- `ttk.Style`：`Top.TFrame`, `Title.TLabel`, `Subtitle.TLabel`, `Caption.TLabel`, `Overline.TLabel`, `Danger.TButton`, `Item.Treeview`, `Error.TLabel`, `Badge.TLabel`, `Status.TLabel`
- PNG 图标：见 `icons-assets.md`（浅深两套）
- 统一封面裁切函数、专注模式换肤钩子
