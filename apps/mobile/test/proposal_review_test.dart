import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:agent_agenda/features/agenda/models/agenda_item.dart';
import 'package:agent_agenda/features/agenda/models/agent_proposal.dart';
import 'package:agent_agenda/features/agenda/presentation/widgets/agent_proposal_card.dart';

void main() {
  testWidgets('Proposal shows cancellation and both dates before approval', (
    tester,
  ) async {
    var accepted = false;
    final proposal = AgentProposal(
      id: 'test',
      summary: 'Cancelar prueba',
      reason: 'Solicitud actual',
      createdAt: DateTime(2030),
      resultingItems: [
        AgendaItem(
          id: 'event',
          title: 'Prueba nocturna',
          isCancellation: true,
          startTime: DateTime(2030, 1, 16, 23, 30),
          endTime: DateTime(2030, 1, 17, 0, 30),
          category: ActivityCategory.general,
        ),
      ],
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AgentProposalCard(
            proposal: proposal,
            onAccept: () => accepted = true,
            onDismiss: () {},
          ),
        ),
      ),
    );
    expect(find.textContaining('Cancelar: Prueba nocturna'), findsOneWidget);
    expect(find.textContaining('16/01/2030 23:30'), findsOneWidget);
    expect(find.textContaining('17/01/2030 00:30'), findsOneWidget);
    expect(accepted, isFalse);
    await tester.tap(find.text('Aprobar'));
    expect(accepted, isTrue);
  });
}
