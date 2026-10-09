import 'dart:convert';

import 'package:agent_agenda/core/network/api_client.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('AI report sends only the selected ID and reviewed fields to the scoped space', () async {
    final requests = <http.Request>[];
    final api = ApiClient.forTesting(
      baseUrl: 'https://agenda-api.example/s/synthetic-space',
      token: 'synthetic-device-token',
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(
          '{"id":"synthetic-receipt","status":"received"}',
          201,
        );
      }),
    );
    await api.reportAiResponse(
      messageId: 'msg-selected',
      reason: AiReportReason.privacy,
      details: '  Revisa esta respuesta.  ',
    );
    expect(requests, hasLength(1));
    final request = requests.single;
    expect(request.method, 'POST');
    expect(
      request.url.toString(),
      'https://agenda-api.example/s/synthetic-space/v1/chat/reports',
    );
    expect(request.headers['Authorization'], 'Bearer synthetic-device-token');
    expect(jsonDecode(request.body), {
      'message_id': 'msg-selected',
      'reason': 'privacy',
      'details': 'Revisa esta respuesta.',
    });
  });

  test(
    'empty optional comment is omitted and an idempotent receipt is accepted',
    () async {
      final api = ApiClient.forTesting(
        baseUrl: 'https://agenda-api.example/s/synthetic-space',
        token: 'synthetic-device-token',
        client: MockClient((request) async {
          expect(jsonDecode(request.body), {
            'message_id': 'msg-selected',
            'reason': 'harmful',
          });
          return http.Response('{"status":"received"}', 200);
        }),
      );
      await api.reportAiResponse(
        messageId: 'msg-selected',
        reason: AiReportReason.harmful,
        details: '  ',
      );
    },
  );

  test('invalid reports are rejected before any request and HTTP failure is propagated', () async {
    var calls = 0;
    final api = ApiClient.forTesting(
      baseUrl: 'https://agenda-api.example/s/synthetic-space',
      token: 'synthetic-device-token',
      client: MockClient((_) async {
        calls++;
        return http.Response('{}', 404);
      }),
    );
    await expectLater(
      api.reportAiResponse(messageId: '', reason: AiReportReason.other),
      throwsArgumentError,
    );
    await expectLater(
      api.reportAiResponse(
        messageId: 'msg-selected',
        reason: AiReportReason.other,
        details: 'a' * 2001,
      ),
      throwsArgumentError,
    );
    expect(calls, 0);
    await expectLater(
      api.reportAiResponse(
        messageId: 'msg-foreign',
        reason: AiReportReason.other,
      ),
      throwsException,
    );
    expect(calls, 1);
  });
}
