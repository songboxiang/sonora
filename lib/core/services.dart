import "dart:convert";
import "dart:io";

import "models.dart";
import "../lms/protocol.dart";
import "../navidrome/subsonic.dart";

/// Shared transport layer for both the CLI probe and the GUI.
///
/// Keeping these functions here avoids two drifting implementations of the
/// LMS/Navidrome quirks we already diagnosed (_version, count:0, f=json, ...).
final HttpClient httpClient = HttpClient();

void closeHttpClient() => httpClient.close();

String formatDuration(int seconds) {
  final m = seconds ~/ 60;
  final s = seconds % 60;
  return "$m:${s.toString().padLeft(2, "0")}";
}

Map<String, dynamic> parseJson(String s) =>
    jsonDecode(s) as Map<String, dynamic>;

/// Reads JSON or key=value credential files. Values are never logged.
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

Future<String> getText(
  String url, {
  Duration timeout = const Duration(seconds: 12),
}) async {
  final req = await httpClient.getUrl(Uri.parse(url)).timeout(timeout);
  final resp = await req.close().timeout(timeout);
  final body = await utf8.decoder.bind(resp).join();
  if (resp.statusCode != 200) throw Exception("HTTP ${resp.statusCode}");
  return body;
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

  String get baseUrl => "http://$host:$port";
}

LmsTarget lmsTargetFromArgs(List<String> args) {
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
    host ??= c["lms_host"];
    final configuredPort = int.tryParse(c["lms_port"] ?? "");
    if (configuredPort != null) port = configuredPort;
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
  void Function(String)? onError,
}) async {
  try {
    final req = await httpClient
        .postUrl(Uri.parse("${target.baseUrl}/jsonrpc.js"))
        .timeout(const Duration(seconds: 8));
    req.headers.contentType = ContentType.json;
    // LMS closes idle connections when a player joins; do not reuse them.
    req.headers.set(HttpHeaders.connectionHeader, "close");
    final auth = target.auth;
    if (auth != null) req.headers.set(HttpHeaders.authorizationHeader, auth);
    final payload = jsonEncode({
      "id": 1,
      "method": "slim.request",
      "params": params,
    });
    // LMS rejects chunked bodies; an explicit length is required.
    req.contentLength = utf8.encode(payload).length;
    req.write(payload);
    final resp = await req.close().timeout(const Duration(seconds: 8));
    final body = await utf8.decoder.bind(resp).join();
    if (resp.statusCode == 401) {
      if (!quiet) onError?.call("HTTP 401: 需要用户名/密码");
      return null;
    }
    if (!body.trimLeft().startsWith("{")) {
      if (!quiet) {
        final brief = body.replaceAll(RegExp(r"\s+"), " ");
        onError?.call(
          "非 JSON 响应：${brief.substring(0, brief.length > 80 ? 80 : brief.length)}",
        );
      }
      return null;
    }
    return parseJson(body);
  } catch (e) {
    if (!quiet) onError?.call("失败 ${e.toString().split('\n').first}");
    return null;
  }
}

Future<int> lmsPlayerCount(
  LmsTarget target, {
  void Function(String)? onError,
}) async {
  final root = await lmsRpc(
    target,
    [
      "",
      ["players", 0, 50],
    ],
    quiet: onError == null,
    onError: onError,
  );
  if (root == null) return -1;
  return parsePlayerCount(root);
}

Future<int> waitForPlayerCount(
  LmsTarget target, {
  Duration timeout = const Duration(seconds: 15),
  void Function(String)? onError,
}) async {
  final deadline = DateTime.now().add(timeout);
  var count = await lmsPlayerCount(target, onError: onError);
  while (count < 1 && DateTime.now().isBefore(deadline)) {
    await Future.delayed(const Duration(seconds: 1));
    count = await lmsPlayerCount(target, onError: onError);
  }
  return count;
}

/// Waits for a player that is actually connected. `players count` alone is
/// not enough: LMS keeps disconnected entries in players_loop for a while.
Future<List<PlayerInfo>> waitForOnlinePlayers(
  LmsTarget target, {
  Duration timeout = const Duration(seconds: 15),
  void Function(String)? onError,
}) async {
  final deadline = DateTime.now().add(timeout);
  var players = await fetchLmsPlayers(target, onError: onError);
  var online = players.where((p) => p.connected).toList();
  while (online.isEmpty && DateTime.now().isBefore(deadline)) {
    await Future.delayed(const Duration(seconds: 1));
    players = await fetchLmsPlayers(target, onError: onError);
    online = players.where((p) => p.connected).toList();
  }
  return online;
}

Future<ServerInfo> probeLms(
  LmsTarget target, {
  void Function(String)? onError,
}) async {
  final root = await lmsRpc(
    target,
    [
      "",
      ["version", "?"],
    ],
    quiet: onError == null,
    onError: onError,
  );
  if (root == null) {
    return ServerInfo(type: "lms", error: "request failed");
  }
  return parseLmsVersion(root);
}

Future<List<PlayerInfo>> fetchLmsPlayers(
  LmsTarget target, {
  void Function(String)? onError,
}) async {
  final root = await lmsRpc(
    target,
    [
      "",
      ["players", 0, 50],
    ],
    quiet: onError == null,
    onError: onError,
  );
  if (root == null) return const <PlayerInfo>[];
  return parsePlayers(root);
}

Future<PlaybackStatus> fetchLmsStatus(
  LmsTarget target,
  String playerId, {
  void Function(String)? onError,
}) async {
  final root = await lmsRpc(
    target,
    [
      playerId,
      ["status", "-", "1"],
    ],
    quiet: onError == null,
    onError: onError,
  );
  if (root == null) return const PlaybackStatus();
  return parseLmsStatus(root, target.baseUrl);
}

Future<void> sendLmsCommand(
  LmsTarget target,
  String playerId,
  List<String> command, {
  void Function(String)? onError,
}) async {
  await lmsRpc(
    target,
    [playerId, command],
    quiet: onError == null,
    onError: onError,
  );
}

class NavidromeTarget {
  NavidromeTarget({required this.host, required this.auth});

  final String host;
  final SubsonicAuth auth;

  String get baseUrl => "http://$host/rest";
  Map<String, String> query([
    Map<String, String> extra = const <String, String>{},
  ]) => auth.query(extra);
}

class NavidromeSearchResult {
  const NavidromeSearchResult({
    this.albums = const <AlbumInfo>[],
    this.songs = const <SongInfo>[],
  });

  final List<AlbumInfo> albums;
  final List<SongInfo> songs;
}

Future<ServerInfo> probeNavidrome(
  NavidromeTarget target, {
  void Function(String)? onError,
}) async {
  try {
    final raw = await getText(
      "${target.baseUrl}/ping?${Uri(queryParameters: target.query()).query}",
    );
    return parsePing(parseJson(raw));
  } catch (e) {
    final msg = "失败 ${e.toString().split('\n').first}";
    onError?.call(msg);
    return ServerInfo(type: "navidrome", error: msg);
  }
}

Future<List<AlbumInfo>> fetchNavidromeAlbums(
  NavidromeTarget target, {
  int size = 500,
  void Function(String)? onError,
}) async {
  try {
    final q = Uri(
      queryParameters: target.query({
        "type": "newest",
        "size": size.toString(),
      }),
    ).query;
    final raw = await getText("${target.baseUrl}/getAlbumList2?$q");
    return parseAlbumList(
      parseJson(raw),
      "http://${target.host}",
      auth: target.auth,
    );
  } catch (e) {
    onError?.call("失败 ${e.toString().split('\n').first}");
    return const <AlbumInfo>[];
  }
}

Future<List<SongInfo>> fetchNavidromeAlbum(
  NavidromeTarget target,
  String id, {
  void Function(String)? onError,
}) async {
  try {
    final q = Uri(queryParameters: target.query({"id": id})).query;
    final raw = await getText("${target.baseUrl}/getAlbum?$q");
    return parseAlbum(
      parseJson(raw),
      base: "http://${target.host}",
      auth: target.auth,
    );
  } catch (e) {
    onError?.call("失败 ${e.toString().split('\n').first}");
    return const <SongInfo>[];
  }
}

/// Server-side search across albums and songs (OpenSubsonic search3).
Future<NavidromeSearchResult> searchNavidrome(
  NavidromeTarget target,
  String query, {
  int albumCount = 20,
  int songCount = 50,
  void Function(String)? onError,
}) async {
  try {
    final q = Uri(
      queryParameters: target.query(<String, String>{
        "query": query,
        "albumCount": albumCount.toString(),
        "songCount": songCount.toString(),
        "artistCount": "10",
      }),
    ).query;
    final raw = await getText("${target.baseUrl}/search3?$q");
    final decoded = parseJson(raw);
    final base = "http://${target.host}";
    return NavidromeSearchResult(
      albums: parseSearch3Albums(decoded, base, auth: target.auth),
      songs: parseSearch3Songs(decoded, base, auth: target.auth),
    );
  } catch (e) {
    onError?.call("搜索失败 ${e.toString().split('\n').first}");
    return const NavidromeSearchResult();
  }
}

Future<String> fetchNavidromeAlbumNote(
  NavidromeTarget target,
  String albumId, {
  void Function(String)? onError,
}) async {
  try {
    final q = Uri(queryParameters: target.query({"id": albumId})).query;
    return parseAlbumNote(
      parseJson(await getText("${target.baseUrl}/getAlbumInfo2?$q")),
    );
  } catch (e) {
    onError?.call("专辑简介 ${e.toString().split('\n').first}");
    return "";
  }
}

Future<String> fetchNavidromeArtistBio(
  NavidromeTarget target,
  String artistId, {
  void Function(String)? onError,
}) async {
  if (artistId.isEmpty) return "";
  try {
    final q = Uri(queryParameters: target.query({"id": artistId})).query;
    return parseArtistBio(
      parseJson(await getText("${target.baseUrl}/getArtistInfo2?$q")),
    );
  } catch (e) {
    onError?.call("艺人简介 ${e.toString().split('\n').first}");
    return "";
  }
}

Future<List<LyricLine>> fetchNavidromeLyrics(
  NavidromeTarget target,
  String songId, {
  void Function(String)? onError,
}) async {
  try {
    final q = Uri(queryParameters: target.query({"id": songId})).query;
    return parseStructuredLyrics(
      parseJson(await getText("${target.baseUrl}/getLyricsBySongId?$q")),
    );
  } catch (e) {
    onError?.call("歌词 ${e.toString().split('\n').first}");
    return const <LyricLine>[];
  }
}

Future<PlaybackStatus> fetchNavidromePlayQueue(
  NavidromeTarget target, {
  void Function(String)? onError,
}) async {
  try {
    final q = Uri(queryParameters: target.query()).query;
    return parsePlayQueue(
      parseJson(await getText("${target.baseUrl}/getPlayQueue?$q")),
    );
  } catch (e) {
    onError?.call("播放队列 ${e.toString().split('\n').first}");
    return const PlaybackStatus();
  }
}
