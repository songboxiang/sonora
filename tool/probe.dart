// ignore_for_file: avoid_print, prefer_interpolation_to_compose_strings
import "package:sonora/core/models.dart";
import "package:sonora/core/services.dart";
import "package:sonora/lms/protocol.dart";
import "package:sonora/navidrome/subsonic.dart";
import "package:sonora/squeezelite/core_runner.dart";

void report(String name, String detail, bool ok) {
  final mark = ok ? "OK" : "!!";
  print("[$mark] $name: $detail");
}

Future<void> checkAppBody() async {
  try {
    final xml = await getText("https://github.com/songboxiang/sonora/releases.atom");
    final v = parseAtomLatestVersion(xml);
    report("主体", "最新 ${v ?? '未解析'}（releases.atom）", v != null);
  } catch (e) {
    report("主体", "失败 ${e.toString().split('\n').first}", false);
  }
}

Future<void> checkCoreSource() async {
  try {
    final xml = await getText(
        "https://sourceforge.net/projects/lmsclients/rss?path=/squeezelite/osx/m1");
    final m = RegExp(r"<title><!\[CDATA\[([^\]]+squeezelite[^\]]*)\]\]></title>")
        .firstMatch(xml);
    final md5m = RegExp(r'<media:hash algo="md5">([^<]+)</media:hash>').firstMatch(xml);
    if (m == null) {
      report("核心源", "未解析到版本", false);
      return;
    }
    report("核心源", "${m.group(1)} | md5=${md5m?.group(1) ?? '无'}", md5m != null);
  } catch (e) {
    report("核心源", "失败 ${e.toString().split('\n').first}", false);
  }
}

Future<void> checkLms(LmsTarget target) async {
  final root = await lmsRpc(
    target,
    ["", ["version", "?"]],
    onError: (msg) => report("LMS", msg, false),
  );
  if (root == null) return;
  final info = parseLmsVersion(root);
  report("LMS", "版本 ${info.version.isEmpty ? '未知' : info.version} "
      "(${target.auth == null ? '无凭证' : '带凭证'})", info.reachable);
}

/// --with-core：自动复制打包核心、拉起子进程，等待 LMS 播放器注册。
///
/// 这是真机验证的主路径：用户不需要手动启动 squeezelite。
Future<void> checkCoreRuntime(List<String> args, LmsTarget target) async {
  var withCore = false;
  String? corePath;
  for (final a in args) {
    if (a == "--with-core") withCore = true;
    if (a.startsWith("--core=")) corePath = a.split("=").skip(1).join("=");
  }
  if (!withCore) return;

  report("核心验证", "模式 --with-core：自动拉起内置核心", true);
  final before = await lmsPlayerCount(target);
  report("播放器", "启动前 count=$before", before >= 0);

  final runner = CoreRunner(
    lmsHost: target.host,
    lmsPort: target.port,
    slimPort: target.slimPort,
    playerName: "Sonora-Probe",
    onLog: (line) => print("      $line"),
  );

  try {
    final p = await runner.start(bundledPath: corePath);
    report("核心", "已自动拉起 pid=${p.pid}", true);

    final online = await waitForOnlinePlayers(
      target,
      timeout: const Duration(seconds: 15),
    );
    final count = await lmsPlayerCount(target);
    report("播放器", "自动拉起后 count=$count / 在线=${online.length}", online.isNotEmpty);
    report(
      "verdict",
      online.isNotEmpty
          ? "server reachable; playback ready"
          : "core started but no player registered",
      online.isNotEmpty,
    );
  } catch (e) {
    report("核心", "启动失败 ${e.toString().split('\n').first}", false);
  } finally {
    await runner.stop();
  }
}

Future<void> checkNavidrome(List<String> args) async {
  var credPath = "/Users/song/navidrome_creds.json";
  var host = "192.168.199.2:4533";
  for (final a in args) {
    if (a.startsWith("--creds=")) credPath = a.split("=").skip(1).join("=");
    if (a.startsWith("--nav-host=")) host = a.split("=").skip(1).join("=");
  }
  final c = readCreds(credPath);
  if (!c.containsKey("user") || !c.containsKey("password")) {
    report("Navidrome", "缺少凭证文件 $credPath", false);
    return;
  }
  try {
    final auth = SubsonicAuth(
      user: c["user"]!,
      password: c["password"]!,
      salt: "sonora-probe",
    );
    final q = Uri(queryParameters: auth.query()).query;
    final ping = await getText("http://$host/rest/ping?$q");
    final info = parsePing(parseJson(ping));
    report("Navidrome", "版本 ${info.version} / openSubsonic / ping=${info.statusText}",
        info.reachable);

    final atom = await getText(
        "https://github.com/navidrome/navidrome/releases.atom");
    final latest = parseAtomLatestVersion(atom);
    final up = latest != null && compareVersions(latest, info.version.split(" ").first) > 0;
    report("Navidrome升级", "当前 ${info.version.split(' ').first} → 最新 ${latest ?? '未知'}"
        " ${up ? '可升级' : '已最新'}", latest != null);

    final withLibs = args.contains("--with-libs");
    final albums = await getText("http://$host/rest/getAlbumList2?${Uri(queryParameters: auth.query({
          "type": "newest", "size": withLibs ? "500" : "3",
        })).query}");
    final list = parseAlbumList(parseJson(albums), "http://$host");
    report("Navidrome曲库", "专辑 ${list.length} 张，首张 ${list.isEmpty ? '-' : list.first.name}",
        list.isNotEmpty);

    if (withLibs) {
      var totalSongs = 0;
      for (final album in list) {
        final detailQuery = Uri(queryParameters: auth.query({"id": album.id})).query;
        final detailRaw = await getText("http://$host/rest/getAlbum?$detailQuery");
        final songs = parseAlbum(parseJson(detailRaw));
        totalSongs += songs.length;
        report(
          "专辑详情",
          "${album.name} / ${album.artist.isEmpty ? '未知艺人' : album.artist}"
          " — ${songs.length} 首 (id=${album.id})",
          songs.isNotEmpty,
        );
        for (var i = 0; i < songs.length; i++) {
          final song = songs[i];
          print("    ${i + 1}. ${song.title}"
              " — ${song.artist.isEmpty ? album.artist : song.artist}"
              " [${formatDuration(song.duration)}] id=${song.id}");
        }
      }
      report("曲库汇总", "共 ${list.length} 张专辑 / $totalSongs 首歌曲", totalSongs > 0);
    }
  } catch (e) {
    report("Navidrome", "失败 ${e.toString().split('\n').first}", false);
  }
}

Future<void> main(List<String> args) async {
  print("=== Sonora v2 probe ===");
  final lms = lmsTargetFromArgs(args);
  await checkAppBody();
  await checkCoreSource();
  await checkLms(lms);
  await checkCoreRuntime(args, lms);
  await checkNavidrome(args);
  closeHttpClient();
}
