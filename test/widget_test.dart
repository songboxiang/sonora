import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:sonora/main.dart";

void main() {
  testWidgets("shows connection form initially", (WidgetTester tester) async {
    await tester.pumpWidget(const SonoraApp());
    expect(find.text("连接 Lyrion Media Server"), findsOneWidget);
    expect(find.text("连接"), findsOneWidget);
    expect(find.byType(TextField), findsNWidgets(2));
  });
}
