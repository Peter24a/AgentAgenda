import 'dart:io';

import 'package:agent_agenda/core/time/canonical_timestamp.dart';
import 'package:agent_agenda/features/agenda/models/agenda_item.dart';
import 'package:agent_agenda/features/agenda/models/agenda_task.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final expected = DateTime.utc(2026, 10, 10, 3, 49, 11, 123, 456);
  const representations = [
    '2026-10-10T03:49:11.123456',
    '2026-10-10T03:49:11.123456Z',
    '2026-10-09T21:49:11.123456-06:00',
    '2026-10-10T09:19:11.123456+05:30',
  ];

  for (final source in representations) {
    test('task preserves instant and UTC roundtrip: $source', () {
      final task = AgendaTask.fromJson({
        'id': 'test-task',
        'title': 'Synthetic timestamp',
        'due_date': source,
      });
      expect(task.dueDate!.toUtc(), expected);
      expect(task.dueDate!.isUtc, isFalse);
      expect(task.dueDate, expected.toLocal());
      expect(task.toJson()['due_date'], expected.toIso8601String());
      final replay = AgendaTask.fromJson(task.toJson());
      expect(replay.dueDate!.toUtc(), expected);
    });

    test('event preserves start/end instants and roundtrip: $source', () {
      final event = AgendaItem.fromJson({
        'id': 'test-event',
        'title': 'Synthetic timestamp',
        'start_time': source,
        'end_time': '2026-10-10T05:00:00',
      });
      final end = DateTime.utc(2026, 10, 10, 5);
      expect(event.startTime.toUtc(), expected);
      expect(event.startTime.isUtc, isFalse);
      expect(event.endTime!.toUtc(), end);
      expect(event.toJson()['start_time'], expected.toIso8601String());
      expect(event.toJson()['end_time'], end.toIso8601String());
      final replay = AgendaItem.fromJson(event.toJson());
      expect(replay.startTime.toUtc(), expected);
      expect(replay.endTime!.toUtc(), end);
    });
  }

  test('optional timestamps stay absent', () {
    final task = AgendaTask.fromJson({
      'id': 'test-task',
      'title': 'No due date',
    });
    expect(task.dueDate, isNull);
    expect(task.toJson()['due_date'], isNull);
    final event = AgendaItem.fromJson({
      'id': 'test-event',
      'title': 'No end',
      'start_time': representations.first,
    });
    expect(event.endTime, isNull);
    expect(event.toJson()['end_time'], isNull);
  });

  test('naive UTC remains intact during a local DST gap', () {
    // This clock time does not exist in New York's local spring transition,
    // but it is a valid UTC instant and must be parsed before localization.
    expect(
      parseCanonicalTimestamp('2026-03-08T02:30:00').toUtc(),
      DateTime.utc(2026, 3, 8, 2, 30),
    );
  });

  test('a date-only canonical value represents UTC midnight', () {
    expect(
      parseCanonicalTimestamp('2026-10-10').toUtc(),
      DateTime.utc(2026, 10, 10),
    );
  });

  test('Mexico City displays the previous local day, without losing UTC', () {
    final local = parseCanonicalTimestamp(representations.first);
    expect(local.timeZoneOffset, const Duration(hours: -6));
    expect(
      (local.year, local.month, local.day, local.hour, local.minute),
      (2026, 10, 9, 21, 49),
    );
    expect(local.toUtc(), expected);
  }, skip: Platform.environment['TZ'] != 'America/Mexico_City');
}
