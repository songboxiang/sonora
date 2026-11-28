// 播放音质信息探针：从 LMS songinfo 读取当前曲目的码率/格式/位深。
// 用法：dart run tool/probe_audio_fields.dart --lms-creds=/path
import "dart:convert";
import "dart:io";

import "package:sonora/core/services.dart";
import "package:sonora/core/settings.dart";
import "package:sonora/lms/library.dart";
import "package:sonora/squeezelite/core_runner.dart";

Future<void> main(List<String> args) async {
  final out = <String, dynamic>{};
  void log(String s) => stdout.writeln("[audio] $s");
  try {
    final target = lmsTargetFromArgs(args);
    var core = CoreRunner.userCorePath();
    if (!File(core).existsSync()) core = CoreRunner.bundledCorePath() ?? core;
    final params = paramsForProfile("bitperfect").copyWith(
      device: "Apple Virtual Sound Device [Core Audio]",
      deviceName: "Apple Virtual Sound Device [Core Audio]",
      allowResample: true,
    );
    final runner = CoreRunner(
      lmsHost: target.host,
      slimPort: target.slimPort,
      params: params,
      onLog: log,
    );
    await runner.start();
    try {
      final players = await waitForOnlinePlayers(
        target,
        timeout: const Duration(seconds: 20),
      );
      if (players.isEmpty) throw Exception("no online LMS player");
      final tracks = await fetchLmsTracks(target, count: 20);
      if (tracks.isEmpty) throw Exception("no tracks");
      final info = await fetchLmsTrackAudioInfo(target, tracks.first.id);
      out
        ..["trackId"] = tracks.first.id
        ..["summary"] = info.summary
        ..["bitrate"] = info.bitrateText
        ..["sampleRate"] = info.sampleRate
        ..["bitDepth"] = info.bitDepth
        ..["format"] = info.formatText
        ..["lossless"] = info.lossless
        ..["verdict"] = info.hasData ? "PASS" : "FAIL";
      log("音质：${info.summary}");
    } finally {
      await runner.stop();
    }
  } catch (e) {
    out
      ..["verdict"] = "FAIL"
      ..["error"] = e.toString().split("\n").first;
  }
  stdout.writeln(jsonEncode(out));
  exitCode = out["verdict"] == "PASS" ? 0 : 1;
}
