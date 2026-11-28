// 验收：两端服务器元数据与层级结构的真实取数（不打印凭证）。
// 用法：dart run tool/probe_library_metadata.dart
import "dart:convert";
import "dart:io";

import "package:sonora/core/services.dart";
import "package:sonora/core/settings.dart";
import "package:sonora/lms/library.dart";
import "package:sonora/navidrome/subsonic.dart";

void log(String s) => stdout.writeln("[meta] $s");

NavidromeTarget navTarget(OpenSubsonicServer server) {
  var user = server.user;
  var pass = server.password;
  if (user.isEmpty || pass.isEmpty) {
    final c = readCreds(server.credsPath.isEmpty
        ? defaultNavCredsPath
        : server.credsPath);
    user = c["user"] ?? "";
    pass = c["password"] ?? c["pass"] ?? "";
  }
  return NavidromeTarget(
    host: server.host,
    auth: SubsonicAuth(
      user: user,
      password: pass,
      salt: DateTime.now().microsecondsSinceEpoch.toString(),
    ),
  );
}

Future<void> main() async {
  final out = <String, dynamic>{};
  try {
    // ---- LMS ----
    final lms = lmsTargetFromArgs([
      "--lms-creds=/Users/song/.squeezelite_gui/config.json",
    ]);
    var lmsAlbums = await fetchLmsAlbums(lms, count: 300);
    lmsAlbums = await enrichLmsAlbumsWithGenres(lms, lmsAlbums);
    lmsAlbums = await enrichLmsAlbumsWithCovers(lms, lmsAlbums);
    final lmsArtists = await fetchLmsArtists(lms);
    final lmsGenres = await fetchLmsGenres(lms);
    final byArtist = groupAlbumsByArtist(lmsAlbums);
    final byGenre = groupAlbumsByGenre(lmsAlbums);
    final byYear = groupAlbumsByYear(lmsAlbums);
    out["lmsAlbums"] = lmsAlbums.length;
    out["lmsArtistsServer"] = lmsArtists.length;
    out["lmsGenresServer"] = lmsGenres.length;
    out["lmsArtistGroups"] = byArtist.length;
    out["lmsGenreGroups"] = byGenre.length;
    out["lmsYearGroups"] = byYear.length;
    out["lmsWithYear"] = lmsAlbums.where((a) => a.year > 0).length;
    out["lmsWithArtist"] = lmsAlbums.where((a) => a.artist.isNotEmpty).length;
    out["lmsWithGenre"] = lmsAlbums.where((a) => a.genre.isNotEmpty).length;
    out["lmsWithCover"] = lmsAlbums.where((a) => a.coverId.isNotEmpty).length;
    out["lmsSample"] = lmsAlbums.isEmpty
        ? <String, dynamic>{}
        : <String, dynamic>{
            "name": lmsAlbums.first.name,
            "artist": lmsAlbums.first.artist,
            "year": lmsAlbums.first.year,
            "meta": lmsAlbums.first.metaText,
          };
    log(
      "LMS ${lmsAlbums.length} 张专辑 / ${lmsArtists.length} 艺人 / "
      "${lmsGenres.length} 曲风；本地层级 ${byArtist.length} 艺人 · "
      "${byGenre.length} 曲风 · ${byYear.length} 年份",
    );

    // ---- OpenSubsonic ----
    final settings = SettingsStore().load();
    final server = settings.activeServer;
    if (server == null) throw Exception("没有 OpenSubsonic 服务器");
    final target = navTarget(server);
    final ping = await probeNavidrome(target);
    final albums = await fetchNavidromeAlbums(target);
    final artists = await fetchNavidromeArtists(target);
    final genres = await fetchNavidromeGenres(target);
    out["server"] = server.name;
    out["version"] = ping.version;
    out["albums"] = albums.length;
    out["artists"] = artists.length;
    out["genres"] = genres.length;
    out["withYear"] = albums.where((a) => a.year > 0).length;
    out["withGenre"] = albums.where((a) => a.genre.isNotEmpty).length;
    out["withCounts"] = albums.where((a) => a.songCount > 0).length;
    out["sample"] = albums.isEmpty
        ? <String, dynamic>{}
        : <String, dynamic>{
            "name": albums.first.name,
            "year": albums.first.year,
            "genre": albums.first.genre,
            "songs": albums.first.songCount,
            "meta": albums.first.metaText,
          };
    log(
      "${server.name} ${ping.version}：${albums.length} 张 / "
      "${artists.length} 艺人 / ${genres.length} 曲风；"
      "带年份 ${out["withYear"]}、带曲风 ${out["withGenre"]}",
    );

    if (albums.isEmpty) throw Exception("专辑为空");
    final songs = await fetchNavidromeAlbum(target, albums.first.id);
    out["songs"] = songs.length;
    out["withTrack"] = songs.where((s) => s.track > 0).length;
    out["withDisc"] = songs.where((s) => s.disc > 0).length;
    out["withPath"] = songs.where((s) => s.path.isNotEmpty).length;
    out["songSample"] = songs.isEmpty
        ? <String, dynamic>{}
        : <String, dynamic>{
            "title": songs.first.title,
            "track": songs.first.trackText,
            "genre": songs.first.genre,
            "meta": songs.first.metaText,
          };
    log(
      "首张专辑 ${songs.length} 首：带曲目号 ${out["withTrack"]}、"
      "带光盘号 ${out["withDisc"]}、带路径 ${out["withPath"]}",
    );

    // Server-side filtered hierarchy.
    if (genres.isNotEmpty) {
      final g = genres.first.name;
      final byG = await fetchNavidromeAlbumsByGenre(target, g);
      out["genreFilter"] = <String, dynamic>{"genre": g, "albums": byG.length};
      log("服务端曲风 $g → ${byG.length} 张专辑");
    }
    final years = groupAlbumsByYear(albums).keys.toList()..sort();
    if (years.isNotEmpty) {
      final y = years.last;
      final byY = await fetchNavidromeAlbumsByYear(target, y);
      out["yearFilter"] = <String, dynamic>{"year": y, "albums": byY.length};
      log("服务端年份 $y → ${byY.length} 张专辑");
    }

    final ok = ping.reachable &&
        albums.isNotEmpty &&
        artists.isNotEmpty &&
        genres.isNotEmpty &&
        lmsAlbums.isNotEmpty &&
        (out["withYear"] as int) > 0 &&
        (out["withTrack"] as int) > 0;
    out
      ..["verdict"] = ok ? "PASS" : "FAIL"
      ..["lmsOk"] = lmsAlbums.isNotEmpty && lmsArtists.isNotEmpty;
  } catch (e) {
    out
      ..["verdict"] = "FAIL"
      ..["error"] = e.toString().split("\n").first;
  }
  stdout.writeln(jsonEncode(out));
  exitCode = out["verdict"] == "PASS" ? 0 : 1;
}
