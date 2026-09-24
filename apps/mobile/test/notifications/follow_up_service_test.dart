import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:agent_agenda/core/notifications/follow_up_plan.dart';
import 'package:agent_agenda/core/notifications/follow_up_service.dart';
import 'package:agent_agenda/features/agenda/models/agenda_item.dart';

class FakeNotifications implements LocalNotificationDriver {
  bool granted = true;
  int permissionRequests = 0;
  int scheduledCalls = 0;
  int testCalls = 0;
  final notices = <int, PlannedFollowUp>{};
  final cancelled = <int>[];
  @override
  Future<void> initialize(void Function(String?) onOpen) async {}
  @override
  Future<bool> allowed() async => granted;
  @override
  Future<bool> requestPermission() async {
    permissionRequests++;
    return granted;
  }

  @override
  Future<bool> openSettings() async => true;
  @override
  Future<Set<int>> pendingIds() async => notices.keys.toSet();
  @override
  Future<void> cancel(int id) async {
    cancelled.add(id);
    notices.remove(id);
  }

  @override
  Future<void> schedule(PlannedFollowUp reminder) async {
    scheduledCalls++;
    notices[reminder.notificationId] = reminder;
  }

  @override
  Future<void> test() async {
    testCalls++;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final now = DateTime.utc(2026, 9, 15, 13); // 07:00 in Mexico City.
  final event = AgendaItem(
    id: 'synthetic',
    title: 'No personal data',
    startTime: DateTime.utc(2026, 9, 15, 15),
    endTime: DateTime.utc(2026, 9, 15, 16),
    category: ActivityCategory.study,
  );
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test(
    'Initialization neither requests permission nor enables alerts',
    () async {
      final driver = FakeNotifications();
      final service = FollowUpService(
        driver: driver,
        now: () => now,
        supported: true,
      );
      await service.init();
      expect(driver.permissionRequests, 0);
      expect(service.settings.enabled, false);
      expect(driver.notices, isEmpty);
    },
  );
  test('Repeated sync is idempotent and removed events cancel reminders without cancelling conversations', () async {
    final driver = FakeNotifications();
    var events = [event];
    final service = FollowUpService(
      driver: driver,
      now: () => now,
      supported: true,
      loader: (_, _) async => events,
    );
    await service.enableFromUserAction();
    expect(driver.notices, hasLength(7));
    await service.synchronize();
    expect(driver.scheduledCalls, 7);
    events = [];
    await service.synchronize();
    expect(driver.notices, hasLength(6));
    expect(driver.cancelled, hasLength(1));
  });
  test(
    'Time changes replace the schedule and explicit deletion cancels offline',
    () async {
      final driver = FakeNotifications();
      var events = [event];
      final service = FollowUpService(
        driver: driver,
        now: () => now,
        supported: true,
        loader: (_, _) async => events,
      );
      await service.enableFromUserAction();
      final id = driver.notices.values
          .singleWhere((n) => n.kind == 'reminder')
          .notificationId;
      events = [
        event.copyWith(
          startTime: event.startTime.add(const Duration(minutes: 15)),
          endTime: event.endTime!.add(const Duration(minutes: 15)),
        ),
      ];
      await service.synchronize();
      expect(driver.notices.containsKey(id), isFalse);
      expect(driver.scheduledCalls, 8);
      await service.removeEvent(event.id);
      expect(driver.notices, hasLength(6));
    },
  );
  test('Restart keeps minimal cache and offline sync preserves last successful timestamp', () async {
    final driver = FakeNotifications();
    final first = FollowUpService(
      driver: driver,
      now: () => now,
      supported: true,
      loader: (_, _) async => [event],
    );
    await first.enableFromUserAction();
    final restarted = FollowUpService(
      driver: driver,
      now: () => now,
      supported: true,
      loader: (_, _) async => throw Exception('synthetic offline'),
    );
    await restarted.init();
    await restarted.synchronize();
    expect(driver.notices, hasLength(7));
    expect(restarted.lastSynced, now);
    expect(restarted.error, contains('última sincronización'));
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString(FollowUpService.cacheKey), contains(event.title));
  });
  test(
    'Permission denial yields no schedules; disabling cancels persisted IDs',
    () async {
      final driver = FakeNotifications()..granted = false;
      final service = FollowUpService(
        driver: driver,
        now: () => now,
        supported: true,
        loader: (_, _) async => [event],
      );
      await service.enableFromUserAction();
      expect(service.permissionGranted, false);
      expect(driver.notices, isEmpty);
      driver.granted = true;
      await service.refreshPermissions();
      expect(driver.notices, hasLength(7));
      await service.saveSettings(service.settings.copyWith(enabled: false));
      expect(driver.notices, isEmpty);
    },
  );
  test('A voluntary test does not turn on scheduled follow-ups', () async {
    final driver = FakeNotifications();
    final service = FollowUpService(
      driver: driver,
      now: () => now,
      supported: true,
    );
    expect(await service.showTestFromUserAction(), true);
    expect(driver.testCalls, 1);
    expect(service.settings.enabled, false);
  });
}
