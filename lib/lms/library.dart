import "../core/models.dart";
import "../core/services.dart";
import "protocol.dart";

/// LMS 曲库的纯解析与服务函数。GUI 和 CLI 共用，避免两套接口理解。

Map<String, dynamic>? _asMap(dynamic v) {
  if (v is Map<String, dynamic>) return v;
  if (v is Map) return Map<String, dynamic>.from(v);
  return null;
}

List<dynamic> _asList(dynamic v) => v is List ? v : const <dynamic>[];

String _str(dynamic v) => v == null ? "" : v.toString();

int _seconds(dynamic v) {
  if (v is num) return v.round();
  return double.tryParse(v.toString())?.round() ??
      int.tryParse(v.toString()) ??
      0;
}

/// `albums 0 N album` → albums_loop。
List<AlbumInfo> parseLmsAlbums(Map<String, dynamic> root, {String base = ""}) {
  final loop = _asList(lmsResult(root)["albums_loop"]);
  return loop.map((e) {
    final m = _asMap(e) ?? <String, dynamic>{};
    final coverId = _str(m["coverid"] ?? m["artwork_track_id"]);
    return AlbumInfo(
      id: _str(m["id"]),
      name: _str(m["album"]).isEmpty
          ? _str(m["favorites_title"])
          : _str(m["album"]),
      artist: _str(m["artist"] ?? m["albumartist"]).isEmpty
          ? _artistFromFavorites(_str(m["favorites_url"]))
          : _str(m["artist"] ?? m["albumartist"]),
      coverUrl: coverId.isEmpty || base.isEmpty
          ? ""
          : "$base/music/$coverId/cover",
      year: _yearFromAlbumName(_str(m["album"])),
      genre: _str(m["genre"]),
    );
  }).toList();
}

/// LMS favorites_url stores the contributor as a URL-encoded query value.
String _artistFromFavorites(String url) {
  if (url.isEmpty) return "";
  final m = RegExp(r"contributor\.name=([^&]+)").firstMatch(url);
  if (m == null) return "";
  final raw = m.group(1) ?? "";
  try {
    return Uri.decodeComponent(raw);
  } catch (_) {
    return raw;
  }
}

/// LMS album titles often begin with [YYYY]; use that as the grouping year.
int _yearFromAlbumName(String name) {
  final m = RegExp(r"^\[(\d{4})\]").firstMatch(name.trimLeft());
  if (m == null) return 0;
  return int.tryParse(m.group(1) ?? "") ?? 0;
}

/// `tracks 0 N` → titles_loop。LMS 的 duration 是浮点秒。
List<SongInfo> parseLmsTracks(Map<String, dynamic> root, {String base = ""}) {
  final loop = _asList(lmsResult(root)["titles_loop"]);
  return loop.map((e) {
    final m = _asMap(e) ?? <String, dynamic>{};
    final coverId = _str(m["coverid"] ?? m["artwork_track_id"]);
    return SongInfo(
      id: _str(m["id"]),
      title: _str(m["title"]),
      artist: _str(m["artist"] ?? m["trackartist"]),
      album: _str(m["album"]),
      duration: _seconds(m["duration"]),
      coverUrl: coverId.isEmpty || base.isEmpty
          ? ""
          : "$base/music/$coverId/cover",
      genre: _str(m["genre"]),
      year: _yearFromAlbumName(_str(m["album"])),
    );
  }).toList();
}

/// `artists 0 N` → artists_loop。
List<ArtistInfo> parseLmsArtists(Map<String, dynamic> root) {
  final loop = _asList(lmsResult(root)["artists_loop"]);
  return loop.map((e) {
    final m = _asMap(e) ?? <String, dynamic>{};
    return ArtistInfo(
      id: _str(m["id"]),
      name: _str(m["artist"]),
      albumCount: 0,
    );
  }).toList();
}

/// `genres 0 N` → genres_loop。
List<GenreInfo> parseLmsGenres(Map<String, dynamic> root) {
  final loop = _asList(lmsResult(root)["genres_loop"]);
  return loop.map((e) {
    final m = _asMap(e) ?? <String, dynamic>{};
    return GenreInfo(name: _str(m["genre"]));
  }).toList();
}

/// LMS ignores server-side artist/genre filters on the current build, so
/// grouping the already fetched catalogue locally is the stable path.
List<ArtistInfo> groupAlbumsByArtist(List<AlbumInfo> albums) {
  final groups = <String, int>{};
  for (final a in albums) {
    final key = a.artist.trim();
    if (key.isEmpty) continue;
    groups[key] = (groups[key] ?? 0) + 1;
  }
  final out = groups.entries
      .map((e) => ArtistInfo(id: e.key, name: e.key, albumCount: e.value))
      .toList();
  out.sort((a, b) => a.name.compareTo(b.name));
  return out;
}

List<GenreInfo> groupAlbumsByGenre(List<AlbumInfo> albums) {
  final groups = <String, int>{};
  for (final a in albums) {
    final key = a.genre.trim();
    if (key.isEmpty) continue;
    groups[key] = (groups[key] ?? 0) + 1;
  }
  final out = groups.entries
      .map((e) => GenreInfo(name: e.key, albumCount: e.value))
      .toList();
  out.sort((a, b) => a.name.compareTo(b.name));
  return out;
}

Map<int, List<AlbumInfo>> groupAlbumsByYear(List<AlbumInfo> albums) {
  final out = <int, List<AlbumInfo>>{};
  for (final a in albums) {
    if (a.year <= 0) continue;
    out.putIfAbsent(a.year, () => <AlbumInfo>[]).add(a);
  }
  return out;
}

List<AlbumInfo> albumsForArtist(List<AlbumInfo> albums, String artist) =>
    albums.where((a) => a.artist == artist).toList();

List<AlbumInfo> albumsForGenre(List<AlbumInfo> albums, String genre) =>
    albums.where((a) => a.genre == genre).toList();

List<AlbumInfo> albumsForYear(List<AlbumInfo> albums, int year) =>
    albums.where((a) => a.year == year).toList();

Future<List<AlbumInfo>> fetchLmsAlbums(
  LmsTarget target, {
  int count = 200,
  void Function(String)? onError,
}) async {
  final root = await lmsRpc(target, [
    "",
    ["albums", 0, count, "album"],
  ], onError: onError);
  if (root == null) return const <AlbumInfo>[];
  return parseLmsAlbums(root, base: target.baseUrl);
}

/// LMS 的 `albumtracks` 在部分服务器上会直接断连，`tracks` 带过滤参数也常被忽略；
/// 因此取全量后在本地按专辑名过滤，结果稳定且可复现。
Future<List<SongInfo>> fetchLmsTracks(
  LmsTarget target, {
  int count = 2000,
  String? album,
  void Function(String)? onError,
}) async {
  final root = await lmsRpc(target, [
    "",
    ["tracks", 0, count],
  ], onError: onError);
  if (root == null) return const <SongInfo>[];
  final all = parseLmsTracks(root, base: target.baseUrl);
  if (album == null || album.isEmpty) return all;
  return all.where((s) => s.album == album).toList();
}

/// LMS exposes cover art id only through `songinfo ... tags:Gc`, never in
/// albums_loop or titles_loop. Fetch one representative track per album and
/// decorate both album and its songs with a cover id.
Future<List<AlbumInfo>> enrichLmsAlbumsWithCovers(
  LmsTarget target,
  List<AlbumInfo> albums, {
  int concurrency = 6,
  void Function(String)? onError,
}) async {
  if (albums.isEmpty) return albums;
  // `tracks 0 N <album>` ignores the search term on this LMS build, so every
  // album resolved to the same first track and therefore the same cover.
  // Fetch the catalogue once and pick a real representative per album.
  final tracks = await fetchLmsTracks(target, count: 3000, onError: onError);
  if (tracks.isEmpty) return albums;
  final representative = lmsRepresentativeTracks(tracks);
  final coverByAlbum = <String, String>{};
  final keys = representative.keys.toList();
  var cursor = 0;
  final workers = List.generate(concurrency, (_) async {
    while (cursor < keys.length) {
      final name = keys[cursor++];
      final cid = await lmsTrackCoverId(
        target,
        representative[name] ?? "",
        onError: onError,
      );
      if (cid.isNotEmpty) coverByAlbum[name] = cid;
    }
  });
  await Future.wait(workers);
  return albums.map((a) {
    final cid = coverByAlbum[a.name] ?? "";
    return cid.isEmpty ? a : a.copyWith(coverId: cid);
  }).toList();
}

/// Parse the coverid from a songinfo response (tags:Gc).
String parseLmsCoverId(Map<String, dynamic> root) {
  final loop = _asList(lmsResult(root)["songinfo_loop"]);
  for (final e in loop) {
    final m = _asMap(e) ?? <String, dynamic>{};
    final cid = _str(m["coverid"] ?? m["artwork_track_id"]);
    if (cid.isNotEmpty) return cid;
  }
  return "";
}

/// Fetch coverid for a single track.
Future<String> lmsTrackCoverId(
  LmsTarget target,
  String trackId, {
  void Function(String)? onError,
}) async {
  if (trackId.isEmpty) return "";
  final root = await lmsRpc(target, [
    "",
    ["songinfo", 0, 100, "track_id:$trackId", "tags:Gc"],
  ], quiet: true, onError: onError);
  if (root == null) return "";
  return parseLmsCoverId(root);
}

/// LMS albums_loop has no genre, but titles_loop does. Enrich the album
/// list from a single full tracks fetch so the genre hierarchy is usable.
Future<List<AlbumInfo>> enrichLmsAlbumsWithGenres(
  LmsTarget target,
  List<AlbumInfo> albums, {
  int count = 3000,
  void Function(String)? onError,
}) async {
  if (albums.isEmpty) return albums;
  final tracks = await fetchLmsTracks(target, count: count, onError: onError);
  if (tracks.isEmpty) return albums;
  final byAlbum = <String, String>{};
  for (final t in tracks) {
    if (t.album.isEmpty || t.genre.isEmpty) continue;
    byAlbum.putIfAbsent(t.album, () => t.genre);
  }
  return albums.map((a) {
    final g = byAlbum[a.name];
    return g == null || g.isEmpty ? a : a.copyWith(genre: g);
  }).toList();
}

Future<List<ArtistInfo>> fetchLmsArtists(
  LmsTarget target, {
  int count = 500,
  void Function(String)? onError,
}) async {
  final root = await lmsRpc(target, [
    "",
    ["artists", 0, count],
  ], onError: onError);
  if (root == null) return const <ArtistInfo>[];
  return parseLmsArtists(root);
}

Future<List<GenreInfo>> fetchLmsGenres(
  LmsTarget target, {
  int count = 100,
  void Function(String)? onError,
}) async {
  final root = await lmsRpc(target, [
    "",
    ["genres", 0, count],
  ], onError: onError);
  if (root == null) return const <GenreInfo>[];
  return parseLmsGenres(root);
}

/// 让当前 LMS 播放器播放指定曲目 id。
/// LMS silently ignores `playlist play <numericId>` (that command expects a
/// URL). Loading through playlistcontrol with a `track_id:` item is the only
/// reliable way to play a library track; verified against a live server.
List<String> lmsPlayCommand(String trackId) {
  final item = trackId.startsWith("track_id:") ? trackId : "track_id:$trackId";
  return <String>["playlistcontrol", "cmd:load", item];
}

/// Pick one representative track id per album name, preserving server order.
Map<String, String> lmsRepresentativeTracks(List<SongInfo> tracks) {
  final out = <String, String>{};
  for (final t in tracks) {
    if (t.album.isEmpty || t.id.isEmpty) continue;
    out.putIfAbsent(t.album, () => t.id);
  }
  return out;
}

/// LMS does not implement a seek player command; it is silently ignored.
/// The supported absolute jump is time SECONDS (verified on a live server).
List<String> lmsSeekCommand(int seconds) => <String>["time", seconds.toString()];

Future<bool> playLmsTrack(
  LmsTarget target,
  String playerId,
  String trackId, {
  void Function(String)? onError,
}) async {
  if (playerId.isEmpty || trackId.isEmpty) return false;
  final root = await lmsRpc(target, [
    playerId,
    lmsPlayCommand(trackId),
  ], onError: onError);
  return root != null;
}
