# Sonora v2 架构设计（草案）

状态：待评审。基于 2026-11-27 对 LMS 9.1.1 的实测，以及对 v1 失败原因的复盘。

## 1. 已验证的事实（不是推测）

环境：LMS 192.168.199.2:9000，Lyrion 9.1.1；VM macOS 27.2.1 / Flutter 3.35.7 / Xcode 27.2。

| 事实 | 证据 |
|---|---|
| LMS 启用 Basic Auth，空凭证被拒 | GET/POST 无 Authorization 均返回 401，头 `WWW-Authenticate: Basic realm="Lyrion Music Server"` |
| 旧版配置里有正确凭证 | `~/.squeezelite_gui/config.json`：`lms_user=songboxiang`、`lms_pass` 已设置、`lms_port=9000` |
| 带正确凭证 POST 可通 | version / players / serverstatus 均 HTTP 200 |
| v1 的 ping 判断字段错误 | version 返回 `result._version`，v1 检查 `containsKey("version")` → 永远 false → 连接必失败 |
| GET 与 POST 行为不同 | GET `/jsonrpc.js` 返回 401 HTML；POST 带凭证返回 JSON。v1 混淆了两者 |
| LMS 当前没有任何播放器 | `players 0 10` → `count:0`；`serverstatus` → `player count:0`，且无 `players_loop` 字段 |
| 旧播放器 ID 已失效 | 保存的 `02:00:00:00:00:00` 发 status → 服务端直接断开连接 |
| 旧版不内置播放器 | 旧版是 tkinter GUI，负责启动/管理独立的 squeezelite 进程；**v2 必须把核心打包进 app 并自动拉起**，不应让用户手动启动 |

结论：v1 连不上是**两个独立缺陷叠加**——协议字段判断错误（代码 bug）+ 无播放器可用（环境事实）。只修前者仍然连不上；只修后者也过不了连接页。

v2 的修正：出厂核心随 bundle 打包，首次启动自动复制到用户可写目录并拉起子进程。播放器注册失败属于核心启动/诊断链路问题，不再是「用户请手动启动 squeezelite」这种人工步骤。

## 2. 设计目标

1. **连接必须可诊断**：每一层失败给出明确原因，不允许"连接失败"这种笼统提示。
2. **播放器是一等公民**：没有播放器时给出可操作指引，而不是假装连上后静默失败。
3. **协议层可离线验证**：用真实响应做 fixture，单元测试不依赖 LMS 在线；同时提供实时 probe 工具，能在 SSH 里验证真实 LMS。
4. **进度条闭环**：拖动只本地预览，松手提交一次 seek，服务端 poll 负责校正；任何一步失败都不能让 UI 卡死或跳回。
5. **可回归**：所有踩过的坑固化为测试用例。
6. **核心自动执行**：squeezelite 随 app 打包，首次启动自动复制到用户目录并拉起；真机验证只验证「启动 app 后自动注册」，不允许人工启动核心。

## 3. 分层架构

```
lib/
  lms/
    transport.dart      HTTP + Basic Auth + 超时 + 错误分类（IO / HTTP / JSON-RPC）
    protocol.dart       命令构造 + 响应解析（纯函数，可测）
    models.dart         ServerInfo / PlayerInfo / PlaybackStatus / LmsConfig
    client.dart         组合 transport + protocol，暴露高层的 status/control
  state/
    connection.dart     连接状态机（见 §4）
    player.dart         播放器发现与选择
    playback.dart       播放状态 + 本地时间轴 + seek 协调（见 §5）
  ui/
    connect_screen.dart 地址/端口/账号/密码 + 逐层诊断输出
    player_screen.dart  封面/进度/控制/音量
  squeezelite/
    core_runner.dart     内置核心定位/复制/启动/停止（参数构造为纯函数，可测）
  main.dart
tool/
  probe.dart            命令行协议探针；--with-core 会自动拉起核心（见 §6）
```

关键约束：`protocol.dart` 是纯函数，不碰网络；`transport.dart` 不含业务解析。这样协议解析可以吃真实 fixture 做测试，网络问题也不会被误判成解析问题。

## 4. 连接状态机（取代 v1 的 bool connected）

```
disconnected
  → probing_server     （POST version?，带凭证）
  → server_ok          （得到 _version）
  → discovering_players（POST players 0 50）
      ├─ players_found    → 选择播放器 → ready
      └─ no_players       → 自动拉起内置核心并重试；仍无播放器则给诊断（阻塞，不进播放页）
```

每一层失败停在对应状态并给出具体原因：
- `auth_failed` — 401，检查账号密码
- `unreachable` — 超时/拒连，检查地址和端口
- `bad_response` — 2xx 但不是预期 JSON，附带原始片段
- `no_players` — 服务器正常但无播放器，这是**正常状态**不是错误

播放器选择策略（对齐旧版经验）：保存的 ID 优先 → 名称匹配 → 唯一播放器 → 让用户手选。`serverstatus` 的 `players_loop` 在当前版本**不存在**，不能依赖，必须用 `players` 命令。

## 5. 进度条协调（v1 最痛的点）

三套时间来源可能打架：服务端 poll（1Hz）、本地 tick（1Hz）、用户拖动。用单一规则解决：

- `authoritative` = 上次成功 poll 的 position 与时间戳
- `preview` = 拖动中的位置，非 null 时 UI 只显示 preview，本地 tick 停止
- 松手 → 发一次 seek → 成功则清 preview 并立即 refresh；失败则清 preview，保留服务端值（静默，下次 poll 自校正）
- poll 返回时若 preview 非 null，**更新 authoritative 但不覆盖 UI 的 preview**
- 拖动期间禁止自动跳曲：tick 到末尾时若 preview 非 null 则不触发 refresh 风暴

测试点：拖动中收到 poll、seek 失败、seek 成功、跨曲边界，各写一个用例。

## 6. 验证策略（针对"我看不到 GUI"这个长期痛点）

`tool/probe.dart` 命令行探针，给定 host/port/user/pass，依次打印：

```
[transport] POST /jsonrpc.js ... 200
[auth]      Authorization header sent ... ok
[server]    version.result._version = 9.1.1
[core]      bundled core copied to user dir ... auto-started pid=1234
[players]   count = 1  ← registered after core auto-start
[verdict]   server reachable; playback ready
```

`dart run tool/probe.dart --with-core --lms-creds=<路径>` 会自动完成核心复制与拉起，真机验证不需要你手动启动 squeezelite。这样我在 SSH 里就能对真实 LMS 验证协议层，不依赖截图。GUI 只验证"渲染与交互"，协议正确性由 probe 和单测保证。

## 7. 配置与凭证

沿用旧版 `~/.squeezelite_gui/config.json` 的语义：`lms_host` / `lms_port` / `lms_user` / `lms_pass` / `np_playerid`。v2 首次启动提供"从旧版导入"按钮，避免用户手输。凭证写入 `~/Library/Application Support/Sonora/config.json`，权限 600。不进 git。

## 8. 交付阶段（每阶段可独立验证）

| 阶段 | 内容 | 验证方式 |
|---|---|---|
| M0 | models + protocol + transport + fixture 单测 + probe.dart | `dart test` 全绿；probe 对真实 LMS 输出 verdict |
| P0（已完成） | 共享服务层 + 连接诊断页 + 自动拉起核心 + 播放控制/曲库只读列表 | `flutter analyze/test` 全绿；`probe --with-core` 与真实 UI 自动连接路径都显示在线播放器 1 个 |
| M1 | widget test 与更细的状态机边界 | probe + widget test；你在 VM 桌面确认页面 |
| M2 | 播放器选择持久化 + 无播放器指引 | probe 无在线播放器时 UI 有明确指引 |
| M3 | Navidrome `clientStream` 音频闭环 | `just_audio` 播一首歌，进度/seek 正常 |
| M4 | 打包 / 签名 / 归档 | `flutter build macos` + adhoc codesign + 去 quarantine |

注意 P0/M3 依赖一个**真实在线播放器**，但不再依赖人工启动。app/probe 负责把打包核心复制到用户目录并拉起。LMS 的 `players count` 会把已断开的残留条目算进去，因此一律用 `connected == 1` 判定在线；若在线数为 0，按「core 启动日志 → LMS 凭证 → 音频设备」顺序诊断。

macOS 本地网络权限：app 已声明 `NSLocalNetworkUsageDescription` 并使用独立 bundle id `com.songboxiang.sonora.v2`。首次手动打开时若系统询问“是否允许访问本地网络”，必须点允许，否则 LMS/Navidrome 连接会以 `No route to host` 失败。SSH 下的无界面进程没有授权界面，因此该场景的验证以命令行探针和 root 授权进程为准。

## 9. 明确不做

- 不做 ASR 字幕（已定）
- 不用 WebView / Python bridge（旧版动作条的坑）
- 不做歌单/搜索/歌词等扩展，先把连接→发现→播放→拖动这条主干打通

## 10. 需要你拍板

1. 核心策略（已定）：squeezelite 随 app 打包并自动拉起；验证时不再需要你手动启动。
2. 凭证导入：是否允许 v2 读取旧版 `~/.squeezelite_gui/config.json`（只读）来自动填账号密码？
3. 产物位置：编译产物留在 VM，还是后续要传回宿主 Mac 使用？

## 11. 打包与升级（详见 UPGRADE.md）

Squeezelite 播放核心随程序打包，但运行时使用用户目录里的可升级副本（不修改自身签名 bundle）。
核心启动参数已实测定死：`-s <lms_host>:<slim_port>`（默认 3483，**不是** JSON-RPC 的 9000）、`-n <播放器名>`、`-m <稳定本地管理 MAC>`。
其中 `-m` 用来避开 LMS 上残留的 `02:00:00:00:00:00`（实测该 MAC 收 HELO 后不注册），MAC 由主机名/用户稳定派生。
升级体系分四条轨道：程序主体与 squeezelite 可自动升级；LMS 服务端与 Navidrome 只做版本校验、
展示更新内容并提示手动升级。四条轨道共用同一条升级流水线，差异只在数据源实现。

为免将来返工，M0 阶段就要定义 MusicLibrary 与 UpdateSource 两个接口：LMS 是第一个实现，
Navidrome 后接；升级页只依赖 updateInfo()，不写死任何 LMS 专属字段。

Navidrome 与 LMS 的播放模型不同：LMS 是外部播放器（squeezelite 注册后受控），Navidrome 是客户端
直接播放 HTTP 音频流，没有「播放器注册」概念。MusicLibrary 需要 playbackMode 字段区分
external_player / client_stream，播放页按模式走不同路径；这一条会影响 M3，需在编码前定死。
完整方案、数据源实测、校验/回滚/清理策略见 docs/UPGRADE.md。
