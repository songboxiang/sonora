# Squeezelite GUI · UI 设计交付包

> 基于 `docs/UI_DESIGN_BRIEF.md`（v1.5.1）产出的完整视觉设计交付物。
> 技术基线：Python tkinter/ttk 单文件桌面应用（macOS Tk 9 / Linux Tk 8.6）。
> 风格基准：Lyrion Material Skin（主色 `#589E81`/`#6CAC92`）+ Audirvana 大字层级。
> 界面语言：简体中文为主 + 英文元数据（中英双语标注）。
> **当前版本 v1.1（风格强化）**：进一步向 LMS Material 皮肤 + Audirvana 靠拢——英文/数字采用 Roboto、中文 Noto Sans SC；曲名放大（播放 42px / 专注 56px）；进度条加厚 8px；卡片去边框改 surface 浅底；修复深色封面占位白底。Change log 见 `design-tokens.json → $meta.v1.1Note`。

## 交付物清单（7 项）

| # | 文件 | 内容 |
|---|---|---|
| 1 | `design-tokens.json` | 浅/深两套颜色（全部 `#RRGGBB` + WCAG 对比度）、字号层级、间距、边框、控件高度、封面尺寸 44/272/280/420、动效毫秒数 |
| 2 | `components.md` | 每个组件的 `ttk.Style` 名、尺寸/padding、五态色值、交互反馈、中文文案 |
| 3 | `screens/` | 5 张 1120×760 设计稿 PNG（正在播放浅/深、音乐库、专注大屏、参数配置）+ 尺寸标注 `README.md` |
| 4 | `states.md` | 状态矩阵：浅/深/跟随系统 × 播放/加载/401/空曲库/无歌词/无封面/无简介/下钻/bit-perfect/转码/专注显隐/窄窗口 |
| 5 | `icons-assets.md` | 图标清单、16/24/32px、浅深两套 PNG、导出规范、ICNS 7 尺寸 |
| 6 | `mapping.md` | **最关键**：令牌 → `C[]` 色板 / `ttk.Style` / 方法落点，无对应物标注「需新增」 |
| 7 | `checklist.md` | 可逐条打勾的验收清单（对比度、三态、窄窗口、封面正方形、ESC 退出、下一曲不裁切等） |

## 核心设计决策

1. **主色拆分**：Lyrion 原色 `#589E81` 在浅底上仅 3.04:1，不满足正文 AA。因此保留为 `brand.decorative`（进度条填充、图标点缀），可交互主色改用加深的浅 `#2F6B52`（6.28:1 白字）／深 `#7CC7A6`（8.60:1 深字）。
2. **深色卡片色** 用 Lyrion 弹层色 `#0D292D`，与深底 `#081F22` 形成克制的层次差，边框 `#22444A`。
3. **radius = 0**：所有容器直角 + 1px 细边框，严格贴合 Tk 能力，不画圆角/阴影/渐变。
4. **三态主题正交**：Auto 运行时读系统外观，整体调用 `_apply_theme()` 重绘；未选中项用 muted 色保证可读（修复旧版「只有选中项可读」）。

## 落地步骤（开发方拿到后）

1. **灌令牌** → 校验 `design-tokens.json`，把色值灌进 `C` 色板的浅/深两套字典与 `_apply_theme()`。
2. **改样式** → 按 `mapping.md` 新增/调整 `ttk.Style`（`Hero.TLabel`、`Card.TFrame`、`ThemeSeg*`、`Danger.TButton`、`Item.Treeview` 等），同步 `_np_after_theme()` / `_focus_theme()`。
3. **调布局** → 按 `screens/` 调整容器尺寸、`grid/pack`、封面常量（44/272/280/420）、工具栏两行、三列控制区不溢出。
4. **补状态** → 按 `states.md` 补齐空态/错误/加载态文案与颜色。
5. **回归 + 同步 .app** → 逻辑测试 + X11 真实 GUI 实例化（几何/三态/封面正方形/ESC/Motion/3s 隐藏）+ macOS Tk 9 冒烟，然后同步 `.app`、重签名、提交版本。

## 禁止项（本交付包已遵守）

- 无 React/Vue/CSS/Tailwind 代码；无仅 Figma 的自动布局描述（全部固定像素）。
- 无半透明、阴影、模糊、渐变、圆角容器、自定义字体文件。
- 无未标注尺寸的效果图（所有 PNG 均 1120×760 且附尺寸说明）。
- 无第三方图标库引用（图标用纯 Python 生成 PNG/ICNS，避免许可风险）。
