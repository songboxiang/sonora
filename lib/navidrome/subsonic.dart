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

  Map<String, String> query([
    Map<String, String> extra = const <String, String>{},
  ]) {
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

/// Authenticated cover-art URL. This endpoint returns binary image data,
/// so the JSON-format flag must be removed just like /rest/stream.
String coverArtUrl({
  required String base,
  required SubsonicAuth auth,
  required String id,
  int size = 300,
}) {
  final q = <String, String>{"id": id, "size": size.toString(), ...auth.query()}
    ..remove("f");
  return "$base/rest/getCoverArt?${Uri(queryParameters: q).query}";
}

String _coverUrl(String base, SubsonicAuth? auth, String id, [int size = 300]) {
  if (id.isEmpty) return "";
  if (auth != null) {
    return coverArtUrl(base: base, auth: auth, id: id, size: size);
  }
  return "$base/rest/getCoverArt?id=$id&size=$size";
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

List<AlbumInfo> parseAlbumList(
  Map<String, dynamic> root,
  String base, {
  SubsonicAuth? auth,
}) {
  final r = response(root);
  final list = _asList(_asMap(r["albumList2"])?["album"]);
  return list.map((e) {
    final m = _asMap(e) ?? <String, dynamic>{};
    return AlbumInfo(
      id: _str(m["id"]),
      name: _str(m["name"]),
      artist: _str(m["artist"]),
      artistId: _str(m["artistId"]),
      coverUrl: _coverUrl(base, auth, _str(m["coverArt"])),
      year: _int(m["year"]),
      genre: _str(m["genre"]),
      songCount: _int(m["songCount"]),
      duration: _int(m["duration"]),
      playCount: _int(m["playCount"]),
      sortName: _str(m["sortName"]),
    );
  }).toList();
}

List<SongInfo> parseAlbum(
  Map<String, dynamic> root, {
  String base = "",
  SubsonicAuth? auth,
}) {
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
      coverUrl: base.isEmpty
          ? ""
          : _coverUrl(base, auth, _str(m["coverArt"]), 300),
      audio: AudioInfo.fromSubsonic(m),
      track: _int(m["track"]),
      disc: _int(m["discNumber"]),
      year: _int(m["year"]),
      genre: _str(m["genre"]),
      path: _str(m["path"]),
      size: _int(m["size"]),
      playCount: _int(m["playCount"]),
    );
  }).toList();
}

/// /rest/search3 result albums, same shape as albumList2.
List<AlbumInfo> parseSearch3Albums(
  Map<String, dynamic> root,
  String base, {
  SubsonicAuth? auth,
}) {
  final search = _asMap(response(root)["search3"]) ?? <String, dynamic>{};
  return _asList(search["album"]).map((e) {
    final m = _asMap(e) ?? <String, dynamic>{};
    return AlbumInfo(
      id: _str(m["id"]),
      name: _str(m["name"]),
      artist: _str(m["artist"]),
      artistId: _str(m["artistId"]),
      coverUrl: _coverUrl(base, auth, _str(m["coverArt"])),
      year: _int(m["year"]),
      genre: _str(m["genre"]),
      songCount: _int(m["songCount"]),
      duration: _int(m["duration"]),
      playCount: _int(m["playCount"]),
      sortName: _str(m["sortName"]),
    );
  }).toList();
}

/// /rest/search3 result songs.
List<SongInfo> parseSearch3Songs(
  Map<String, dynamic> root,
  String base, {
  SubsonicAuth? auth,
}) {
  final search = _asMap(response(root)["search3"]) ?? <String, dynamic>{};
  return _asList(search["song"]).map((e) {
    final m = _asMap(e) ?? <String, dynamic>{};
    return SongInfo(
      id: _str(m["id"]),
      title: _str(m["title"]),
      artist: _str(m["artist"]),
      album: _str(m["album"]),
      duration: _int(m["duration"]),
      coverUrl: _coverUrl(base, auth, _str(m["coverArt"]), 300),
      audio: AudioInfo.fromSubsonic(m),
      track: _int(m["track"]),
      disc: _int(m["discNumber"]),
      year: _int(m["year"]),
      genre: _str(m["genre"]),
      path: _str(m["path"]),
      size: _int(m["size"]),
      playCount: _int(m["playCount"]),
    );
  }).toList();
}

/// /rest/getArtists artist index, flattened in index order.
List<ArtistInfo> parseArtists(Map<String, dynamic> root, String base, {SubsonicAuth? auth}) {
  final artists = _asMap(response(root)["artists"]) ?? <String, dynamic>{};
  final out = <ArtistInfo>[];
  for (final idx in _asList(artists["index"])) {
    final group = _asMap(idx) ?? <String, dynamic>{};
    for (final e in _asList(group["artist"])) {
      final m = _asMap(e) ?? <String, dynamic>{};
      out.add(ArtistInfo(
        id: _str(m["id"]),
        name: _str(m["name"]),
        coverUrl: _coverUrl(base, auth, _str(m["coverArt"])),
        albumCount: _int(m["albumCount"]),
        sortName: _str(m["sortName"]),
      ));
    }
  }
  return out;
}

/// /rest/getGenres genre index.
List<GenreInfo> parseGenres(Map<String, dynamic> root) {
  final genres = _asMap(response(root)["genres"]) ?? <String, dynamic>{};
  return _asList(genres["genre"]).map((e) {
    final m = _asMap(e) ?? <String, dynamic>{};
    return GenreInfo(
      name: _str(m["value"]),
      albumCount: _int(m["albumCount"]),
      songCount: _int(m["songCount"]),
    );
  }).toList();
}

/// getAlbumInfo2 note / Last.fm style description.
String parseAlbumNote(Map<String, dynamic> root) {
  final info = _asMap(response(root)["albumInfo"]) ?? <String, dynamic>{};
  return _str(info["note"]);
}

/// getArtistInfo2 biography.
String parseArtistBio(Map<String, dynamic> root) {
  final info = _asMap(response(root)["artistInfo2"]) ?? <String, dynamic>{};
  return _str(info["biography"]);
}

List<LyricLine> parseStructuredLyrics(Map<String, dynamic> root) {
  final r = response(root);
  final sets = _asList(_asMap(r["lyricsList"])?["structuredLyrics"]);
  if (sets.isEmpty) return const <LyricLine>[];
  final first = _asMap(sets.first) ?? <String, dynamic>{};
  return _asList(first["line"]).map((e) {
    final m = _asMap(e) ?? <String, dynamic>{};
    return LyricLine(timeMs: _int(m["start"]), text: _str(m["value"]));
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
