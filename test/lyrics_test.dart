import "package:flutter_test/flutter_test.dart";
import "package:sonora/core/lyrics.dart";

void main() {
  test("LRC meta tags are skipped and stamps become milliseconds", () {
    final lines = parseLrc(
      "[ti:示例]\n[ar:艺人]\n[00:12.50]第一句\n[01:03]第二句",
    );
    expect(lines.length, 2);
    expect(lines.first.timeMs, 12500);
    expect(lines.first.text, "第一句");
    expect(lines.last.timeMs, 63000);
  });

  test("multiple stamps on one line are expanded", () {
    final lines = parseLrc("[00:01.00][01:02.00]副歌");
    expect(lines.length, 2);
    expect(lines.map((l) => l.timeMs), <int>[1000, 62000]);
  });

  test("plain lyrics advance three seconds per line", () {
    final lines = parseLrc("第一行\n第二行\n第三行");
    expect(lines.map((l) => l.timeMs), <int>[0, 3000, 6000]);
    expect(lines.last.text, "第三行");
  });
}
