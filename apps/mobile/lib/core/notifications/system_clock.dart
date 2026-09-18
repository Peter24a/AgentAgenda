import 'package:flutter/services.dart';

class SystemClock {
  static const channel = MethodChannel('agent_agenda/system_clock');

  /// Returns whether Android opened a clock app, not whether an alarm is active.
  static Future<bool> openAlarm({
    required int hour,
    required int minute,
    required List<int> weekdays,
  }) async {
    if (hour < 0 ||
        hour > 23 ||
        minute < 0 ||
        minute > 59 ||
        weekdays.isEmpty ||
        weekdays.any((day) => day < 1 || day > 7)) {
      return false;
    }
    try {
      return await channel.invokeMethod<bool>('setAlarm', {
            'hour': hour,
            'minute': minute,
            'weekdays': weekdays,
          }) ??
          false;
    } on PlatformException {
      return false;
    } on MissingPluginException {
      return false;
    }
  }
}
