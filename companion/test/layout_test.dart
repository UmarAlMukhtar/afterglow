import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:afterglow_companion/home.dart';
import 'package:afterglow_companion/model.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(native, (_) async => true);
  });
  for (final size in [
    const Size(375, 812),
    const Size(812, 375),
    const Size(768, 1024),
    const Size(1280, 720),
    const Size(1440, 900),
  ]) {
    testWidgets('demo, all styles and fullscreen fit $size', (tester) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final model = AfterglowModel(android: true)..permission = true;
      model.setDemo(true);
      await tester.pumpWidget(AfterglowApp(model: model));
      for (final style in styles.keys) {
        model.change(() => model.style = style);
        await tester.pump(const Duration(milliseconds: 100));
        expect(tester.takeException(), isNull);
      }
      await tester.ensureVisible(find.text('Enter fullscreen'));
      await tester.tap(find.text('Enter fullscreen'));
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.byTooltip('Return to controls (Escape)'), findsOneWidget);
      await tester.tap(find.byTooltip('Return to controls (Escape)'));
      await tester.pump();
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
      model.dispose();
    });
  }
  testWidgets('large system type and reduced motion retain usable controls', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(375, 812);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final model = AfterglowModel(android: true)..reduceMotion = true;
    model.setDemo(true);
    await tester.pumpWidget(
      MaterialApp(
        home: MediaQuery(
          data: const MediaQueryData(
            size: Size(375, 812),
            textScaler: TextScaler.linear(2),
            disableAnimations: true,
          ),
          child: Home(model: model),
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 100));
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
    model.dispose();
  });
  test('demo pause freezes its position and resume keeps its place', () async {
    final model = AfterglowModel(android: false)..setDemo(true);
    await model.command('playPause');
    final position = model.position;
    await Future<void>.delayed(const Duration(milliseconds: 30));
    expect(model.position, position);
    await model.command('playPause');
    expect(model.playing, true);
    model.dispose();
  });
}
