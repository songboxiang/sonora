import "package:just_audio/just_audio.dart";

import "../core/models.dart";
import "subsonic.dart";

/// Client-side streaming for the Navidrome/OpenSubsonic track.
///
/// LMS uses an external player (squeezelite), so audio is produced outside the
/// app. Navidrome has no slimproto player: this class owns the only in-app
/// audio pipeline. Keep it isolated so the two tracks never mix.
class NavidromeAudio {
  NavidromeAudio({this.onLog});

  final void Function(String)? onLog;
  final AudioPlayer _player = AudioPlayer();

  /// Builds an authenticated /rest/stream URL.
  ///
  /// Important: the password is never sent; only the md5 token is. `f=json`
  /// is removed because the stream endpoint returns binary audio, not JSON.
  static String streamUrl({
    required String host,
    required SubsonicAuth auth,
    required String songId,
  }) {
    final q = <String, String>{"id": songId, ...auth.query()}..remove("f");
    return "http://$host/rest/stream?${Uri(queryParameters: q).query}";
  }

  bool get isPlaying => _player.playing;
  Duration? get duration => _player.duration;
  Duration get position => _player.position;
  Stream<Duration> get positionStream => _player.positionStream;
  Stream<Duration?> get durationStream => _player.durationStream;
  Stream<PlayerState> get stateStream => _player.playerStateStream;

  Future<void> playSong({
    required String host,
    required SubsonicAuth auth,
    required SongInfo song,
  }) async {
    final url = streamUrl(host: host, auth: auth, songId: song.id);
    _log("stream ${url.replaceFirst(RegExp(r"t=[^&]+"), "t=<hidden>")}");
    final d = await _player.setUrl(url);
    _log("loaded ${song.title} duration=${d?.inSeconds ?? -1}s");
    // On headless VMs AVAudioSession may never report a device; do not let
    // that block the control path. Playback errors still surface via streams.
    await _player.play().timeout(
          const Duration(seconds: 3),
          onTimeout: () {},
        );
    _log("play requested");
  }

  Future<void> resume() => _player.play();
  Future<void> pause() => _player.pause();
  Future<void> seek(Duration position) => _player.seek(position);
  Future<void> setVolume(double volume) => _player.setVolume(volume.clamp(0.0, 1.0));
  Future<void> setLoopMode(LoopMode mode) => _player.setLoopMode(mode);
  Future<void> setShuffleModeEnabled(bool enabled) =>
      _player.setShuffleModeEnabled(enabled);
  Future<void> stop() => _player.stop();
  Future<void> dispose() => _player.dispose();

  void _log(String line) => onLog?.call(line);
}
