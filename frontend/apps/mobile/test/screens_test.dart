import 'package:colyv_app/main.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

Future<void> settle(WidgetTester tester) async {
  await tester.pump(); // starts the animation
  await tester.pump(const Duration(seconds: 2)); // lets it finish
}

void main() {
  setUpAll(() async {
    // Tests draw text in a square placeholder font unless the real one is loaded; load Geist so sizes are true.
    final loader = FontLoader('Geist');
    for (final f in ['Light', 'Regular', 'Medium', 'SemiBold', 'Bold']) {
      loader.addFont(rootBundle.load('assets/fonts/Geist-$f.ttf'));
    }
    await loader.load();
  });

  testWidgets('preview shell shows the three screens and the period switch changes the numbers', (tester) async {
    tester.view.physicalSize = const Size(1000, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(const ColyvApp());
    await settle(tester);
    expect(find.text('Display name'), findsOneWidget);
    expect(find.text('48.2K'), findsOneWidget);

    await tester.tap(find.text('7 days'));
    await settle(tester);
    expect(find.text('11.4K'), findsOneWidget);

    await tester.tap(find.text('Today').first);
    await settle(tester);
    expect(find.text('Confirm you were paid'), findsOneWidget);

    await tester.tap(find.text('Brand card'));
    await settle(tester);
    expect(find.text('9 of 10'), findsOneWidget);
  });
}
