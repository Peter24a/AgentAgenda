import 'package:agent_agenda/core/theme/beam_color_notifier.dart';
import 'package:agent_agenda/features/agenda/presentation/widgets/agent_screen_border.dart';
import 'package:agent_agenda/features/agenda/presentation/widgets/premium_agent_button.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late bool previousEnabled;
  late BeamPathStyle previousPathStyle;

  setUp(() {
    previousEnabled = BeamColorConfig.isEnabled.value;
    previousPathStyle = BeamColorConfig.currentPathStyle.value;
    BeamColorConfig.isEnabled.value = true;
    BeamColorConfig.currentPathStyle.value = BeamPathStyle.saraAssistantLoop;
  });

  tearDown(() {
    BeamColorConfig.isEnabled.value = previousEnabled;
    BeamColorConfig.currentPathStyle.value = previousPathStyle;
  });

  testWidgets('Disabling the ribbon stops frames and enabling resumes them', (
    tester,
  ) async {
    await tester.pumpWidget(_testApp(surfaceKey: GlobalKey()));
    await tester.pump(const Duration(milliseconds: 32));
    expect(tester.binding.transientCallbackCount, greaterThan(0));

    BeamColorConfig.isEnabled.value = false;
    await tester.pumpAndSettle();
    expect(tester.binding.transientCallbackCount, 0);
    expect(tester.binding.hasScheduledFrame, isFalse);
    await tester.pump(const Duration(seconds: 1));
    expect(tester.binding.transientCallbackCount, 0);

    BeamColorConfig.isEnabled.value = true;
    await tester.pump(const Duration(milliseconds: 32));
    expect(tester.binding.transientCallbackCount, greaterThan(0));

    await tester.pumpWidget(const SizedBox.shrink());
    expect(tester.binding.transientCallbackCount, 0);
  });

  testWidgets('Reduced motion stops the ribbon and can be changed at runtime', (
    tester,
  ) async {
    final surfaceKey = GlobalKey();
    await tester.pumpWidget(_testApp(surfaceKey: surfaceKey));
    expect(tester.binding.transientCallbackCount, greaterThan(0));

    await tester.pumpWidget(
      _testApp(surfaceKey: surfaceKey, reduceMotion: true),
    );
    await tester.pumpAndSettle();
    expect(tester.binding.transientCallbackCount, 0);
    expect(tester.binding.hasScheduledFrame, isFalse);

    // Toggling the decoration must not override the accessibility preference.
    BeamColorConfig.isEnabled.value = false;
    await tester.pump();
    BeamColorConfig.isEnabled.value = true;
    await tester.pump(const Duration(seconds: 1));
    expect(tester.binding.transientCallbackCount, 0);

    await tester.pumpWidget(_testApp(surfaceKey: surfaceKey));
    await tester.pump(const Duration(milliseconds: 32));
    expect(tester.binding.transientCallbackCount, greaterThan(0));
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('A hidden route does not keep requesting animation frames', (
    tester,
  ) async {
    final surfaceKey = GlobalKey();
    await tester.pumpWidget(_testApp(surfaceKey: surfaceKey));
    expect(tester.binding.transientCallbackCount, greaterThan(0));

    await tester.pumpWidget(
      _testApp(surfaceKey: surfaceKey, tickerEnabled: false),
    );
    await tester.pumpAndSettle();
    expect(tester.binding.transientCallbackCount, 0);

    await tester.pumpWidget(_testApp(surfaceKey: surfaceKey));
    await tester.pump(const Duration(milliseconds: 32));
    expect(tester.binding.transientCallbackCount, greaterThan(0));
    await tester.pumpWidget(const SizedBox.shrink());
  });

  for (final width in [320.0, 390.0]) {
    for (final textScale in [1.0, 2.0]) {
      testWidgets(
        'Ribbon and assistant fit width $width at text scale $textScale with safe insets',
        (tester) async {
          tester.view.devicePixelRatio = 1;
          tester.view.physicalSize = Size(width, 720);
          addTearDown(tester.view.resetDevicePixelRatio);
          addTearDown(tester.view.resetPhysicalSize);
          final surfaceKey = GlobalKey();
          var openings = 0;
          const safeInsets = EdgeInsets.fromLTRB(0, 24, 0, 34);
          await tester.pumpWidget(
            _testApp(
              surfaceKey: surfaceKey,
              textScale: textScale,
              safeInsets: safeInsets,
              onTap: () => openings++,
            ),
          );
          // Allow the measured assistant bounds to reach the next paint.
          await tester.pump(const Duration(milliseconds: 32));
          final buttonRect = tester.getRect(find.byKey(surfaceKey));
          expect(buttonRect.left, greaterThanOrEqualTo(24));
          expect(buttonRect.right, lessThanOrEqualTo(width - 24));
          expect(buttonRect.top, greaterThanOrEqualTo(safeInsets.top));
          expect(buttonRect.bottom, lessThanOrEqualTo(720 - safeInsets.bottom));
          expect(buttonRect.height, greaterThanOrEqualTo(48));
          final labelRect = tester.getRect(
            find.descendant(
              of: find.byType(PremiumAgentButton),
              matching: find.byType(Text),
            ),
          );
          expect(buttonRect.contains(labelRect.topLeft), isTrue);
          expect(buttonRect.contains(labelRect.bottomRight), isTrue);
          expect(tester.takeException(), isNull);

          // The decoration covers the screen but must not intercept this tap.
          await tester.tap(find.byKey(surfaceKey));
          await tester.pump(const Duration(milliseconds: 250));
          expect(openings, 1);
          await tester.pump(const Duration(milliseconds: 350));
          await tester.pump(const Duration(seconds: 5));
          expect(tester.takeException(), isNull);
          await tester.pumpWidget(const SizedBox.shrink());
        },
      );
    }
  }
}

Widget _testApp({
  required GlobalKey surfaceKey,
  bool reduceMotion = false,
  bool tickerEnabled = true,
  double textScale = 1,
  EdgeInsets safeInsets = EdgeInsets.zero,
  VoidCallback? onTap,
}) => MaterialApp(
  builder: (context, child) => MediaQuery(
    data: MediaQuery.of(context).copyWith(
      disableAnimations: reduceMotion,
      textScaler: TextScaler.linear(textScale),
      padding: safeInsets,
      viewPadding: safeInsets,
    ),
    child: child!,
  ),
  home: TickerMode(
    enabled: tickerEnabled,
    child: AgentScreenBorder(
      assistantKey: surfaceKey,
      child: Scaffold(
        body: const SafeArea(
          child: Center(child: SizedBox.square(dimension: 40)),
        ),
        bottomNavigationBar: SafeArea(
          top: false,
          child: Align(
            heightFactor: 1,
            child: PremiumAgentButton(
              surfaceKey: surfaceKey,
              onTap: onTap ?? () {},
            ),
          ),
        ),
      ),
    ),
  ),
);
