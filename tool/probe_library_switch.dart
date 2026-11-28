// 曲库切换与输出设备参数验收探针（不打印凭证）。
// 用法：dart run tool/probe_library_switch.dart [--creds=/path] [--profile=best]
import "dart:convert";
import "dart:io";

import "package:sonora/core/services.dart";
import "package:sonora/core/settings.dart";
import "package:sonora/lms/library.dart";
import "package:sonora/squeezelite/core_runner.dart";

Map<String, String> opts(List<String> args) {
  final out = <String, String>{};
  for (final a in args) {
    if (a.startsWith("--") && a.contains("=")) {
      final i = a.indexOf("=");
      out[a.substring(2, i)] = a.substring(i + 1);
    }
  }
  return out;
}

Future<void> main(List<String> args) async {
  final o = opts(args);
  final credPath = o["creds"] ?? "/Users/song/.squeezelite_gui/config.json";
  final profile = o["profile"] ?? "bitperfect";
  final out = <String, dynamic>{"creds": credPath, "profile": profile};
  void log(String s) => stdout.writeln("[switch] $s");
  try {
    final target = lmsTargetFromArgs(["--lms-creds=$credPath"]);
    final info = await probeLms(target);
    out["lmsVersion"] = info.version;
    if (!info.reachable) throw Exception("LMS 不可达：${info.error}");

    final albums = await fetchLmsAlbums(target, count: 200);
    out["albums"] = albums.length;
    out["firstAlbum"] = albums.isEmpty ? "" : albums.first.name;
    if (albums.isEmpty) throw Exception("LMS 专辑为空");
    final songs = await fetchLmsTracks(target, album: albums.first.name);
    out["firstAlbumSongs"] = songs.length;
    if (songs.isEmpty) throw Exception("首张专辑没有曲目");

    var core = CoreRunner.userCorePath();
    if (!File(core).existsSync()) {
      final bundled = CoreRunner.bundledCorePath();
      if (bundled == null || !File(bundled).existsSync()) {
        throw Exception("找不到核心二进制");
      }
      core = bundled;
    }
    final listed = await Process.run(core, ["-l"]);
    final devices = parseOutputDevices("${listed.stdout}\n${listed.stderr}");
    out["devices"] = devices.map((d) => d.name).toList();
    log(
      "扫描到 ${devices.length} 个设备，默认沿用上一次：${devices.isEmpty ? '系统默认' : devices.first.id}",
    );

    final params = paramsForProfile(profile).copyWith(
      device: devices.isEmpty ? "" : devices.first.name,
      deviceName: devices.isEmpty ? "" : devices.first.name,
    );
    out["args"] = buildCoreArgs(
      params: params,
      lmsHost: target.host,
      slimPort: target.slimPort,
    );

    final runner = CoreRunner(
      lmsHost: target.host,
      slimPort: target.slimPort,
      params: params,
      onLog: log,
    );
    out["started"] = (await runner.start()).pid;
    final online = await waitForOnlinePlayers(
      target,
      timeout: const Duration(seconds: 20),
    );
    out["onlinePlayers"] = online.length;
    await runner.stop();
    out["verdict"] = online.isNotEmpty ? "PASS" : "FAIL";
  } catch (e) {
    out["verdict"] = "FAIL";
    out["error"] = e.toString().split("\n").first;
  }
  stdout.writeln(jsonEncode(out));
  exitCode = out["verdict"] == "PASS" ? 0 : 1;
}
