import "dart:io";

import "package:crypto/crypto.dart";

import "services.dart";

/// A concrete downloadable release advertised by a source.
class ReleaseAsset {
  const ReleaseAsset({
    required this.version,
    this.revision,
    required this.url,
    this.filename = "",
    this.md5 = "",
    this.size = -1,
    this.notes = const <String>[],
  });

  final String version;
  final int? revision;
  final String url;
  final String filename;

  /// MD5 of the downloaded archive, as advertised by the source (integrity only).
  final String md5;

  /// Advertised byte size of the downloaded archive, -1 when unknown.
  final int size;
  final List<String> notes;

  String get displayVersion =>
      revision == null ? version : "$version.r$revision";
}

/// Result of a download + verification pipeline. Never installs anything.
class VerifyResult {
  VerifyResult({
    required this.ok,
    required this.stage,
    this.path = "",
    this.sha256 = "",
    this.detail = "",
    this.binaryPath = "",
  });

  final bool ok;

  /// Last completed stage: downloaded / hash / structure / verified / failed.
  final String stage;
  final String path;
  final String sha256;
  final String detail;

  /// 可选：verifyCoreArchive(extractBinary: true) 时暂存的核心二进制路径。
  final String binaryPath;
}

// ---------------------------------------------------------------------------
// Pure parsers (unit-testable, no I/O)
// ---------------------------------------------------------------------------

/// Latest version tag from a GitHub releases atom feed.
String? parseReleaseVersion(String xml) {
  final entryRe = RegExp(r"<entry>.*?</entry>", dotAll: true);
  for (final m in entryRe.allMatches(xml)) {
    final title = RegExp(
      r"<title>([^<]+)</title>",
    ).firstMatch(m.group(0) ?? "")?.group(1);
    if (title != null && RegExp(r"^v?\d+\.\d+").hasMatch(title.trim())) {
      return title.trim();
    }
  }
  // Fallback: any version-looking <title> outside entries (older feeds).
  for (final m in RegExp(r"<title>([^<]+)</title>").allMatches(xml)) {
    final t = (m.group(1) ?? "").trim();
    if (RegExp(r"^v?\d+\.\d+").hasMatch(t)) return t;
  }
  return null;
}

/// Release note lines from the newest atom entry (falls back to all entries).
List<String> parseReleaseNotes(String xml, {int max = 8}) {
  final entry = RegExp(
    r"<entry>.*?</entry>",
    dotAll: true,
  ).firstMatch(xml)?.group(0);
  final scope = entry ?? xml;
  final out = <String>[];
  for (final m in RegExp(
    r"<content[^>]*>(.*?)</content>",
    dotAll: true,
  ).allMatches(scope)) {
    var text = m.group(1) ?? "";
    // Decode entities first: atom feeds often escape tags as &lt;br/&gt;.
    text = text
        .replaceAll("&lt;", "<")
        .replaceAll("&gt;", ">")
        .replaceAll("&amp;", "&");
    // Then treat HTML line breaks as newlines so notes render as separate lines.
    text = text.replaceAll(
      RegExp(r"<br\s*/?>|</p>|</li>", caseSensitive: false),
      "\n",
    );
    text = text.replaceAll(RegExp(r"<[^>]+>"), " ");
    for (final line in text.split(RegExp(r"\r?\n"))) {
      final clean = line.trim();
      if (clean.isNotEmpty) out.add(clean);
      if (out.length >= max) return out;
    }
  }
  return out;
}

/// Parses SourceForge RSS into the newest squeezelite dmg release.
/// The feed advertises md5 + filesize on each item, so no manual hash needed.
ReleaseAsset? parseCoreRss(String xml) {
  final items = RegExp(r"<item>(.*?)</item>", dotAll: true).allMatches(xml);
  for (final m in items) {
    final item = m.group(1) ?? "";
    final rawTitle = RegExp(
      r"<title><!\[CDATA\[(.*?)\]\]></title>",
      dotAll: true,
    ).firstMatch(item)?.group(1);
    final title =
        rawTitle ??
        RegExp(r"<title>([^<]+)</title>").firstMatch(item)?.group(1) ??
        "";
    if (!title.toLowerCase().endsWith(".dmg")) continue;

    final link =
        RegExp(r"<link>([^<]+)</link>").firstMatch(item)?.group(1)?.trim() ??
        "";
    final md5 =
        RegExp(
          r'<media:hash[^>]*algo="md5"[^>]*>([^<]+)</media:hash>',
        ).firstMatch(item)?.group(1)?.trim() ??
        "";
    final sizeRaw = RegExp(r'filesize="(\d+)"').firstMatch(item)?.group(1);
    final size = sizeRaw == null ? -1 : int.tryParse(sizeRaw) ?? -1;
    final parsed = _parseCoreVersionFromName(title);
    if (parsed == null || link.isEmpty) continue;
    return ReleaseAsset(
      version: parsed.version,
      revision: parsed.revision,
      url: link,
      filename: title.split("/").last,
      md5: md5,
      size: size,
    );
  }
  return null;
}

class _VersionRevision {
  const _VersionRevision(this.version, this.revision);
  final String version;
  final int revision;
}

/// Parses version and revision from a name like
/// `Squeezelite-M1-2.0.0r1610.dmg` into 2.0.0 / 1610.
_VersionRevision? _parseCoreVersionFromName(String name) {
  final m = RegExp(r"(\d+\.\d+(?:\.\d+)?)[r.\-](\d+)").firstMatch(name);
  if (m == null) return null;
  return _VersionRevision(m.group(1)!, int.parse(m.group(2)!));
}

/// Parses a `SHA256SUMS` file into {filename: hash} (case-insensitive hash).
Map<String, String> parseSha256Sums(String text) {
  final out = <String, String>{};
  for (final line in text.split(RegExp(r"\r?\n"))) {
    final parts = line.trim().split(RegExp(r"\s+"));
    if (parts.length >= 2 && RegExp(r"^[0-9a-fA-F]{64}$").hasMatch(parts[0])) {
      out[parts.sublist(1).join(" ")] = parts[0].toLowerCase();
    }
  }
  return out;
}

/// True when advertised hash/size match the observed values.
bool hashMatches({
  required String actualHash,
  required String expectedHash,
  int actualSize = -1,
  int expectedSize = -1,
}) {
  if (expectedHash.isEmpty) return false;
  if (actualHash.toLowerCase() != expectedHash.toLowerCase()) return false;
  if (expectedSize >= 0 && actualSize >= 0 && actualSize != expectedSize) {
    return false;
  }
  return true;
}

// ---------------------------------------------------------------------------
// Side-effecting helpers
// ---------------------------------------------------------------------------

/// SHA256 of a file, streamed (safe for large archives).
Future<String> sha256File(String path) async {
  final digest = await sha256.bind(File(path).openRead()).first;
  return digest.toString();
}

/// MD5 of a file, streamed.
Future<String> md5File(String path) async {
  final digest = await md5.bind(File(path).openRead()).first;
  return digest.toString();
}

/// Downloads [url] to [dest] (parent created as needed), returns the path.
Future<String> downloadToFile(
  String url,
  String dest, {
  void Function(String line)? onLog,
  Duration timeout = const Duration(minutes: 5),
}) async {
  final req = await httpClient.getUrl(Uri.parse(url)).timeout(timeout);
  final resp = await req.close().timeout(timeout);
  if (resp.statusCode != 200 && resp.statusCode != 206) {
    await resp.drain();
    throw Exception("HTTP ${resp.statusCode}");
  }
  await File(dest).parent.create(recursive: true);
  final sink = File(dest).openWrite();
  try {
    await resp.pipe(sink);
  } finally {
    await sink.close();
  }
  onLog?.call("下载完成 ${File(dest).lengthSync()} bytes → $dest");
  return dest;
}

String updateCacheDir(String track, String version) {
  final home = Platform.environment["HOME"] ?? "";
  return "$home/Library/Caches/Sonora/updates/$track/$version";
}

/// Verifies a downloaded app zip against its SHA256SUMS sidecar.
/// [zipUrl] and optional [sumsUrl] are separated so a release can host them
/// anywhere. When [sumsUrl] is null, the hash must be passed as [expectedSha].
Future<VerifyResult> verifyAppArchive({
  required String zipUrl,
  String? sumsUrl,
  String? expectedSha,
  String? cacheDir,
  void Function(String line)? onLog,
}) async {
  final dir = cacheDir ?? updateCacheDir("app", "incoming");
  try {
    final zipPath = await downloadToFile(
      zipUrl,
      "$dir/download/Sonora.zip",
      onLog: onLog,
    );
    String sha;
    if (sumsUrl != null) {
      final sumsRaw = await getText(sumsUrl);
      final sums = parseSha256Sums(sumsRaw);
      final name = sums.keys.firstWhere(
        (k) => k.toLowerCase().endsWith(".zip"),
        orElse: () => "",
      );
      if (name.isEmpty) {
        return VerifyResult(
          ok: false,
          stage: "hash",
          path: zipPath,
          detail: "SHA256SUMS 中没有 zip 条目",
        );
      }
      sha = await sha256File(zipPath);
      if (!hashMatches(actualHash: sha, expectedHash: sums[name]!)) {
        return VerifyResult(
          ok: false,
          stage: "hash",
          path: zipPath,
          sha256: sha,
          detail: "SHA256 不符：期望 ${sums[name]}，实际 $sha",
        );
      }
      onLog?.call("SHA256 校验通过 $sha");
    } else if (expectedSha != null && expectedSha.isNotEmpty) {
      sha = await sha256File(zipPath);
      if (!hashMatches(actualHash: sha, expectedHash: expectedSha)) {
        return VerifyResult(
          ok: false,
          stage: "hash",
          path: zipPath,
          sha256: sha,
          detail: "SHA256 不符：期望 $expectedSha，实际 $sha",
        );
      }
      onLog?.call("SHA256 校验通过 $sha");
    } else {
      return VerifyResult(
        ok: false,
        stage: "hash",
        path: zipPath,
        detail: "未提供 SHA256SUMS 或期望 hash，拒绝安装",
      );
    }

    // Structural sanity: a Sonora.app bundle with an Info.plist must be inside.
    final listed = await Process.run("unzip", ["-l", zipPath]);
    final listing = listed.stdout.toString();
    if (listed.exitCode != 0 ||
        !RegExp(r"Sonora\.app/Contents/Info\.plist").hasMatch(listing)) {
      return VerifyResult(
        ok: false,
        stage: "structure",
        path: zipPath,
        sha256: sha,
        detail: "zip 内缺少 Sonora.app/Contents/Info.plist",
      );
    }
    onLog?.call("结构校验通过：含 Sonora.app/Contents/Info.plist");
    return VerifyResult(
      ok: true,
      stage: "verified",
      path: zipPath,
      sha256: sha,
      detail: "主体包下载并校验通过（未安装）",
    );
  } catch (e) {
    return VerifyResult(
      ok: false,
      stage: "failed",
      detail: "失败 ${e.toString().split("\n").first}",
    );
  }
}

/// Verifies a downloaded squeezelite dmg: advertised MD5 + filesize, then
/// mounts it and hashes the extracted binary. Never installs the binary.
Future<VerifyResult> verifyCoreArchive({
  required ReleaseAsset release,
  String? cacheDir,
  bool extractBinary = false,
  void Function(String line)? onLog,
}) async {
  final dir =
      cacheDir ??
      updateCacheDir(
        "core",
        release.displayVersion.replaceAll(RegExp(r"\s"), ""),
      );
  final dmgPath =
      "$dir/download/${release.filename.isEmpty ? 'core.dmg' : release.filename}";
  var mountPoint = "";
  try {
    await downloadToFile(release.url, dmgPath, onLog: onLog);
    final md5 = await md5File(dmgPath);
    final size = File(dmgPath).lengthSync();
    onLog?.call("dmg md5=$md5 size=$size");
    if (!hashMatches(
      actualHash: md5,
      expectedHash: release.md5,
      actualSize: size,
      expectedSize: release.size,
    )) {
      return VerifyResult(
        ok: false,
        stage: "hash",
        path: dmgPath,
        detail:
            "MD5/size 不符：期望 ${release.md5}/${release.size}B，实际 $md5/${size}B",
      );
    }
    onLog?.call("MD5 + filesize 校验通过");

    // Mount the dmg read-only, hash the binary, then always detach.
    mountPoint = "$dir/mnt";
    await Directory(mountPoint).create(recursive: true);
    final attach = await Process.run("hdiutil", [
      "attach",
      dmgPath,
      "-mountpoint",
      mountPoint,
      "-nobrowse",
      "-readonly",
      "-quiet",
    ]);
    if (attach.exitCode != 0) {
      return VerifyResult(
        ok: false,
        stage: "structure",
        path: dmgPath,
        detail: "挂载失败：${attach.stderr.toString().trim()}",
      );
    }
    final binary = "$mountPoint/Squeezelite.app/Contents/MacOS/Squeezelite";
    if (!File(binary).existsSync()) {
      return VerifyResult(
        ok: false,
        stage: "structure",
        path: dmgPath,
        detail: "dmg 内缺少 Squeezelite.app/Contents/MacOS/Squeezelite",
      );
    }
    final binarySha = await sha256File(binary);
    onLog?.call("核心二进制 sha256=$binarySha");
    var extracted = "";
    if (extractBinary) {
      final stamp = DateTime.now().millisecondsSinceEpoch;
      extracted = "$dir/stage/$stamp/squeezelite";
      await File(extracted).parent.create(recursive: true);
      await File(binary).copy(extracted);
      await Process.run("chmod", ["755", extracted]);
      onLog?.call("核心已暂存到 $extracted");
    }
    return VerifyResult(
      ok: true,
      stage: "verified",
      path: dmgPath,
      sha256: binarySha,
      binaryPath: extracted,
      detail: extractBinary ? "核心包校验通过并已暂存（未安装）" : "核心包下载并校验通过（未安装）",
    );
  } catch (e) {
    return VerifyResult(
      ok: false,
      stage: "failed",
      detail: "失败 ${e.toString().split("\n").first}",
    );
  } finally {
    if (mountPoint.isNotEmpty) {
      await Process.run("hdiutil", ["detach", mountPoint, "-quiet"]);
    }
  }
}
