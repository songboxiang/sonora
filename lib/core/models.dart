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

  /// LMS artwork id; cover URL requires Basic Auth and is built in the UI.
  final String coverId;

  /// Richer metadata returned by the servers when available.
  final int year;
  final String genre;
  final int songCount;
  final int duration;
  final int playCount;
  final String sortName;
  const AlbumInfo({
    required this.id,
    required this.name,
    this.artist = "",
    this.artistId = "",
    this.coverUrl = "",
    this.coverId = "",
    this.year = 0,
    this.genre = "",
    this.songCount = 0,
    this.duration = 0,
    this.playCount = 0,
    this.sortName = "",
  });

  AlbumInfo copyWith({
    String? id,
    String? name,
    String? artist,
    String? artistId,
    String? coverUrl,
    String? coverId,
    int? year,
    String? genre,
    int? songCount,
    int? duration,
    int? playCount,
    String? sortName,
  }) {
    return AlbumInfo(
      id: id ?? this.id,
      name: name ?? this.name,
      artist: artist ?? this.artist,
      artistId: artistId ?? this.artistId,
      coverUrl: coverUrl ?? this.coverUrl,
      coverId: coverId ?? this.coverId,
      year: year ?? this.year,
      genre: genre ?? this.genre,
      songCount: songCount ?? this.songCount,
      duration: duration ?? this.duration,
      playCount: playCount ?? this.playCount,
      sortName: sortName ?? this.sortName,
    );
  }

  String get metaText {
    final parts = <String>[
      if (year > 0) "$year",
      if (genre.isNotEmpty) genre,
      if (songCount > 0) "$songCount 首",
      if (duration > 0) _shortDuration(duration),
    ];
    return parts.join(" · ");
  }
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

  /// LMS artwork id (songinfo coverid); used by the authenticated provider.
  final String coverId;

  /// Position inside the album and richer library metadata.
  final int track;
  final int disc;
  final int year;
  final String genre;
  final String path;
  final int size;
  final int playCount;
  const SongInfo({
    required this.id,
    required this.title,
    this.artist = "",
    this.album = "",
    this.duration = 0,
    this.coverUrl = "",
    this.audio,
    this.coverId = "",
    this.track = 0,
    this.disc = 0,
    this.year = 0,
    this.genre = "",
    this.path = "",
    this.size = 0,
    this.playCount = 0,
  });

  String get trackText => track > 0 ? (disc > 1 ? "$disc-$track" : "$track") : "";

  String get metaText {
    final parts = <String>[
      if (trackText.isNotEmpty) trackText,
      if (year > 0) "$year",
      if (genre.isNotEmpty) genre,
      if (duration > 0) _shortDuration(duration),
    ];
    return parts.join(" · ");
  }
}

/// One entry of an artist index (OpenSubsonic getArtists / LMS artists).
class ArtistInfo {
  final String id;
  final String name;
  final String coverUrl;
  final int albumCount;
  final String sortName;
  const ArtistInfo({
    required this.id,
    required this.name,
    this.coverUrl = "",
    this.albumCount = 0,
    this.sortName = "",
  });
}

/// One entry of the genre index (OpenSubsonic getGenres / LMS genres).
class GenreInfo {
  final String name;
  final int albumCount;
  final int songCount;
  const GenreInfo({
    required this.name,
    this.albumCount = 0,
    this.songCount = 0,
  });
}

/// How the library page groups and drills down into the catalogue.
enum LibraryGrouping { all, artist, genre, year }

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

String _shortDuration(int seconds) {
  if (seconds <= 0) return "";
  final m = seconds ~/ 60;
  final sec = seconds % 60;
  return "$m:${sec.toString().padLeft(2, "0")}";
}
