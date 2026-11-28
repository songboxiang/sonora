// UI 层冒烟测试：验证服务器管理页、纯曲库页、播放效果面板与升级页真实渲染。
import "package:flutter_test/flutter_test.dart";
import "package:sonora/main.dart";

void main() {
  Future<void> pumpApp(WidgetTester tester) async {
    await tester.pumpWidget(const SonoraApp());
    await tester.pumpAndSettle(const Duration(seconds: 2));
  }

  // initState schedules a device scan with an 8s timeout timer; advance the
  // fake clock past it so no timer is left pending at test teardown.
  Future<void> settle(WidgetTester tester) async {
    await tester.pump(const Duration(seconds: 9));
    await tester.pumpAndSettle();
  }

  testWidgets("四个页签与音乐服务器列表渲染", (tester) async {
    await pumpApp(tester);
    expect(find.text("Sonora v2"), findsOneWidget);
    for (final label in ["连接", "播放", "曲库", "升级"]) {
      expect(find.text(label), findsWidgets);
    }
    expect(find.text("音乐服务器"), findsOneWidget);
    expect(find.text("我的 LMS 服务器"), findsOneWidget);
    expect(find.text("我的音乐服务器"), findsWidgets);
    expect(find.text("添加服务器"), findsOneWidget);
    expect(find.text("切换"), findsWidgets);
    expect(find.text("修改"), findsWidgets);
    await settle(tester);
  });

  testWidgets("LMS 服务器下直接展示设备扫描、命名与参数配置", (tester) async {
    await pumpApp(tester);
    // 显式选中 LMS，避免依赖用户上次持久化的轨道。
    await tester.tap(find.text("修改").first);
    await tester.pumpAndSettle();
    expect(find.text("服务器配置"), findsOneWidget);
    expect(find.text("扫描设备"), findsOneWidget);
    expect(find.textContaining("设备显示名称"), findsOneWidget);
    expect(find.text("参数配置"), findsOneWidget);
    expect(find.text("连接并自动拉起核心"), findsOneWidget);
    expect(find.text("停止核心"), findsOneWidget);
    expect(find.text("保存配置"), findsOneWidget);
    await settle(tester);
  });

  testWidgets("曲库页只保留曲库功能与连接状态", (tester) async {
    await pumpApp(tester);
    await tester.tap(find.text("曲库").first);
    await tester.pumpAndSettle();
    expect(find.text("曲库"), findsWidgets);
    expect(find.textContaining("连接状态"), findsOneWidget);
    expect(find.text("搜索歌曲 / 专辑"), findsOneWidget);
    expect(find.text("加载专辑"), findsOneWidget);
    expect(find.text("曲库轨道"), findsNothing);
    await settle(tester);
  });

  testWidgets("播放页渲染当前播放效果面板", (tester) async {
    await pumpApp(tester);
    await tester.tap(find.text("播放").first);
    await tester.pumpAndSettle();
    expect(find.text("当前播放效果"), findsOneWidget);
    for (final label in ["输出模式", "音质", "无损", "输出"]) {
      expect(find.textContaining("$label："), findsWidgets);
    }
    await settle(tester);
  });

  testWidgets("升级页渲染主体与核心下载、安装按钮", (tester) async {
    await pumpApp(tester);
    await tester.tap(find.text("升级").first);
    await tester.pumpAndSettle();
    for (final label in ["下载并校验主体", "安装替换主体", "下载并校验核心", "安装替换核心"]) {
      expect(find.text(label), findsOneWidget);
    }
    await settle(tester);
  });
}
