import "dart:convert";
import "dart:io";
import "package:sonora/core/models.dart";
import "package:sonora/navidrome/subsonic.dart";
import "package:sonora/lms/protocol.dart";

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
  final out = <String, String>{};
  final f = File(path);
  if (!f.existsSync()) return out;
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

Future<void> checkAppBody() async {
  try {
    final xml = await getText("https://github.com/songboxiang/sonora/releases.atom");
    final v = parseAtomLatestVersion(xml);
    report("主体", "最新 ${v ?? '未解析'}（releases.atom）", v != null);
  } catch (e) {
    report("主体", "失败 ${e.toString().split('\n').first}", false);
  }
}

Future<void> checkCore() async {
  try {
    final xml = await getText(
        "https://sourceforge.net/projects/lmsclients/rss?path=/squeezelite/osx/m1");
    final m = RegExp(r"<title><!\[CDATA\[([^\]]+squeezelite[^\]]*)\]\]></title>")
        .firstMatch(xml);
    final md5m = RegExp(r'<media:hash algo="md5">([^<]+)</media:hash>').firstMatch(xml);
    if (m == null) {
      report("核心", "未解析到版本", false);
      return;
    }
    report("核心", "${m.group(1)} | md5=${md5m?.group(1) ?? '无'}", md5m != null);
  } catch (e) {
    report("核心", "失败 ${e.toString().split('\n').first}", false);
  }
}

Future<void> checkLms(List<String> args) async {
  String? host;
  String? user;
  String? pass;
  var credPath = "";
  for (final a in args) {
    if (a.startsWith("--lms-host=")) host = a.split("=").skip(1).join("=");
    if (a.startsWith("--lms-user=")) user = a.split("=").skip(1).join("=");
    if (a.startsWith("--lms-pass=")) pass = a.split("=").skip(1).join("=");
    if (a.startsWith("--lms-creds=")) credPath = a.split("=").skip(1).join("=");
  }
  if (credPath.isNotEmpty) {
    final c = readCreds(credPath);
    user ??= c["user"] ?? c["lms_user"];
    pass ??= c["password"] ?? c["pass"] ?? c["lms_pass"];
  }
  host ??= "192.168.199.2";
  final auth = user != null && pass != null
      ? "Basic ${base64Encode(utf8.encode("$user:$pass"))}"
      : null;
  try {
    final uri = Uri.parse("http://$host:9000/jsonrpc.js");
    final req = await _http.postUrl(uri);
    req.headers.contentType = ContentType.json;
    if (auth != null) req.headers.set(HttpHeaders.authorizationHeader, auth);
    req.write(jsonEncode({
      "id": 1,
      "method": "slim.request",
      "params": ["", ["version", "?"]],
    }));
    final resp = await req.close().timeout(const Duration(seconds: 8));
    final body = await utf8.decoder.bind(resp).join();
    if (resp.statusCode == 401) {
      report("LMS", "HTTP 401：需要用户名/密码（传 --lms-creds=路径）", false);
      return;
    }
    if (!body.trimLeft().startsWith("{")) {
      final brief = body.replaceAll(RegExp(r"\s+"), " ");
      report("LMS", "非 JSON 响应：" + brief.substring(0, brief.length > 80 ? 80 : brief.length), false);
      return;
    }
    final info = parseLmsVersion(parseJson(body));
    report("LMS", "版本 ${info.version.isEmpty ? '未知' : info.version} "
        "(${auth == null ? '无凭证' : '带凭证'})", info.reachable);
  } catch (e) {
    report("LMS", "失败 ${e.toString().split('\n').first}", false);
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
  await checkAppBody();
  await checkCore();
  await checkLms(args);
  await checkNavidrome(args);
  _http.close();
}
