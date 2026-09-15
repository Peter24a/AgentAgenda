import 'package:flutter_test/flutter_test.dart';
import 'package:agent_agenda/features/agenda/models/agenda_item.dart';
import 'package:agent_agenda/features/agenda/models/agenda_task.dart';
import 'package:agent_agenda/core/network/api_client.dart';

void main() {
  group('AgendaItem Model Tests', () {
    test('serialization to and from JSON preserves all properties', () {
      final now = DateTime.now();
      final item = AgendaItem(
        id: 'evt-test-1',
        title: 'Reunión de planificación',
        description: 'Revisión semanal con el equipo',
        startTime: now,
        endTime: now.add(const Duration(hours: 1)),
        category: ActivityCategory.work,
        isCompleted: true,
      );

      final json = item.toJson();
      expect(json['id'], 'evt-test-1');
      expect(json['title'], 'Reunión de planificación');
      expect(json['description'], 'Revisión semanal con el equipo');
      expect(json['category'], 'work');
      expect(json['is_completed'], true);

      final restored = AgendaItem.fromJson(json);
      expect(restored.id, item.id);
      expect(restored.title, item.title);
      expect(restored.description, item.description);
      expect(restored.category, item.category);
      expect(restored.isCompleted, true);
    });

    test('default values when json fields are missing or null', () {
      final json = {
        'id': 'evt-min',
        'title': 'Pausa activa',
        'start_time': '2026-09-14T10:00:00.000',
      };

      final item = AgendaItem.fromJson(json);
      expect(item.id, 'evt-min');
      expect(item.title, 'Pausa activa');
      expect(item.description, isNull);
      expect(item.endTime, isNull);
      expect(item.category, ActivityCategory.general);
      expect(item.isCompleted, false);
    });
  });

  group('AgendaTask Model Tests', () {
    test('serialization to and from JSON', () {
      final task = AgendaTask(
        id: 'tsk-100',
        title: 'Comprar boletos de avión',
        description: 'Viaje a conferencia de IA',
        status: 'pending',
        priority: 'high',
        dueDate: DateTime(2026, 9, 20),
        version: 2,
      );

      final json = task.toJson();
      expect(json['id'], 'tsk-100');
      expect(json['priority'], 'high');
      expect(task.isCompleted, false);

      final restored = AgendaTask.fromJson(json);
      expect(restored.id, task.id);
      expect(restored.title, task.title);
      expect(restored.isCompleted, false);
      expect(restored.version, 2);
    });
  });

  group('ApiClient Platform URL Tests', () {
    test('ApiClient provides valid default platform URL', () {
      expect(ApiClient.defaultPlatformUrl, isNotEmpty);
      expect(ApiClient.defaultPlatformUrl.startsWith('http'), isTrue);
    });
  });
}
