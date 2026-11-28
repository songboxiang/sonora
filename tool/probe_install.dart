// 升级替换 + 回滚的无 GUI 端到端探针。
// 在临时目录里模拟 /Applications 与用户核心目录，不触碰真实安装。
// 用法：dart run tool/probe_install.dart [--home=/tmp/x] [--core=0]
import "dart:convert";
import "dart:io";

import "package:sonora/core/installer.dart";
import "package:sonora/core/services.dart";
import "package:sonora/core/updates.dart";

const coreRssUrl =
    "https://sourceforge.net/projects/lmsclients/rss?path=/squeezelite/osx/m1";

Map<String, String> parseArgs(List<String> args) {
  final out = <String, String>{};
  for (final a in args) {
    if (a.startsWith("--") && a.contains("=")) {
      final i = a.indexOf("=");
      out[a.substring(2, i)] = a.substring(i + 1);
    }
  }
  return out;
}

Future<void> run(String exe, List<String> args) async {
  final r = await Process.run(exe, args);
  if (r.exitCode != 0) {
    throw Exception("$exe ${args.join(" ")} 失败：${r.stderr.toString().trim()}");
  }
}

Future<void> main(List<String> args) async {
  final opt = parseArgs(args);
  final tmp = Directory.systemTemp.createTempSync("sonora-upgrade-e2e-");
  final home = opt["home"] ?? tmp.path;
  final repo = Directory.current.path;
  final zip = opt["zip"] ?? "$repo/dist/Sonora-2.1.2.zip";
  final sums = opt["sums"] ?? "$repo/dist/SHA256SUMS";
  final appTarget = opt["app-target"] ?? "${tmp.path}/Applications/Sonora.app";
  final coreTarget =
      opt["core-target"] ??
      "$home/Library/Application Support/Sonora/Core/squeezelite";
  final doCore = opt["core"] != "0";
  final steps = <Map<String, dynamic>>[];
  final out = <String, dynamic>{
    "home": home,
    "appTarget": appTarget,
    "coreTarget": coreTarget,
    "steps": steps,
  };

  void log(String line) => stdout.writeln("[install] $line");

  void addStep(
    String name,
    InstallResult r, {
    Map<String, dynamic> extra = const {},
  }) {
    steps.add(<String, dynamic>{"name": name, ...r.toJson(), ...extra});
    log("$name: ok=${r.ok} stage=${r.stage} ${r.detail}");
  }

  try {
    // ---------- 主体：先造一个 2.0.18 的旧 app ----------
    final sumsMap = parseSha256Sums(File(sums).readAsStringSync());
    final zipName = File(zip).uri.pathSegments.last;
    final expectedSha =
        sumsMap[zipName] ??
        sumsMap.entries.firstWhere((e) => e.key.endsWith(".zip")).value;
    if (expectedSha.isEmpty) throw Exception("SHA256SUMS 里没有 zip 条目");
    final hash = await sha256File(zip);
    if (hash.toLowerCase() != expectedSha.toLowerCase()) {
      throw Exception("zip hash 与 SHA256SUMS 不符");
    }

    final seedDir = "${tmp.path}/seed-app";
    await run("ditto", ["-x", "-k", zip, seedDir]);
    final seedApp = "$seedDir/Sonora.app";
    final plist = File("$seedApp/Contents/Info.plist");
    final originalPlist = plist.readAsStringSync();
    final newVersion = parseInfoPlistVersion(originalPlist);
    if (newVersion == null) throw Exception("新包没有版本号");
    const oldVersion = "2.0.18";
    final patched = plist.readAsStringSync().replaceFirstMapped(
      RegExp(r"(<key>CFBundleShortVersionString</key>\s*<string>)[^<]+"),
      (m) => "${m.group(1)}$oldVersion",
    );
    await plist.writeAsString(patched);
    await run("codesign", ["--force", "--deep", "--sign", "-", seedApp]);
    await Directory(appTarget).parent.create(recursive: true);
    if (Directory(appTarget).existsSync()) {
      await Directory(appTarget).delete(recursive: true);
    }
    await run("ditto", [seedApp, appTarget]);

    final installer = UpdateInstaller(
      home: home,
      appTarget: appTarget,
      coreTarget: coreTarget,
      onLog: log,
    );

    final appInstall = await installer.installApp(
      zipPath: zip,
      expectedSha: expectedSha,
      expectedVersion: newVersion,
    );
    addStep(
      "app_install",
      appInstall,
      extra: <String, dynamic>{
        "versionAfter": parseInfoPlistVersion(
          File("$appTarget/Contents/Info.plist").readAsStringSync(),
        ),
      },
    );
    if (!appInstall.ok) throw Exception("主体安装失败");

    final appRollback = await installer.rollback(track: UpdateTrack.app);
    addStep(
      "app_rollback",
      appRollback,
      extra: <String, dynamic>{
        "versionAfter": parseInfoPlistVersion(
          File("$appTarget/Contents/Info.plist").readAsStringSync(),
        ),
      },
    );
    if (!appRollback.ok) throw Exception("主体回滚失败");

    // ---------- 核心：造旧核心，先验证失败自动回滚，再验证正常安装 + 手动回滚 ----------
    if (doCore) {
      final bundled = File("$repo/macos/Runner/Resources/Core/squeezelite");
      if (!bundled.existsSync()) throw Exception("找不到内置核心 $bundled");
      final oldCoreSha = await sha256File(bundled.path);
      await Directory(coreTarget).parent.create(recursive: true);
      await run("ditto", [bundled.path, coreTarget]);
      final manifestPath = userCoreManifestPath(home: home);
      await File(manifestPath).writeAsString(
        "${jsonEncode(<String, dynamic>{"version": "2.0.0", "revision": 1610, "binarySha256": oldCoreSha})}\n",
      );

      final rss = await getText(coreRssUrl);
      final asset = parseCoreRss(rss);
      if (asset == null) throw Exception("核心 RSS 解析失败");
      final verified = await verifyCoreArchive(
        release: asset,
        cacheDir: "$home/Library/Caches/Sonora/updates/core/e2e",
        extractBinary: true,
        onLog: log,
      );
      steps.add(<String, dynamic>{
        "name": "core_verify",
        "ok": verified.ok,
        "stage": verified.stage,
        "binaryPath": verified.binaryPath,
        "sha256": verified.sha256,
        "detail": verified.detail,
      });
      if (!verified.ok || verified.binaryPath.isEmpty) {
        throw Exception("核心校验/暂存失败：${verified.detail}");
      }

      // 模拟安装后健康检查失败：仅当检查目标是最终安装路径时返回 false。
      final failing = UpdateInstaller(
        home: home,
        appTarget: appTarget,
        coreTarget: coreTarget,
        onLog: log,
        healthcheckOverride: (track, path) =>
            track == "core" && path == coreTarget ? false : true,
      );
      final failResult = await failing.installCore(
        verification: verified,
        version: asset.version,
        revision: asset.revision,
      );
      final shaAfterFail = await sha256File(coreTarget);
      addStep(
        "core_fail_auto_rollback",
        failResult,
        extra: <String, dynamic>{
          "shaAfter": shaAfterFail,
          "oldSha": oldCoreSha,
        },
      );
      if (failResult.ok ||
          failResult.stage != "healthcheck" ||
          !failResult.rolledBack ||
          shaAfterFail != oldCoreSha) {
        throw Exception("核心失败自动回滚未恢复旧二进制");
      }

      final coreInstall = await installer.installCore(
        verification: verified,
        version: asset.version,
        revision: asset.revision,
      );
      final installedSha = await sha256File(coreTarget);
      final installedManifest = readCoreManifest(manifestPath);
      addStep(
        "core_install",
        coreInstall,
        extra: <String, dynamic>{
          "shaAfter": installedSha,
          "manifestVersion": installedManifest?["version"],
          "manifestRevision": installedManifest?["revision"],
        },
      );
      if (!coreInstall.ok || installedSha != coreInstall.sha256) {
        throw Exception("核心安装失败或 hash 不符");
      }

      final coreRollback = await installer.rollback(track: UpdateTrack.core);
      final rollbackSha = await sha256File(coreTarget);
      final rollbackManifest = readCoreManifest(manifestPath);
      addStep(
        "core_rollback",
        coreRollback,
        extra: <String, dynamic>{
          "shaAfter": rollbackSha,
          "oldSha": oldCoreSha,
          "manifestVersion": rollbackManifest?["version"],
          "manifestRevision": rollbackManifest?["revision"],
        },
      );
      if (!coreRollback.ok || rollbackSha != oldCoreSha) {
        throw Exception("核心手动回滚未恢复旧二进制");
      }
    }

    out["verdict"] = "PASS";
  } catch (e) {
    out["verdict"] = "FAIL";
    out["error"] = e.toString().split("\n").first;
  }
  stdout.writeln(jsonEncode(out));
  exitCode = out["verdict"] == "PASS" ? 0 : 1;
}
