// Requires a paired device or a temporary TEST_ACCESS_TOKEN supplied by file.
// Sends one chat message; does not create agenda proposals.
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:agent_agenda/core/network/api_client.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('Paired device reaches backend and completes LLM stream', (
    tester,
  ) async {
    const verifyArchive = bool.fromEnvironment('VERIFY_PERSONAL_ARCHIVE');
    final api = ApiClient.instance;
    await api.init();
    const testToken = String.fromEnvironment('TEST_ACCESS_TOKEN');
    if (testToken.isNotEmpty) await api.setAuthToken(testToken);
    expect(await api.checkHealth(), isTrue);
    final events = await api
        .streamChat(
          message: verifyArchive
              ? 'Según mis documentos, ¿qué carrera estudio y cuáles son mis metas de posgrado? Cita fuentes y distingue información histórica. No crees propuestas.'
              : 'Prueba técnica de conexión. Responde únicamente: Conexión correcta. No crees eventos ni propuestas.',
        )
        .toList()
        .timeout(const Duration(seconds: 120));
    expect(events.whereType<ChatErrorEvent>(), isEmpty);
    expect(events.whereType<ChatDoneEvent>(), hasLength(1));
    if (verifyArchive) {
      final answer = events
          .whereType<ChatTokenEvent>()
          .map((e) => e.token)
          .join();
      expect(
        answer.contains('Fuentes disponibles para esta respuesta'),
        isTrue,
      );
      expect(answer.contains('[D1]'), isTrue);
      // Supply archive-specific expectations privately, never as test fixtures.
      const expectedTerms = String.fromEnvironment('EXPECTED_ANSWER_TERMS');
      final body = answer
          .split('Fuentes disponibles para esta respuesta')
          .first
          .toLowerCase();
      for (final term in expectedTerms.split('|').where((e) => e.isNotEmpty)) {
        expect(
          body.contains(term.toLowerCase()),
          isTrue,
          reason: 'The answer must contain the expected documentary facts.',
        );
      }
    }
    expect(
      events.whereType<ChatTokenEvent>().map((e) => e.token).join().trim(),
      isNotEmpty,
    );
  });
}
