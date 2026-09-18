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
    int hour,
    int minute,
    int duration, {
    bool completed = false,
    bool provisional = false,
    ActivityCategory category = ActivityCategory.study,
  }) {
    final start = time(hour, minute);
    return AgendaItem(
      id: id,
      title: 'Actividad sintética',
      startTime: start,
      endTime: start.add(Duration(minutes: duration)),
      category: category,
      isCompleted: completed,
      isProvisional: provisional,
    );
  }

  const enabled = FollowUpSettings(enabled: true);

  test(
    'No schedules before explicit activation; default alarm is 06:45 weekdays',
    () {
      const settings = FollowUpSettings();
      expect(settings.enabled, false);
      expect(settings.alarmHour, 6);
      expect(settings.alarmMinute, 45);
      expect(settings.alarmWeekdays, [1, 2, 3, 4, 5]);
      expect(planFollowUps([event('a', 9, 0, 60)], settings, time(7)), isEmpty);
    },
  );
  test('Variable timing follows block ends rather than fixed intervals', () {
    final result = planFollowUps(
      [event('short', 9, 0, 60), event('long', 11, 0, 120)],
      enabled,
      time(7),
    );
    expect(result.map((n) => n.at), [time(10), time(12, 45)]);
  });
  test('Sleep, completed and provisional activities never create prompts', () {
    final result = planFollowUps(
      [
        event('completed', 9, 0, 60, completed: true),
        event('draft', 11, 0, 60, provisional: true),
        event('sleep', 13, 0, 90, category: ActivityCategory.sleep),
        event('overlap', 13, 0, 45),
      ],
      enabled,
      time(7),
    );
    expect(result, isEmpty);
  });
  test(
    'Quiet hours and wake boundary use Mexico City, not the machine timezone',
    () {
      expect(inQuietHours(time(6, 44).toUtc(), enabled), true);
      expect(inQuietHours(time(6, 45).toUtc(), enabled), false);
      expect(inQuietHours(time(22, 30).toUtc(), enabled), true);
      final result = planFollowUps(
        [
          event('early', 5, 30, 60),
          event('night', 22, 0, 60),
          event('bedtime-margin', 21, 30, 45),
        ],
        enabled,
        time(0),
      );
      expect(result, isEmpty);
    },
  );
  test('Cross-midnight sleep suppresses prompts even after the configured wake time', () {
    final sleep = AgendaItem(
      id: 'sleep',
      title: 'Sueño sintético',
      startTime: time(23, 0, 14),
      endTime: time(8),
      category: ActivityCategory.sleep,
    );
    expect(
      planFollowUps([sleep, event('early-study', 6, 45, 45)], enabled, time(5)),
      isEmpty,
    );
  });
  test(
    'At most configured daily limit and at least 75 minutes between prompts',
    () {
      final events = [
        for (var hour = 7; hour <= 20; hour++) event('$hour', hour, 0, 30),
      ];
      final result = planFollowUps(events, enabled, time(6));
      expect(result.length, 4);
      for (var i = 1; i < result.length; i++) {
        expect(
          result[i].at.difference(result[i - 1].at).inMinutes,
          greaterThanOrEqualTo(75),
        );
      }
    },
  );
  test('Recurring occurrences get stable, distinct IDs and duplicate events collapse', () {
    final first = event('series', 9, 0, 60);
    final next = first.copyWith(
      startTime: time(9, 0, 16),
      endTime: time(10, 0, 16),
    );
    final result = planFollowUps([first, first, next], enabled, time(7));
    expect(result.length, 2);
    expect(result[0].notificationId, isNot(result[1].notificationId));
    expect(
      result[0].notificationId,
      planFollowUps([first], enabled, time(7)).single.notificationId,
    );
  });
  test(
    'Canonical provisional and conditional markers are preserved for filtering',
    () {
      for (final marker in ['[PROVISIONAL]', '[CONDICIONAL]']) {
        final item = AgendaItem.fromJson({
          'id': marker,
          'title': 'Actividad',
          'description': '$marker Sin confirmar',
          'start_time': time(9).toUtc().toIso8601String(),
          'end_time': time(10).toUtc().toIso8601String(),
        });
        expect(item.isProvisional, true);
        expect(planFollowUps([item], enabled, time(7)), isEmpty);
      }
    },
  );
  test('Invalid quiet window fails closed', () {
    expect(
      planFollowUps(
        [event('a', 9, 0, 60)],
        enabled.copyWith(quietHour: 5),
        time(7),
      ),
      isEmpty,
    );
  });
}
