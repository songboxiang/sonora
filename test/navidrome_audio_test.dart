import "dart:convert";
import "package:crypto/crypto.dart";
import "package:flutter_test/flutter_test.dart";

import "package:sonora/navidrome/audio.dart";
import "package:sonora/navidrome/subsonic.dart";

void main() {
  const auth = SubsonicAuth(
    user: "demo",
    password: "secret",
    salt: "salt123",
    client: "Sonora",
  );

  test("stream URL carries token and never the password", () {
    final url = NavidromeAudio.streamUrl(
      host: "192.168.199.2:4533",
      auth: auth,
      songId: "abc-123",
    );
    final q = Uri.parse(url).queryParameters;
    expect(url.startsWith("http://192.168.199.2:4533/rest/stream?"), isTrue);
    expect(q["id"], "abc-123");
    expect(q["u"], "demo");
    expect(q["s"], "salt123");
    expect(q["v"], "1.16.1");
    expect(q["c"], "Sonora");
    expect(q["t"], md5.convert(utf8.encode("secretsalt123")).toString());
    expect(url.contains("secret"), isFalse);
  });

  test("stream URL drops f=json (binary endpoint)", () {
    final url = NavidromeAudio.streamUrl(
      host: "navidrome.local",
      auth: auth,
      songId: "s1",
    );
    expect(Uri.parse(url).queryParameters.containsKey("f"), isFalse);
  });
}
