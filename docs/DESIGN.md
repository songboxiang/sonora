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
| P1（已完成） | Navidrome `clientStream` 音频闭环：`NavidromeAudio` + `just_audio` + 曲库点歌播放 + 音源互斥 | CLI `/rest/stream` 返回 `audio/flac`；UI 自动播放加载 273s 流并 seek 到 136s，位置回读 136s |
| N1（已完成） | Navidrome 体验补齐：search3 服务端搜索、带 token 的封面、getAlbumInfo2/getArtistInfo2 简介、结构化歌词、当前曲目列表即播放队列与结束后自动下一首 | `flutter analyze/test`（51 项）全绿；`dart run tool/probe_navidrome_extras.dart` 打印搜索/封面/歌词/简介/队列计数与 verdict；UI 曲库页搜索、封面与简介，播放页封面、逐行歌词与可点击队列 |
| L1（已完成） | 连接/曲库重构：连接页集中 LMS+Navidrome 地址凭证与「修改配置」；曲库页分条显示 LMS/Navidrome 并一键切换，切到 LMS 自动拉起引擎、切走自动停止；输出设备扫描/命名与音质参数面板 | `lib/core/settings.dart` 持久化 `settings.json`（记住上次输出设备、账号、轨道）；`lib/lms/library.dart` 读取 LMS 专辑/曲目并走 LMS playlist 播放；修正 `CoreRunner` 把输出设备误写成 `-a` 的问题，改为 `-o`（`-a` 实际是延迟:重采样）；预设「完美码率直通 / 最佳音质 / DSD直通 / USB DAC 直连」并逐项提供 `-o/-n/-a/-r/-D/-b/-M` 帮助释意。`flutter analyze` 无问题、`flutter test` 63 项全绿；`dart run tool/probe_library_switch.dart` 真实服务验收：LMS 60 张专辑、首张 14 首、扫描到 1 个设备、完整参数启动后在线播放器 1 个，verdict=PASS |
| M4（已完成） | release 打包 / adhoc 签名 / zip+dmg 归档 / 安装到 `/Applications` | `bash tool/package.sh` 一条命令：`flutter analyze/test/build --release` → 核心 sha256 校验 → 核心单独 adhoc 签名 → 签名后回写 manifest → `--deep` 签整包 → 去 quarantine → `dist/Sonora-<ver>.zip` + `.dmg` + `SHA256SUMS`；安装版实测首次启动时从 bundle 自动复制核心，播放器 `connected=1` |
| U1（已完成） | 升级页主体/核心两轨「下载 + 校验」，不自动替换 | `lib/core/updates.dart`：atom 版本/发布说明、SourceForge RSS（版本+md5+filesize+链接）纯解析 + 单测；`verifyAppArchive`（下载 zip → SHA256SUMS 校验 → zip 内含 `Sonora.app/Contents/Info.plist`）、`verifyCoreArchive`（下载 dmg → md5+size → 挂载 → 二进制 sha256）→ `VerifyResult`。UI 新增第 4 个「升级」页签，headless 钩子 `SONORA_AUTO_UPDATE=1` + `SONORA_APP_ZIP`/`SONORA_APP_SUMS`/`SONORA_CORE_VERIFY`。端到端实测：主体 19MB zip（SHA256+结构通过）、核心 2.3MB dmg（md5+size+sha256 通过）；篡改 zip 被 SHA256 拒绝停在 hash 阶段 |
| U2（已完成） | 主体/核心「替换 + 回滚」：`lib/core/installer.dart` 备份→暂存→同目录 rename 交换→健康检查→失败自动回滚；两轨均支持按备份 ID 手动回滚 | `dart run tool/probe_install.dart` 在临时目录模拟 `/Applications` 与用户核心目录：主体 2.0.18→2.1.0 替换成功、回滚回 2.0.18；核心 dmg 校验→签名→安装后 hash=`244e440d...`，手动回滚恢复原 hash=`46857580...`；模拟健康检查失败时 `rolledBack=true` 且旧二进制 hash 完整恢复。UI 第 4 页签新增「安装替换主体 / 核心」「回滚主体 / 核心」与备份选择器；headless 追加 `SONORA_APP_INSTALL` / `SONORA_CORE_INSTALL` / `SONORA_ROLLBACK` 与假目标路径注入 |

发布版本：与主线延续，v2 重写版首个正式包为 **2.1.0**（`pubspec.yaml` 的 `version: 2.1.0+1`）；`CFBundleShortVersionString=2.1.0`，高于远端 `v2.0.18`。归档输出到 `dist/`（已 gitignore）。

签名顺序要点：核心 `Resources/Core/squeezelite` 是裸 Mach-O，`codesign --deep` 不会自动签它，必须先单独 `codesign --force --sign -`；签名会改变文件 sha256，所以要在签整包**之前**用签名后 hash 回写 bundle 内的 `core-manifest.json`，否则 manifest 与实际分发核心不符、自检必然失败。

注意 P0/M3 依赖一个**真实在线播放器**，但不再依赖人工启动。app/probe 负责把打包核心复制到用户目录并拉起。LMS 的 `players count` 会把已断开的残留条目算进去，因此一律用 `connected == 1` 判定在线；若在线数为 0，按「core 启动日志 → LMS 凭证 → 音频设备」顺序诊断。

升级轨数据来源约束：`github.com/songboxiang/sonora` 只有 tag 没有正式 GitHub Release，Releases API 返回 404，`releases.atom` 只给版本号与 tag 链接、没有 asset 地址。因此主体下载 URL 由升级页手动填写（配合 `SHA256SUMS` 地址），校验逻辑不假设任何固定下载地址；远端确实发布 asset 后可直接填入。核心轨相反，SourceForge RSS 自带 md5/filesize/下载链接，全自动。两轨下载校验后可直接替换，见 U2。连接与曲库配置见 L1。

macOS 本地网络权限：app 已声明 `NSLocalNetworkUsageDescription` 并使用独立 bundle id `com.songboxiang.sonora.v2`。首次手动打开时若系统询问“是否允许访问本地网络”，必须点允许，否则 LMS/Navidrome 连接会以 `No route to host` 失败。SSH 下的无界面进程没有授权界面，因此该场景的验证以命令行探针和 root 授权进程为准。

构建约束：Xcode 27 不再接受 10.15 部署目标。`Runner.xcodeproj` 与 `macos/Podfile`（含 `post_install` 强制覆盖所有 Pod target）都设为 12.0；否则新增 `just_audio` / `audio_session` 后 CocoaPods 生成的工程会因为 10.15 而构建失败。

播放边界：`NavidromeAudio.playSong()` 对 `AudioPlayer.play()` 加 3 秒超时，避免无音频设备的无界面环境把控制路径卡死；`NavidromeAudio.streamUrl()` 只带 md5 token，绝不发明文密码，也不带对二进制流无意义的 `f=json`。LMS 与 Navidrome 音源互斥：开始客户端流会停止 squeezelite 核心，连接 LMS 会停止客户端音频。

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
