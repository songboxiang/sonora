// N1 验收探针：搜索 / 封面 / 歌词 / 简介 / 播放队列。
// 只打印计数与判定，不打印 token 或密码。
// 用法：dart run tool/probe_navidrome_extras.dart [--query=爱]
import "dart:convert";
import "dart:io";

import "package:sonora/core/services.dart";
import "package:sonora/navidrome/subsonic.dart";

Map<String, String> opts(List<String> args) {
  final out = <String, String>{};
  for (final a in args) {
    if (a.startsWith("--") && a.contains("=")) {
      final i = a.indexOf("=");
      out[a.substring(2, i)] = a.substring(i + 1);
    }
  }
  return out;
}

Future<void> main(List<String> args) async {
  final o = opts(args);
  final credPath = o["creds"] ?? "/Users/song/navidrome_creds.json";
  final host = o["host"] ?? "192.168.199.2:4533";
  final query = o["query"] ?? "爱";
  final c = readCreds(credPath);
  final result = <String, dynamic>{
    "creds": credPath,
    "host": host,
    "query": query,
  };
  final user = c["user"] ?? "";
  final pass = c["password"] ?? c["pass"] ?? "";
  if (user.isEmpty || pass.isEmpty) {
    result["verdict"] = "FAIL";
    result["error"] = "凭证缺少 user/password";
    stdout.writeln(jsonEncode(result));
    exitCode = 1;
    return;
  }

  final target = NavidromeTarget(
    host: host,
    auth: SubsonicAuth(
      user: user,
      password: pass,
      salt: DateTime.now().microsecondsSinceEpoch.toString(),
    ),
  );

  final ping = await probeNavidrome(target);
  result["ping"] = ping.statusText;

  final search = await searchNavidrome(target, query);
  result["searchAlbums"] = search.albums.length;
  result["searchSongs"] = search.songs.length;
  result["coverHasToken"] = search.albums.isEmpty
      ? false
      : search.albums.first.coverUrl.contains("t=") &&
            !search.albums.first.coverUrl.contains("f=json");

  final albums = await fetchNavidromeAlbums(target, size: 3);
  result["albums"] = albums.length;
  var noteLen = 0;
  var bioLen = 0;
  var lyricLines = 0;
  if (albums.isNotEmpty) {
    final first = albums.first;
    final songs = await fetchNavidromeAlbum(target, first.id);
    result["detailSongs"] = songs.length;
    result["songHasCoverUrl"] = songs.isEmpty
        ? false
        : songs.first.coverUrl.contains("getCoverArt");
    noteLen = (await fetchNavidromeAlbumNote(target, first.id)).length;
    bioLen = (await fetchNavidromeArtistBio(target, first.artistId)).length;
    if (songs.isNotEmpty) {
      lyricLines = (await fetchNavidromeLyrics(target, songs.first.id)).length;
    }
  }
  result["albumNoteChars"] = noteLen;
  result["artistBioChars"] = bioLen;
  result["lyricLines"] = lyricLines;

  final queue = await fetchNavidromePlayQueue(target);
  result["playQueue"] = queue.mode;

  result["verdict"] = ping.reachable && albums.isNotEmpty ? "PASS" : "FAIL";
  stdout.writeln(jsonEncode(result));
  exitCode = result["verdict"] == "PASS" ? 0 : 1;
}
