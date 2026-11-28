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
      artist: _str(m["artist"] ?? m["albumartist"]),
      coverUrl: coverId.isEmpty || base.isEmpty
          ? ""
          : "$base/music/$coverId/cover",
    );
  }).toList();
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
    );
  }).toList();
}

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

/// 让当前 LMS 播放器播放指定曲目 id。
Future<bool> playLmsTrack(
  LmsTarget target,
  String playerId,
  String trackId, {
  void Function(String)? onError,
}) async {
  if (playerId.isEmpty || trackId.isEmpty) return false;
  final root = await lmsRpc(target, [
    playerId,
    ["playlist", "play", trackId],
  ], onError: onError);
  return root != null;
}
