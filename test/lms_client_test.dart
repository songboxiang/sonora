import "package:flutter_test/flutter_test.dart";
import "package:sonora/lms/lms_client.dart";

void main() {
  group("PlaybackStatus.fromLms", () {
    test("parses basic fields", () {
      final s = PlaybackStatus.fromLms({
        "mode": "play",
        "title": "Song",
        "artist": "Artist",
        "album": "Album",
        "duration": "200",
        "time": 42,
      }, "http://localhost:9000");
      expect(s.mode, "play");
      expect(s.title, "Song");
      expect(s.artist, "Artist");
      expect(s.album, "Album");
      expect(s.duration, 200);
      expect(s.position, 42);
      expect(s.isPlaying, isTrue);
      expect(s.artworkUrl, "");
    });

    test("maps LMS perceptual volume to linear slider", () {
      expect(PlaybackStatus.fromLms({"volume": 0}, "http://x").volume, 0);
      expect(PlaybackStatus.fromLms({"volume": 25}, "http://x").volume, 50);
      expect(PlaybackStatus.fromLms({"volume": 64}, "http://x").volume, 80);
      expect(PlaybackStatus.fromLms({"volume": 100}, "http://x").volume, 100);
    });

    test("slider and LMS volume conversions are inverse", () {
      for (final slider in [0, 10, 25, 50, 75, 90, 100]) {
        final back = PlaybackStatus.lmsToSlider(LmsClient.sliderToLms(slider));
        expect(back, closeTo(slider, 2));
      }
    });

    test("builds artwork url from artwork_track_id or coverid", () {
      final a = PlaybackStatus.fromLms({"artwork_track_id": "123"}, "http://x:9000");
      expect(a.artworkUrl, "http://x:9000/music/123/cover");
      final b = PlaybackStatus.fromLms({"coverid": "456"}, "http://x:9000");
      expect(b.artworkUrl, "http://x:9000/music/456/cover");
    });

    test("tolerates missing fields", () {
      final s = PlaybackStatus.fromLms({}, "http://x");
      expect(s.mode, "stop");
      expect(s.title, "");
      expect(s.duration, 0);
      expect(s.position, 0);
      expect(s.volume, 100);
      expect(s.isPlaying, isFalse);
    });
  });

  test("LmsConfig.base builds endpoint prefix", () {
    const c = LmsConfig(host: "192.168.1.2", port: 9001);
    expect(c.base, "http://192.168.1.2:9001");
  });
}
