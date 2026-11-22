# Sonora 颂诺 · Web 版（v2.0.0）

高保真音乐播放器 —— pywebview 渲染层重构版本。相对 Tk 版（v1.6.0，
见仓库根目录）是一次**大版本升级**：渲染层换成 HTML/CSS，实现毛玻璃、
圆角、阴影、渐变与精细字体抗锯齿；Python 逻辑层原样复用 Tk 版纯函数。

## 在 macOS 上手动测试（三步）

1. 克隆 / 更新本仓库，进入本目录：
   ```
   cd squeezelite-gui/sonora-web
   ```
2. 双击 `run_mac.command`（或终端执行 `bash run_mac.command`）。
   - 首次运行会自动创建 `.venv` 并安装 `pywebview` / `Pillow`（需联网一次）；
   - 之后启动无需联网。
3. 应用窗口弹出后，在「服务器设置」里填入你的 LMS 地址（默认读取 Tk 版
   已有配置），即可用真实 LMS 数据测试音乐库、播放、歌词、收藏等全部功能。

> 需要 Python 3.9+（python.org 官方版或 `brew install python`）。
> pywebview 使用 macOS 系统自带的 WKWebView，不打包浏览器内核。

## 命令行运行（开发者）

```
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

调试模式：`SQWEB_DEBUG=1 python3 main.py`

## 目录结构

```
sonora-web/
├── main.py                     pywebview 窗口入口
├── requirements.txt            运行依赖
├── run_mac.command             macOS 一键启动脚本
├── backend/
│   ├── legacy_core.py          Tk v1.6.0 原样复用的纯函数（LMS RPC 等）
│   └── api.py                  Bridge API（JS 可调用，45+ 方法）
├── web/
│   ├── index.html              单页界面结构
│   ├── tokens.css / app.css    设计令牌与基础样式
│   ├── refine.css / refine2.css / refine3.css / refine4.css  视觉精修层
│   └── app.js                  前端交互逻辑
├── build_preview.py            生成离线预览 preview.html（mock 数据）
├── docs/IA.md                  信息架构与 API 契约
└── README.md / CHANGELOG.md    本文件与更新日志
```

## 功能一览（v2.0.0）

- 音乐库：专辑 / 艺术家 / 音乐 / 流派四类，网格⇄列表、排序、搜索、首字母跳转、真实封面
- 播放器：大封面毛玻璃、歌词 / 简介 / 详情、LED 规格屏、mini 播放器、专注大屏模式
- 播放列表：队列 + 命名列表、下钻浏览、右键菜单、收藏体系（固定「♥ 收藏」列表，收藏自动加入/移除）
- 交互：面板拖拽缩放（双击复位）、音乐库就地播放列表抽屉、新建/删除列表、播放模式、音量控制
- 设置：服务器 / 播放器引擎 / 参数配置 / 升级更新 / 帮助、明暗主题
- Bridge：45+ JS 可调用 API，真实 LMS 双向数据互通

## 版本历史

见同目录 `CHANGELOG.md`。Tk 版 v1.x 历史见仓库根目录 `CHANGELOG.md` 与 git tags。

## 封装成独立 macOS App（无需终端、无需预装 Python）

本目录提供两种把 Web 版变成真正 `.app` 的方式：

### 方式 A：一键封装（推荐，最终形态）
在 macOS 上执行：
```
bash build_app.sh
```
它会用 PyInstaller 把 Python 运行时 + 依赖全部打包，产物
`~/Applications/Sonora 颂诺.app`：双击即用、**无终端窗口、无需预装 Python、
无需联网**（构建时需联网一次装 pyinstaller / pywebview / Pillow）。
若首次被 Gatekeeper 拦截，执行 `xattr -cr "$HOME/Applications/Sonora 颂诺.app"`。

### 方式 B：文本型 App（随包附带，改源码方便）
压缩包里附带的 `Sonora 颂诺.app` 是标准 app 结构，launcher 指向
`Contents/Resources` 里的源码。双击图标启动，首次自动建 `.venv` 并装依赖
（需联网一次）。适合想直接改 `web/*.js` / `*.css` 调试的场景：
源码就在 `Contents/Resources/web/`，改完重开即可生效，无需重新打包。
若被 Gatekeeper 拦截：`xattr -cr "Sonora 颂诺.app"`。
