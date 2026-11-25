import "dart:async";
import "package:flutter/foundation.dart";
import "../lms/lms_client.dart";

/// Holds playback state, drives a 1s poll, and maintains a local timeline
/// so the progress bar advances smoothly between server polls.
class PlayerProvider extends ChangeNotifier {
  final LmsClient client;
  Timer? _pollTimer;
  Timer? _tickTimer;

  PlaybackStatus _status = const PlaybackStatus();
  PlaybackStatus get status => _status;

  bool _connected = false;
  bool get connected => _connected;

  String _error = "";
  String get error => _error;

  int? _seekPreview;
  int? get seekPreview => _seekPreview;

  bool _busy = false;
  bool get busy => _busy;

  PlayerProvider(this.client);

  void startPolling() {
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(const Duration(seconds: 1), (_) => refresh());
    _tickTimer?.cancel();
    _tickTimer = Timer.periodic(const Duration(seconds: 1), (_) => _tick());
    refresh();
  }

  void _tick() {
    if (!_status.isPlaying || _seekPreview != null) return;
    final next = _status.position + 1;
    if (next > _status.duration && _status.duration > 0) {
      refresh();
      return;
    }
    _status = PlaybackStatus(
      mode: _status.mode, title: _status.title, artist: _status.artist,
      album: _status.album, duration: _status.duration, position: next,
      volume: _status.volume, artworkUrl: _status.artworkUrl, trackId: _status.trackId,
    );
    notifyListeners();
  }

  Future<void> refresh() async {
    try {
      final s = await client.status();
      _connected = true;
      _error = "";
      final pos = _seekPreview ?? s.position;
      _status = PlaybackStatus(
        mode: s.mode, title: s.title, artist: s.artist, album: s.album,
        duration: s.duration, position: pos, volume: s.volume,
        artworkUrl: s.artworkUrl, trackId: s.trackId,
      );
    } catch (e) {
      _connected = false;
      _error = e.toString();
    }
    notifyListeners();
  }

  Future<void> connect(LmsConfig cfg) async {
    client.updateConfig(cfg);
    final ok = await client.ping();
    if (!ok) {
      _connected = false;
      _error = "连接失败，请检查地址与端口";
      notifyListeners();
      return;
    }
    await refresh();
  }

  void previewSeek(int seconds) {
    _seekPreview = seconds.clamp(0, _status.duration);
    _status = PlaybackStatus(
      mode: _status.mode, title: _status.title, artist: _status.artist,
      album: _status.album, duration: _status.duration, position: _seekPreview!,
      volume: _status.volume, artworkUrl: _status.artworkUrl, trackId: _status.trackId,
    );
    notifyListeners();
  }

  Future<void> commitSeek(int seconds) async {
    _busy = true;
    notifyListeners();
    try {
      await client.seek(seconds);
      _seekPreview = null;
      await refresh();
    } catch (_) {
      _seekPreview = null;
    } finally {
      _busy = false;
      notifyListeners();
    }
  }

  Future<void> togglePlay() async => _act(() => client.toggle());
  Future<void> next() async => _act(() => client.next());
  Future<void> previous() async => _act(() => client.previous());
  Future<void> setVolume(int v) async => _act(() => client.setVolume(v));

  Future<void> _act(Future<void> Function() fn) async {
    _busy = true;
    notifyListeners();
    try {
      await fn();
      await refresh();
    } catch (e) {
      _error = e.toString();
      notifyListeners();
    } finally {
      _busy = false;
    }
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _tickTimer?.cancel();
    super.dispose();
  }
}
