# LMS 端数据来源与插件清单

> 实测环境：Lyrion Music Server **9.1.1**（`192.168.199.2:9000`，Basic Auth），
> 抽样日期 2026-11-22。本文件对应 APP v1.5.1。

## 结论先说

**你现有的 LMS 已经安装了所需插件，不需要再装任何东西。**

v1.5.0 及以前，本 APP 误用了 `artistinfo` / `albuminfo` 这两个不存在的
LMS 命令，服务端收到后直接 `RemoteDisconnected`，被误判为「未安装插件」，
于是歌手简介一直走维基百科、歌词一直走公网在线源。v1.5.1 起改为官方
`musicartistinfo` CLI，数据全部可由 LMS 端直接提供。

## 需要哪些插件

| 想要的数据 | 是否需要插件 | 获取方式 |
| --- | --- | --- |
| 曲名 / 艺术家 / 专辑 / 流派 / 年份 / 音轨号 / 采样率 / 位深 / 码率 / 文件路径 | **不需要** | `status` / `songinfo` / `titles` + `tags:...Iro` |
| 专辑封面 | **不需要** | `/music/<coverid>/cover_300x300.jpg`，`albums tags:alj` 取 `artwork_track_id` |
| **内嵌**歌词（写在音频文件 tag 里的 USLT / SYLT / Vorbis LYRICS） | **不需要** | `songinfo 0 100 track_id:<id> tags:w` |
| 歌手简介 / 传记 | 需要 **Music & Artist Information** | `musicartistinfo biography artist:<name>` |
| 专辑评论 / 介绍 | 需要 **Music & Artist Information** | `musicartistinfo albumreview artist:<a> album:<b>` |
| 歌词（同名 `.lrc` 或在线源 LRCLIB 等） | 需要 **Music & Artist Information** | `musicartistinfo lyrics track_id:<id>` |
| 艺人照片 / 专辑封面候选 | 需要 **Music & Artist Information** | `musicartistinfo artistphoto / albumcovers`（本次实测返回 `error`，图片源未配置，属可选） |
| Squeezebox 硬件 / LMS Web 界面上显示歌词 | 可选 **Song Lyrics** + 依赖 **Song Info** | 仅面向 LMS 自带界面，不是给本 APP 的 JSON-RPC 数据源 |
| 客厅大屏信息展示 | 可选 **Music Information Screen** | 与数据获取无关 |

### 必装（且已装）

**Music & Artist Information**（Michael Herger，插件目录名 `MusicArtistInfo`）

- LMS 9.x 的**默认插件仓库已包含**，一般无需添加第三方仓库。
- 老旧教程里的 `http://www.herger.net/slim-plugins/repo.xml` 已不推荐：
  官方论坛明确指出该仓库不再必需，且曾导致插件更新卡住；如曾添加，建议移除。
- 作用：从 Wikipedia / Last.fm / Discogs / MusicBrainz / AllMusic、
  LMS-Community API 取传记与专辑评论；歌词支持音乐目录下的同名 `.lrc`、
  插件自己的歌词缓存目录，以及 LRCLIB 在线源。

### 可选（本 APP 用不到）

- **Song Info**（Erland Isaksson）：为 **Song Lyrics** 提供框架。
- **Song Lyrics**：在 LMS Web / Squeezebox 硬件界面显示歌词（ChartLyrics、
  Musixmatch）。它不向外部客户端提供可直接调用的 JSON-RPC 歌词命令，
  本 APP 用的是 MAI 的 `musicartistinfo lyrics`。
- **Music Information Screen**：HTPC 大屏展示插件，纯展示层。

## 安装步骤（若换服务器 / 重装 LMS）

1. 浏览器打开 `http://<LMS 地址>:9000/` → 右上角 **设置 (Settings)** →
   **插件 (Plugins)** 标签页。
2. 在「推荐的第三方插件 / 所有第三方插件」里找到
   **Music and Artist Information**，勾选。
   - 找不到时勾选「显示所有第三方插件」，或检查 LMS 是否能访问插件仓库。
   - **不要**再手工添加 `herger.net` 旧仓库（除非官方另行通知）。
3. 点「应用 / Apply」，按提示**重启 LMS**。
4. 若要用音乐目录里的同名 `.lrc`：在插件设置里确认歌词目录，然后
   LMS「设置 → 信息」执行一次**重新扫描曲库**（清除并重新扫描更彻底）。
5. 无需在 APP 里装任何东西；v1.5.1 起自动探测命令。

## 官方 CLI 命令参考（`musicartistinfo`）

来源：`https://github.com/michaelherger/MusicArtistInfo/blob/master/CLI.md`
（文本返回为纯文本、已去格式；CLI/Telnet 需 URI 转义参数，**JSON-RPC 不需要**）。

```
musicartistinfo biography   [artist:abba | artist_id:123]
musicartistinfo albumreview [artist:abba album:gold | album_id:123] [lang:german]
musicartistinfo lyrics      [artist:abba title:waterloo | track_id:123 | url:...]
musicartistinfo artistphoto [artist:abba | artist_id:123]
musicartistinfo artistphotos[artist:abba | artist_id:123]
musicartistinfo albumcovers [artist:abba album:gold | album_id:123 | mbid:abc]
musicartistinfo localfiles  folder:/path/to/folder
```

JSON-RPC 调用示例（本 APP 使用的方式，`params[0]` 为空表示服务端全局命令）：

```bash
curl -s -u 'user:pass' -X POST http://192.168.199.2:9000/jsonrpc.js \
  -H 'Content-Type: application/json' \
  -d '{"id":1,"method":"slim.request","params":["",["musicartistinfo","biography","artist:王杰"]]}'
```

返回：`{"artist":"王杰","biography":"..."}`。
歌词返回 `{"artist":"...","title":"...","lyrics":"..."}`；
查不到时返回 `{"error":"I'm sorry, didn't find any relevant information."}`。

## 本 APP 侧的开关

配置文件：`~/.squeezelite_gui/config.json`（权限 600）

| 键 | 默认 | 作用 |
| --- | --- | --- |
| `bio_lms_plugin` | 未设置 = **启用** | 设为 `false` 才彻底跳过 MAI 插件，简介全部走维基百科 |
| `lyrics_prefer_lms` | 未设置 = `false` | 设为 `true` 时歌词强制优先用 MAI（纯文本，失去逐行高亮） |

探测到插件命令断连后会缓存状态、不再反复请求；重启 APP 可重新探测
（例如刚装好插件时）。

### 数据优先级（v1.5.1）

- 简介：`musicartistinfo biography` → 维基百科中文 → 维基百科英文；
  专辑评论：`musicartistinfo albumreview` → 维基百科中 / 英文。
  专辑元信息始终来自 LMS 标签。缓存 `bio_cache.json`。
- 歌词：`songinfo tags:w`（内嵌）→ `musicartistinfo lyrics`（LMS 端）
  → 在线 LRCLIB / 网易云 → 手动 LRC。因 MAI 歌词无时间轴，默认让
  **带时间轴的在线 LRC 优先**以保留逐行高亮；MAI 作为不走公网的兜底。

## 本次实测结果（2026-11-22）

| 探测 | 结果 |
| --- | --- |
| `musicartistinfo biography artist:王杰` | OK，505 字中文传记（含 HTML 标签，APP 已清洗） |
| `musicartistinfo lyrics track_id:<id>` | 抽样 5 首（王杰 / 李健 / 动力火车）**全部命中**，255–430 字，均为**纯文本无时间轴** |
| `songinfo ... tags:w` | 抽样曲目内嵌歌词为空（该曲库歌词来自插件 / 在线源，未写进音频 tag） |
| `musicartistinfo albumreview` | 中文 / 古典专辑多返回 `error`（无匹配的在线评论），APP 自动回退维基百科 |
| `musicartistinfo artistphoto` | 返回 `error`（图片源未配置），APP 不使用 |
| 旧命令 `artistinfo` / `albuminfo` | `RemoteDisconnected`（命令不存在，已弃用） |

## 若想让「歌词」也完全不经过公网

把 `lyrics_prefer_lms` 设为 `true` 即可，但会失去逐行高亮。更好的做法是
在 LMS 侧把带时间轴的 `.lrc` 放到音乐目录（与音频文件同名），让 MAI 直接
读取带时间轴的歌词——此时 APP 会识别到 `[mm:ss.xx]` 并优先采用，
兼顾「全部来自 LMS」与「逐行同步」。
