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
- Navidrome 播放验收：CLI 请求 `/rest/stream?id=<songId>&u/t/s/v/c` 应返回 `206/200` 且 `Content-Type: audio/flac`（不得带明文密码或 `f=json`）。UI 自动播放钩子 `SONORA_AUTO_PLAY=1` 会加载第一张专辑第一首歌，打印 `duration=273s → seek 到 136s → seek 后位置 136s`；实测已通过。播放页与曲库点歌走同一 `NavidromeAudio`。
- macOS 本地网络权限：首次手动打开 `.app` 需允许“访问本地网络”，否则 socket 报 `No route to host`。Info.plist 已声明 `NSLocalNetworkUsageDescription`，bundle id 为 `com.songboxiang.sonora.v2`。无界面 SSH 进程无授权界面，因此该场景的验收用命令行探针或 root 进程完成。
- CocoaPods 部署目标：`macos/Podfile` 必须保持 `platform :osx, '12.0'` 且 `post_install` 强制覆盖所有 Pod target 的 `MACOSX_DEPLOYMENT_TARGET`，否则 `just_audio`/`audio_session` 会生成 10.15 工程并被 Xcode 27 拒绝。
- 发布打包验收（M4）：`bash tool/package.sh` → `dist/Sonora-<ver>.zip` + `.dmg` + `SHA256SUMS`，全程自动校验核心 sha256、签名、版本。安装 `ditto dist/stage/Sonora.app /Applications/Sonora.app` 后 `codesign --verify --deep --strict /Applications/Sonora.app` 须通过、核心 hash 须等于 bundle manifest 的 `binarySha256`。实测：删除用户目录核心副本模拟首次安装，从 `/Applications/Sonora.app` 启动后自动从 bundle 复制（sha 一致）并在 3 秒内使 `Sonora-UI` 达 `connected=1`。`--no-build` 可跳过 analyze/test/build 仅重签归档。
- 签名顺序不可颠倒：`Resources/Core/squeezelite` 是裸 Mach-O，`--deep` 不签它 → 先单独 adhoc 签核心 → 用签名后 sha256/size 回写 `core-manifest.json` → 再 `--deep` 签整包（把更新后的 manifest 纳入封印）。若先签整包再改 manifest，签名验证会失败。adhoc 签名不可公证，从网络下载首次打开需右键「打开」一次。
- 发布版本：`pubspec.yaml` 的 `version` 为唯一版本源，当前 `2.1.0+1`（v2 重写版首个正式包，高于远端 `v2.0.18`）；升级检测须用 `compareVersions` 而非字符串比较。
- 升级页下载校验（U1）：`lib/core/updates.dart` 提供纯函数 `parseReleaseVersion`/`parseReleaseNotes`/`parseCoreRss`/`parseSha256Sums`/`hashMatches`（12 项单测）与副作用 `verifyAppArchive`/`verifyCoreArchive`；UI 第 4 页签展示当前/最新版本、发布说明、两轨下载校验结果与实时日志，headless 钩子 `SONORA_AUTO_UPDATE=1` + `SONORA_APP_ZIP`/`SONORA_APP_SUMS`/`SONORA_CORE_VERIFY`。实测：`SHA256SUMS` 校验 19MB zip 通过并确认含 `Sonora.app/Contents/Info.plist`；SourceForge 2.3MB dmg 的 md5/filesize 与 RSS 一致、挂载后二进制 sha256=`46857580...`（源二进制未签名，与 bundle 内签名后的 `244e440d...` 不同，属正常）；篡改 zip（尾部追加字节）被 SHA256 拒绝并停在 hash 阶段。校验产物可直接交给 U2 安装。
- 升级页替换与回滚（U2）：`lib/core/installer.dart` 只接受已校验产物，安装前二次核对 hash。主体 zip 解压到暂存 → 旧 `/Applications/Sonora.app` 复制到 `~/Library/Application Support/Sonora/Backups/app/<id>` → 同目录 rename 交换 → Info.plist 版本 + `codesign --verify --deep --strict` → 成功清理暂存、失败自动恢复。核心 dmg 校验时 `extractBinary: true` 暂存裸二进制 → adhoc 签名 → 备份旧核心与 manifest → 替换用户目录副本 → 写 `Core/core-manifest.json` → `-t` 版本/revision + 签名/hash 健康检查 → 失败恢复旧二进制与 manifest。两轨都可按备份 ID 手动回滚；核心替换前会停掉运行中的核心，成功后自动拉起。验收：`dart run tool/probe_install.dart` 全链路 PASS——主体 2.0.18→2.1.0→回滚 2.0.18；核心安装后 sha=`244e440d...`、手动回滚恢复 `46857580...`；注入健康检查失败时 `rolledBack=true` 且旧 hash 不变。UI 升级页已接入按钮与备份下拉，headless 可用 `SONORA_APP_TARGET`/`SONORA_CORE_TARGET` 注入假目标。
- Navidrome 体验（N1）：`search3` 服务端搜索专辑/歌曲；`getCoverArt` URL 带 md5 token、不带明文密码与 `f=json`；`getAlbumInfo2`/`getArtistInfo2` 提供专辑简介与艺人简介；`getLyricsBySongId` 的结构化歌词按当前播放位置高亮；当前曲目列表即播放队列，可点选跳转，播放结束自动下一首。验收：`dart run tool/probe_navidrome_extras.dart --query=爱` 打印 ping / 搜索命中 / 封面 token / 详情歌曲数 / 简介字数 / 歌词行数 / 播放队列状态与 verdict。VM 无声卡时进度与切歌可验，听声需在有音频设备的机器上。
- 主体下载 URL 来源：本仓库只有 tag、无正式 Release，Releases API 404、`releases.atom` 无 asset 链接，因此升级页让用户输入 zip + SHA256SUMS 地址，逻辑不写死下载地址；核心轨由 RSS 自动提供，无需手填。
