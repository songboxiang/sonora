import "dart:math" as math;

/// How audio is produced for a music library.
/// LMS controls an external player (squeezelite); Navidrome streams to this client.
enum PlaybackMode { externalPlayer, clientStream }

class ServerInfo {
  final String type;
  final String version;
  final bool reachable;
  final String? error;
  const ServerInfo({
    required this.type,
    this.version = "",
    this.reachable = false,
    this.error,
  });

  String get statusText => reachable ? "ok" : (error ?? "failed");
}

class UpdateInfo {
  final String current;
  final String latest;
  final List<String> notes;
  final String manualUrl;
  final String source;
  const UpdateInfo({
    this.current = "",
    this.latest = "",
    this.notes = const <String>[],
    this.manualUrl = "",
    this.source = "",
  });

  bool get hasUpdate {
    if (current.isEmpty || latest.isEmpty) return false;
    return compareVersions(latest, current) > 0;
  }
}

class PlaybackStatus {
  final String mode;
  final String title;
  final String artist;
  final String album;
  final int duration;
  final int position;
  final int volume;
  final String artworkUrl;
  final String trackId;
  const PlaybackStatus({
    this.mode = "stop",
    this.title = "",
    this.artist = "",
    this.album = "",
    this.duration = 0,
    this.position = 0,
    this.volume = 100,
    this.artworkUrl = "",
    this.trackId = "",
  });
  bool get isPlaying => mode == "play";
}

class PlayerInfo {
  final String id;
  final String name;
  /// 1 when the player is currently connected to LMS. Stale entries remain
  /// in `players_loop` after a probe/core exits, so the UI must filter on this.
  final bool connected;
  const PlayerInfo({
    required this.id,
    required this.name,
    this.connected = true,
  });
}

class AlbumInfo {
  final String id;
  final String name;
  final String artist;
  final String coverUrl;
  const AlbumInfo({
    required this.id,
    required this.name,
    this.artist = "",
    this.coverUrl = "",
  });
}

class SongInfo {
  final String id;
  final String title;
  final String artist;
  final String album;
  final int duration;
  const SongInfo({
    required this.id,
    required this.title,
    this.artist = "",
    this.album = "",
    this.duration = 0,
  });
}

class LyricLine {
  final int timeMs;
  final String text;
  const LyricLine({required this.timeMs, required this.text});
}

/// Compare dotted versions such as 9.1.1, 2.0.0.1465, 0.55.2 (a057a680).
/// Returns -1 / 0 / 1. Non-numeric segments are ignored.
int compareVersions(String a, String b) {
  List<int> parts(String v) {
    final head = v.trim().split(RegExp(r"\s+")).first;
    final clean = head.replaceFirst(RegExp(r"^v"), "");
    return clean
        .split(RegExp(r"[.\-]"))
        .map((s) => int.tryParse(s) ?? 0)
        .toList();
  }
  final pa = parts(a);
  final pb = parts(b);
  final n = math.max(pa.length, pb.length);
  for (var i = 0; i < n; i++) {
    final x = i < pa.length ? pa[i] : 0;
    final y = i < pb.length ? pb[i] : 0;
    if (x != y) return x < y ? -1 : 1;
  }
  return 0;
}
