// 验收：从真实 settings.json 加载服务器，凭证路径为空时能回退并取到曲库。
// 用法：dart run tool/probe_server_settings.dart
import "dart:convert";
import "dart:io";

import "package:sonora/core/services.dart";
import "package:sonora/core/settings.dart";
import "package:sonora/navidrome/subsonic.dart";

Future<void> main() async {
  final out = <String, dynamic>{};
  try {
    final settings = SettingsStore().load();
    final server = settings.activeServer;
    if (server == null) throw Exception("没有 OpenSubsonic 服务器");
    out
      ..["serverName"] = server.name
      ..["host"] = server.host
      ..["credsPath"] = server.credsPath;
    if (server.credsPath != defaultNavCredsPath) {
      throw Exception("凭证路径未回退到默认值");
    }
    var user = server.user;
    var pass = server.password;
    if (user.isEmpty || pass.isEmpty) {
      final c = readCreds(server.credsPath);
      user = c["user"] ?? "";
      pass = c["password"] ?? c["pass"] ?? "";
    }
    if (user.isEmpty || pass.isEmpty) throw Exception("凭证仍不完整");
    final target = NavidromeTarget(
      host: server.host,
      auth: SubsonicAuth(
        user: user,
        password: pass,
        salt: DateTime.now().microsecondsSinceEpoch.toString(),
      ),
    );
    final ping = await probeNavidrome(target);
    final albums = await fetchNavidromeAlbums(target);
    out
      ..["reachable"] = ping.reachable
      ..["version"] = ping.version
      ..["albums"] = albums.length
      ..["verdict"] = ping.reachable && albums.isNotEmpty ? "PASS" : "FAIL";
  } catch (e) {
    out
      ..["verdict"] = "FAIL"
      ..["error"] = e.toString().split("\n").first;
  }
  stdout.writeln(jsonEncode(out));
}
