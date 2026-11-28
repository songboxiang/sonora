// UI 层冒烟测试：主页只保留曲库/播放，服务器与升级收进设置页。
import "dart:io";

import "package:flutter_test/flutter_test.dart";
import "package:sonora/core/settings.dart";
import "package:sonora/main.dart";

void main() {
  late Directory testHome;

  setUp(() {
    sonoraAutoRestore = false;
    testHome = Directory.systemTemp.createTempSync("sonora-ui-test");
    sonoraSettingsPathOverride = "${testHome.path}/settings.json";
  });

  tearDown(() {
    sonoraSettingsPathOverride = null;
    if (testHome.existsSync()) testHome.deleteSync(recursive: true);
  });

  Future<void> pumpApp(WidgetTester tester) async {
    await tester.pumpWidget(const SonoraApp());
    await tester.pumpAndSettle(const Duration(seconds: 2));
  }

  Future<void> settle(WidgetTester tester) async {
    await tester.pump(const Duration(seconds: 9));
    await tester.pumpAndSettle();
  }

  testWidgets("主页只有曲库和播放，设置入口在右上角", (tester) async {
    await pumpApp(tester);
    expect(find.text("Sonora v2"), findsOneWidget);
    expect(find.text("曲库"), findsWidgets);
    expect(find.text("播放"), findsWidgets);
    expect(find.text("连接"), findsNothing);
    expect(find.text("升级"), findsNothing);
    expect(find.byTooltip("设置（服务器与升级）"), findsOneWidget);
    expect(find.byTooltip("折叠为小封面"), findsOneWidget);
    await settle(tester);
  });

  testWidgets("设置页包含服务器配置与升级", (tester) async {
    await pumpApp(tester);
    await tester.tap(find.byTooltip("设置（服务器与升级）"));
    await tester.pumpAndSettle();
    expect(find.text("设置"), findsWidgets);
    expect(find.text("服务器"), findsWidgets);
    expect(find.text("升级"), findsWidgets);
    expect(find.text("音乐服务器"), findsOneWidget);
    expect(find.text("我的 LMS 服务器"), findsWidgets);
    expect(find.text("我的音乐服务器"), findsWidgets);
    expect(find.text("添加服务器"), findsOneWidget);

    await tester.tap(find.text("修改").first);
    await tester.pumpAndSettle();
    expect(find.text("服务器配置"), findsOneWidget);
    expect(find.text("扫描设备"), findsOneWidget);
    expect(find.textContaining("设备显示名称"), findsOneWidget);
    expect(find.text("参数配置"), findsOneWidget);
    expect(find.text("连接并自动拉起核心"), findsOneWidget);
    expect(find.text("保存配置"), findsOneWidget);

    await tester.tap(find.text("升级").last);
    await tester.pumpAndSettle();
    for (final label in [
      "下载并校验主体",
      "安装替换主体",
      "下载并校验核心",
      "安装替换核心",
    ]) {
      expect(find.text(label), findsOneWidget);
    }
    await settle(tester);
  });

  testWidgets("曲库页只保留曲库功能与连接状态", (tester) async {
    await pumpApp(tester);
    expect(find.textContaining("连接状态"), findsOneWidget);
    expect(find.text("加载专辑"), findsOneWidget);
    expect(find.byTooltip("大图标"), findsOneWidget);
    expect(find.byTooltip("列表"), findsOneWidget);
    expect(find.text("排序"), findsOneWidget);
    expect(find.text("曲库轨道"), findsNothing);
    expect(
      find.text("搜索歌曲 / 专辑").evaluate().isNotEmpty ||
          find.textContaining("LMS 专辑").evaluate().isNotEmpty,
      isTrue,
    );
    await settle(tester);
  });

  testWidgets("播放页渲染音质、歌词、资料与模式开关", (tester) async {
    await pumpApp(tester);
    await tester.tap(find.text("播放").first);
    await tester.pumpAndSettle();
    expect(find.text("当前播放效果"), findsOneWidget);
    for (final label in ["输出模式", "音质", "无损", "输出"]) {
      expect(find.textContaining("$label："), findsWidgets);
    }
    expect(find.text("歌词"), findsOneWidget);
    expect(find.text("曲目资料"), findsOneWidget);
    for (final tip in ["顺序播放", "列表循环", "单曲循环", "随机播放"]) {
      expect(find.byTooltip(tip), findsWidgets);
    }
    expect(find.byTooltip("大屏模式"), findsOneWidget);
    expect(find.byTooltip("折叠为小封面"), findsNothing);
    await settle(tester);
  });

  testWidgets("迷你播放器可折叠为小封面", (tester) async {
    await pumpApp(tester);
    await tester.tap(find.byTooltip("折叠为小封面"));
    await tester.pumpAndSettle();
    expect(find.byTooltip("折叠为小封面"), findsNothing);
    await settle(tester);
  });
}
