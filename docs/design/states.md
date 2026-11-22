# 状态矩阵 / State Matrix

> 主题（浅 Light / 深 Dark / 跟随系统 Auto）× 各业务状态。
> 主题为全局正交维度：Auto 在运行时读取系统主题，整体调用 `_apply_theme()` 刷新，下列所有状态色值均随主题切换为对应浅/深列。
> 每个状态给出：文案、颜色令牌、控件可见性、加载指示、可恢复操作。

---

## 主题维度 / Theme Axis

| 主题 Theme | 说明 | 落点 |
|---|---|---|
| 浅 Light | 强制浅色板 | `C` 浅字典 |
| 深 Dark | 强制深色板 | `C` 深字典 |
| 跟随系统 Auto | 运行时读系统外观，切换时整体重绘 | `_apply_theme()` + 系统通知；换肤刷新列表同步 `_np_after_theme()` / `_focus_theme()` |

---

## 播放态 / Playback States

| 状态 | 中文文案 / English | 颜色令牌 | 控件可见性 | 加载指示 | 恢复操作 |
|---|---|---|---|---|---|
| 播放中 Playing | 播放中 / Playing | primary, 进度 progressFill | 播放按钮→暂停图标；进度条推进 | 无 | — |
| 暂停 Paused | 已暂停 / Paused | textSecondary | 暂停→播放图标；进度静止 | 无 | 点播放 |
| 停止 Stopped | 已停止 / Stopped | textSecondary | 进度归零，封面可用占位 | 无 | 点播放 |

## 加载与错误 / Loading & Error

| 状态 | 文案 | 颜色令牌 | 控件可见性 | 加载指示 | 恢复操作 |
|---|---|---|---|---|---|
| 加载中 Loading | 载入中… / Loading… | textSecondary | 内容区显示骨架/占位封面 | 进度条不确定态 (mode='indeterminate') | 自动 |
| 网络错误 Network error | 无法连接服务器 / Cannot reach server | error | 内容区替换为错误提示 | 无 | `重试 Retry` 按钮 |
| 401 需密码 | 需要密码 / Authentication required | warning | 弹出模态密码框 | 无 | 输入密码 → 提交；`取消 Cancel` |

## 内容空态 / Empty Content

| 状态 | 文案 | 颜色令牌 | 控件可见性 | 加载指示 | 恢复操作 |
|---|---|---|---|---|---|
| 空曲库 Empty library | 曲库为空 / Library is empty | textSecondary | Treeview 隐藏，显示空态插画+文案 | 无 | `刷新 Refresh` |
| 无歌词 No lyrics | 暂无歌词 / No lyrics available | textSecondary | 歌词视图显示提示 | 无 | — |
| 无封面 No cover | 无封面 / No cover art | textSecondary | 显示统一占位封面（正方形） | 无 | — |
| 无简介 No bio | 暂无简介 / No biography | textSecondary | 简介视图显示提示 | 无 | — |

## 导航与音频链路 / Navigation & Audio Path

| 状态 | 文案 | 颜色令牌 | 控件可见性 | 加载指示 | 恢复操作 |
|---|---|---|---|---|---|
| 专辑下钻 Drill-down | 面包屑：音乐库 › 歌手 › 专辑 | textSecondary/primary | 面包屑 + 返回按钮显示 | 无 | 点面包屑返回 |
| bit-perfect 直通 | 直通 Bit-perfect | success | 音频链路卡片徽章=成功色 | 无 | — |
| 已转码警告 Transcoded | 已转码 / Transcoded (重采样) | warning | 音频链路卡片徽章=警告色 | 无 | 查看详情 |
| 待确认 Pending | 待确认 / Awaiting confirmation | warning | 按钮禁用或显示确认弹窗 | 无 | 确认 / 取消 |

## 专注大屏 / Focus Mode

| 状态 | 文案 | 颜色令牌 | 控件可见性 | 加载指示 | 恢复操作 |
|---|---|---|---|---|---|
| 显示退出按钮 | 退出专注 / Exit focus (ESC) | onPrimary on primary | 鼠标移动后显示 120ms 淡入（ without alpha → 直接显示） | 无 | 点按钮 / ESC |
| 隐藏退出按钮 | — | — | 静止 3s 后隐藏 (`after(3000)`) | 无 | 移动鼠标唤出 |

## 窄窗口 / Narrow Window

| 状态 | 文案 | 颜色令牌 | 控件可见性 | 加载指示 | 恢复操作 |
|---|---|---|---|---|---|
| 1120×760 最小 | — | — | 全部内容不溢出；播放三列用 uniform grid；工具栏两行；Treeview 横向滚动条 | 无 | 窗口小于最小值时限制 `minsize(1120,760)` |
