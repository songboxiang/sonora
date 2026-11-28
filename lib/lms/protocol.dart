import "dart:math" as math;
import "../core/models.dart";

/// Pure parsers for LMS JSON-RPC. Kept separate from transport so the
/// underscore-prefixed fields and player-count quirks are locked by tests.
Map<String, dynamic>? _asMap(dynamic v) {
  if (v is Map<String, dynamic>) return v;
  if (v is Map) return Map<String, dynamic>.from(v);
  return null;
}

List<dynamic> _asList(dynamic v) => v is List ? v : const <dynamic>[];

String _str(dynamic v) => v == null ? "" : v.toString();

int _int(dynamic v) {
  if (v is num) return v.toInt();
  return int.tryParse(v.toString()) ?? 0;
}

Map<String, dynamic> lmsResult(Map<String, dynamic> root) =>
    _asMap(root["result"]) ?? <String, dynamic>{};

/// LMS "version ?" returns {"_version": "9.1.1"}, NOT {"version": ...}.
ServerInfo parseLmsVersion(Map<String, dynamic> root) {
  final r = lmsResult(root);
  final v = _str(r["_version"]).isNotEmpty
      ? _str(r["_version"])
      : _str(r["version"]);
  return ServerInfo(
    type: "lms",
    version: v,
    reachable: v.isNotEmpty,
    error: v.isEmpty ? "response has no _version/version" : null,
  );
}

int parsePlayerCount(Map<String, dynamic> root) {
  final r = lmsResult(root);
  final c = r["count"];
  if (c != null) return _int(c);
  final loop = _asList(r["players_loop"]);
  if (loop.isNotEmpty) return loop.length;
  return 0;
}

List<PlayerInfo> parsePlayers(Map<String, dynamic> root) {
  final loop = _asList(lmsResult(root)["players_loop"]);
  return loop.map((e) {
    final m = _asMap(e) ?? <String, dynamic>{};
    return PlayerInfo(
      id: _str(m["playerid"]),
      name: _str(m["name"]).isEmpty ? _str(m["playerid"]) : _str(m["name"]),
      connected: _int(m["connected"]) == 1,
    );
  }).toList();
}

/// UI slider is linear 0..100; LMS mixer volume is perceptual 0..100.
/// Matches legacy Sonora: slider = sqrt(lms/100)*100, inverse = x^2.
int lmsToSlider(int raw) {
  final x = (raw.clamp(0, 100) as num).toDouble() / 100.0;
  return (100.0 * math.sqrt(x)).round();
}

int sliderToLms(int slider) {
  final x = (slider.clamp(0, 100) as num).toDouble() / 100.0;
  return (100.0 * x * x).round();
}

PlaybackStatus parseLmsStatus(Map<String, dynamic> root, String base) {
  final m = lmsResult(root);
  final art = m["artwork_track_id"] ?? m["coverid"];
  final artId = _str(art);
  final rawVol = m["volume"];
  final vol = rawVol == null ? 100 : lmsToSlider(_int(rawVol));
  return PlaybackStatus(
    mode: _str(m["mode"]).isEmpty ? "stop" : _str(m["mode"]),
    title: _str(m["title"]),
    artist: _str(m["artist"]),
    album: _str(m["album"]),
    duration: _int(m["duration"]),
    position: _int(m["time"]),
    volume: vol,
    artworkUrl: artId.isEmpty ? "" : "$base/music/$artId/cover",
    trackId: _str(m["id"]),
  );
}

/// `songinfo 0 100 track_id:<id> tags:rTIoQ` 的技术字段。
AudioInfo parseLmsAudioInfo(Map<String, dynamic> root) {
  final r = lmsResult(root);
  final loop = _asList(r["songinfo_loop"]);
  final m = <String, dynamic>{};
  for (final item in loop) {
    final one = _asMap(item) ?? <String, dynamic>{};
    for (final entry in one.entries) {
      m[entry.key] = entry.value;
    }
  }
  if (m.isEmpty) return const AudioInfo();
  return AudioInfo.fromLms(m);
}
