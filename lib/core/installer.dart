import "dart:convert";
import "dart:io";

import "../squeezelite/core_runner.dart";
import "updates.dart";

/// 升级的两条可替换轨道。LMS / Navidrome 只能提示手动升级。
enum UpdateTrack { app, core }

/// 一次升级前的备份索引。备份实体保存在独立目录，回滚只认这份记录。
class BackupRecord {
  const BackupRecord({
    required this.id,
    required this.track,
    required this.version,
    required this.createdAt,
    required this.targetPath,
    required this.backupPath,
    this.sha256 = "",
    this.notes = "",
  });

  final String id;
  final UpdateTrack track;

  /// 被替换掉的旧版本（主体读 Info.plist，核心读用户目录 manifest）。
  final String version;
  final String createdAt;
  final String targetPath;

  /// 旧文件副本；空字符串表示首次安装，没有可回滚内容。
  final String backupPath;
  final String sha256;
  final String notes;

  Map<String, dynamic> toJson() => <String, dynamic>{
    "id": id,
    "track": track.name,
    "version": version,
    "createdAt": createdAt,
    "targetPath": targetPath,
    "backupPath": backupPath,
    "sha256": sha256,
    "notes": notes,
  };

  factory BackupRecord.fromJson(Map<String, dynamic> m) {
    final trackName = (m["track"] ?? "app").toString();
    final track = UpdateTrack.values.firstWhere(
      (t) => t.name == trackName,
      orElse: () => UpdateTrack.app,
    );
    return BackupRecord(
      id: (m["id"] ?? "").toString(),
      track: track,
      version: (m["version"] ?? "").toString(),
      createdAt: (m["createdAt"] ?? "").toString(),
      targetPath: (m["targetPath"] ?? "").toString(),
      backupPath: (m["backupPath"] ?? "").toString(),
      sha256: (m["sha256"] ?? "").toString(),
      notes: (m["notes"] ?? "").toString(),
    );
  }

  static String sanitize(String s) => s
      .replaceAll(RegExp(r"[^0-9A-Za-z._-]+"), "_")
      .replaceAll(RegExp(r"^_+|_+$"), "");

  static String stamp(DateTime t) {
    String two(int n) => n.toString().padLeft(2, "0");
    return "${t.year}${two(t.month)}${two(t.day)}T${two(t.hour)}${two(t.minute)}${two(t.second)}";
  }

  static String makeId(String version, DateTime t) {
    final v = sanitize(version);
    final us = t.microsecond.toString().padLeft(6, "0");
    return "${v.isEmpty ? "unknown" : v}-${stamp(t)}$us";
  }
}

/// 安装 / 回滚结果。stage 便于 UI 与 CLI 精确显示停在哪一步。
class InstallResult {
  const InstallResult({
    required this.ok,
    required this.stage,
    required this.detail,
    this.path = "",
    this.sha256 = "",
    this.backupId = "",
    this.rolledBack = false,
  });

  final bool ok;

  /// hash / staged / backed_up / install / healthcheck / installed /
  /// rollback / rolled_back / rollback_failed / failed
  final String stage;
  final String detail;
  final String path;
  final String sha256;
  final String backupId;
  final bool rolledBack;

  Map<String, dynamic> toJson() => <String, dynamic>{
    "ok": ok,
    "stage": stage,
    "path": path,
    "sha256": sha256,
    "backupId": backupId,
    "rolledBack": rolledBack,
    "detail": detail,
  };
}

String updateSupportDir({String? home}) {
  final h = home ?? Platform.environment["HOME"] ?? "";
  return "$h/Library/Application Support/Sonora";
}

String backupRootFor(UpdateTrack track, {String? home}) =>
    "${updateSupportDir(home: home)}/Backups/${track.name}";

String backupDirFor(UpdateTrack track, String id, {String? home}) =>
    "${backupRootFor(track, home: home)}/$id";

String userCoreManifestPath({String? home}) =>
    "${updateSupportDir(home: home)}/Core/core-manifest.json";

/// 从 Info.plist 原文读取短版本号；纯函数便于单测。
String? parseInfoPlistVersion(String text) {
  final m = RegExp(
    r"<key>CFBundleShortVersionString</key>\s*<string>([^<]+)</string>",
  ).firstMatch(text);
  final v = m?.group(1)?.trim() ?? "";
  return v.isEmpty ? null : v;
}

/// `Squeezelite 2.0.0-1610, Copyright ...` → version / revision。
Map<String, dynamic>? parseSqueezeliteVersion(String output) {
  final m = RegExp(
    r"Squeezelite\s+(\d+\.\d+(?:\.\d+)?)[.\-rR](\d+)",
  ).firstMatch(output);
  if (m == null) return null;
  return <String, dynamic>{
    "version": m.group(1),
    "revision": int.tryParse(m.group(2) ?? ""),
  };
}

String normalizeUpdateVersion(String s) =>
    s.trim().replaceFirst(RegExp(r"^v"), "");

Map<String, dynamic>? readCoreManifest(String path) {
  try {
    final decoded = jsonDecode(File(path).readAsStringSync());
    if (decoded is Map<String, dynamic>) return decoded;
  } catch (_) {}
  return null;
}

String _homeOf(String? home) => home ?? Platform.environment["HOME"] ?? "";

/// 主体与核心的替换 / 回滚服务。
///
/// 设计约束：
/// - 只接受已经通过 [VerifyResult] 校验的产物；安装前再核一次 hash。
/// - 旧版先复制到 `~/Library/Application Support/Sonora/Backups/<track>/<id>`，
///   再用同目录 rename 做交换；任何失败都会尝试自动恢复。
/// - 目标路径可注入，方便在假目录里做无 GUI、无特权端到端验证。
class UpdateInstaller {
  UpdateInstaller({
    String? home,
    String? appTarget,
    String? coreTarget,
    this.onLog,
    this.strictSigning = true,
    this.verifySignature = true,
    this.healthcheckOverride,
  }) : home = _homeOf(home),
       appTarget = appTarget ?? "/Applications/Sonora.app",
       coreTarget = coreTarget ?? CoreRunner.userCorePath(home: _homeOf(home)),
       cacheDir = "${_homeOf(home)}/Library/Caches/Sonora/updates";

  final String home;
  final String appTarget;
  final String coreTarget;
  final String cacheDir;
  final void Function(String line)? onLog;

  /// 核心裸 Mach-O 是否做 adhoc 签名（分发要求）。测试可用 false。
  final bool strictSigning;

  /// 安装前后是否调用 codesign --verify。假 bundle 测试可用 false。
  final bool verifySignature;

  /// 仅用于自动化验收：返回 false 可模拟健康检查失败，验证自动回滚。
  final bool Function(String track, String path)? healthcheckOverride;

  void _log(String line) => onLog?.call(line);

  Future<ProcessResult> _run(
    String exe,
    List<String> args, {
    String? log,
  }) async {
    if (log != null) _log(log);
    final r = await Process.run(exe, args);
    if (r.exitCode != 0) {
      final err = r.stderr.toString().trim();
      _log(
        "$exe 失败(${r.exitCode}) ${err.isEmpty ? r.stdout.toString().trim() : err}",
      );
    }
    return r;
  }

  Future<void> _remove(String path) async {
    final f = File(path);
    if (f.existsSync()) {
      await f.delete();
      return;
    }
    final d = Directory(path);
    if (d.existsSync()) await d.delete(recursive: true);
  }

  Future<bool> _copy(String src, String dest) async {
    if (!File(src).existsSync() && !Directory(src).existsSync()) return false;
    await File(dest).parent.create(recursive: true);
    final r = await _run("ditto", [src, dest]);
    return r.exitCode == 0 &&
        (File(dest).existsSync() || Directory(dest).existsSync());
  }

  Future<bool> _move(String src, String dest) async {
    if (!File(src).existsSync() && !Directory(src).existsSync()) return false;
    final r = await _run("mv", [src, dest]);
    return r.exitCode == 0;
  }

  Future<String> _sha(String path) => sha256File(path);

  Future<void> _stripQuarantine(String path) async {
    final r = await Process.run("xattr", ["-d", "com.apple.quarantine", path]);
    if (r.exitCode != 0 && !r.stderr.toString().contains("No such xattr")) {
      _log("去 quarantine 失败：${r.stderr.toString().trim()}");
    }
  }

  Future<void> _writeRecord({
    required UpdateTrack track,
    required String id,
    required String version,
    required String targetPath,
    required String backupPath,
    String sha256 = "",
    String notes = "",
  }) async {
    final dir = backupDirFor(track, id, home: home);
    await Directory(dir).create(recursive: true);
    final rec = BackupRecord(
      id: id,
      track: track,
      version: version,
      createdAt: DateTime.now().toUtc().toIso8601String(),
      targetPath: targetPath,
      backupPath: backupPath,
      sha256: sha256,
      notes: notes,
    );
    await File(
      "$dir/backup.json",
    ).writeAsString("${jsonEncode(rec.toJson())}\n");
  }

  List<BackupRecord> listBackups(UpdateTrack track) {
    final root = Directory(backupRootFor(track, home: home));
    if (!root.existsSync()) return <BackupRecord>[];
    final out = <BackupRecord>[];
    for (final e in root.listSync()) {
      if (e is! Directory) continue;
      final f = File("${e.path}/backup.json");
      if (!f.existsSync()) continue;
      try {
        out.add(
          BackupRecord.fromJson(
            jsonDecode(f.readAsStringSync()) as Map<String, dynamic>,
          ),
        );
      } catch (_) {
        _log("忽略损坏的备份索引：${f.path}");
      }
    }
    out.sort((a, b) => b.createdAt.compareTo(a.createdAt));
    return out;
  }

  Future<bool> _verifyApp(String path, {String? expectedVersion}) async {
    final forced = healthcheckOverride?.call("app", path);
    if (forced != null) {
      _log("主体健康检查被测试钩子覆盖为 $forced");
      return forced;
    }
    final plistPath = "$path/Contents/Info.plist";
    if (!Directory(path).existsSync() || !File(plistPath).existsSync()) {
      _log("健康检查失败：缺少 $plistPath");
      return false;
    }
    final version = parseInfoPlistVersion(File(plistPath).readAsStringSync());
    if (version == null) {
      _log("健康检查失败：Info.plist 无 CFBundleShortVersionString");
      return false;
    }
    if (expectedVersion != null &&
        normalizeUpdateVersion(version) !=
            normalizeUpdateVersion(expectedVersion)) {
      _log("健康检查失败：版本 $version != 期望 $expectedVersion");
      return false;
    }
    if (verifySignature) {
      final r = await _run("codesign", [
        "--verify",
        "--deep",
        "--strict",
        path,
      ]);
      if (r.exitCode != 0) return false;
    }
    _log("主体健康检查通过：$path ($version)");
    return true;
  }

  Future<bool> _verifyCore(
    String path, {
    String? expectedSha,
    String? expectedVersion,
    int? revision,
  }) async {
    final forced = healthcheckOverride?.call("core", path);
    if (forced != null) {
      _log("核心健康检查被测试钩子覆盖为 $forced");
      return forced;
    }
    if (!File(path).existsSync()) {
      _log("健康检查失败：核心不存在 $path");
      return false;
    }
    if (File(path).statSync().mode & 0x111 == 0) {
      _log("健康检查失败：核心不可执行 $path");
      return false;
    }
    if (expectedSha != null && expectedSha.isNotEmpty) {
      final sha = await _sha(path);
      if (sha.toLowerCase() != expectedSha.toLowerCase()) {
        _log("健康检查失败：核心 sha256 $sha != $expectedSha");
        return false;
      }
    }
    if (verifySignature) {
      final r = await _run("codesign", ["--verify", "--strict", path]);
      if (r.exitCode != 0) return false;
    }
    ProcessResult probe;
    try {
      probe = await Process.run(path, [
        "-t",
      ]).timeout(const Duration(seconds: 5));
    } catch (_) {
      _log("健康检查失败：核心 -t 探测超时");
      return false;
    }
    final parsed = parseSqueezeliteVersion(probe.stdout.toString());
    if (parsed == null) {
      _log("健康检查失败：核心 -t 未输出版本：${probe.stdout.toString().trim()}");
      return false;
    }
    if (expectedVersion != null &&
        normalizeUpdateVersion(parsed["version"].toString()) !=
            normalizeUpdateVersion(expectedVersion)) {
      _log("健康检查失败：核心版本 ${parsed["version"]} != $expectedVersion");
      return false;
    }
    if (revision != null && parsed["revision"] != revision) {
      _log("健康检查失败：核心 revision ${parsed["revision"]} != $revision");
      return false;
    }
    _log("核心健康检查通过：$path (${parsed["version"]}-${parsed["revision"]})");
    return true;
  }

  /// 替换程序主体：zip 已在升级页校验过，这里再次核对 hash 后执行。
  Future<InstallResult> installApp({
    required String zipPath,
    String? expectedSha,
    String? expectedVersion,
  }) async {
    final id = BackupRecord.makeId(
      expectedVersion ?? "unknown",
      DateTime.now(),
    );
    final stage = "$cacheDir/app/stage/$id";
    final backupDir = backupDirFor(UpdateTrack.app, id, home: home);
    final parent = Directory(appTarget).parent.path;
    final newPath = "$parent/.Sonora.app.new-$id";
    final oldPath = "$parent/.Sonora.app.old-$id";
    var backupId = "";
    var swapped = false;
    var restored = false;

    // 所有 fail() 调用都发生在交换目标之前，不需要回滚。
    InstallResult fail(String stageName, String detail) => InstallResult(
      ok: false,
      stage: stageName,
      detail: detail,
      backupId: backupId,
    );

    try {
      if (!File(zipPath).existsSync()) {
        return fail("staged", "zip 不存在：$zipPath");
      }
      if (expectedSha != null && expectedSha.isNotEmpty) {
        final sha = await _sha(zipPath);
        if (sha.toLowerCase() != expectedSha.toLowerCase()) {
          return fail("hash", "安装前 zip hash 已变化：$sha != $expectedSha");
        }
      }
      await Directory(stage).create(recursive: true);
      final unzip = await _run("ditto", [
        "-x",
        "-k",
        zipPath,
        stage,
      ], log: "解压主体到暂存 $stage");
      if (unzip.exitCode != 0) return fail("staged", "解压失败");

      final stagedApp = "$stage/Sonora.app";
      final stagedPlist = File("$stagedApp/Contents/Info.plist");
      if (!stagedPlist.existsSync()) {
        return fail("staged", "zip 内缺少 Sonora.app/Contents/Info.plist");
      }
      final stagedVersion = parseInfoPlistVersion(
        stagedPlist.readAsStringSync(),
      );
      if (stagedVersion == null || stagedVersion.isEmpty) {
        return fail("staged", "暂存包没有版本号");
      }
      if (expectedVersion != null &&
          normalizeUpdateVersion(stagedVersion) !=
              normalizeUpdateVersion(expectedVersion)) {
        return fail("staged", "包版本 $stagedVersion != 期望 $expectedVersion");
      }
      if (!await _verifyApp(stagedApp, expectedVersion: stagedVersion)) {
        return fail("staged", "暂存包健康检查失败");
      }

      await Directory(backupDir).create(recursive: true);
      final hadOld = Directory(appTarget).existsSync();
      var oldVersion = "unknown";
      var oldSha = "";
      var backupPath = "";
      if (hadOld) {
        oldVersion =
            parseInfoPlistVersion(
              File("$appTarget/Contents/Info.plist").readAsStringSync(),
            ) ??
            "unknown";
        backupPath = "$backupDir/Sonora.app";
        if (!await _copy(appTarget, backupPath)) {
          return fail("backed_up", "备份旧主体失败：$appTarget");
        }
        oldSha = await _sha("$backupPath/Contents/Info.plist");
      }
      await _writeRecord(
        track: UpdateTrack.app,
        id: id,
        version: oldVersion,
        targetPath: appTarget,
        backupPath: backupPath,
        sha256: oldSha,
        notes: hadOld ? "" : "首次安装，无旧版可回滚",
      );
      backupId = id;
      _log(hadOld ? "已备份旧主体 → $backupPath" : "首次安装，没有旧主体可备份");

      await _remove(newPath);
      await _remove(oldPath);
      if (!await _move(stagedApp, newPath)) {
        return fail("install", "无法把暂存包移到目标目录");
      }
      if (hadOld) {
        if (!await _move(appTarget, oldPath)) {
          await _remove(newPath);
          return fail("install", "旧主体移出失败，未替换");
        }
        swapped = true;
      }
      if (!await _move(newPath, appTarget)) {
        if (swapped && Directory(oldPath).existsSync()) {
          restored = await _move(oldPath, appTarget);
        }
        return InstallResult(
          ok: false,
          stage: "install",
          detail: "新主体就位失败",
          backupId: backupId,
          rolledBack: restored,
        );
      }

      if (!await _verifyApp(appTarget, expectedVersion: stagedVersion)) {
        if (swapped && Directory(oldPath).existsSync()) {
          restored = await _move(oldPath, appTarget);
        }
        if (!restored && backupPath.isNotEmpty) {
          await _remove(appTarget);
          restored = await _copy(backupPath, appTarget);
        }
        return InstallResult(
          ok: false,
          stage: "healthcheck",
          detail: "新主体健康检查失败，已尝试回滚",
          backupId: backupId,
          rolledBack: restored,
        );
      }
      await _remove(oldPath);
      await _remove(stage);
      return InstallResult(
        ok: true,
        stage: "installed",
        path: appTarget,
        sha256: expectedSha ?? "",
        backupId: backupId,
        detail: "主体已替换为 $stagedVersion（重启后生效）",
      );
    } catch (e) {
      if (swapped && Directory(oldPath).existsSync()) {
        restored = await _move(oldPath, appTarget);
      }
      return InstallResult(
        ok: false,
        stage: "failed",
        detail: e.toString().split("\n").first,
        backupId: backupId,
        rolledBack: restored,
      );
    }
  }

  /// 替换用户目录里的 squeezelite：签名后的二进制 + 用户 manifest 一起换。
  Future<InstallResult> installCore({
    required VerifyResult verification,
    required String version,
    int? revision,
  }) async {
    final label = revision == null ? version : "$version.r$revision";
    final id = BackupRecord.makeId(label, DateTime.now());
    final stageDir = "$cacheDir/core/stage/$id";
    final staged = "$stageDir/squeezelite";
    final backupDir = backupDirFor(UpdateTrack.core, id, home: home);
    final manifestPath = userCoreManifestPath(home: home);
    final parent = Directory(coreTarget).parent.path;
    final oldPath = "$parent/.squeezelite.old-$id";
    final oldManifestPath = "$parent/.core-manifest.old-$id.json";
    var backupId = "";
    var swapped = false;
    var manifestSwapped = false;
    var restored = false;

    Future<void> restore() async {
      if (swapped && File(oldPath).existsSync()) {
        await _remove(coreTarget);
        restored = await _copy(oldPath, coreTarget);
      }
      if (manifestSwapped && File(oldManifestPath).existsSync()) {
        await _remove(manifestPath);
        await _copy(oldManifestPath, manifestPath);
      }
      await _remove(oldPath);
      await _remove(oldManifestPath);
    }

    try {
      if (verification.binaryPath.isEmpty ||
          !File(verification.binaryPath).existsSync()) {
        return InstallResult(
          ok: false,
          stage: "staged",
          detail: "校验结果里没有可安装的核心二进制；请重新下载并校验",
        );
      }
      await Directory(stageDir).create(recursive: true);
      await _remove(staged);
      if (!await _copy(verification.binaryPath, staged)) {
        return InstallResult(ok: false, stage: "staged", detail: "复制核心到暂存失败");
      }
      final preSha = await _sha(staged);
      if (verification.sha256.isNotEmpty &&
          preSha.toLowerCase() != verification.sha256.toLowerCase()) {
        return InstallResult(
          ok: false,
          stage: "hash",
          detail: "暂存核心 hash 变化：$preSha != ${verification.sha256}",
        );
      }
      if (strictSigning) {
        final sign = await _run("codesign", [
          "--force",
          "--sign",
          "-",
          staged,
        ], log: "adhoc 签名暂存核心 $staged");
        if (sign.exitCode != 0) {
          return InstallResult(
            ok: false,
            stage: "staged",
            detail: "核心 adhoc 签名失败",
          );
        }
      }
      await _run("chmod", ["755", staged]);
      await _stripQuarantine(staged);
      final finalSha = await _sha(staged);
      if (!await _verifyCore(
        staged,
        expectedSha: finalSha,
        expectedVersion: version,
        revision: revision,
      )) {
        return InstallResult(
          ok: false,
          stage: "staged",
          detail: "暂存核心健康检查失败，未替换",
        );
      }

      await Directory(backupDir).create(recursive: true);
      var oldVersion = "unknown";
      var oldSha = "";
      var backupPath = "";
      if (File(coreTarget).existsSync()) {
        backupPath = "$backupDir/squeezelite";
        if (!await _copy(coreTarget, backupPath)) {
          return InstallResult(
            ok: false,
            stage: "backed_up",
            detail: "备份旧核心失败",
          );
        }
        oldSha = await _sha(coreTarget);
      }
      final oldManifest = readCoreManifest(manifestPath);
      if (oldManifest != null) {
        oldVersion = (oldManifest["version"] ?? oldVersion).toString();
        final rev = oldManifest["revision"];
        if (rev != null) oldVersion = "$oldVersion.r$rev";
        await _copy(manifestPath, "$backupDir/core-manifest.json");
      }
      await _writeRecord(
        track: UpdateTrack.core,
        id: id,
        version: oldVersion,
        targetPath: coreTarget,
        backupPath: backupPath,
        sha256: oldSha,
        notes: "安装 $label",
      );
      backupId = id;
      _log(backupPath.isEmpty ? "首次安装核心，无旧版可回滚" : "已备份旧核心 → $backupPath");

      await _remove(oldPath);
      await _remove(oldManifestPath);
      if (File(coreTarget).existsSync()) {
        if (!await _move(coreTarget, oldPath)) {
          return InstallResult(
            ok: false,
            stage: "install",
            detail: "旧核心移出失败，未替换",
          );
        }
        swapped = true;
      }
      if (File(manifestPath).existsSync()) {
        if (!await _move(manifestPath, oldManifestPath)) {
          await restore();
          return InstallResult(
            ok: false,
            stage: "install",
            detail: "旧 manifest 移出失败",
            backupId: backupId,
            rolledBack: restored,
          );
        }
        manifestSwapped = true;
      }
      if (!await _copy(staged, coreTarget)) {
        await restore();
        return InstallResult(
          ok: false,
          stage: "install",
          detail: "新核心复制失败",
          backupId: backupId,
          rolledBack: restored,
        );
      }
      await _run("chmod", ["755", coreTarget]);
      await _stripQuarantine(coreTarget);
      await File(manifestPath).writeAsString(
        "${jsonEncode(<String, dynamic>{"version": version, "revision": revision, "binarySha256": finalSha, "binarySize": File(coreTarget).lengthSync(), "signedAfterAdhoc": strictSigning, "installedAt": DateTime.now().toUtc().toIso8601String(), "source": verification.path})}\n",
      );

      if (!await _verifyCore(
        coreTarget,
        expectedSha: finalSha,
        expectedVersion: version,
        revision: revision,
      )) {
        await restore();
        return InstallResult(
          ok: false,
          stage: "healthcheck",
          detail: "新核心健康检查失败，已尝试回滚",
          backupId: backupId,
          rolledBack: restored,
        );
      }
      await _remove(oldPath);
      await _remove(oldManifestPath);
      await _remove(stageDir);
      return InstallResult(
        ok: true,
        stage: "installed",
        path: coreTarget,
        sha256: finalSha,
        backupId: backupId,
        detail: "核心已替换为 $label（签名后 hash $finalSha）",
      );
    } catch (e) {
      await restore();
      return InstallResult(
        ok: false,
        stage: "failed",
        detail: e.toString().split("\n").first,
        backupId: backupId,
        rolledBack: restored,
      );
    }
  }

  /// 手动回滚：默认取最新备份，也可指定备份 ID。
  Future<InstallResult> rollback({
    required UpdateTrack track,
    String? backupId,
  }) async {
    final backups = listBackups(track);
    if (backups.isEmpty) {
      return InstallResult(ok: false, stage: "rollback", detail: "没有可回滚的备份");
    }
    BackupRecord? chosen;
    if (backupId != null && backupId.isNotEmpty) {
      for (final b in backups) {
        if (b.id == backupId) chosen = b;
      }
      if (chosen == null) {
        return InstallResult(
          ok: false,
          stage: "rollback",
          detail: "找不到备份 $backupId",
        );
      }
    } else {
      chosen = backups.first;
    }
    if (chosen.backupPath.isEmpty ||
        (!File(chosen.backupPath).existsSync() &&
            !Directory(chosen.backupPath).existsSync())) {
      return InstallResult(
        ok: false,
        stage: "rollback",
        detail: "备份实体不存在：${chosen.backupPath}",
        backupId: chosen.id,
      );
    }
    _log("回滚 ${track.name} → ${chosen.version}（备份 ${chosen.id}）");
    return track == UpdateTrack.app
        ? _rollbackApp(chosen)
        : _rollbackCore(chosen);
  }

  Future<InstallResult> _rollbackApp(BackupRecord rec) async {
    final suffix = BackupRecord.stamp(DateTime.now());
    final parent = Directory(appTarget).parent.path;
    final oldPath = "$parent/.Sonora.app.rb-$suffix";
    var swapped = false;
    var restored = false;
    try {
      await _remove(oldPath);
      if (Directory(appTarget).existsSync()) {
        if (!await _move(appTarget, oldPath)) {
          return InstallResult(
            ok: false,
            stage: "rollback",
            detail: "当前主体移出失败",
            backupId: rec.id,
          );
        }
        swapped = true;
      }
      if (!await _copy(rec.backupPath, appTarget)) {
        if (swapped) restored = await _move(oldPath, appTarget);
        return InstallResult(
          ok: false,
          stage: "rollback",
          detail: "恢复旧主体失败",
          backupId: rec.id,
          rolledBack: restored,
        );
      }
      final healthy = await _verifyApp(
        appTarget,
        expectedVersion: rec.version == "unknown" ? null : rec.version,
      );
      if (!healthy) {
        if (swapped) restored = await _move(oldPath, appTarget);
        return InstallResult(
          ok: false,
          stage: "rollback_failed",
          detail: "回滚后健康检查失败",
          backupId: rec.id,
          rolledBack: restored,
        );
      }
      await _remove(oldPath);
      return InstallResult(
        ok: true,
        stage: "rolled_back",
        path: appTarget,
        backupId: rec.id,
        detail: "主体已回滚到 ${rec.version}（重启后生效）",
      );
    } catch (e) {
      if (swapped && Directory(oldPath).existsSync()) {
        restored = await _move(oldPath, appTarget);
      }
      return InstallResult(
        ok: false,
        stage: "rollback_failed",
        detail: e.toString().split("\n").first,
        backupId: rec.id,
        rolledBack: restored,
      );
    }
  }

  Future<InstallResult> _rollbackCore(BackupRecord rec) async {
    final suffix = BackupRecord.stamp(DateTime.now());
    final manifestPath = userCoreManifestPath(home: home);
    final parent = Directory(coreTarget).parent.path;
    final oldPath = "$parent/.squeezelite.rb-$suffix";
    final oldManifestPath = "$parent/.core-manifest.rb-$suffix.json";
    final backupManifest =
        "${Directory(rec.backupPath).parent.path}/core-manifest.json";
    var swapped = false;
    var manifestSwapped = false;
    var restored = false;
    try {
      await _remove(oldPath);
      await _remove(oldManifestPath);
      if (File(coreTarget).existsSync()) {
        if (!await _move(coreTarget, oldPath)) {
          return InstallResult(
            ok: false,
            stage: "rollback",
            detail: "当前核心移出失败",
            backupId: rec.id,
          );
        }
        swapped = true;
      }
      if (File(manifestPath).existsSync()) {
        await _move(manifestPath, oldManifestPath);
        manifestSwapped = true;
      }
      if (!await _copy(rec.backupPath, coreTarget)) {
        if (swapped) restored = await _copy(oldPath, coreTarget);
        return InstallResult(
          ok: false,
          stage: "rollback",
          detail: "恢复旧核心失败",
          backupId: rec.id,
          rolledBack: restored,
        );
      }
      await _run("chmod", ["755", coreTarget]);
      await _stripQuarantine(coreTarget);
      if (File(backupManifest).existsSync()) {
        await _copy(backupManifest, manifestPath);
      }
      final healthy = await _verifyCore(
        coreTarget,
        expectedSha: rec.sha256.isEmpty ? null : rec.sha256,
      );
      if (!healthy) {
        if (swapped) restored = await _copy(oldPath, coreTarget);
        if (manifestSwapped && File(oldManifestPath).existsSync()) {
          await _copy(oldManifestPath, manifestPath);
        }
        return InstallResult(
          ok: false,
          stage: "rollback_failed",
          detail: "回滚后核心健康检查失败",
          backupId: rec.id,
          rolledBack: restored,
        );
      }
      await _remove(oldPath);
      await _remove(oldManifestPath);
      return InstallResult(
        ok: true,
        stage: "rolled_back",
        path: coreTarget,
        sha256: rec.sha256,
        backupId: rec.id,
        detail: "核心已回滚到 ${rec.version}",
      );
    } catch (e) {
      if (swapped && File(oldPath).existsSync()) {
        restored = await _copy(oldPath, coreTarget);
      }
      if (manifestSwapped && File(oldManifestPath).existsSync()) {
        await _copy(oldManifestPath, manifestPath);
      }
      return InstallResult(
        ok: false,
        stage: "rollback_failed",
        detail: e.toString().split("\n").first,
        backupId: rec.id,
        rolledBack: restored,
      );
    }
  }
}
