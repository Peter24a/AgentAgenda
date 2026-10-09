import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:timezone/data/latest.dart' as timezone_data;
import 'package:timezone/timezone.dart' as tz;

import '../../features/agenda/models/agenda_item.dart';
import '../network/api_client.dart';
import 'follow_up_plan.dart';

abstract class LocalNotificationDriver {
  Future<void> initialize(void Function(String?) onOpen);
  Future<bool> allowed();
  Future<bool> requestPermission();
  Future<Set<int>> pendingIds();
  Future<void> schedule(PlannedFollowUp reminder);
  Future<void> cancel(int id);
  Future<void> test();
  Future<bool> openSettings();
}

class AndroidLocalNotificationDriver implements LocalNotificationDriver {
  String spaceKey = '';
  final _plugin = FlutterLocalNotificationsPlugin();
  AndroidFlutterLocalNotificationsPlugin? get _android => _plugin
      .resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin
      >();
  static const details = NotificationDetails(
    android: AndroidNotificationDetails(
      'agenda_follow_up_v1',
      'Seguimientos de agenda',
      channelDescription:
          'Conversaciones durante el día y recordatorios de tus actividades.',
      importance: Importance.defaultImportance,
      priority: Priority.defaultPriority,
      visibility: NotificationVisibility.private,
      icon: 'ic_notification',
      category: AndroidNotificationCategory.reminder,
      timeoutAfter: 30 * 60 * 1000,
    ),
  );

  @override
  Future<void> initialize(void Function(String?) onOpen) async {
    await _plugin.initialize(
      settings: const InitializationSettings(
        android: AndroidInitializationSettings('ic_notification'),
      ),
      onDidReceiveNotificationResponse: (response) => onOpen(response.payload),
    );
    final launch = await _plugin.getNotificationAppLaunchDetails();
    if (launch?.didNotificationLaunchApp == true) {
      onOpen(launch?.notificationResponse?.payload);
    }
  }

  @override
  Future<bool> allowed() async =>
      await _android?.areNotificationsEnabled() ?? false;
  @override
  Future<bool> requestPermission() async =>
      await _android?.requestNotificationsPermission() ?? false;
  @override
  Future<bool> openSettings() async =>
      await _android?.openAppNotificationSettings() ?? false;
  @override
  Future<Set<int>> pendingIds() async =>
      (await _plugin.pendingNotificationRequests()).map((n) => n.id).toSet();
  @override
  Future<void> cancel(int id) => _plugin.cancel(id: id);
  @override
  Future<void> schedule(PlannedFollowUp reminder) => _plugin.zonedSchedule(
    id: reminder.notificationId,
    scheduledDate: tz.TZDateTime.from(
      reminder.at,
      tz.getLocation(agendaTimezone),
    ),
    title: reminder.kind == 'reminder'
        ? 'SARA · Recordatorio'
        : 'SARA · ¿Cómo vas?',
    body: reminder.body,
    notificationDetails: details,
    androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
    matchDateTimeComponents: reminder.repeatsDaily
        ? DateTimeComponents.time
        : null,
    payload: jsonEncode({
      'space_key': spaceKey,
      'kind': reminder.kind,
      'event_id': reminder.eventId.isEmpty ? null : reminder.eventId,
      'notification_key': reminder.key,
      'scheduled_at': reminder.at.toUtc().toIso8601String(),
      'repeats_daily': reminder.repeatsDaily,
    }),
  );
  @override
  Future<void> test() => _plugin.show(
    id: 2147483646,
    title: 'Prueba de seguimiento',
    body: 'Esta prueba fue solicitada por ti. Los avisos de tu agenda se configuran por separado.',
    notificationDetails: details,
    payload: '{"kind":"follow_up_test"}',
  );
}

typedef FollowUpLoader = Future<List<AgendaItem>> Function(
  DateTime start,
  DateTime end,
);

class FollowUpService extends ChangeNotifier {
  static final instance = FollowUpService(namespace: 'disconnected');
  static const settingsKey = 'follow_up_settings_v1';
  static const cacheKey = 'follow_up_event_cache_v1';
  static const syncedKey = 'follow_up_synced_at_v1';
  static const scheduledKey = 'follow_up_scheduled_v1';

  final LocalNotificationDriver _driver;
  final FollowUpLoader _loader;
  final DateTime Function() _now;
  final bool supported;
  Map<String, dynamic>? openedNotification;
  final ValueNotifier<bool> openCheckIn = ValueNotifier(false);
  FollowUpSettings settings = const FollowUpSettings();
  DateTime? lastSynced;
  bool permissionGranted = false;
  bool busy = false;
  bool initialized = false;
  String? error;
  List<PlannedFollowUp> planned = [];
  List<AgendaItem> _cache = [];
  Map<int, String> _scheduled = {};
  SharedPreferences? _prefs;
  Future<void>? _initializing;
  Future<void> _tail = Future.value();
  String namespace;
  int _scopeEpoch = 0;
  String _key(String key) => namespace.isEmpty ? key : '$key::$namespace';

  FollowUpService({
    LocalNotificationDriver? driver,
    FollowUpLoader? loader,
    DateTime Function()? now,
    bool? supported,
    this.namespace = '',
  }) : _driver = driver ?? AndroidLocalNotificationDriver(),
       _loader =
           loader ??
           ((start, end) =>
               ApiClient.instance.getAgendaRange(start: start, end: end)),
       _now = now ?? DateTime.now,
       supported =
           supported ??
           (!kIsWeb && defaultTargetPlatform == TargetPlatform.android);

  Future<void> init() => _initializing ??= _initialize();
  Future<void> _initialize() async {
    timezone_data.initializeTimeZones();
    if (!supported) {
      initialized = true;
      return;
    }
    try {
      _prefs = await SharedPreferences.getInstance();
      if (_driver is AndroidLocalNotificationDriver) {
        _driver.spaceKey = namespace;
      }
      final settingsJson = _prefs!.getString(_key(settingsKey));
      if (settingsJson != null) {
        settings = FollowUpSettings.fromJson(jsonDecode(settingsJson));
      }
      lastSynced = DateTime.tryParse(_prefs!.getString(_key(syncedKey)) ?? '');
      final cacheJson = _prefs!.getString(_key(cacheKey));
      if (cacheJson != null) {
        _cache = (jsonDecode(cacheJson) as List)
            .map((e) => AgendaItem.fromJson(Map<String, dynamic>.from(e)))
            .toList();
      }
      final scheduledJson = _prefs!.getString(_key(scheduledKey));
      if (scheduledJson != null) {
        _scheduled = (jsonDecode(scheduledJson) as Map<String, dynamic>).map(
          (key, value) => MapEntry(int.parse(key), value as String),
        );
      }
      await _driver.initialize((payload) {
        if (payload == null) return;
        try {
          final value = Map<String, dynamic>.from(jsonDecode(payload) as Map);
          if (namespace == 'disconnected' ||
              (value['space_key'] ?? '') != namespace) {
            return;
          }
          if (['check_in', 'reminder', 'follow_up'].contains(value['kind'])) {
            final now = tz.TZDateTime.from(
              _now(),
              tz.getLocation(agendaTimezone),
            );
            openedNotification = {
              'kind': value['kind'] == 'reminder' ? 'reminder' : 'check_in',
              'event_id': value['event_id'],
              'notification_key': value['repeats_daily'] == true
                  ? '${value['notification_key']}-${now.year}-${now.month}-${now.day}'
                  : value['notification_key'] ??
                        'legacy-${now.microsecondsSinceEpoch}',
              'scheduled_at': value['repeats_daily'] == true
                  ? _now().toUtc().toIso8601String()
                  : value['scheduled_at'],
            };
            openCheckIn.value = true;
          }
        } catch (_) {
          /* Ignore unrelated/malformed payloads. */
        }
      });
      initialized = true;
      await _reconcile();
    } catch (_) {
      error = 'No se pudieron preparar los avisos locales. Cierra y vuelve a abrir la app.';
      initialized = true;
    }
    notifyListeners();
  }

  Future<void> _serial(Future<void> Function() operation) {
    final epoch = _scopeEpoch;
    final task = _tail.then((_) async {
      if (epoch != _scopeEpoch) return;
      await init();
      if (!supported || _prefs == null) return;
      busy = true;
      notifyListeners();
      try {
        await operation();
      } catch (_) {
        error = 'No se pudieron actualizar todos los avisos. Reintenta la sincronización.';
      } finally {
        busy = false;
        notifyListeners();
      }
    });
    _tail = task.catchError((Object _) {});
    return task;
  }

  Future<void> saveSettings(FollowUpSettings value) => _serial(() async {
    settings = value;
    await _prefs!.setString(_key(settingsKey), jsonEncode(settings.toJson()));
    error = null;
    await _reconcile();
  });

  /// Only call this following the user's permission/enable button.
  Future<void> enableFromUserAction() async {
    await init();
    if (!supported) return;
    try {
      await _driver.requestPermission();
    } catch (_) {
      /* The visible status remains denied. */
    }
    await saveSettings(settings.copyWith(enabled: true));
    await synchronize();
  }

  Future<void> refreshPermissions() => _serial(() async {
    await _reconcile();
  });

  Future<void> synchronize() => _serial(() async {
    final epoch = _scopeEpoch;
    if (!settings.enabled) {
      await _reconcile();
      return;
    }
    final now = tz.TZDateTime.from(_now(), tz.getLocation(agendaTimezone));
    // Include yesterday so cross-midnight sleep intervals can suppress alerts.
    final start = tz.TZDateTime(now.location, now.year, now.month, now.day - 1);
    final end = tz.TZDateTime(now.location, now.year, now.month, now.day + 8);
    try {
      final canonical = await _loader(start, end);
      if (epoch != _scopeEpoch) return;
      _cache = canonical;
      lastSynced = _now();
      await _persistCache();
      await _prefs!.setString(
        _key(syncedKey),
        lastSynced!.toUtc().toIso8601String(),
      );
      error = null;
    } catch (_) {
      if (epoch != _scopeEpoch) return;
      error = 'Sin conexión con la agenda. Los avisos conservan la última sincronización; los cambios externos aún no llegaron.';
    }
    await _reconcile();
  });

  Future<void> removeEvent(String eventId, {DateTime? occurrence}) =>
      _serial(() async {
        _cache.removeWhere(
          (e) =>
              e.id == eventId &&
              (occurrence == null || e.startTime.isAtSameMomentAs(occurrence)),
        );
        await _persistCache();
        await _reconcile();
      });

  Future<void> _persistCache() => _prefs!
      .setString(
        _key(cacheKey),
        jsonEncode(
          _cache
              .map(
                (event) => {
                  'id': event.id,
                  'title': event.title,
                  'start_time': event.startTime.toUtc().toIso8601String(),
                  'end_time': event.endTime?.toUtc().toIso8601String(),
                  'category': event.category.name,
                  'is_completed': event.isCompleted,
                  'is_provisional': event.isProvisional,
                },
              )
              .toList(),
        ),
      )
      .then((_) {});

  Future<void> _reconcile() async {
    permissionGranted = await _driver.allowed();
    final freshEnough =
        lastSynced != null && _now().difference(lastSynced!).inDays < 7;
    final next = permissionGranted && namespace != 'disconnected'
        ? planFollowUps(freshEnough ? _cache : [], settings, _now())
        : <PlannedFollowUp>[];
    final nextIds = next.map((n) => n.notificationId).toSet();
    final pending = await _driver.pendingIds();
    // This application owns these scheduled notices; remove orphaned schedules too.
    for (final id in {..._scheduled.keys, ...pending}.difference(nextIds)) {
      await _driver.cancel(id);
    }
    final signatures = <int, String>{};
    for (final notification in next) {
      if (_scheduled[notification.notificationId] != notification.signature ||
          !pending.contains(notification.notificationId)) {
        await _driver.schedule(notification);
      }
      signatures[notification.notificationId] = notification.signature;
    }
    _scheduled = signatures;
    planned = next;
    await _prefs!.setString(
      _key(scheduledKey),
      jsonEncode(_scheduled.map((id, value) => MapEntry(id.toString(), value))),
    );
  }

  Future<bool> showTestFromUserAction() async {
    await init();
    if (!supported) return false;
    try {
      permissionGranted = await _driver.allowed();
      if (!permissionGranted) {
        permissionGranted = await _driver.requestPermission();
      }
      notifyListeners();
      if (!permissionGranted) return false;
      await _driver.test();
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<bool> openPermissionSettings() async {
    try {
      return supported && await _driver.openSettings();
    } catch (_) {
      return false;
    }
  }

  /// Serialized with reconciliation; an old loader cannot populate a new space.
  Future<void> selectSpace(String newNamespace) async {
    if (namespace == newNamespace) return;
    _scopeEpoch++;
    final task = _tail.then((_) async {
      await init();
      if (_prefs != null && supported) {
        for (final id in {..._scheduled.keys, ...await _driver.pendingIds()}) {
          await _driver.cancel(id);
        }
        for (final key in [cacheKey, syncedKey, scheduledKey]) {
          await _prefs!.remove(_key(key));
        }
        // Pre-platform caches have no account identity. Discard them.
        for (final key in [settingsKey, cacheKey, syncedKey, scheduledKey]) {
          await _prefs!.remove(key);
        }
      }
      namespace = newNamespace;
      if (_driver is AndroidLocalNotificationDriver) {
        _driver.spaceKey = namespace;
      }
      settings = const FollowUpSettings();
      _cache = [];
      _scheduled = {};
      planned = [];
      lastSynced = null;
      openedNotification = null;
      openCheckIn.value = false;
      error = null;
      final saved = _prefs?.getString(_key(settingsKey));
      if (saved != null) {
        settings = FollowUpSettings.fromJson(jsonDecode(saved));
      }
      if (_prefs != null && supported) await _reconcile();
      notifyListeners();
    });
    _tail = task.catchError((Object _) {});
    await task;
  }
}
