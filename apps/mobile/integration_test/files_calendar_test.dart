// Uses the paired phone, synthetic files and a future synthetic calendar event.
// Originals and real appointments are never opened or changed by this test.
import 'dart:convert';
import 'dart:io';

import 'package:agent_agenda/core/network/api_client.dart';
import 'package:agent_agenda/features/agenda/models/agent_proposal.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:path_provider/path_provider.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets(
    'Phone uploads and retrieves files; LLM creates, moves and cancels a synthetic event',
    (tester) async {
      final api = ApiClient.instance;
      await api.init();
      expect(await api.checkHealth(), isTrue);
      final marker = 'pruebaagenda${DateTime.now().millisecondsSinceEpoch}';
      final docIds = <String>[];
      final eventIds = <String>[];
      final pendingIds = <String>[];
      final directory = await (await getTemporaryDirectory()).createTemp(
        'agenda-test-',
      );
      try {
        final fixtures = {
          '$marker.txt': utf8.encode(
            'Documento sintético de prueba. Sin datos personales.',
          ),
          '$marker.png': base64Decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aN1sAAAAASUVORK5CYII=',
          ),
        };
        for (final entry in fixtures.entries) {
          final file = File('${directory.path}/${entry.key}');
          await file.writeAsBytes(entry.value);
          final doc = await api.uploadDocument(
            PlatformFile(
              name: entry.key,
              size: entry.value.length,
              path: file.path,
            ),
            onProgress: (_) {},
          );
          docIds.add(doc['id'] as String);
          final downloaded = await api.downloadDocument(
            '/v1/documents/${doc['id']}/download',
          );
          expect(await downloaded.readAsBytes(), entry.value);
          await downloaded.parent.delete(recursive: true);
        }
        final docs = await api.listDocuments(query: marker);
        expect(docs.length, 2);
        expect(
          docs.every(
            (d) => (d['revisions'] as List).every(
              (r) => r['extracted_text'] == null,
            ),
          ),
          isTrue,
        );
        final fileEvents = await api
            .streamChat(message: '/archivo $marker')
            .toList()
            .timeout(const Duration(seconds: 45));
        expect(fileEvents.whereType<ChatErrorEvent>(), isEmpty);
        final links = fileEvents
            .whereType<ChatTokenEvent>()
            .map((e) => e.token)
            .join();
        for (final id in docIds) {
          expect(
            links.contains('/v1/documents/$id/versions/1/download'),
            isTrue,
          );
        }

        Future<ChatProposalEvent> propose(String message, DateTime date) async {
          final events = await api
              .streamChat(message: message, date: date)
              .toList()
              .timeout(const Duration(seconds: 150));
          expect(events.whereType<ChatErrorEvent>(), isEmpty);
          expect(events.whereType<ChatDoneEvent>().length, 1);
          final proposals = events.whereType<ChatProposalEvent>().toList();
          expect(proposals.length, 1);
          final proposal = proposals.single;
          pendingIds.add(proposal.proposal.id);
          expect(proposal.proposal.resultingItems.length, 1);
          expect(
            proposal.proposal.resultingItems.single.title.contains(marker),
            isTrue,
          );
          return proposal;
        }

        final create = await propose(
          'Prueba técnica aislada: agenda únicamente "$marker" el 15 de enero de 2030 de 22:00 a 23:00, zona America/Mexico_City. No cambies otras actividades. Genera la propuesta.',
          DateTime(2030, 1, 15),
        );
        final eventId = create.proposal.resultingItems.single.id;
        eventIds.add(eventId);
        expect(await api.confirmProposal(create.proposal.id), isTrue);
        expect(
          (await api.getEvents(date: DateTime(2030, 1, 15)))
              .where((e) => e.id == eventId)
              .length,
          1,
        );
        final move = await propose(
          'Mueve únicamente "$marker", id $eventId, al 16 de enero de 2030 de 23:30 hasta el 17 de enero a las 00:30, America/Mexico_City. Conserva el mismo id.',
          DateTime(2030, 1, 15),
        );
        expect(move.proposal.resultingItems.single.id, eventId);
        expect(await api.confirmProposal(move.proposal.id), isTrue);
        final moved = (await api.getEvents(date: DateTime(2030, 1, 16)))
            .singleWhere((e) => e.id == eventId);
        expect(moved.startTime.toUtc(), DateTime.utc(2030, 1, 17, 5, 30));
        expect(moved.endTime!.toUtc(), DateTime.utc(2030, 1, 17, 6, 30));
        expect(
          (await api.getEvents(date: DateTime(2030, 1, 15)))
              .any((e) => e.id == eventId),
          isFalse,
        );
        final cancel = await propose(
          'Cancela únicamente "$marker", id $eventId. Usa la acción delete y conserva los datos actuales del evento. Genera la propuesta.',
          DateTime(2030, 1, 16),
        );
        expect(cancel.proposal.resultingItems.single.id, eventId);
        expect(cancel.proposal.resultingItems.single.isCancellation, isTrue);
        expect(await api.confirmProposal(cancel.proposal.id), isTrue);
        expect(
          (await api.getEvents(date: DateTime(2030, 1, 16)))
              .any((e) => e.id == eventId),
          isFalse,
        );
      } finally {
        for (final id in pendingIds) {
          final proposal = await api.getProposal(id);
          if (proposal?.status == ProposalStatus.pending) {
            await api.rejectProposal(id);
          }
        }
        for (final id in eventIds) {
          await api.deleteEvent(id);
        }
        for (final id in docIds) {
          await api.deleteDocument(id);
        }
        await directory.delete(recursive: true);
      }
    },
    timeout: const Timeout(Duration(minutes: 10)),
  );
}
