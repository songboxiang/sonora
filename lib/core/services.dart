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

Future<AudioInfo> fetchLmsTrackAudioInfo(
  LmsTarget target,
  String trackId, {
  void Function(String)? onError,
}) async {
  if (trackId.isEmpty) return const AudioInfo();
  final root = await lmsRpc(target, [
    "",
    ["songinfo", 0, 100, "track_id:$trackId", "tags:rTIoQ"],
  ], onError: onError);
  if (root == null) return const AudioInfo();
  return parseLmsAudioInfo(root);
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

/// Server-side artist index (OpenSubsonic getArtists), flattened by index.
Future<List<ArtistInfo>> fetchNavidromeArtists(
  NavidromeTarget target, {
  void Function(String)? onError,
}) async {
  try {
    final q = Uri(queryParameters: target.query()).query;
    return parseArtists(
      parseJson(await getText("${target.baseUrl}/getArtists?$q")),
      "http://${target.host}",
      auth: target.auth,
    );
  } catch (e) {
    onError?.call("艺术家索引 ${e.toString().split('\n').first}");
    return const <ArtistInfo>[];
  }
}

/// Server-side genre index (OpenSubsonic getGenres).
Future<List<GenreInfo>> fetchNavidromeGenres(
  NavidromeTarget target, {
  void Function(String)? onError,
}) async {
  try {
    final q = Uri(queryParameters: target.query()).query;
    return parseGenres(
      parseJson(await getText("${target.baseUrl}/getGenres?$q")),
    );
  } catch (e) {
    onError?.call("流派索引 ${e.toString().split('\n').first}");
    return const <GenreInfo>[];
  }
}

/// Albums filtered by genre on the server (Navidrome supports byGenre).
Future<List<AlbumInfo>> fetchNavidromeAlbumsByGenre(
  NavidromeTarget target,
  String genre, {
  int size = 500,
  void Function(String)? onError,
}) async {
  if (genre.isEmpty) return const <AlbumInfo>[];
  try {
    final q = Uri(queryParameters: target.query({
      "type": "byGenre",
      "genre": genre,
      "size": size.toString(),
    })).query;
    return parseAlbumList(
      parseJson(await getText("${target.baseUrl}/getAlbumList2?$q")),
      "http://${target.host}",
      auth: target.auth,
    );
  } catch (e) {
    onError?.call("流派专辑 ${e.toString().split('\n').first}");
    return const <AlbumInfo>[];
  }
}

/// Albums filtered by release year on the server (fromYear/toYear).
Future<List<AlbumInfo>> fetchNavidromeAlbumsByYear(
  NavidromeTarget target,
  int year, {
  int size = 500,
  void Function(String)? onError,
}) async {
  if (year <= 0) return const <AlbumInfo>[];
  try {
    final q = Uri(queryParameters: target.query({
      "type": "byYear",
      "fromYear": "$year",
      "toYear": "$year",
      "size": size.toString(),
    })).query;
    return parseAlbumList(
      parseJson(await getText("${target.baseUrl}/getAlbumList2?$q")),
      "http://${target.host}",
      auth: target.auth,
    );
  } catch (e) {
    onError?.call("年份专辑 ${e.toString().split('\n').first}");
    return const <AlbumInfo>[];
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

/// LMS exposes rich track metadata only through songinfo tags. Lowercase
/// letters are the readable fields (a=artist, l=album, g=genre, y=year,
/// t=track, i=disc, u=path); uppercase A/D/O add album artist, added time and
/// play count. Returned keys are kept verbatim so the UI can label them.
Future<Map<String, String>> fetchLmsTrackInfo(
  LmsTarget target,
  String trackId, {
  void Function(String)? onError,
}) async {
  if (trackId.isEmpty) return const <String, String>{};
  final root = await lmsRpc(target, [
    "",
    ["songinfo", 0, 100, "track_id:$trackId", "tags:algyAtidOu"],
  ], quiet: true, onError: onError);
  if (root == null) return const <String, String>{};
  final loop = lmsResult(root)["songinfo_loop"];
  if (loop is! List) return const <String, String>{};
  final out = <String, String>{};
  for (final item in loop) {
    if (item is! Map) continue;
    for (final entry in item.entries) {
      final v = entry.value?.toString() ?? "";
      if (v.isNotEmpty) out[entry.key.toString()] = v;
    }
  }
  return out;
}

/// Parse unsynchronised or LRC lyrics returned by a server as plain text.
List<LyricLine> parsePlainLyrics(String raw) {
  if (raw.trim().isEmpty) return const <LyricLine>[];
  final out = <LyricLine>[];
  final stamped = RegExp(r"\[(\d{1,3}):(\d{2}(?:[.:]\d+)?)\](.*)");
  var hasStamp = false;
  for (final line in raw.split(RegExp(r"\r?\n"))) {
    final m = stamped.firstMatch(line);
    if (m == null) {
      if (!hasStamp && line.trim().isNotEmpty) {
        out.add(LyricLine(timeMs: 0, text: line.trim()));
      }
      continue;
    }
    hasStamp = true;
    final min = int.tryParse(m.group(1) ?? "") ?? 0;
    final sec = double.tryParse((m.group(2) ?? "").replaceFirst(":", ".")) ?? 0;
    final text = (m.group(3) ?? "").trim();
    if (text.isNotEmpty) {
      out.add(LyricLine(timeMs: ((min * 60 + sec) * 1000).round(), text: text));
    }
  }
  out.sort((a, b) => a.timeMs.compareTo(b.timeMs));
  return out;
}

/// LMS lyricsLive is usually provided by a plugin; songinfo LYRICS is the
/// portable fallback. Missing lyrics simply produce an empty list.
Future<List<LyricLine>> fetchLmsLyrics(
  LmsTarget target,
  String trackId, {
  void Function(String)? onError,
}) async {
  if (trackId.isEmpty) return const <LyricLine>[];
  final root = await lmsRpc(target, [
    "",
    ["songinfo", 0, 100, "track_id:$trackId", "tags:L"],
  ], quiet: true, onError: onError);
  if (root == null) return const <LyricLine>[];
  final loop = lmsResult(root)["songinfo_loop"];
  if (loop is! List) return const <LyricLine>[];
  for (final item in loop) {
    if (item is! Map) continue;
    final raw = item["lyrics"] ?? item["LYRICS"] ?? item["comment"];
    if (raw != null && raw.toString().trim().isNotEmpty) {
      return parsePlainLyrics(raw.toString());
    }
  }
  return const <LyricLine>[];
}

/// Find a Subsonic playlist by name, creating it when absent. Sonora uses a
/// single default playlist so the context menu works on a fresh server.
Future<String> fetchOrCreateNavidromePlaylist(
  NavidromeTarget target, {
  String name = "Sonora",
  void Function(String)? onError,
}) async {
  try {
    final q = Uri(queryParameters: target.query()).query;
    final root = parseJson(
      await getText("${target.baseUrl}/getPlaylists?$q"),
    );
    final resp = root["subsonic-response"];
    if (resp is Map) {
      final lists = resp["playlists"];
      final items = lists is Map ? lists["playlist"] : null;
      if (items is List) {
        for (final item in items) {
          if (item is Map && item["name"] == name) {
            return item["id"]?.toString() ?? "";
          }
        }
      }
    }
    final param = Uri(queryParameters: target.query({"name": name})).query;
    final created = parseJson(
      await getText("${target.baseUrl}/createPlaylist?$param"),
    );
    final pl = created["subsonic-response"];
    if (pl is Map && pl["playlist"] is Map) {
      return pl["playlist"]["id"]?.toString() ?? "";
    }
    return "";
  } catch (e) {
    onError?.call("播放列表 ${e.toString().split('\n').first}");
    return "";
  }
}

Future<bool> addNavidromeSongToPlaylist(
  NavidromeTarget target,
  String playlistId,
  String songId, {
  void Function(String)? onError,
}) async {
  if (playlistId.isEmpty || songId.isEmpty) return false;
  try {
    final q = Uri(
      queryParameters: target.query({
        "playlistId": playlistId,
        "songIdToAdd": songId,
      }),
    ).query;
    final root = parseJson(
      await getText("${target.baseUrl}/updatePlaylist?$q"),
    );
    return (root["subsonic-response"]?["status"] ?? "").toString() == "ok";
  } catch (e) {
    onError?.call("加入播放列表 ${e.toString().split('\n').first}");
    return false;
  }
}
