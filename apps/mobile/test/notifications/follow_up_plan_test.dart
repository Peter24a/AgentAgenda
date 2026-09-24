import 'package:flutter_test/flutter_test.dart';
import 'package:timezone/data/latest.dart' as data;
import 'package:timezone/timezone.dart' as tz;
import 'package:agent_agenda/core/notifications/follow_up_plan.dart';
import 'package:agent_agenda/features/agenda/models/agenda_item.dart';

void main() {
  setUpAll(data.initializeTimeZones);
  DateTime time(int hour, [int minute = 0, int day = 15]) =>
      tz.TZDateTime(tz.getLocation(agendaTimezone), 2026, 9, day, hour, minute);
  AgendaItem event(
    String id,
    int hour, {
    bool provisional = false,
    bool completed = false,
    ActivityCategory category = ActivityCategory.study,
  }) => AgendaItem(
    id: id,
    title: 'Actividad sintética',
    startTime: time(hour),
    endTime: time(hour + 1),
    category: category,
    isProvisional: provisional,
    isCompleted: completed,
  );
  const enabled = FollowUpSettings(enabled: true);
  test('Disabled settings do not schedule anything', () {
    expect(
      planFollowUps([event('a', 9)], const FollowUpSettings(), time(7)),
      isEmpty,
    );
  });
  test('An empty calendar still gets six recurring conversations 150 minutes apart', () {
    final plan = planFollowUps([], enabled, time(7));
    expect(plan.length, 6);
    expect(plan.every((n) => n.repeatsDaily && n.kind == 'check_in'), isTrue);
    for (var i = 1; i < plan.length; i++) {
      expect(plan[i].at.difference(plan[i - 1].at).inMinutes, 150);
    }
    expect(plan.first.at, time(9));
    expect(plan.last.at, time(21, 30));
    expect(
      planFollowUps([], enabled, time(23)).map((n) => n.notificationId),
      plan.map((n) => n.notificationId),
    );
  });
  test('Activity reminders fire ten minutes before start; old completion flags do not suppress them', () {
    final reminders = planFollowUps(
      [event('a', 9, completed: true)],
      enabled,
      time(7),
    ).where((n) => n.kind == 'reminder').toList();
    expect(reminders.length, 1);
    expect(reminders.single.at, time(8, 50));
    expect(reminders.single.body, contains('Actividad sintética'));
  });
  test('Unaccepted and sleep activities do not create reminders; known sleep suppresses recurring slots', () {
    final plan = planFollowUps(
      [
        event('draft', 11, provisional: true),
        event('sleep', 14, category: ActivityCategory.sleep),
        event('overlap', 14),
      ],
      enabled,
      time(7),
    );
    expect(plan.where((n) => n.kind == 'reminder'), isEmpty);
    expect(plan.any((n) => n.at == time(14)), isFalse);
  });
  test('Quiet hours and invalid windows fail closed', () {
    expect(inQuietHours(time(6, 44).toUtc(), enabled), isTrue);
    expect(inQuietHours(time(22, 30), enabled), isTrue);
    expect(
      planFollowUps([event('a', 9)], enabled.copyWith(quietHour: 5), time(7)),
      isEmpty,
    );
    final plan = planFollowUps([], enabled.copyWith(quietHour: 20), time(7));
    expect(
      plan.every((n) => !inQuietHours(n.at, enabled.copyWith(quietHour: 20))),
      isTrue,
    );
    expect(plan.every((n) => (n.at as tz.TZDateTime).hour < 20), isTrue);
  });
  test(
    'Reminder occurrences have distinct stable IDs and duplicates collapse',
    () {
      final first = event('series', 9);
      final second = first.copyWith(
        startTime: time(9, 0, 16),
        endTime: time(10, 0, 16),
      );
      final plan = planFollowUps(
        [first, first, second],
        enabled,
        time(7),
      ).where((n) => n.kind == 'reminder').toList();
      expect(plan.length, 2);
      expect(plan.first.notificationId, isNot(plan.last.notificationId));
    },
  );
}
