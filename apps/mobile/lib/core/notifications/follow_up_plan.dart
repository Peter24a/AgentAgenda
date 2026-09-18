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
    this.dailyLimit = 4,
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
      dailyLimit: const [2, 4, 6, 8].contains(json['daily_limit'])
          ? json['daily_limit'] as int
          : 4,
    );
  }
}

class PlannedFollowUp {
  final String key;
  final String eventId;
  final DateTime eventStart;
  final DateTime at;
  const PlannedFollowUp({
    required this.key,
    required this.eventId,
    required this.eventStart,
    required this.at,
  });

  // Stable across process restarts; do not rely on Dart's hashCode.
  int get notificationId {
    var value = 2166136261;
    for (final code in key.codeUnits) {
      value = ((value ^ code) * 16777619) & 0x7fffffff;
    }
    return value == 0 ? 1 : value;
  }

  String get signature => '$key|${at.toUtc().toIso8601String()}';
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
  final sleep = events
      .where((e) => !e.isProvisional && e.category == ActivityCategory.sleep)
      .toList();
  final candidates = <PlannedFollowUp>[];
  final seen = <String>{};
  final limit = now.add(const Duration(days: 7));
  for (final event in events) {
    if (event.isCompleted ||
        event.isProvisional ||
        event.category == ActivityCategory.sleep) {
      continue;
    }
    final end = agendaEventEnd(event);
    final duration = end.difference(event.startTime);
    if (duration.inMinutes < 20) continue;
    // One prompt at the end of short blocks, 15 minutes before long blocks end.
    final at = duration.inMinutes >= 90
        ? end.subtract(const Duration(minutes: 15))
        : end;
    if (!at.isAfter(now.add(const Duration(minutes: 1))) ||
        !at.isBefore(limit)) {
      continue;
    }
    if (inQuietHours(at, settings)) continue;
    // Leave a margin before bedtime for inexact Android delivery.
    final local = tz.TZDateTime.from(at, tz.getLocation(agendaTimezone));
    if (local.hour * 60 + local.minute >
        settings.quietHour * 60 + settings.quietMinute - 45) {
      continue;
    }
    if (sleep.any(
      (s) =>
          !at.isBefore(s.startTime.subtract(const Duration(minutes: 30))) &&
          at.isBefore(agendaEventEnd(s)),
    )) {
      continue;
    }
    final key =
        'followup|${event.id}|${event.startTime.toUtc().toIso8601String()}';
    if (seen.add(key)) {
      candidates.add(
        PlannedFollowUp(
          key: key,
          eventId: event.id,
          eventStart: event.startTime,
          at: at,
        ),
      );
    }
  }
  candidates.sort((a, b) => a.at.compareTo(b.at));
  final result = <PlannedFollowUp>[];
  final dailyCounts = <String, int>{};
  final usedIds = <int>{};
  for (final followUp in candidates) {
    final date = tz.TZDateTime.from(
      followUp.at,
      tz.getLocation(agendaTimezone),
    );
    final day = '${date.year}-${date.month}-${date.day}';
    if ((dailyCounts[day] ?? 0) >= settings.dailyLimit) continue;
    if (result.isNotEmpty &&
        followUp.at.difference(result.last.at).inMinutes < 75) {
      continue;
    }
    // In the unlikely event of an ID collision, never overwrite another notice.
    if (!usedIds.add(followUp.notificationId)) continue;
    result.add(followUp);
    dailyCounts[day] = (dailyCounts[day] ?? 0) + 1;
  }
  return result;
}
