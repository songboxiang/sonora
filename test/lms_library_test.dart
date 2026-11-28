import "dart:convert";

import "package:flutter_test/flutter_test.dart";
import "package:sonora/lms/library.dart";

Map<String, dynamic> j(String s) => jsonDecode(s) as Map<String, dynamic>;

void main() {
  test("parseLmsAlbums reads albums_loop and cover id", () {
    final root = j(
      "{\"result\":{\"count\":2,\"albums_loop\":["
      "{\"id\":410,\"album\":\"春之祭\",\"artist\":\"久石让\",\"coverid\":91},"
      "{\"id\":411,\"favorites_title\":\"无封面\"}]}}",
    );
    final albums = parseLmsAlbums(root, base: "http://lms:9000");
    expect(albums.length, 2);
    expect(albums.first.id, "410");
    expect(albums.first.name, "春之祭");
    expect(albums.first.coverUrl, "http://lms:9000/music/91/cover");
    expect(albums.last.name, "无封面");
    expect(albums.last.coverUrl, "");
  });

  test("parseLmsTracks converts float duration to seconds", () {
    final root = j(
      "{\"result\":{\"titles_loop\":["
      "{\"id\":4425,\"title\":\"一场游戏一场梦\",\"artist\":\"王杰\","
      "\"album\":\"歌坛杰作\",\"duration\":258.173}]}}",
    );
    final songs = parseLmsTracks(root);
    expect(songs.single.id, "4425");
    expect(songs.single.duration, 258);
    expect(songs.single.album, "歌坛杰作");
  });
}
