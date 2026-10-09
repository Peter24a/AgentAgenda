import 'dart:convert';

import 'package:agent_agenda/core/network/space_session.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class MemorySessionStore implements SessionStore {
  final Map<String, String> values = {};
  @override
  Future<String?> read(String key) async => values[key];
  @override
  Future<void> write(String key, String value) async => values[key] = value;
  @override
  Future<void> delete(String key) async => values.remove(key);
}

Map<String, dynamic> syntheticGrant({String space = 'personal'}) => {
  'space_id': space,
  'space_name': 'Espacio de prueba',
  'base_url': '$defaultAgendaServer/s/$space',
  'device_id': 'synthetic-device',
  'access_token': 'synthetic-access',
  'refresh_token': 'synthetic-refresh',
  'expires_in': 3600,
  'scopes': ['agenda:read'],
};

void main() {
  test('fresh install is empty and makes no authenticated requests', () async {
    var calls = 0;
    final manager = SpaceSessionManager(
      store: MemorySessionStore(),
      client: MockClient((_) async {
        calls++;
        return http.Response('{}', 500);
      }),
    );
    await manager.init();
    expect(manager.state, ConnectionState.disconnected);
    expect(manager.session, isNull);
    expect(calls, 0);
  });

  test('activation code and fragment/query link parse; absent or unsafe links rejected', () {
    expect(
      ActivationInput.parse('  Test-123456 ', defaultAgendaServer).code,
      'Test-123456',
    );
    expect(
      ActivationInput.parse(
        '$defaultAgendaServer/activar#code=Test-123456',
        defaultAgendaServer,
      ).code,
      'Test-123456',
    );
    expect(
      ActivationInput.parse(
        '$defaultAgendaServer/activar?code=Test-123456',
        defaultAgendaServer,
      ).code,
      'Test-123456',
    );
    for (final invalid in [
      '',
      'a',
      'bad code',
      'https://other.example/activar#code=Test-123456',
    ]) {
      expect(
        () => ActivationInput.parse(invalid, defaultAgendaServer),
        throwsA(isA<ConnectionException>()),
      );
    }
    expect(
      () => normalizeServer('http://agenda.example'),
      throwsA(isA<ConnectionException>()),
    );
    expect(
      () => normalizeServer('https://secret@agenda.example'),
      throwsA(isA<ConnectionException>()),
    );
  });

  test(
    'activation verifies device and persists reconnectable scoped session',
    () async {
      final store = MemorySessionStore();
      final calls = <http.Request>[];
      final client = MockClient((request) async {
        calls.add(request);
        if (request.url.path == '/platform/v1/activate') {
          final data = jsonDecode(request.body) as Map<String, dynamic>;
          expect(data['code'], 'Test-123456');
          expect(data['platform'], 'android');
          expect(data['request_id'], matches(RegExp(r'^[a-f0-9]{48}$')));
          expect(request.headers['Authorization'], isNull);
          return http.Response(jsonEncode(syntheticGrant()), 200);
        }
        expect(request.url.path, '/s/personal/v1/auth/me');
        expect(request.headers['Authorization'], 'Bearer synthetic-access');
        return http.Response('{"device_id":"synthetic-device"}', 200);
      });
      final manager = SpaceSessionManager(store: store, client: client);
      await manager.activate('Test-123456');
      expect(manager.state, ConnectionState.connected);
      expect(manager.session?.baseUrl, '$defaultAgendaServer/s/personal');
      expect(store.values.containsKey(SpaceSessionManager.attemptKey), false);
      final restored = SpaceSessionManager(store: store, client: client);
      await restored.init();
      expect(restored.state, ConnectionState.connected);
      expect(restored.session?.spaceId, 'personal');
      expect(calls, hasLength(3));
    },
  );

  test('lost activation response reuses a durable request ID', () async {
    final store = MemorySessionStore();
    final ids = <String>[];
    final names = <String>[];
    var first = true;
    final client = MockClient((request) async {
      if (request.url.path == '/platform/v1/activate') {
        ids.add(
          (jsonDecode(request.body) as Map<String, dynamic>)['request_id']
              as String,
        );
        names.add(
          (jsonDecode(request.body) as Map<String, dynamic>)['device_name']
              as String,
        );
        if (first) {
          first = false;
          throw http.ClientException('synthetic network failure');
        }
        return http.Response(jsonEncode(syntheticGrant()), 200);
      }
      return http.Response('{"device_id":"synthetic-device"}', 200);
    });
    final manager = SpaceSessionManager(store: store, client: client);
    await expectLater(
      manager.activate('Test-123456'),
      throwsA(isA<http.ClientException>()),
    );
    final restarted = SpaceSessionManager(store: store, client: client);
    await restarted.activate(
      'Test-123456',
      deviceName: 'Otro nombre tras reiniciar',
    );
    expect(ids[0], ids[1]);
    expect(names[0], names[1]);
    expect(restarted.state, ConnectionState.connected);
  });

  test(
    'expired or consumed invitation does not show an empty agenda',
    () async {
      for (final status in [400, 409, 423]) {
        final store = MemorySessionStore();
        final manager = SpaceSessionManager(
          store: store,
          client: MockClient((_) async => http.Response('{}', status)),
        );
        await expectLater(
          manager.activate('Test-123456'),
          throwsA(isA<ConnectionException>()),
        );
        expect(manager.state, ConnectionState.disconnected);
        expect(manager.session, isNull);
        expect(manager.message, isNotEmpty);
        expect(store.values, isEmpty);
      }
    },
  );

  test('successful activation survives a lost identity response', () async {
    final store = MemorySessionStore();
    final manager = SpaceSessionManager(
      store: store,
      client: MockClient((request) async {
        if (request.url.path == '/platform/v1/activate') {
          return http.Response(jsonEncode(syntheticGrant()), 200);
        }
        throw http.ClientException('synthetic offline');
      }),
    );
    await manager.activate('Test-123456');
    expect(manager.state, ConnectionState.unavailable);
    expect(manager.session?.spaceId, 'personal');
    expect(store.values.containsKey(SpaceSessionManager.sessionKey), true);
  });

  test('wrong identity invalidates the durable session', () async {
    final store = MemorySessionStore();
    final manager = SpaceSessionManager(
      store: store,
      client: MockClient(
        (request) async => request.url.path == '/platform/v1/activate'
            ? http.Response(jsonEncode(syntheticGrant()), 200)
            : http.Response('{"device_id":"another-device"}', 200),
      ),
    );
    await manager.activate('Test-123456');
    expect(manager.session, isNull);
    expect(manager.state, ConnectionState.disconnected);
    expect(store.values.containsKey(SpaceSessionManager.sessionKey), false);
  });

  test('scoped session rejects a backend URL from another host or space', () {
    for (final base in [
      'https://other.example/s/personal',
      '$defaultAgendaServer/s/walter',
      '$defaultAgendaServer/s/personal?token=x',
    ]) {
      expect(
        () => SpaceSession.fromJson({
          ...syntheticGrant(),
          'base_url': base,
        }, defaultAgendaServer),
        throwsA(isA<ConnectionException>()),
      );
    }
  });

  test('authenticated requests preserve the space prefix and do not send tokens to siblings', () async {
    final manager = SpaceSessionManager(store: MemorySessionStore());
    manager.session = SpaceSession.fromJson(
      syntheticGrant(),
      defaultAgendaServer,
    );
    var calls = 0;
    final client = SpaceHttpClient(
      manager,
      MockClient((request) async {
        calls++;
        expect(request.url.path, '/s/personal/v1/documents/id/download');
        expect(request.headers['Authorization'], 'Bearer synthetic-access');
        expect(request.followRedirects, false);
        return http.Response('test', 200);
      }),
    );
    await client.get(
      Uri.parse('$defaultAgendaServer/s/personal/v1/documents/id/download'),
    );
    for (final url in [
      '$defaultAgendaServer/s/walter/v1/agenda/events',
      '$defaultAgendaServer/v1/agenda/events',
      'https://other.example/s/personal/v1/agenda/events',
    ]) {
      await expectLater(
        client.get(Uri.parse(url)),
        throwsA(isA<ConnectionException>()),
      );
    }
    expect(calls, 1);
  });

  test('rejected renewal clears local access and invokes cleanup', () async {
    final store = MemorySessionStore();
    var cleaned = false;
    final manager = SpaceSessionManager(
      store: store,
      client: MockClient((request) async {
        expect(request.url.path, '/s/personal/v1/auth/refresh');
        return http.Response('{}', 401);
      }),
    );
    manager.session = SpaceSession.fromJson({
      ...syntheticGrant(),
      'expires_at': DateTime.now()
          .subtract(const Duration(seconds: 1))
          .toIso8601String(),
    }, defaultAgendaServer);
    await store.write(
      SpaceSessionManager.sessionKey,
      jsonEncode(manager.session!.toJson()),
    );
    manager.onDisconnect = () async {
      cleaned = true;
    };
    await manager.verify();
    expect(manager.state, ConnectionState.disconnected);
    expect(manager.session, isNull);
    expect(cleaned, true);
    expect(store.values, isEmpty);
  });

  test(
    '401 renews once with a scoped refresh then retries the request body',
    () async {
      var refreshes = 0;
      final manager = SpaceSessionManager(
        store: MemorySessionStore(),
        client: MockClient((request) async {
          refreshes++;
          expect(request.url.path, '/s/personal/v1/auth/refresh');
          return http.Response(
            jsonEncode({
              'access_token': 'synthetic-new',
              'refresh_token': 'synthetic-new-refresh',
              'expires_in': 3600,
            }),
            200,
          );
        }),
      );
      manager.session = SpaceSession.fromJson(
        syntheticGrant(),
        defaultAgendaServer,
      );
      var attempts = 0;
      final client = SpaceHttpClient(
        manager,
        MockClient((request) async {
          attempts++;
          expect(request.body, '{"synthetic":true}');
          return http.Response(
            '{}',
            request.headers['Authorization'] == 'Bearer synthetic-new'
                ? 200
                : 401,
          );
        }),
      );
      final response = await client.post(
        Uri.parse('$defaultAgendaServer/s/personal/v1/agenda/events'),
        body: '{"synthetic":true}',
      );
      expect(response.statusCode, 200);
      expect(refreshes, 1);
      expect(attempts, 2);
    },
  );
}
