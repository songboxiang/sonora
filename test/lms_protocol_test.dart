import "dart:convert";
import "package:flutter_test/flutter_test.dart";
import "package:sonora/lms/protocol.dart";
import "package:sonora/core/models.dart";

Map<String, dynamic> j(String s) => jsonDecode(s) as Map<String, dynamic>;

void main() {
  test("version uses underscore-prefixed field", () {
    final s = parseLmsVersion(j(
        "{\"result\":{\"_version\":\"9.1.1\"},\"id\":1}"));
    expect(s.version, "9.1.1");
    expect(s.reachable, isTrue);
  });

  test("version without field is not reachable", () {
    final s = parseLmsVersion(j("{\"result\":{}}"));
    expect(s.reachable, isFalse);
  });

  test("player count reads count field", () {
    expect(parsePlayerCount(j("{\"result\":{\"count\":0}}")), 0);
    expect(parsePlayerCount(j(
        "{\"result\":{\"players_loop\":[{\"playerid\":\"x\"}]}}")), 1);
  });

  test("parsePlayers maps ids and names", () {
    final p = parsePlayers(j(
        "{\"result\":{\"players_loop\":[{\"playerid\":\"02:00:00:00:00:00\",\"name\":\"客厅\"}]}}"));
    expect(p.single.id, "02:00:00:00:00:00");
    expect(p.single.name, "客厅");
  });

  test("parsePlayers keeps connected flag for stale entries", () {
    final p = parsePlayers(j(
        "{\"result\":{\"players_loop\":["
        "{\"playerid\":\"a\",\"name\":\"live\",\"connected\":1},"
        "{\"playerid\":\"b\",\"name\":\"stale\",\"connected\":0}]}}"));
    expect(p.first.connected, isTrue);
    expect(p.last.connected, isFalse);
  });

  test("volume curve matches legacy app", () {
    expect(lmsToSlider(0), 0);
    expect(lmsToSlider(25), 50);
    expect(lmsToSlider(64), 80);
    expect(lmsToSlider(100), 100);
    for (final s in [0, 10, 25, 50, 75, 90, 100]) {
      expect(lmsToSlider(sliderToLms(s)), closeTo(s, 2));
    }
  });

  test("status parses fields and artwork", () {
    final s = parseLmsStatus(j(
        "{\"result\":{\"mode\":\"play\",\"title\":\"Song\",\"artist\":\"Artist\","
        "\"duration\":\"200\",\"time\":42,\"volume\":25,\"artwork_track_id\":\"123\"}}"),
        "http://192.168.199.2:9000");
    expect(s.mode, "play");
    expect(s.isPlaying, isTrue);
    expect(s.duration, 200);
    expect(s.position, 42);
    expect(s.volume, 50);
    expect(s.artworkUrl, "http://192.168.199.2:9000/music/123/cover");
  });

  test("version comparison handles mixed formats", () {
    expect(compareVersions("0.64.2", "0.55.2 (a057a680)"), 1);
    expect(compareVersions("v2.0.18", "2.0.9"), 1);
    expect(compareVersions("9.1.1", "9.1.1"), 0);
  });
}
