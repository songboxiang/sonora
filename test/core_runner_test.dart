import "dart:io";

import "package:flutter_test/flutter_test.dart";
import "package:sonora/squeezelite/core_runner.dart";

void main() {
  group("CoreRunner 参数构造", () {
    test("默认参数指向 slimproto 3483 并带播放器名", () {
      expect(
        CoreRunner.buildArgs(lmsHost: "192.168.199.2"),
        equals(["-s", "192.168.199.2:3483", "-n", "Sonora"]),
      );
    });

    test("自定义端口、名称、音频设备", () {
      expect(
        CoreRunner.buildArgs(
          lmsHost: "lms.local",
          slimPort: 9001,
          playerName: "客厅",
          device: "builtin:0",
        ),
        equals([
          "-s", "lms.local:9001",
          "-n", "客厅",
          "-a", "builtin:0",
        ]),
      );
    });

    test("空设备字符串不会生成 -a", () {
      final args = CoreRunner.buildArgs(
        lmsHost: "lms.local",
        device: "",
      );
      expect(args, isNot(contains("-a")));
    });

    test("显式 MAC 会生成 -m，避免 LMS 残留 MAC 冲突", () {
      final args = CoreRunner.buildArgs(
        lmsHost: "lms.local",
        mac: "02:ab:cd:ef:12:34",
      );
      expect(args, containsAll(["-m", "02:ab:cd:ef:12:34"]));
    });

    test("MAC 由种子稳定生成且保留本地管理位", () {
      final a = CoreRunner.macFromSeed("sonora:vm");
      final b = CoreRunner.macFromSeed("sonora:vm");
      expect(a, equals(b));
      expect(a.startsWith("02:"), isTrue);
      expect(a.split(":").length, equals(6));
    });
  });

  group("CoreRunner 路径决策", () {
    test("用户副本固定落在 Application Support", () {
      expect(
        CoreRunner.userCorePath(home: "/tmp/fakehome"),
        equals(
          "/tmp/fakehome/Library/Application Support/Sonora/Core/squeezelite",
        ),
      );
    });

    test("从 macOS app bundle 推导 Resources/Core", () {
      expect(
        CoreRunner.bundledCorePath(
          executable: "/Applications/Sonora.app/Contents/MacOS/sonora",
          workingDirectory: "/tmp",
        ),
        equals("/Applications/Sonora.app/Contents/Resources/Core/squeezelite"),
      );
    });

    test("开发态回退到项目 bin/", () {
      final dir = Directory.systemTemp.createTempSync("sonora_core_probe");
      final bin = Directory("${dir.path}/bin")..createSync(recursive: true);
      File("${bin.path}/squeezelite").writeAsStringSync("stub");
      expect(
        CoreRunner.bundledCorePath(
          executable: "/usr/local/bin/dart",
          workingDirectory: dir.path,
        ),
        equals("${bin.path}/squeezelite"),
      );
      dir.deleteSync(recursive: true);
    });
  });
}
