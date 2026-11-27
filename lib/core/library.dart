import "models.dart";

/// One implementation per music server. The UI only depends on this contract,
/// so adding Navidrome after LMS does not rewrite the screens.
abstract class MusicLibrary {
  String get id;
  String get displayName;
  PlaybackMode get playbackMode;

  Future<ServerInfo> probe();
  Future<UpdateInfo> updateInfo();
  Future<List<PlayerInfo>> listPlayers();
  Future<PlaybackStatus> status(String playerId);
  Future<void> control(String playerId, List<String> command);
  Stream<PlaybackStatus> subscribe();
}

/// Where a release version and its notes come from. Implementations do not
/// install anything; they only report.
abstract class UpdateSource {
  String get name;
  Future<UpdateInfo> check(String current);
}
