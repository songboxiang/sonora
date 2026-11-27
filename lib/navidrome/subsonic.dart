import "dart:convert";
import "package:crypto/crypto.dart";
import "../core/models.dart";

/// Pure OpenSubsonic protocol helpers. No network access here: every parser
/// takes decoded JSON so it can be unit-tested with real captured responses.
class SubsonicAuth {
  final String user;
  final String password;
  final String salt;
  final String client;
  const SubsonicAuth({
    required this.user,
    required this.password,
    required this.salt,
    this.client = "Sonora",
  });

  /// Subsonic token = md5(password + salt). Password itself is never sent.
  String get token => md5.convert(utf8.encode(password + salt)).toString();

  Map<String, String> query([Map<String, String> extra = const <String, String>{}]) {
    final q = <String, String>{
      "u": user,
      "t": token,
      "s": salt,
      "v": "1.16.1",
      "c": client,
      // Important: this server ignores "format=json" and returns XML.
      // "f=json" is the parameter that actually works on Navidrome 0.55.2.
      "f": "json",
    };
    q.addAll(extra);
    return q;
  }
}

Map<String, dynamic>? _asMap(dynamic v) {
  if (v is Map<String, dynamic>) return v;
  if (v is Map) return Map<String, dynamic>.from(v);
  return null;
}

List<dynamic> _asList(dynamic v) {
  if (v is List) return v;
  return const <dynamic>[];
}

String _str(dynamic v) => v == null ? "" : v.toString();

int _int(dynamic v) {
  if (v is num) return v.toInt();
  return int.tryParse(v.toString()) ?? 0;
}

Map<String, dynamic> response(Map<String, dynamic> root) =>
    _asMap(root["subsonic-response"]) ?? <String, dynamic>{};

ServerInfo parsePing(Map<String, dynamic> root) {
  final r = response(root);
  final ok = _str(r["status"]) == "ok";
  return ServerInfo(
    type: "navidrome",
    version: _str(r["serverVersion"]),
    reachable: ok,
    error: ok ? null : _str((_asMap(r["error"]) ?? {})["message"]),
  );
}

List<AlbumInfo> parseAlbumList(Map<String, dynamic> root, String base) {
  final r = response(root);
  final list = _asList(_asMap(r["albumList2"])?["album"]);
  return list.map((e) {
    final m = _asMap(e) ?? <String, dynamic>{};
    final coverId = _str(m["coverArt"]);
    return AlbumInfo(
      id: _str(m["id"]),
      name: _str(m["name"]),
      artist: _str(m["artist"]),
      coverUrl: coverId.isEmpty
          ? ""
          : "$base/rest/getCoverArt?id=$coverId&size=300",
    );
  }).toList();
}

List<SongInfo> parseAlbum(Map<String, dynamic> root) {
  final r = response(root);
  final list = _asList(_asMap(r["album"])?["song"]);
  return list.map((e) {
    final m = _asMap(e) ?? <String, dynamic>{};
    return SongInfo(
      id: _str(m["id"]),
      title: _str(m["title"]),
      artist: _str(m["artist"]),
      album: _str(m["album"]),
      duration: _int(m["duration"]),
    );
  }).toList();
}

List<LyricLine> parseStructuredLyrics(Map<String, dynamic> root) {
  final r = response(root);
  final sets = _asList(_asMap(r["lyricsList"])?["structuredLyrics"]);
  if (sets.isEmpty) return const <LyricLine>[];
  final first = _asMap(sets.first) ?? <String, dynamic>{};
  return _asList(first["line"]).map((e) {
    final m = _asMap(e) ?? <String, dynamic>{};
    return LyricLine(
      timeMs: _int(m["start"]),
      text: _str(m["value"]),
    );
  }).toList();
}

PlaybackStatus parsePlayQueue(Map<String, dynamic> root) {
  final r = response(root);
  final q = _asMap(r["playQueue"]) ?? <String, dynamic>{};
  final entries = _asList(q["entry"]);
  final currentId = _str(q["current"]);
  final pos = _int(q["positionMs"]) ~/ 1000;
  for (final e in entries) {
    final m = _asMap(e) ?? <String, dynamic>{};
    if (_str(m["id"]) == currentId) {
      return PlaybackStatus(
        mode: _str(q["status"]) == "playing" ? "play" : "pause",
        title: _str(m["title"]),
        artist: _str(m["artist"]),
        album: _str(m["album"]),
        duration: _int(m["duration"]),
        position: pos,
        trackId: currentId,
      );
    }
  }
  return const PlaybackStatus();
}

/// Extract the newest release tag from GitHub releases.atom (plain text).
/// Used as a rate-limit-free fallback to the GitHub Releases API.
String? parseAtomLatestVersion(String xml) {
  final titles = RegExp(r"<title>([^<]+)</title>").allMatches(xml);
  for (final m in titles) {
    final t = m.group(1)?.trim() ?? "";
    if (RegExp(r"^v?\d+\.\d+(\.\d+)?").hasMatch(t)) return t;
  }
  return null;
}
