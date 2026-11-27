// ignore_for_file: avoid_print, prefer_interpolation_to_compose_strings
import "dart:convert";
import "dart:io";

import "package:sonora/core/models.dart";
import "package:sonora/lms/protocol.dart";
import "package:sonora/navidrome/subsonic.dart";
import "package:sonora/squeezelite/core_runner.dart";

final HttpClient _http = HttpClient();

Future<String> getText(String url, {Duration timeout = const Duration(seconds: 12)}) async {
  final uri = Uri.parse(url);
  final req = await _http.getUrl(uri).timeout(timeout);
  final resp = await req.close().timeout(timeout);
  final body = await utf8.decoder.bind(resp).join();
  if (resp.statusCode != 200) throw Exception("HTTP ${resp.statusCode}");
  return body;
}

Map<String, dynamic> parseJson(String s) => jsonDecode(s) as Map<String, dynamic>;

Map<String, String> readCreds(String path) {
  final f = File(path);
  if (!f.existsSync()) return <String, String>{};
  final raw = f.readAsStringSync();
  if (raw.trimLeft().startsWith("{")) {
    final decoded = jsonDecode(raw) as Map<String, dynamic>;
    return decoded.map((k, v) => MapEntry<String, String>(k, v.toString()));
  }
  final out = <String, String>{};
  for (final line in f.readAsLinesSync()) {
    final i = line.indexOf("=");
    if (i > 0) out[line.substring(0, i).trim()] = line.substring(i + 1).trim();
  }
  return out;
}

void report(String name, String detail, bool ok) {
  final mark = ok ? "OK" : "!!";
  print("[$mark] $name: $detail");
}

class LmsTarget {
  LmsTarget({
    required this.host,
    required this.port,
    required this.slimPort,
    required this.user,
    required this.pass,
  });

  final String host;
  final int port;
  final int slimPort;
  final String? user;
  final String? pass;

  String? get auth => user != null && pass != null
      ? "Basic ${base64Encode(utf8.encode("$user:$pass"))}"
      : null;
}

LmsTarget parseLmsTarget(List<String> args) {
  String? host;
  String? user;
  String? pass;
  var port = 9000;
  var slimPort = 3483;
  var credPath = "";
  for (final a in args) {
    if (a.startsWith("--lms-host=")) host = a.split("=").skip(1).join("=");
    if (a.startsWith("--lms-port=")) {
      port = int.tryParse(a.split("=").skip(1).join("=")) ?? 9000;
    }
    if (a.startsWith("--slim-port=")) {
      slimPort = int.tryParse(a.split("=").skip(1).join("=")) ?? 3483;
    }
    if (a.startsWith("--lms-user=")) user = a.split("=").skip(1).join("=");
    if (a.startsWith("--lms-pass=")) pass = a.split("=").skip(1).join("=");
    if (a.startsWith("--lms-creds=")) credPath = a.split("=").skip(1).join("=");
  }
  if (credPath.isNotEmpty) {
    final c = readCreds(credPath);
    user ??= c["user"] ?? c["lms_user"];
    pass ??= c["password"] ?? c["pass"] ?? c["lms_pass"];
    final configuredSlim = int.tryParse(c["slim_port"] ?? "");
    if (configuredSlim != null) slimPort = configuredSlim;
  }
  return LmsTarget(
    host: host ?? "192.168.199.2",
    port: port,
    slimPort: slimPort,
    user: user,
    pass: pass,
  );
}

Future<Map<String, dynamic>?> lmsRpc(
  LmsTarget target,
  List<dynamic> params, {
  bool quiet = false,
}) async {
  try {
    final uri = Uri.parse("http://${target.host}:${target.port}/jsonrpc.js");
    final req = await _http.postUrl(uri).timeout(const Duration(seconds: 8));
    req.headers.contentType = ContentType.json;
    // LMS 在播放器接入时会关闭空闲长连接；禁用复用避免拿到已失效连接。
    req.headers.set(HttpHeaders.connectionHeader, "close");
    final auth = target.auth;
    if (auth != null) req.headers.set(HttpHeaders.authorizationHeader, auth);
    final payload = jsonEncode({"id": 1, "method": "slim.request", "params": params});
    // LMS 不接受 chunked body；显式 contentLength 避免连接被提前关闭。
    req.contentLength = utf8.encode(payload).length;
    req.write(payload);
    final resp = await req.close().timeout(const Duration(seconds: 8));
    final body = await utf8.decoder.bind(resp).join();
    if (resp.statusCode == 401) {
      if (!quiet) {
        report("LMS", "HTTP 401：需要用户名/密码（传 --lms-creds=路径）", false);
      }
      return null;
    }
    if (!body.trimLeft().startsWith("{")) {
      if (!quiet) {
        final brief = body.replaceAll(RegExp(r"\s+"), " ");
        report(
          "LMS",
          "非 JSON 响应：" + brief.substring(0, brief.length > 80 ? 80 : brief.length),
          false,
        );
      }
      return null;
    }
    return parseJson(body);
  } catch (e) {
    if (!quiet) report("LMS", "失败 ${e.toString().split('\n').first}", false);
    return null;
  }
}

Future<int> lmsPlayerCount(LmsTarget target) async {
  final root = await lmsRpc(target, ["", ["players", 0, 50]], quiet: true);
  if (root == null) return -1;
  return parsePlayerCount(root);
}

Future<void> checkAppBody() async {
  try {
    final xml = await getText("https://github.com/songboxiang/sonora/releases.atom");
    final v = parseAtomLatestVersion(xml);
    report("主体", "最新 ${v ?? '未解析'}（releases.atom）", v != null);
  } catch (e) {
    report("主体", "失败 ${e.toString().split('\n').first}", false);
  }
}

Future<void> checkCoreSource() async {
  try {
    final xml = await getText(
        "https://sourceforge.net/projects/lmsclients/rss?path=/squeezelite/osx/m1");
    final m = RegExp(r"<title><!\[CDATA\[([^\]]+squeezelite[^\]]*)\]\]></title>")
        .firstMatch(xml);
    final md5m = RegExp(r'<media:hash algo="md5">([^<]+)</media:hash>').firstMatch(xml);
    if (m == null) {
      report("核心源", "未解析到版本", false);
      return;
    }
    report("核心源", "${m.group(1)} | md5=${md5m?.group(1) ?? '无'}", md5m != null);
  } catch (e) {
    report("核心源", "失败 ${e.toString().split('\n').first}", false);
  }
}

Future<void> checkLms(LmsTarget target) async {
  final root = await lmsRpc(target, ["", ["version", "?"]]);
  if (root == null) return;
  final info = parseLmsVersion(root);
  report("LMS", "版本 ${info.version.isEmpty ? '未知' : info.version} "
      "(${target.auth == null ? '无凭证' : '带凭证'})", info.reachable);
}

/// --with-core：自动复制打包核心、拉起子进程，等待 LMS 播放器注册。
///
/// 这是真机验证的主路径：用户不需要手动启动 squeezelite。
Future<void> checkCoreRuntime(List<String> args, LmsTarget target) async {
  var withCore = false;
  String? corePath;
  for (final a in args) {
    if (a == "--with-core") withCore = true;
    if (a.startsWith("--core=")) corePath = a.split("=").skip(1).join("=");
  }
  if (!withCore) return;

  report("核心验证", "模式 --with-core：自动拉起内置核心", true);
  final before = await lmsPlayerCount(target);
  report("播放器", "启动前 count=$before", before >= 0);

  final runner = CoreRunner(
    lmsHost: target.host,
    lmsPort: target.port,
    slimPort: target.slimPort,
    playerName: "Sonora-Probe",
    onLog: (line) => print("      $line"),
  );

  try {
    final p = await runner.start(bundledPath: corePath);
    report("核心", "已自动拉起 pid=${p.pid}", true);

    var count = before;
    for (var i = 0; i < 15; i++) {
      await Future.delayed(const Duration(seconds: 1));
      count = await lmsPlayerCount(target);
      if (count >= 1) break;
    }
    report(
      "播放器",
      "自动拉起后 count=$count",
      count >= 1,
    );
    report(
      "verdict",
      count >= 1 ? "server reachable; playback ready" : "core started but no player registered",
      count >= 1,
    );
  } catch (e) {
    report("核心", "启动失败 ${e.toString().split('\n').first}", false);
  } finally {
    await runner.stop();
  }
}

Future<void> checkNavidrome(List<String> args) async {
  var credPath = "/Users/song/navidrome_creds.json";
  var host = "192.168.199.2:4533";
  for (final a in args) {
    if (a.startsWith("--creds=")) credPath = a.split("=").skip(1).join("=");
    if (a.startsWith("--nav-host=")) host = a.split("=").skip(1).join("=");
  }
  final c = readCreds(credPath);
  if (!c.containsKey("user") || !c.containsKey("password")) {
    report("Navidrome", "缺少凭证文件 $credPath", false);
    return;
  }
  try {
    final auth = SubsonicAuth(
      user: c["user"]!,
      password: c["password"]!,
      salt: "sonora-probe",
    );
    final q = Uri(queryParameters: auth.query()).query;
    final ping = await getText("http://$host/rest/ping?$q");
    final info = parsePing(parseJson(ping));
    report("Navidrome", "版本 ${info.version} / openSubsonic / ping=${info.statusText}",
        info.reachable);

    final atom = await getText(
        "https://github.com/navidrome/navidrome/releases.atom");
    final latest = parseAtomLatestVersion(atom);
    final up = latest != null && compareVersions(latest, info.version.split(" ").first) > 0;
    report("Navidrome升级", "当前 ${info.version.split(' ').first} → 最新 ${latest ?? '未知'}"
        " ${up ? '可升级' : '已最新'}", latest != null);

    final albums = await getText("http://$host/rest/getAlbumList2?${Uri(queryParameters: auth.query({
          "type": "newest", "size": "3",
        })).query}");
    final list = parseAlbumList(parseJson(albums), "http://$host");
    report("Navidrome曲库", "专辑 ${list.length} 张，首张 ${list.isEmpty ? '-' : list.first.name}",
        list.isNotEmpty);
  } catch (e) {
    report("Navidrome", "失败 ${e.toString().split('\n').first}", false);
  }
}

Future<void> main(List<String> args) async {
  print("=== Sonora v2 probe ===");
  final lms = parseLmsTarget(args);
  await checkAppBody();
  await checkCoreSource();
  await checkLms(lms);
  await checkCoreRuntime(args, lms);
  await checkNavidrome(args);
  _http.close();
}
