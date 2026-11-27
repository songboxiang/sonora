# Sonora v2 —— 打包与自动升级设计

状态：待评审 · 2026-11-27
前置：`docs/DESIGN.md`（协议层与连接状态机）。本文只覆盖「核心打包 + 升级体系 + 远端版本提示」。

## 1. 实测事实（不是推测）

| 数据源 | VM 实测 | 对设计的约束 |
|---|---|---|
| `api.github.com/repos/songboxiang/sonora/releases/latest` | 403 rate limit | 不能作为唯一版本源，必须有降级链 |
| `github.com/songboxiang/sonora/releases.atom` | 200，5608 B | 免限流，可作主体版本 + 发布说明源 |
| `git ls-remote --tags <repo>` | 200，能列出 v2.0.x tags | 最终兜底版本发现 |
| `lms-community.github.io/lms-server-repository/servers.json` | 200 | LMS 最新版本库可用 |
| `sourceforge.net/.../rss?path=/squeezelite/osx/m1` | 200 | squeezelite 最新版本可用 |
| `github.com/ralph-irving/squeezelite/commits/master.atom` | 200 | squeezelite 更新日志可用 |
| 旧版 `squeezelite_gui.py` | 已有 `sq_local_version` / `changelog` / `lms_latest` / `upgrade_squeezelite` | 移植成熟逻辑，不重写 |

结论：升级体系的数据源都现成且可达；唯一不可靠的是 GitHub API，需要原子化降级。旧版代码是可以直接搬过来的资产。

## 2. 四条轨道，统一引擎

```
┌─ 本地可自动升级 ──────────────────────────┐
│ A. 程序主体   GitHub → 校验 → 替换 → 重启 │
│ B. Squeezelite SourceForge → 校验 → 替换 │
└───────────────────────────────────────────┘
┌─ 远端只读提示 ────────────────────────────┐
│ C. LMS 服务端   JSON-RPC 取当前 / repo 取最新 → 手动升级链接 │
│ D. Navidrome    LibraryAdapter 取当前/最新 → 手动升级链接   │
└───────────────────────────────────────────┘
```

A/B 共用同一条流水线：`check → compare → notes → download → verify → stage → install → healthcheck → cleanup`。
差异只在 `UpdateSource` 实现（版本从哪来、包什么格式、如何验证）。C/D 只走 `check → compare → notes → 提示`，**永不自动改远端服务**。

## 3. Squeezelite 打包模型

关键约束：**运行时绝不修改自身已签名的 app bundle**。所以 bundle 里只放「出厂核心」，运行时用用户可写目录里的副本。

```
Sonora.app/Contents/Resources/Core/
  squeezelite.arm64       # 出厂核心（随程序打包）
  squeezelite.x86_64      # 出厂核心（universal 可只放一份）
  core-manifest.json      # 出厂版本 / sha256 / 来源

~/Library/Application Support/Sonora/Core/
  squeezelite             # 实际运行的副本（可升级）
  core-state.json         # 当前版本 / revision / sha256 / 安装时间 / 来源

~/Library/Application Support/Sonora/Core/backups/
  squeezelite.<version>.<timestamp>.bak

~/Library/Caches/Sonora/updates/<track>/<version>/
  download/  staged/  manifest.json
```

首次启动逻辑：
1. 读 `core-state.json`；不存在则从 bundle 复制对应架构的核心到用户目录，写入 state。
2. 存在则校验 sha256；损坏则从 bundle 恢复（出厂核心是最后的救命副本）。
3. 由 CoreRunner 自动启动独立子进程，记录 PID 并监听退出；不做进程内嵌——崩溃时才能留下可检测的孤儿进程。用户永远不需要手动执行二进制。

架构选择：优先 universal；若上游只给分离包，按 `uname -m` 选 arm64/x86_64。两种都要能落到同一个 `Core/squeezelite` 路径，上层不感知。

## 4. 各轨道细节

### 4.1 程序主体（A）

版本发现降级链（按顺序，取第一个成功）：
1. GitHub Releases API：`GET /repos/songboxiang/sonora/releases/latest`（有 token 时带 token，解除限流）
2. `https://github.com/songboxiang/sonora/releases.atom` → 解析最新 entry 的 `<title>` 作为版本
3. `git ls-remote --tags https://github.com/songboxiang/sonora.git` → 取最大语义版本

发布说明：Releases body（API/Atom）优先；失败时用 `commits.atom` 最近 N 条提交作为「更新内容」展示，并标注来源。

安装方式（自更新）：
- 下载 zip → 校验 → 解压到 staged 临时目录 → 验证 `.app` 结构与签名。
- 写 `pending-update.json`，用随 app 附带的独立 `UpdateHelper` 小程序执行替换：等主进程退出 → 原子替换目标 `.app` → 重启主程序。
- 替换目标固定为 `/Applications/Sonora.app`（已定）。实测宿主与 VM 的 `/Applications` 均为 `root:admin 775`，`song` 用户在 admin 组且 `test -w` 通过 → 普通权限即可原子替换，不需要每次弹管理员密码。若目标机器用户不在 admin 组，降级为系统授权对话框。
- **签名策略（已定）**：adhoc 签名，不购买开发者身份。程序只在自己机器上使用，构建产物由我本地生成并去掉 quarantine 属性。代价：无法公证；从互联网直接下载首次打开需右键「打开」一次。UpdateHelper 替换后重新执行 `codesign --force --deep -s -`，保证新包仍可运行。

### 4.2 Squeezelite 核心（B）

版本发现：SourceForge RSS（`sf_m1_rss` / `sf_intel_rss`，已验证 200）解析文件名，匹配旧版正则：
`squeezelite-(\d+\.\d+(?:\.\d+)?)[.\-](\d+)-osx-(m1|intel)\.(tar\.gz|tgz|zip)`
另有 M1 的 `Squeezelite-M1-2.0.0r1610.dmg` 形式，需兼容 dmg（hdiutil attach → 提取二进制 → detach，旧版已实现）。

更新日志：`ralph-irving/squeezelite` 的 `commits/master.atom`，API 可用时增强。

安装流程：
1. 下载到 `Caches/.../download/`，记录字节数与源提供的校验值。
2. **校验（已实测可全自动，无需人工提供 hash）**：SourceForge RSS 每项都带 `media:content filesize` 与 `media:hash algo="md5"`（已实测 3 处 md5 字段），下载后字节数与 MD5 必须一致；再叠加 `squeezelite -t` 自报版本与目标一致、`codesign -dv` 通过。MD5 只用于完整性（防损坏/截断），不当作安全签名；任一不符即不替换，升级页显示原因。
3. 暂停正在运行的播放器（graceful stop，不是 kill -9）。
4. 旧二进制复制到 `backups/`，新二进制原子 rename 到 `Core/squeezelite`，chmod 755，去 quarantine。
5. 重启播放器，做健康检查：LMS `players` 里出现该 ID 且 `status` 能返回 → 成功。
6. 失败则自动回滚到备份并重启旧版，升级页显示失败原因。
7. 成功 N 次启动后清理旧备份（默认 N=3，可设）。

### 4.3 LMS 服务端（C）

- 当前版本：JSON-RPC `["version","?"]` → `result._version`（兼容 `version` 字段）。注意 v1 就是在这里判断错字段。
- 最新版本：`lms-server-repository/servers.json` 的 `latest` / `macos` 通道，可选 stable / dev。
- 更新内容：`LMS-Community/slimserver` 的 `commits/public/9.1.atom`，可从 `lyrion.org/downloads` 补充。
- 行为：升级页显示「当前 → 最新」和说明，按钮为「前往手动升级」，链接指向 `downloads.lyrion.org`。**不自动下载、不自动安装**。

### 4.4 Navidrome（D）

名称更正：此前误写作 Novidrome，正确为 **Navidrome**。本地地址 `http://192.168.199.2:4533/app/#/login`。

实测事实（VM 直接访问）：
- 不带任何凭证请求 `GET /rest/ping?format=json`，返回 XML：`status="failed" ... type="navidrome" serverVersion="0.55.2 (a057a680)" openSubsonic="true"` → **版本探测不需要密码**，解析 `serverVersion` 即可。
- 本地当前 0.55.2；`github.com/navidrome/navidrome/releases.atom` 最新 v0.64.2（200，218 KB，含完整发布说明）→ 升级内容直接取 release entry，不需要额外抓取。
- v1 API `/api/v1/openapi.json` 返回 404，官方文档也标注 WIP → 客户端只走 OpenSubsonic `/rest/`，不碰 v1。

协议与鉴权：根路径 `/rest/`，token 鉴权 `u=user&t=token&s=salt&v=1.16.1&c=Sonora`，其中 `token = md5(password + salt)`，不传明文密码。失败响应也带 `serverVersion`，所以没配凭证时版本卡片仍能显示。

**实测坑（务必按这个写）**：资料里写的 `format=json` 在这台 0.55.2 上**被忽略、仍返回 XML**；必须用 `f=json` 才返回 JSON。凭证在 VM `/Users/song/navidrome_creds.json`（`user = ...` / `password = ...`，权限 600）。

带 token 的实测结果：
- `ping` 200 / ok / `serverVersion=0.55.2 (a057a680)` / `openSubsonic=true`
- `getAlbumList2?type=newest` 返回 3 张专辑（首张「情歌精选」）；`getAlbum` 返回 32 首，首曲「爱如潮水」
- `getLyricsBySongId` 返回 1 组 `structuredLyrics`，36 行带时间戳歌词 → 歌词功能有真实数据
- `getPlayQueue` 当前为空（未播放），`getArtists` 返回 0 而专辑存在 → **曲库浏览要以专辑为入口，不能依赖 `getArtists`**，艺术家信息从专辑/歌曲字段或 `getArtist` 另取

统一接口（UI 不写死 LMS 专属字段）：

```dart
abstract class MusicLibrary {
  String get id;
  String get displayName;
  PlaybackMode get playbackMode;         // external_player | client_stream
  Future<ProbeResult> probe();           // 可达性 + 当前版本
  Future<UpdateInfo> updateInfo();       // 当前/最新/说明/手动升级地址
  Future<List<PlayerInfo>> listPlayers();
  Future<PlaybackStatus> status(String playerId);
  Future<void> control(String playerId, List<String> command);
  Stream<LibraryEvent> subscribe();      // LMS: Comet；Navidrome: 轮询适配器
}
```

**架构影响（重要）**：Navidrome 没有 LMS 那种「播放器注册」概念，`/rest/stream` 是 HTTP 音频流，由客户端自己播放。因此：
- 打包的 squeezelite 只服务 LMS 轨，对 Navidrome 无效；`playbackMode=client_stream` 时播放页走客户端播放器，不再找播放器列表。
- Navidrome 无长连接推送；用 `getPlayQueue` + `status` 低频轮询（前台 2~3 s、后台降频）模拟事件。
- 结构化歌词用 `getLyricsBySongId` 的 `structuredLyrics`，直接渲染逐行 LRC；简介用 `getArtistInfo2` / `getAlbumInfo2`；封面 `getCoverArt`。这些正好对上用户设想里的歌词与简介需求。

## 5. 升级状态机

```
idle → checking → up_to_date | update_available
update_available → downloading → verifying → staging → installing
  → healthcheck → installed → cleaning → idle
                ↘ failed → cleanup_failed → idle (保留备份)
任一阶段可进入：network_error / checksum_mismatch / signature_invalid /
                 install_failed / healthcheck_failed / cancelled
```

- 每一步产生带时间戳的日志行，实时显示在升级页（沿用旧版「升级日志」的交互习惯）。
- 下载支持取消；安装开始后不可取消，失败走回滚。
- 启动时默认只 `check`（不自动装），自动安装开关默认关闭——避免半夜自动换核心把播放搞坏。

## 6. 校验、回滚与清理

- **校验优先级**：源提供的 hash（GitHub 发布资产若有 sha256 用 sha256；SourceForge 用 MD5 + filesize）> 自报版本 + 签名 > 拒绝自动安装。永远不「先装上再看看」。
- **回滚**：升级前备份旧版到独立目录；健康检查失败自动恢复；程序主体保留上一版本 `.app` 直到新版本连续启动成功。
- **清理清单化**：每次升级生成 `manifest.json` 记录它创建的所有路径。成功删 download + staged；失败删 staged、保留下载供排查。清理范围严格限定在 `~/Library/Caches/Sonora` 与 `~/Library/Application Support/Sonora`，不碰其他目录。
- 升级页提供「清理升级缓存」按钮，按同一清单执行，并回显清理了多少文件。

## 7. 升级页布局

四个分区，每张卡片独立刷新、独立报错：

| 分区 | 显示 | 操作 |
|---|---|---|
| 程序主体 | 当前版本 / 最新 / 渠道 / 更新内容 / 日志 | 检查更新、下载安装、重启生效 |
| Squeezelite 核心 | 当前版本+revision / 最新 / 架构 / 运行状态 / 更新内容 / 日志 | 检查更新、安装、回滚、启动/停止引擎 |
| LMS 服务端 | 当前 / 最新 / 更新内容 / 上次检查时间 | 前往手动升级、重新检查 |
| Navidrome | 当前 0.55.2 / 最新 v0.64.2 / 发布说明 | 前往手动升级、重新检查 |

全局设置：启动时自动检查（默认开）、渠道 stable/dev、是否允许自动安装（默认关）、代理、LMS 凭证。

## 8. 决策状态

1. **签名策略 — 已定**：adhoc，不买开发者身份。首次分发需去掉 quarantine；无法公证。
2. **SourceForge hash — 已解决**：RSS 自带 `media:hash algo="md5"` + `filesize`，全自动校验，不需要你手动提供。
3. **Navidrome — 已解决**：地址 `192.168.199.2:4533`；`GET /rest/ping` 的失败响应即含 `serverVersion`，无需凭证；最新版本与发布说明取 `navidrome/navidrome` 的 `releases.atom`。待你提供 token 后才能验证业务接口（曲库、歌词、播放队列）。
4. **安装位置 — 已定**：`/Applications`。实测宿主与 VM 均为 `root:admin 775` 且用户在 admin 组，无需提权即可替换；非 admin 环境降级为授权对话框。

## 9. 验证计划

- `tool/probe_update.dart`：一条命令打印四条轨道的版本源可达性、解析结果、更新内容条数、最终 verdict。我在 SSH 里就能验收，不依赖截图。Navidrome 轨直接打 `192.168.199.2:4533/rest/ping` 取 `serverVersion`，并与 `releases.atom` 的最新 tag 比较。
- 单测 fixture：`releases.atom`、`servers.json`、SourceForge RSS、`commits.atom`、旧版真实响应；版本比较覆盖 `9.1.1` / `2.0.0.1465` / `9.1.2 - 1792854063`。
- 流水线集成测试（本地假文件）：成功、hash 不符、下载中断、健康检查失败回滚、清理清单完整性。
- 深度曲库验收：`dart run tool/probe.dart --with-libs --lms-creds=<路径>` → 逐个 `getAlbum` 读取全部专辑详情与歌曲列表，打印每首歌名、艺人、时长、ID 与曲库汇总。
- 真实验收：`dart run tool/probe.dart --with-core --lms-creds=<路径>` → 自动复制打包核心、拉起子进程、等待出现 `connected == 1` 的在线播放器（不能只看 `players count`，它包含离线残留）→ 打印 `count / 在线` 与 verdict。真实 UI 的“连接并自动拉起核心”按钮走同一套 `lib/core/services.dart`，自动连接钩子 `SONORA_AUTO_CONNECT=1` 可复现该路径。全程不需要人工启动 squeezelite。
- macOS 本地网络权限：首次手动打开 `.app` 需允许“访问本地网络”，否则 socket 报 `No route to host`。Info.plist 已声明 `NSLocalNetworkUsageDescription`，bundle id 为 `com.songboxiang.sonora.v2`。无界面 SSH 进程无授权界面，因此该场景的验收用命令行探针或 root 进程完成。
