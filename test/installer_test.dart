import "dart:convert";
import "dart:io";

import "package:flutter_test/flutter_test.dart";
import "package:sonora/core/installer.dart";

void main() {
  group("备份索引", () {
    test("ID 清洗版本号并带时间戳", () {
      final id = BackupRecord.makeId(
        "v2.1.0+1",
        DateTime.utc(2026, 11, 28, 2, 30, 15),
      );
      expect(id, startsWith("v2.1.0_1-20261128T023015"));
    });
    test("记录 JSON 往返保留轨道与备份路径", () {
      final rec = BackupRecord(
        id: "2.0.0.r1610-20261128T020000",
        track: UpdateTrack.core,
        version: "2.0.0.r1610",
        createdAt: "2026-11-28T02:00:00.000Z",
        targetPath: "/tmp/core/squeezelite",
        backupPath: "/tmp/backups/core/squeezelite",
        sha256: "abc",
        notes: "安装 2.0.0.r1610",
      );
      final decoded = BackupRecord.fromJson(
        jsonDecode(jsonEncode(rec.toJson())) as Map<String, dynamic>,
      );
      expect(decoded.track, UpdateTrack.core);
      expect(decoded.id, rec.id);
      expect(decoded.backupPath, rec.backupPath);
      expect(decoded.sha256, "abc");
    });
  });

  group("版本与健康检查解析", () {
    test("从 Info.plist 读取短版本", () {
      final plist =
          "<?xml version=\"1.0\"?><plist><dict>"
          "<key>CFBundleShortVersionString</key><string>2.1.0</string>"
          "</dict></plist>";
      expect(parseInfoPlistVersion(plist), "2.1.0");
      expect(parseInfoPlistVersion("<plist><dict/></plist>"), isNull);
    });
    test("解析 squeezelite -t 的版本与 revision", () {
      final parsed = parseSqueezeliteVersion(
        "Squeezelite 2.0.0-1610, Copyright 2012-2026",
      )!;
      expect(parsed["version"], "2.0.0");
      expect(parsed["revision"], 1610);
      expect(parseSqueezeliteVersion("no version here"), isNull);
    });
    test("版本比较忽略前导 v", () {
      expect(normalizeUpdateVersion("v2.1.0"), "2.1.0");
      expect(normalizeUpdateVersion(" 2.1.0 "), "2.1.0");
    });
  });

  group("路径与备份列表", () {
    test("备份与 manifest 路径固定在用户目录", () {
      expect(
        backupRootFor(UpdateTrack.app, home: "/tmp/fakehome"),
        "/tmp/fakehome/Library/Application Support/Sonora/Backups/app",
      );
      expect(
        userCoreManifestPath(home: "/tmp/fakehome"),
        "/tmp/fakehome/Library/Application Support/Sonora/Core/core-manifest.json",
      );
    });
    test("按创建时间倒序列出有效备份，忽略损坏索引", () {
      final home = Directory.systemTemp.createTempSync("sonora-install-test-");
      addTearDown(() => home.deleteSync(recursive: true));
      final root = Directory(backupRootFor(UpdateTrack.core, home: home.path));
      final older = BackupRecord(
        id: "old",
        track: UpdateTrack.core,
        version: "2.0.0.r1595",
        createdAt: "2026-11-27T01:00:00.000Z",
        targetPath: "/tmp/core",
        backupPath: "/tmp/old",
      );
      final newer = BackupRecord(
        id: "new",
        track: UpdateTrack.core,
        version: "2.0.0.r1610",
        createdAt: "2026-11-28T01:00:00.000Z",
        targetPath: "/tmp/core",
        backupPath: "/tmp/new",
      );
      for (final rec in <BackupRecord>[older, newer]) {
        final d = Directory("${root.path}/${rec.id}")
          ..createSync(recursive: true);
        File(
          "${d.path}/backup.json",
        ).writeAsStringSync(jsonEncode(rec.toJson()));
      }
      File(
        "${root.path}/broken/backup.json",
      ).parent.createSync(recursive: true);
      File("${root.path}/broken/backup.json").writeAsStringSync("not json");

      final installer = UpdateInstaller(home: home.path);
      final list = installer.listBackups(UpdateTrack.core);
      expect(list.length, 2);
      expect(list.first.id, "new");
      expect(list.last.version, "2.0.0.r1595");
    });
  });
}
