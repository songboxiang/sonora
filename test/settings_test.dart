import "dart:convert";
import "dart:io";

import "package:flutter_test/flutter_test.dart";
import "package:sonora/core/settings.dart";

void main() {
  group("输出设备扫描", () {
    test("解析 squeezelite -l 的编号与名称", () {
      final text =
          "Output devices:\n"
          "  0 - Apple Virtual Sound Device [Core Audio]\n"
          "  1 - USB DAC [Core Audio]\n";
      final devices = parseOutputDevices(text);
      expect(devices.length, 2);
      expect(devices.first.id, "0");
      expect(devices.last.name, contains("USB DAC"));
    });
    test("忽略非设备行", () {
      expect(parseOutputDevices("no devices here"), isEmpty);
    });
  });

  group("配置持久化", () {
    test("默认配置使用 LMS 轨道和默认输出", () {
      final s = AppSettings();
      expect(s.activeLibrary, "lms");
      expect(s.coreParams.device, "");
      expect(s.lastDevice, "");
    });

    test("JSON 往返保留账号、轨道与上次输出设备", () {
      final s = AppSettings()
        ..navUser = "demo"
        ..navPassword = "secret"
        ..activeLibrary = "navidrome"
        ..coreParams = paramsForProfile("dsd").copyWith(device: "1");
      final decoded = AppSettings.fromJson(
        jsonDecode(jsonEncode(s.toJson())) as Map<String, dynamic>,
      );
      expect(decoded.navUser, "demo");
      expect(decoded.navPassword, "secret");
      expect(decoded.activeLibrary, "navidrome");
      expect(decoded.lastDevice, "1");
      expect(decoded.coreParams.profile, "dsd");
      expect(decoded.coreParams.dop, isTrue);
    });

    test("旧版单服务器配置迁移为默认服务器", () {
      final decoded = AppSettings.fromJson(<String, dynamic>{
        "navHost": "10.0.0.8:4533",
        "navUser": "legacy",
        "navPassword": "secret",
      });
      expect(decoded.servers.length, 1);
      expect(decoded.servers.first.name, "我的音乐服务器");
      expect(decoded.servers.first.host, "10.0.0.8:4533");
      expect(decoded.activeServerId, decoded.servers.first.id);
    });

    test("多服务器配置往返保留名称与当前选择", () {
      final s = AppSettings();
      s.servers = <OpenSubsonicServer>[
        const OpenSubsonicServer(
          id: "nas",
          name: "家里 NAS",
          host: "10.0.0.2:4533",
          user: "u1",
          password: "p1",
        ),
        const OpenSubsonicServer(
          id: "office",
          name: "办公室",
          host: "10.0.0.3:4533",
          user: "u2",
          password: "p2",
        ),
      ];
      s.activeServerId = "office";
      final decoded = AppSettings.fromJson(
        jsonDecode(jsonEncode(s.toJson())) as Map<String, dynamic>,
      );
      expect(decoded.servers.length, 2);
      expect(decoded.servers.last.name, "办公室");
      expect(decoded.activeServer?.name, "办公室");
      expect(decoded.navHost, "10.0.0.3:4533");
    });

    test("SettingsStore 写入后可读回，损坏文件回退默认", () async {
      final dir = Directory.systemTemp.createTempSync("sonora-settings-test-");
      addTearDown(() => dir.deleteSync(recursive: true));
      final path = "${dir.path}/settings.json";
      final store = SettingsStore(path: path);
      final s = AppSettings()..lmsHost = "10.0.0.2";
      await store.save(s);
      expect(SettingsStore(path: path).load().lmsHost, "10.0.0.2");
      File(path).writeAsStringSync("not json");
      expect(SettingsStore(path: path).load().lmsHost, "192.168.199.2");
    });
  });

  group("音质预设", () {
    test("各预设的关键开关不同", () {
      expect(paramsForProfile("bitperfect").allowResample, isFalse);
      expect(paramsForProfile("bitperfect").dop, isFalse);
      expect(paramsForProfile("best").dop, isTrue);
      expect(paramsForProfile("dsd").dop, isTrue);
      expect(paramsForProfile("dsd").extraArgs, contains("dsd"));
      expect(paramsForProfile("custom").profile, "custom");
    });

    test("每个参数都有帮助释意", () {
      for (final key in <String>[
        "device",
        "deviceName",
        "playerName",
        "latencyMs",
        "allowResample",
        "rates",
        "dop",
        "buffers",
        "modelName",
        "extraArgs",
      ]) {
        expect(coreParamHelp[key]?.isNotEmpty, isTrue, reason: key);
      }
    });
  });
}
