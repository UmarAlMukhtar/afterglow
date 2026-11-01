import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:afterglow_companion/home.dart';
import 'package:afterglow_companion/model.dart';
import 'package:afterglow_companion/lyrics.dart';

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('native device: demo, styles, import, fullscreen, media and capture', (
    tester,
  ) async {
    final model = AfterglowModel();
    await model.init(startDemo: true);
    await tester.pumpWidget(AfterglowApp(model: model));
    await tester.pump(const Duration(seconds: 2));
    expect(find.text('afterglow'), findsOneWidget);
    for (final style in styles.keys) {
      model.change(() => model.style = style);
      await tester.pump(const Duration(milliseconds: 300));
      expect(tester.takeException(), isNull);
    }
    debugPrint('VERIFY styles done');
    await model.command('playPause');
    final paused = model.position;
    await tester.pump(const Duration(milliseconds: 500));
    expect(model.position, paused);
    debugPrint('VERIFY pause done');
    await model.command('playPause');
    await model.importLyrics(demoLrc, 'fixture.lrc');
    debugPrint('VERIFY import done');
    expect(model.lyrics.quality, 'word');
    model.change(() {
      model.offset = 1.5;
      model.reduceMotion = true;
    });
    await model.stage(true);
    debugPrint('VERIFY fullscreen entered');
    await tester.pump(const Duration(seconds: 1));
    expect(find.byTooltip('Return to controls (Escape)'), findsOneWidget);
    await model.stage(false);
    model.change(() {
      model.offset = 0;
      model.reduceMotion = false;
    });
    if (Platform.isAndroid) {
      debugPrint('VERIFY creating fixture');
      await native.invokeMethod('debugFixture', 'start');
      model.setDemo(false);
      model.preferred = 'com.afterglow.afterglow_companion';
      // Enable notification access in Android's UI while this test waits.
      for (var i = 0; i < 180; i++) {
        await model.poll();
        if (model.permission && model.track.isNotEmpty) break;
        if (i == 0 && !model.permission) {
          await native.invokeMethod('permissions');
        }
        await tester.pump(const Duration(seconds: 1));
      }
      expect(
        model.permission,
        true,
        reason: 'Notification access is required for the native media test.',
      );
      expect(model.title, 'Afterglow test 1');
    } else {
      model.setDemo(false);
      // Run tools/windows_fixture while the desktop integration test executes.
      for (var i = 0; i < 20; i++) {
        await model.poll();
        if (model.title.startsWith('Afterglow test')) break;
        await tester.pump(const Duration(seconds: 1));
      }
      expect(model.title.startsWith('Afterglow test'), true);
    }
    await model.importLyrics(demoLrc, 'fixture.lrc');
    await model.command('playPause');
    await tester.pump(const Duration(seconds: 1));
    await model.poll();
    expect(model.playing, false);
    final stoppedPosition = model.position;
    await tester.pump(const Duration(milliseconds: 700));
    await model.poll();
    expect((model.position - stoppedPosition).abs(), lessThan(.2));
    await model.command('playPause');
    await tester.pump(const Duration(seconds: 1));
    await model.poll();
    expect(model.playing, true);
    await model.command('next');
    await tester.pump(const Duration(seconds: 1));
    await model.poll();
    expect(model.title, 'Afterglow test 2');
    await model.command('previous');
    await tester.pump(const Duration(seconds: 1));
    await model.poll();
    expect(model.title, 'Afterglow test 1');
    await model.importLyrics(demoLrc, 'fixture.lrc');
    // Android shows system dialogs. The test deliberately waits for actual consent.
    final capture = model.capture(true);
    for (var i = 0; i < 120; i++) {
      await tester.pump(const Duration(seconds: 1));
      final raw = await native.invokeMethod<Map>('snapshot', {
        'preferred': model.preferred,
      });
      if (raw?['capturing'] == true) break;
    }
    await capture;
    await model.poll();
    expect(model.capturing, true);
    var peak = 0.0;
    for (var i = 0; i < 15; i++) {
      await tester.pump(const Duration(milliseconds: 400));
      await model.poll();
      if (model.level > peak) peak = model.level;
    }
    expect(
      peak,
      greaterThan(.001),
      reason: 'Actual output audio must produce nonzero reaction.',
    );
    await model.showOverlay(true);
    // Allow the user to enable Appear on top, then retry when permission returns.
    if (Platform.isAndroid && !model.overlay) {
      for (var i = 0; i < 120; i++) {
        await tester.pump(const Duration(seconds: 1));
        final result = await model.call('overlay', true);
        if (result == true) {
          model.overlay = true;
          break;
        }
      }
    }
    expect(model.overlay, true);
    await tester.pump(const Duration(seconds: 2));
    await model.showOverlay(false);
    await model.capture(false);
    await model.poll();
    expect(model.capturing, false);
    if (Platform.isAndroid) await native.invokeMethod('debugFixture', 'stop');
    await model.stage(false);
    model.setDemo(true);
    await tester.pump(const Duration(seconds: 1));
    binding.reportData = {
      'platform': Platform.operatingSystem,
      'audioPeak': peak,
      'nativeMedia': 'pass',
      'overlay': 'pass',
    };
    await tester.pumpWidget(const SizedBox());
    model.dispose();
  });
}
