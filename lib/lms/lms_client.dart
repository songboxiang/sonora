import "dart:async";
import "dart:math" as math;
import "dart:convert";
import "dart:io";

/// Pure-Dart LMS JSON-RPC client. No Python, no webview bridge.
/// Protocol: POST {base}/jsonrpc.js  {"id":1,"method":"slim.request","params":[playerId,[cmd,...]]}
class LmsConfig {
  final String host;
  final int port;
  final String user;
  final String password;
  final String playerId;

  const LmsConfig({
    this.host = "127.0.0.1",
    this.port = 9000,
    this.user = "",
    this.password = "",
    this.playerId = "",
  });

  String get base => "http://$host:$port";
}

/// Normalized now-playing snapshot consumed by the UI layer.
class PlaybackStatus {
  final String mode; // play | pause | stop
  final String title;
  final String artist;
  final String album;
  final int duration;
  final int position;
  final int volume; // 0..100
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

  /// Parses an LMS "status" result into a UI-friendly snapshot.
  /// Kept static and pure so it can be unit-tested without a server.
  static PlaybackStatus fromLms(Map<String, dynamic> m, String base) {
    final mode = (m["mode"] ?? "stop").toString();
    int vol = 100;
    final v = m["volume"];
    if (v != null) {
      final raw = (v is num) ? v.toInt() : int.tryParse(v.toString()) ?? 100;
      vol = lmsToSlider(raw);
    }
    String artwork = "";
    final art = m["artwork_track_id"] ?? m["coverid"];
    if (art != null && art.toString().isNotEmpty) {
      artwork = "$base/music/$art/cover";
    }
    return PlaybackStatus(
      mode: mode,
      title: (m["title"] ?? "").toString(),
      artist: (m["artist"] ?? "").toString(),
      album: (m["album"] ?? "").toString(),
      duration: _toInt(m["duration"]),
      position: _toInt(m["time"]),
      volume: vol,
      artworkUrl: artwork,
      trackId: (m["id"] ?? "").toString(),
    );
  }

  /// LMS mixer volume (0..100, perceptual curve) -> UI slider (0..100, linear).
  /// Matches the legacy Sonora Web behaviour: slider = sqrt(lms / 100) * 100.
  static int lmsToSlider(int raw) {
    final x = (raw.clamp(0, 100) as num).toDouble() / 100.0;
    return (100.0 * math.sqrt(x)).round();
  }

  static int _toInt(dynamic v) {
    if (v == null) return 0;
    if (v is num) return v.toInt();
    return int.tryParse(v.toString()) ?? 0;
  }
}

class LmsException implements Exception {
  final String message;
  LmsException(this.message);
  @override
  String toString() => "LmsException: $message";
}

class LmsClient {
  LmsConfig config;
  final HttpClient _http = HttpClient();
  int _reqId = 0;

  LmsClient(this.config);

  void updateConfig(LmsConfig cfg) => config = cfg;

  Future<dynamic> rpc(List<dynamic> command, {String? playerId, Duration timeout = const Duration(seconds: 5)}) async {
    final pid = playerId ?? config.playerId;
    final id = ++_reqId;
    final body = jsonEncode({
      "id": id,
      "method": "slim.request",
      "params": [pid, command],
    });
    final uri = Uri.parse("${config.base}/jsonrpc.js");
    try {
      final req = await _http.postUrl(uri).timeout(timeout);
      req.headers.contentType = ContentType.json;
      if (config.user.isNotEmpty) {
        final token = base64Encode(utf8.encode("${config.user}:${config.password}"));
        req.headers.set(HttpHeaders.authorizationHeader, "Basic $token");
      }
      req.write(body);
      final resp = await req.close().timeout(timeout);
      final text = await utf8.decoder.bind(resp).join();
      if (resp.statusCode != 200) {
        throw LmsException("HTTP ${resp.statusCode}");
      }
      final decoded = jsonDecode(text) as Map<String, dynamic>;
      if (decoded.containsKey("error")) {
        throw LmsException("RPC error: ${decoded["error"]}");
      }
      return decoded["result"];
    } on SocketException {
      throw LmsException("无法连接 ${config.host}:${config.port}");
    } on TimeoutException catch (_) {
      throw LmsException("连接超时 ${config.host}:${config.port}");
    }
  }

  Future<bool> ping() async {
    try {
      final r = await rpc(const ["version", "?"], timeout: const Duration(seconds: 3));
      return r is Map && r.containsKey("version");
    } catch (_) {
      return false;
    }
  }

  Future<PlaybackStatus> status() async {
    final r = await rpc(const ["status", "-", "1", "tags:ACITW"]);
    if (r is! Map) return const PlaybackStatus();
    return PlaybackStatus.fromLms(Map<String, dynamic>.from(r), config.base);
  }

  Future<void> play() => rpc(const ["play"]);
  Future<void> pause() => rpc(const ["pause", "1"]);
  Future<void> toggle() => rpc(const ["playlist", "toggle"]);
  Future<void> next() => rpc(const ["playlist", "index", "+1"]);
  Future<void> previous() => rpc(const ["playlist", "index", "-1"]);
  Future<void> seek(int seconds) => rpc(["seek", seconds]);
  /// UI slider (0..100, linear) -> LMS mixer volume (0..100, perceptual curve).
  /// Inverse of PlaybackStatus.lmsToSlider.
  static int sliderToLms(int slider) {
    final x = (slider.clamp(0, 100) as num).toDouble() / 100.0;
    return (100.0 * x * x).round();
  }

  Future<void> setVolume(int slider) => rpc(["mixer", "volume", sliderToLms(slider).toString()]);

  void dispose() => _http.close();
}
