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

  test("parseLmsAlbums derives artist and year from favorites/title", () {
    final root = j(
      "{\"result\":{\"albums_loop\":[{\"id\":410,"
      "\"album\":\"[2020]斯特拉文斯基 春之祭\","
      "\"favorites_title\":\"[2020]斯特拉文斯基 春之祭\","
      "\"favorites_url\":\"db:album.title=x&contributor.name=%E4%B9%85%E7%9F%B3%E8%AE%A9\"}]}}",
    );
    final a = parseLmsAlbums(root).single;
    expect(a.artist, "久石让");
    expect(a.year, 2020);
    expect(a.metaText, contains("2020"));
  });

  test("parseLmsTracks and parseLmsArtists/Genres read hierarchy", () {
    final tracks = parseLmsTracks(
      j(
        "{\"result\":{\"titles_loop\":[{\"id\":1,\"title\":\"t\","
        "\"album\":\"[2019]A\",\"genre\":\"POP\"}]}}",
      ),
    );
    expect(tracks.single.genre, "POP");
    expect(tracks.single.year, 2019);

    final artists = parseLmsArtists(
      j("{\"result\":{\"artists_loop\":[{\"id\":569,\"artist\":\"本間昭光\"}]}}"),
    );
    expect(artists.single.name, "本間昭光");
    expect(artists.single.id, "569");

    final genres = parseLmsGenres(
      j("{\"result\":{\"genres_loop\":[{\"id\":77,\"genre\":\"无音乐曲风\"}]}}"),
    );
    expect(genres.single.name, "无音乐曲风");
  });

  test("local grouping builds artist/genre/year indexes", () {
    final root = j(
      "{\"result\":{\"albums_loop\":["
      "{\"id\":1,\"album\":\"[2020]A\",\"artist\":\"甲\",\"genre\":\"POP\"},"
      "{\"id\":2,\"album\":\"[2020]B\",\"artist\":\"乙\",\"genre\":\"POP\"},"
      "{\"id\":3,\"album\":\"[2021]C\",\"artist\":\"甲\",\"genre\":\"Jazz\"}]}}",
    );
    final albums = parseLmsAlbums(root);
    final byArtist = groupAlbumsByArtist(albums);
    expect(byArtist.length, 2);
    expect(byArtist.map((a) => a.name), containsAll(<String>["甲", "乙"]));
    expect(byArtist.firstWhere((a) => a.name == "甲").albumCount, 2);
    expect(albumsForArtist(albums, "甲").length, 2);

    final byGenre = groupAlbumsByGenre(albums);
    expect(byGenre.length, 2);
    expect(albumsForGenre(albums, "POP").length, 2);

    final byYear = groupAlbumsByYear(albums);
    expect(byYear[2020]?.length, 2);
    expect(albumsForYear(albums, 2021).single.name, "[2021]C");
  });

  test("parseLmsCoverId reads coverid from songinfo_loop", () {
    final root = j(
      "{\"result\":{\"songinfo_loop\":[{\"id\":4425},"
      "{\"title\":\"一场游戏一场梦\"},{\"coverid\":\"1c6ae12c\"}]}}",
    );
    expect(parseLmsCoverId(root), "1c6ae12c");
    expect(parseLmsCoverId(j("{\"result\":{}}")), "");
  });

  test("AlbumInfo copyWith preserves coverId and new metadata", () {
    final a = parseLmsAlbums(
      j("{\"result\":{\"albums_loop\":[{\"id\":1,\"album\":\"A\"}]}}"),
    ).single.copyWith(coverId: "abc", year: 2020, genre: "Pop");
    expect(a.coverId, "abc");
    expect(a.year, 2020);
    expect(a.genre, "Pop");
    expect(a.metaText, contains("2020"));
  });

  test("play command uses playlistcontrol track_id, not playlist play", () {
    expect(
      lmsPlayCommand("4425"),
      equals(<String>["playlistcontrol", "cmd:load", "track_id:4425"]),
    );
    expect(
      lmsPlayCommand("track_id:4425"),
      equals(<String>["playlistcontrol", "cmd:load", "track_id:4425"]),
    );
  });

  test("seek command uses LMS time, not unsupported seek", () {
    expect(lmsSeekCommand(120), equals(<String>["time", "120"]));
    expect(lmsSeekCommand(0), equals(<String>["time", "0"]));
  });

  test("representative tracks are one distinct id per album", () {
    final tracks = parseLmsTracks(
      j(
        "{\"result\":{\"titles_loop\":["
        "{\"id\":11,\"title\":\"a1\",\"album\":\"甲\"},"
        "{\"id\":12,\"title\":\"a2\",\"album\":\"甲\"},"
        "{\"id\":21,\"title\":\"b1\",\"album\":\"乙\"},"
        "{\"id\":22,\"title\":\"b2\",\"album\":\"乙\"},"
        "{\"id\":31,\"title\":\"c1\",\"album\":\"丙\"}]}}",
      ),
    );
    final picked = lmsRepresentativeTracks(tracks);
    expect(picked.length, 3);
    expect(picked, equals(<String, String>{"甲": "11", "乙": "21", "丙": "31"}));
  });
}
