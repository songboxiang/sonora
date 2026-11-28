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

/// 当前曲目的技术信息。两个轨道的字段来源不同，缺失项显示 "-"。
class AudioInfo {
  const AudioInfo({
    this.bitrate = "",
    this.sampleRate = 0,
    this.bitDepth = 0,
    this.channels = 0,
    this.format = "",
    this.lossless = false,
  });

  /// 原始展示串，例如 LMS 返回 "815kbps VBR"。
  final String bitrate;
  final int sampleRate;
  final int bitDepth;
  final int channels;
  final String format;
  final bool lossless;

  bool get hasData =>
      bitrate.isNotEmpty || sampleRate > 0 || bitDepth > 0 || format.isNotEmpty;

  String get bitrateText {
    if (bitrate.isEmpty) return "-";
    return bitrate
        .replaceFirst(RegExp(r"kbps"), " kbps")
        .replaceAll(RegExp(r"\s+"), " ")
        .trim();
  }

  String get sampleRateText {
    if (sampleRate <= 0) return "-";
    final k = sampleRate / 1000.0;
    final digits = k == k.roundToDouble() ? 0 : 1;
    return "${k.toStringAsFixed(digits)} kHz";
  }

  String get bitDepthText => bitDepth > 0 ? "$bitDepth bit" : "-";
  String get channelsText =>
      channels > 0 ? (channels == 1 ? "单声道" : "$channels 声道") : "-";

  String get formatText {
    final f = format.trim().toUpperCase();
    if (f.isEmpty) return "-";
    const aliases = <String, String>{
      "FLC": "FLAC",
      "FLAC": "FLAC",
      "M4A": "AAC",
      "M4B": "AAC",
      "AIF": "AIFF",
      "DSF": "DSD",
      "DFF": "DSD",
    };
    return aliases[f] ?? f;
  }

  String get summary {
    if (!hasData) return "暂无音质信息";
    final parts = <String>[
      if (format.isNotEmpty) formatText,
      if (sampleRate > 0) sampleRateText,
      if (bitDepth > 0) bitDepthText,
      if (bitrate.isNotEmpty) bitrateText,
      if (channels > 0) channelsText,
    ];
    return parts.join(" · ");
  }

  static AudioInfo fromLms(Map<String, dynamic> m) {
    final lossless =
        m["lossless"] == true ||
        m["lossless"].toString() == "1" ||
        m["lossless"].toString().toLowerCase() == "true";
    return AudioInfo(
      bitrate: (m["bitrate"] ?? "").toString(),
      sampleRate: int.tryParse((m["samplerate"] ?? "").toString()) ?? 0,
      bitDepth: int.tryParse((m["samplesize"] ?? "").toString()) ?? 0,
      format: (m["type"] ?? "").toString(),
      lossless: lossless,
    );
  }

  static AudioInfo fromSubsonic(Map<String, dynamic> m) {
    final contentType = (m["contentType"] ?? "").toString().toLowerCase();
    final suffix = (m["suffix"] ?? "").toString();
    final fmt = suffix.isNotEmpty
        ? suffix
        : contentType.contains("/")
        ? contentType.split("/").last
        : contentType;
    final bitRate = int.tryParse((m["bitRate"] ?? "").toString()) ?? 0;
    const losslessFormats = <String>{
      "FLAC",
      "ALAC",
      "WAV",
      "AIFF",
      "DSF",
      "DFF",
      "DSD",
    };
    return AudioInfo(
      bitrate: bitRate > 0 ? "$bitRate kbps" : "",
      sampleRate: int.tryParse((m["samplingRate"] ?? "").toString()) ?? 0,
      bitDepth: int.tryParse((m["bitDepth"] ?? "").toString()) ?? 0,
      channels: int.tryParse((m["channelCount"] ?? "").toString()) ?? 0,
      format: fmt,
      lossless: losslessFormats.contains(fmt.toUpperCase()),
    );
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

  /// OpenSubsonic artistId, used by getArtistInfo2.
  final String artistId;
  final String coverUrl;
  const AlbumInfo({
    required this.id,
    required this.name,
    this.artist = "",
    this.artistId = "",
    this.coverUrl = "",
  });
}

class SongInfo {
  final String id;
  final String title;
  final String artist;
  final String album;
  final int duration;

  /// Authenticated getCoverArt URL; never contains the plain password.
  final String coverUrl;

  /// Technical metadata when the server provides it.
  final AudioInfo? audio;
  const SongInfo({
    required this.id,
    required this.title,
    this.artist = "",
    this.album = "",
    this.duration = 0,
    this.coverUrl = "",
    this.audio,
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
