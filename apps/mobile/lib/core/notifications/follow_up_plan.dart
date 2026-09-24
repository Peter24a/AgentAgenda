import 'package:timezone/timezone.dart' as tz;

import '../../features/agenda/models/agenda_item.dart';
import '../../features/agenda/models/agenda_view.dart';

const agendaTimezone = 'America/Mexico_City';

class FollowUpSettings {
  final bool enabled;
  final int alarmHour;
  final int alarmMinute;
  final List<int> alarmWeekdays;
  final int quietHour;
  final int quietMinute;
  final int dailyLimit;

  const FollowUpSettings({
    this.enabled = false,
    this.alarmHour = 6,
    this.alarmMinute = 45,
    this.alarmWeekdays = const [1, 2, 3, 4, 5],
    this.quietHour = 22,
    this.quietMinute = 30,
    this.dailyLimit = 6,
  });

  FollowUpSettings copyWith({
    bool? enabled,
    int? alarmHour,
    int? alarmMinute,
    List<int>? alarmWeekdays,
    int? quietHour,
    int? quietMinute,
    int? dailyLimit,
  }) => FollowUpSettings(
    enabled: enabled ?? this.enabled,
    alarmHour: alarmHour ?? this.alarmHour,
    alarmMinute: alarmMinute ?? this.alarmMinute,
    alarmWeekdays: alarmWeekdays ?? this.alarmWeekdays,
    quietHour: quietHour ?? this.quietHour,
    quietMinute: quietMinute ?? this.quietMinute,
    dailyLimit: dailyLimit ?? this.dailyLimit,
  );

  Map<String, dynamic> toJson() => {
    'enabled': enabled,
    'alarm_hour': alarmHour,
    'alarm_minute': alarmMinute,
    'alarm_weekdays': alarmWeekdays,
    'quiet_hour': quietHour,
    'quiet_minute': quietMinute,
    'daily_limit': dailyLimit,
  };

  factory FollowUpSettings.fromJson(Map<String, dynamic> json) {
    int bounded(String key, int fallback, int maximum, [int minimum = 0]) {
      final value = json[key];
      return value is int && value >= minimum && value <= maximum
          ? value
          : fallback;
    }

    final days = json['alarm_weekdays'];
    return FollowUpSettings(
      enabled: json['enabled'] == true,
      alarmHour: bounded('alarm_hour', 6, 23),
      alarmMinute: bounded('alarm_minute', 45, 59),
      alarmWeekdays: days is List
          ? (days
                .whereType<int>()
                .where((d) => d >= 1 && d <= 7)
                .toSet()
                .toList()
              ..sort())
          : const [1, 2, 3, 4, 5],
      quietHour: bounded('quiet_hour', 22, 23),
      quietMinute: bounded('quiet_minute', 30, 59),
      dailyLimit: const [2, 3, 4, 6, 8].contains(json['daily_limit'])
          ? json['daily_limit'] as int
          : 6,
    );
  }
}

class PlannedFollowUp {
  final String key;
  final String eventId;
  final DateTime eventStart;
  final DateTime at;
  final String kind;
  final String body;
  final bool repeatsDaily;
  const PlannedFollowUp({
    required this.key,
    required this.eventId,
    required this.eventStart,
    required this.at,
    this.kind = 'check_in',
    this.body =
        '¿Cómo va tu día? Cuéntame qué has hecho y qué quieres ajustar.',
    this.repeatsDaily = false,
  });

  // Stable across process restarts; do not rely on Dart's hashCode.
  int get notificationId {
    var value = 2166136261;
    for (final code in key.codeUnits) {
      value = ((value ^ code) * 16777619) & 0x7fffffff;
    }
    return value == 0 ? 1 : value;
  }

  String get signature => repeatsDaily
      ? '$key|$body|daily'
      : '$key|${at.toUtc().toIso8601String()}|$body';
}

bool inQuietHours(DateTime instant, FollowUpSettings settings) {
  final local = tz.TZDateTime.from(instant, tz.getLocation(agendaTimezone));
  final minute = local.hour * 60 + local.minute;
  final wake = settings.alarmHour * 60 + settings.alarmMinute;
  final quiet = settings.quietHour * 60 + settings.quietMinute;
  // An invalid/empty awake window fails closed instead of allowing night alerts.
  return quiet <= wake || minute < wake || minute >= quiet;
}

List<PlannedFollowUp> planFollowUps(
  List<AgendaItem> events,
  FollowUpSettings settings,
  DateTime now,
) {
  if (!settings.enabled) return [];
  final zone = tz.getLocation(agendaTimezone);
  final localNow = tz.TZDateTime.from(now, zone);
  final sleep = events
      .where((e) => !e.isProvisional && e.category == ActivityCategory.sleep)
      .toList();
  final result = <PlannedFollowUp>[];
  final seen = <int>{};
  void add(PlannedFollowUp value) {
    if (seen.add(value.notificationId)) result.add(value);
  }

  // Recurring local prompts continue while the app is closed, without a server
  // push token or an obligation to mark calendar activities as complete.
  var count = 0;
  for (
    var minute = 9 * 60;
    minute <= 21 * 60 + 30 && count < settings.dailyLimit;
    minute += 150
  ) {
    var at = tz.TZDateTime(
      zone,
      localNow.year,
      localNow.month,
      localNow.day,
      minute ~/ 60,
      minute % 60,
    );
    if (!at.isAfter(now.add(const Duration(minutes: 1)))) {
      at = tz.TZDateTime(
        zone,
        at.year,
        at.month,
        at.day + 1,
        at.hour,
        at.minute,
      );
    }
    if (inQuietHours(at, settings) ||
        minute > settings.quietHour * 60 + settings.quietMinute - 45) {
      continue;
    }
    // A recurring time must not conflict with any known sleep window.
    final conflicts = sleep.any((event) {
      final start = tz.TZDateTime.from(event.startTime, zone);
      final end = tz.TZDateTime.from(agendaEventEnd(event), zone);
      final from = start.hour * 60 + start.minute - 30;
      final to = end.hour * 60 + end.minute;
      return end.difference(start).inHours >= 24 ||
          (to <= from
              ? minute >= from || minute < to
              : minute >= from && minute < to);
    });
    if (conflicts) continue;
    add(
      PlannedFollowUp(
        key: 'daily-check-in-$minute',
        eventId: '',
        eventStart: at,
        at: at,
        repeatsDaily: true,
        body: minute >= 20 * 60
            ? 'Cuéntame cómo estuvo tu día y qué te gustaría retomar mañana.'
            : '¿Cómo va tu día? Cuéntame qué has hecho o si cambió el plan.',
      ),
    );
    count++;
  }
  for (final event in events) {
    if (event.isProvisional || event.category == ActivityCategory.sleep) {
      continue;
    }
    final at = event.startTime.subtract(const Duration(minutes: 10));
    if (!at.isAfter(now.add(const Duration(minutes: 1))) ||
        !at.isBefore(now.add(const Duration(days: 7))) ||
        inQuietHours(at, settings)) {
      continue;
    }
    if (sleep.any(
      (e) =>
          !at.isBefore(e.startTime.subtract(const Duration(minutes: 30))) &&
          at.isBefore(agendaEventEnd(e)),
    )) {
      continue;
    }
    add(
      PlannedFollowUp(
        key:
            'reminder|${event.id}|${event.startTime.toUtc().toIso8601String()}',
        eventId: event.id,
        eventStart: event.startTime,
        at: at,
        kind: 'reminder',
        body: event.title.isEmpty
            ? 'Tienes una actividad en unos 10 minutos.'
            : 'En unos 10 minutos: ${event.title}',
      ),
    );
  }
  result.sort((a, b) => a.at.compareTo(b.at));
  return result;
}
