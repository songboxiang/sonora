# Sonora v2 升级与回滚操作手册（一页）

适用：macOS v2 分支、2.1.0+1。两条可升级轨：**程序主体** `/Applications/Sonora.app`、**Squeezelite 核心** `~/Library/Application Support/Sonora/Core/squeezelite`。LMS / Navidrome 只提示手动升级。

## 0. 升级前确认

```bash
# 主体版本（未安装则跳过）
/usr/libexec/PlistBuddy -c 'Print CFBundleShortVersionString' /Applications/Sonora.app/Contents/Info.plist
# 核心版本
"$HOME/Library/Application Support/Sonora/Core/squeezelite" -t | head -1
```

主体下载地址需自行提供：本仓库只有 tag、没有 Release asset，升级页填 **zip URL + 同目录 SHA256SUMS URL**。本机临时发布：

```bash
cd ~/Projects/sonora_v2/dist && python3 -m http.server 8000
# zip:  http://127.0.0.1:8000/Sonora-2.1.0.zip
# sums: http://127.0.0.1:8000/SHA256SUMS
```

核心源自动：SourceForge RSS 自带版本、md5、文件大小和下载链接，无需手填。

## 1. 正常升级（UI）

1. 打开 Sonora → 第 4 个页签 **升级** → **重新检查版本**。
2. 主体：填 zip + SHA256SUMS 地址 → **下载并校验主体**。显示「通过 / verified」后按钮才可用。
3. 点 **安装替换主体** → 状态显示 `installed`。**重启 Sonora 后新版本才生效**。
4. 核心：点 **下载并校验核心** → 校验通过后点 **安装替换核心**。若核心正在运行，会先停止、替换并写 manifest、再自动拉起。
5. 全程展开右侧日志抽屉看实时阶段；失败行会带 `stage`（hash / staged / healthcheck 等）。

安装器保证：校验过的包才会装；装前再核一次 hash；旧版先备份；同目录 rename 交换；健康检查失败自动回滚。

## 2. 回滚（UI）

1. 在同一升级页的备份下拉里选版本（默认最新备份）。
2. 点 **回滚主体** 或 **回滚核心**。
3. 主体回滚后需重启；核心回滚后若原本运行会自动拉起。
4. 若发生自动回滚，状态行显示 `rolledBack=true`，日志有「已尝试回滚」。

备份位置（每次替换前自动生成，`backup.json` 记录版本、目标路径、hash）：

```
~/Library/Application Support/Sonora/Backups/app/<id>/Sonora.app + backup.json
~/Library/Application Support/Sonora/Backups/core/<id>/squeezelite + core-manifest.json + backup.json
```

## 3. 手动恢复（UI 不可用时）

```bash
B="$HOME/Library/Application Support/Sonora/Backups/<track>/<id>"

# 主体：恢复旧 bundle 并验签
ditto "$B/Sonora.app" /Applications/Sonora.app
codesign --verify --deep --strict /Applications/Sonora.app

# 核心：停核心 → 恢复二进制与 manifest → 验签 → 看版本
pkill -f 'squeezelite -s' || true
ditto "$B/squeezelite" "$HOME/Library/Application Support/Sonora/Core/squeezelite"
ditto "$B/core-manifest.json" "$HOME/Library/Application Support/Sonora/Core/core-manifest.json"
chmod 755 "$HOME/Library/Application Support/Sonora/Core/squeezelite"
codesign --verify --strict "$HOME/Library/Application Support/Sonora/Core/squeezelite"
"$HOME/Library/Application Support/Sonora/Core/squeezelite" -t | head -1
```

`<track>` 为 `app` 或 `core`；`<id>` 取 `backup.json` 同目录名。恢复核心后重新点连接页「连接 LMS」即可拉起。

## 4. 升级后验收

```bash
# 主体版本与签名
/usr/libexec/PlistBuddy -c 'Print CFBundleShortVersionString' /Applications/Sonora.app/Contents/Info.plist
codesign --verify --deep --strict /Applications/Sonora.app

# 核心二进制 hash 必须等于用户 manifest 的 binarySha256
shasum -a 256 "$HOME/Library/Application Support/Sonora/Core/squeezelite"
python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["binarySha256"])' \
  "$HOME/Library/Application Support/Sonora/Core/core-manifest.json"

# LMS 在线播放器（不能只看 players count）
cd ~/Projects/sonora_v2 && dart run tool/probe.dart --with-core \
  --lms-creds=/Users/song/.squeezelite_gui/config.json
```

可选全流程自检（临时目录，不碰真实安装）：

```bash
cd ~/Projects/sonora_v2 && dart run tool/probe_install.dart
```

## N1 曲库与播放补充

- 曲库页新增「搜索歌曲 / 专辑」：输入关键词点搜索，结果按专辑 / 歌曲分组显示；点专辑进入曲目，点歌曲直接播放。
- 专辑与歌曲列表显示封面；选中专辑后显示专辑简介与艺人简介。
- 播放页显示当前封面与逐行歌词，当前行随进度高亮；下方「播放队列 N 首」可点任意曲目跳转，结束时自动下一首。
- 可选 CLI 验收：`cd ~/Projects/sonora_v2 && dart run tool/probe_navidrome_extras.dart --query=爱`。

## 连接与曲库切换补充

- 「连接」页右上「修改配置」集中维护 LMS / Navidrome 地址与账号密码；账号留空时会读取凭证路径里的旧配置。
- 「曲库」页分条显示 **LMS 曲库** 与 **Navidrome 曲库**，点「切换」切换当前轨道：切到 LMS 自动拉起引擎，切到 Navidrome 自动停止。曲目列表与封面/歌词随轨道切换。
- LMS 输出设备在「修改配置 → 输出设备」里扫描、选择并重命名；参数预设含「完美码率直通 / 最佳音质 / DSD直通 / USB DAC 直连」，每项参数下方有帮助说明。上次选中的设备会在下次启动自动沿用。
- 参数要点：`-o` 输出设备名（绕过系统混音应选 USB DAC）；`-a 10:0` 表示 10ms 延迟且不允许 macOS 重采样；`-r 44100-384000` 告诉 LMS 可支持的采样率；`-D` 在 DAC 支持 DoP 时直通 DSD。
- CLI 验收：`cd ~/Projects/sonora_v2 && dart run tool/probe_library_switch.dart`。

## 5. 注意事项

- adhoc 签名无法公证：网络下载的 app 首次打开需右键「打开」；首次联网需允许「本地网络」。
- 替换的是用户目录核心，不是 bundle 内置核心；不要手改 `/Applications/Sonora.app/Contents/Resources/Core`。
- 主体升级必须重启 app；核心升级/回滚会自动停启。失败时保留备份供回滚，暂存目录在成功后清理。
