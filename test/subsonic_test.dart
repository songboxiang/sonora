import "dart:convert";
import "package:crypto/crypto.dart";
import "package:flutter_test/flutter_test.dart";
import "package:sonora/navidrome/subsonic.dart";

Map<String, dynamic> j(String s) => jsonDecode(s) as Map<String, dynamic>;

void main() {
  group("SubsonicAuth", () {
    const a = SubsonicAuth(user: "admin", password: "secret", salt: "abc123");
    test("sends token, never password", () {
      final q = a.query();
      expect(q["u"], "admin");
      expect(q["t"], a.token);
      expect(q.containsKey("p"), isFalse);
      expect(q["v"], "1.16.1");
      expect(q["f"], "json");
    });
    test("token is md5 of password plus salt", () {
      expect(
        a.token,
        md5
            .convert(
              utf8.encode(
                "secret"
                "abc123",
              ),
            )
            .toString(),
      );
      expect(a.token.length, 32);
    });
  });

  test("parsePing reads serverVersion", () {
    final s = parsePing(
      j(
        "{\"subsonic-response\":{\"status\":\"ok\",\"version\":\"1.16.1\","
        "\"type\":\"navidrome\",\"serverVersion\":\"0.55.2 (a057a680)\","
        "\"openSubsonic\":true}}",
      ),
    );
    expect(s.type, "navidrome");
    expect(s.version, "0.55.2 (a057a680)");
    expect(s.reachable, isTrue);
  });

  test("parsePing reports failure message", () {
    final s = parsePing(
      j(
        "{\"subsonic-response\":{\"status\":\"failed\",\"error\":{\"code\":10,\"message\":\"missing parameter\"}}}",
      ),
    );
    expect(s.reachable, isFalse);
    expect(s.error, "missing parameter");
  });

  test("parseAlbumList builds cover url", () {
    final list = parseAlbumList(
      j(
        "{\"subsonic-response\":{\"albumList2\":{\"album\":["
        "{\"id\":\"a1\",\"name\":\"情歌精选\",\"artist\":\"张国荣\",\"coverArt\":\"c1\"}]}}}",
      ),
      "http://192.168.199.2:4533",
    );
    expect(list.length, 1);
    expect(list.first.name, "情歌精选");
    expect(
      list.first.coverUrl,
      "http://192.168.199.2:4533/rest/getCoverArt?id=c1&size=300",
    );
  });

  test("parseAlbum reads songs", () {
    final songs = parseAlbum(
      j(
        "{\"subsonic-response\":{\"album\":{\"song\":["
        "{\"id\":\"s1\",\"title\":\"爱如潮水\",\"artist\":\"张信哲\",\"duration\":289}]}}}",
      ),
    );
    expect(songs.single.id, "s1");
    expect(songs.single.duration, 289);
  });

  test("parseStructuredLyrics keeps timestamps", () {
    final lines = parseStructuredLyrics(
      j(
        "{\"subsonic-response\":{\"lyricsList\":{\"structuredLyrics\":["
        "{\"line\":[{\"start\":1200,\"value\":\"第一行\"},{\"start\":3400,\"value\":\"第二行\"}]}]}}}",
      ),
    );
    expect(lines.length, 2);
    expect(lines.first.timeMs, 1200);
    expect(lines.last.text, "第二行");
  });

  test("parsePlayQueue returns empty status when nothing plays", () {
    final s = parsePlayQueue(j("{\"subsonic-response\":{\"playQueue\":{}}}"));
    expect(s.mode, "stop");
    expect(s.isPlaying, isFalse);
  });

  test("atom fallback skips feed title and finds version", () {
    const xml =
        "<feed><title>Release notes from navidrome</title>"
        "<entry><title>v0.64.2</title></entry></feed>";
    expect(parseAtomLatestVersion(xml), "v0.64.2");
  });

  test("authenticated cover art url carries token and never password", () {
    const auth = SubsonicAuth(
      user: "demo",
      password: "secret",
      salt: "salt123",
    );
    final url = coverArtUrl(
      base: "http://192.168.199.2:4533",
      auth: auth,
      id: "c1",
      size: 300,
    );
    expect(url, contains("/rest/getCoverArt?"));
    expect(url, contains("id=c1"));
    expect(url, contains("size=300"));
    expect(url, contains("t="));
    expect(url, isNot(contains("secret")));
    expect(url, isNot(contains("f=json")));
  });

  test("search3 parses albums and songs with authenticated covers", () {
    const auth = SubsonicAuth(
      user: "demo",
      password: "secret",
      salt: "salt123",
    );
    final root = j(
      "{\"subsonic-response\":{\"search3\":{"
      "\"album\":[{\"id\":\"a1\",\"name\":\"专辑\",\"artist\":\"艺人\",\"artistId\":\"ar1\",\"coverArt\":\"c1\"}],"
      "\"song\":[{\"id\":\"s1\",\"title\":\"歌\",\"artist\":\"艺人\",\"album\":\"专辑\",\"duration\":180,\"coverArt\":\"c1\"}]}}}",
    );
    final albums = parseSearch3Albums(
      root,
      "http://192.168.199.2:4533",
      auth: auth,
    );
    final songs = parseSearch3Songs(
      root,
      "http://192.168.199.2:4533",
      auth: auth,
    );
    expect(albums.single.artistId, "ar1");
    expect(albums.single.coverUrl, contains("t="));
    expect(songs.single.duration, 180);
    expect(songs.single.coverUrl, contains("id=c1"));
  });

  test("album note and artist biography parsers", () {
    final note = parseAlbumNote(
      j("{\"subsonic-response\":{\"albumInfo\":{\"note\":\"专辑简介\"}}}"),
    );
    final bio = parseArtistBio(
      j("{\"subsonic-response\":{\"artistInfo2\":{\"biography\":\"艺人简介\"}}}"),
    );
    expect(note, "专辑简介");
    expect(bio, "艺人简介");
  });

  test("album songs get cover urls when base and auth are provided", () {
    const auth = SubsonicAuth(
      user: "demo",
      password: "secret",
      salt: "salt123",
    );
    final songs = parseAlbum(
      j(
        "{\"subsonic-response\":{\"album\":{\"song\":["
        "{\"id\":\"s1\",\"title\":\"歌\",\"coverArt\":\"c1\"}]}}}",
      ),
      base: "http://192.168.199.2:4533",
      auth: auth,
    );
    expect(songs.single.coverUrl, contains("getCoverArt"));
    expect(songs.single.coverUrl, isNot(contains("secret")));
  });

  test("parseAlbum carries audio metadata", () {
    final songs = parseAlbum(
      j(
        "{\"subsonic-response\":{\"album\":{\"song\":[{\"id\":\"s1\","
        "\"title\":\"Song\",\"bitRate\":865,\"samplingRate\":44100,"
        "\"bitDepth\":16,\"channelCount\":2,\"suffix\":\"flac\","
        "\"contentType\":\"audio/flac\"}]}}}",
      ),
    );
    expect(songs.single.audio?.bitrateText, "865 kbps");
    expect(songs.single.audio?.sampleRateText, "44.1 kHz");
    expect(songs.single.audio?.bitDepthText, "16 bit");
    expect(songs.single.audio?.formatText, "FLAC");
    expect(songs.single.audio?.channels, 2);
    expect(songs.single.audio?.lossless, isTrue);
  });
}
