import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:agent_agenda/core/notifications/system_clock.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final calls = <MethodCall>[];
  setUp(() {
    calls.clear();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemClock.channel, (call) async {
          calls.add(call);
          return true;
        });
  });
  tearDown(
    () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemClock.channel, null),
  );
  test('Clock dispatch carries editable time and weekdays; no dispatch during setup', () async {
    expect(calls, isEmpty);
    expect(
      await SystemClock.openAlarm(
        hour: 6,
        minute: 45,
        weekdays: [1, 2, 3, 4, 5],
      ),
      true,
    );
    expect(calls.single.method, 'setAlarm');
    expect(calls.single.arguments, {
      'hour': 6,
      'minute': 45,
      'weekdays': [1, 2, 3, 4, 5],
    });
  });
  test(
    'Empty days and invalid time cannot silently create a one-off alarm',
    () async {
      expect(
        await SystemClock.openAlarm(hour: 6, minute: 45, weekdays: []),
        false,
      );
      expect(
        await SystemClock.openAlarm(hour: 24, minute: 0, weekdays: [1]),
        false,
      );
      expect(calls, isEmpty);
    },
  );
  test(
    'No compatible clock is reported without claiming the alarm is active',
    () async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(
            SystemClock.channel,
            (_) async => throw PlatformException(code: 'unavailable'),
          );
      expect(
        await SystemClock.openAlarm(hour: 6, minute: 45, weekdays: [1]),
        false,
      );
    },
  );
}
