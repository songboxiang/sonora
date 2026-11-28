import "dart:convert";
import "dart:io";

import "models.dart";
import "services.dart";
import "../lms/protocol.dart";

/// A lyric result together with the source that supplied it, so the UI can
/// tell whether the text came from LMS itself or from a fallback provider.
class LyricResult {
  final List<LyricLine> lines;
  final String source;
  const LyricResult(this.lines, this.source);
  bool get isEmpty => lines.isEmpty;
}

class _Candidate {
  final String text;
  final String source;
  const _Candidate(this.text, this.source);
}

final Map<String, LyricResult> _lyricCache = <String, LyricResult>{};
final Map<String, Map<String, String>> _bioCache =
    <String, Map<String, String>>{};

bool _hasTimestamps(String text) =>
    RegExp(r"\[\d{1,3}:\d{1,2}(?:[.:]\d+)?\]").hasMatch(text);

String _stripHtml(String raw) {
  var s = raw.replaceAll(
    RegExp(r"<(script|style)[^>]*>.*?</\1>", caseSensitive: false, dotAll: true),
    " ",
  );
  s = s.replaceAll(RegExp(r"<[^>]+>"), " ");
  s = s
      .replaceAll("&nbsp;", " ")
      .replaceAll("&amp;", "&")
      .replaceAll("&quot;", '"')
      .replaceAll("&#39;", "'")
      .replaceAll("&lt;", "<")
      .replaceAll("&gt;", ">");
  return s.replaceAll(RegExp(r"[ \t]+"), " ").trim();
}

Future<String> _get(
  String url, {
  Map<String, String> headers = const <String, String>{},
  Duration timeout = const Duration(seconds: 6),
}) async {
  final req = await httpClient.getUrl(Uri.parse(url)).timeout(timeout);
  req.headers.set(
    HttpHeaders.userAgentHeader,
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
  );
  headers.forEach((key, value) => req.headers.set(key, value));
  final resp = await req.close().timeout(timeout);
  final body = await utf8.decoder.bind(resp).join();
  if (resp.statusCode != 200) throw Exception("HTTP ${resp.statusCode}");
  return body;
}

/// Parse LRC (or plain text) into timestamped lines. Meta tags such as
/// [ti:...] are ignored; multiple timestamps on one line are expanded.
List<LyricLine> parseLrc(String raw) {
  final text = raw.replaceAll("\r\n", "\n").replaceAll("\r", "\n");
  final out = <LyricLine>[];
  final stamp = RegExp(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]");
  final meta = RegExp(r"^\[(ti|ar|al|by|offset|re|ve):.*\]$", caseSensitive: false);
  var timed = false;
  for (final line in text.split("\n")) {
    final s = line.trim();
    if (s.isEmpty || meta.hasMatch(s)) continue;
    final matches = stamp.allMatches(s).toList();
    if (matches.isEmpty) {
      out.add(LyricLine(timeMs: -1, text: s));
      continue;
    }
    timed = true;
    final body = s.substring(matches.last.end).trim();
    if (body.isEmpty) continue;
    for (final m in matches) {
      final min = int.tryParse(m.group(1) ?? "") ?? 0;
      final sec = int.tryParse(m.group(2) ?? "") ?? 0;
      final rawFrac = m.group(3) ?? "0";
      final fracValue = int.tryParse(rawFrac) ?? 0;
      final fracMs = switch (rawFrac.length) {
        1 => fracValue * 100,
        2 => fracValue * 10,
        _ => fracValue,
      };
      final ms = ((min * 60 + sec) * 1000) + fracMs;
      out.add(LyricLine(timeMs: ms, text: body));
    }
  }
  if (timed) {
    final kept = out.where((l) => l.timeMs >= 0).toList()
      ..sort((a, b) => a.timeMs.compareTo(b.timeMs));
    return kept;
  }
  // Plain text: space lines three seconds apart so the highlight advances.
  return <LyricLine>[
    for (var i = 0; i < out.length; i++)
      LyricLine(timeMs: i * 3000, text: out[i].text),
  ];
}

Future<List<_Candidate>> _lrclib(String title, String artist, String album) async {
  final out = <_Candidate>[];
  final q = <String, String>{"track_name": title};
  if (artist.isNotEmpty) q["artist_name"] = artist;
  if (album.isNotEmpty) q["album_name"] = album;
  try {
    final body = await _get(
      "https://lrclib.net/api/get?${Uri(queryParameters: q).query}",
    );
    final d = jsonDecode(body) as Map<String, dynamic>;
    final synced = (d["syncedLyrics"] ?? "").toString();
    final plain = (d["plainLyrics"] ?? "").toString();
    if (synced.isNotEmpty) out.add(_Candidate(synced, "LRCLIB 同步歌词"));
    if (plain.isNotEmpty && plain != synced) {
      out.add(_Candidate(plain, "LRCLIB 纯文本歌词"));
    }
  } catch (_) {}
  return out;
}

Future<List<_Candidate>> _netease(String title, String artist) async {
  final out = <_Candidate>[];
  final query = "$title $artist".trim();
  final headers = <String, String>{"Referer": "https://music.163.com"};
  try {
    final search = await _get(
      "https://music.163.com/api/search/get?${Uri(queryParameters: <String, String>{"s": query, "type": "1", "offset": "0", "limit": "6"}).query}",
      headers: headers,
    );
    final songs =
        (((jsonDecode(search) as Map<String, dynamic>)["result"] as Map?)?["songs"]
                as List?) ??
            const <dynamic>[];
    for (final song in songs.take(3)) {
      final id = song is Map ? song["id"] : null;
      if (id == null) continue;
      try {
        final body = await _get(
          "https://music.163.com/api/song/lyric?${Uri(queryParameters: <String, String>{"id": id.toString(), "lv": "1", "kv": "1", "tv": "-1"}).query}",
          headers: headers,
        );
        final lrc =
            (((jsonDecode(body) as Map<String, dynamic>)["lrc"] as Map?)?["lyric"]
                    as String?) ??
                "";
        if (lrc.trim().isNotEmpty) {
          final name = song["name"] ?? "";
          out.add(_Candidate(lrc, "网易云音乐 · $name"));
        }
      } catch (_) {}
    }
  } catch (_) {}
  return out;
}

Future<List<_Candidate>> _qq(String title, String artist) async {
  final out = <_Candidate>[];
  final query = "$title $artist".trim();
  final headers = <String, String>{
    "Referer": "https://y.qq.com/",
  };
  try {
    final search = await _get(
      "https://c.y.qq.com/soso/fcgi-bin/client_search_cp?${Uri(queryParameters: <String, String>{"w": query, "format": "json", "n": "6", "p": "1"}).query}",
      headers: headers,
    );
    final songs = ((((jsonDecode(search) as Map<String, dynamic>)["data"] as Map?)?["song"]
                as Map?)?["list"] as List?) ??
            const <dynamic>[];
    for (final song in songs.take(2)) {
      final mid = song is Map ? song["songmid"] : null;
      if (mid == null) continue;
      try {
        final body = await _get(
          "https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg?${Uri(queryParameters: <String, String>{"songmid": mid.toString(), "format": "json", "nobase64": "1"}).query}",
          headers: headers,
        );
        var lrc = ((jsonDecode(body) as Map<String, dynamic>)["lyric"] ?? "").toString();
        if (lrc.isEmpty || lrc == "{}") continue;
        final name = song["songname"] ?? "";
        out.add(_Candidate(lrc, "QQ 音乐 · $name"));
      } catch (_) {}
    }
  } catch (_) {}
  return out;
}

bool _isPlaceholder(String text) {
  const markers = <String>["此歌曲为没有填词的纯音乐", "没有填词", "暂无歌词", "纯音乐，请您欣赏"];
  return markers.any(text.contains);
}

LyricResult _best(List<_Candidate> candidates) {
  final usable =
      candidates.where((c) => !_isPlaceholder(c.text)).toList();
  final timed = usable.where((c) => _hasTimestamps(c.text)).toList();
  final chosen = timed.isNotEmpty
      ? timed.first
      : (usable.isEmpty ? null : usable.first);
  if (chosen == null) return const LyricResult(<LyricLine>[], "");
  return LyricResult(parseLrc(chosen.text), chosen.source);
}

/// LMS lyrics are stored under the lowercase `w` tag. Older builds asked for
/// `L`, which LMS silently ignores. When the server has no embedded lyrics we
/// fall back to the Music & Artist Information plugin and then to online LRC
/// providers, mirroring the earlier desktop build.
Future<LyricResult> fetchResolvedLyrics(
  LmsTarget target,
  String trackId, {
  String title = "",
  String artist = "",
  String album = "",
  int duration = 0,
  bool online = true,
  void Function(String)? onError,
}) async {
  final key = "$title|$artist|$album";
  final cached = _lyricCache[key];
  if (cached != null) return cached;

  if (trackId.isNotEmpty) {
    final root = await lmsRpc(
      target,
      <dynamic>[
        "",
        <dynamic>["songinfo", 0, 100, "track_id:$trackId", "tags:wlc"],
      ],
      quiet: true,
      onError: onError,
    );
    if (root != null) {
      final loop = lmsResult(root)["songinfo_loop"];
      if (loop is List) {
        for (final item in loop) {
          if (item is! Map) continue;
          for (final k in <String>["lyrics", "w", "LYRICS"]) {
            final raw = item[k]?.toString() ?? "";
            if (raw.trim().isNotEmpty) {
              final result = LyricResult(
                parseLrc(raw),
                "LMS 内嵌歌词",
              );
              _lyricCache[key] = result;
              return result;
            }
          }
        }
      }
    }

    final mai = await lmsRpc(
      target,
      <dynamic>[
        "",
        <dynamic>["musicartistinfo", "lyrics", "track_id:$trackId"],
      ],
      quiet: true,
      onError: onError,
    );
    if (mai != null) {
      final raw = _stripHtml((mai["result"]?["lyrics"] ?? "").toString());
      if (raw.isNotEmpty && !raw.startsWith("I'm sorry")) {
        final result = LyricResult(parseLrc(raw), "LMS · Music & Artist Information");
        _lyricCache[key] = result;
        return result;
      }
    }
  }

  if (online && title.trim().isNotEmpty) {
    final candidates = <_Candidate>[
      ...await _lrclib(title, artist, album),
      ...await _netease(title, artist),
      ...await _qq(title, artist),
    ];
    final best = _best(candidates);
    if (!best.isEmpty) {
      _lyricCache[key] = best;
      return best;
    }
  }
  return const LyricResult(<LyricLine>[], "");
}

/// Artist/album descriptions from the same LMS plugin, used by the track
/// information card on the playback page.
Future<Map<String, String>> fetchLmsBios(
  LmsTarget target, {
  String artist = "",
  String album = "",
  void Function(String)? onError,
}) async {
  final key = "$artist|$album";
  final cached = _bioCache[key];
  if (cached != null) return cached;
  final out = <String, String>{};
  if (artist.isNotEmpty) {
    final root = await lmsRpc(
      target,
      <dynamic>[
        "",
        <dynamic>["musicartistinfo", "biography", "artist:$artist"],
      ],
      quiet: true,
      onError: onError,
    );
    final text = _stripHtml((root?["result"]?["biography"] ?? "").toString());
    if (text.isNotEmpty) out["艺人介绍"] = text;
  }
  if (album.isNotEmpty) {
    final args = <dynamic>["musicartistinfo", "albumreview"];
    if (artist.isNotEmpty) args.add("artist:$artist");
    args.add("album:$album");
    final root = await lmsRpc(
      target,
      <dynamic>["", args],
      quiet: true,
      onError: onError,
    );
    final text = _stripHtml((root?["result"]?["albumreview"] ?? "").toString());
    if (text.isNotEmpty) out["专辑介绍"] = text;
  }
  _bioCache[key] = out;
  return out;
}
