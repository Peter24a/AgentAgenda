import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:agent_agenda/main.dart';
import 'package:agent_agenda/core/network/space_session.dart' as session;
import 'package:flutter/material.dart';

import 'space_session_test.dart' show MemorySessionStore, syntheticGrant;

void main() {
  setUpAll(() async {
    await initializeDateFormatting('es', null);
  });

  testWidgets('App smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(
      AgentAgendaApp(
        manager: session.SpaceSessionManager(store: MemorySessionStore()),
      ),
    );
    expect(find.text('AgentAgenda'), findsOneWidget);
    expect(find.text('Conecta tu espacio'), findsOneWidget);
    expect(find.text('Conectar mi espacio'), findsOneWidget);
    await tester.tap(find.text('Conectar mi espacio'));
    await tester.pump();
    expect(
      find.text('Introduce el código o enlace de activación que recibiste.'),
      findsOneWidget,
    );
  });

  testWidgets(
    'Disconnected session removes account screen and pushed private routes',
    (tester) async {
      final manager = session.SpaceSessionManager(store: MemorySessionStore());
      manager.session = session.SpaceSession.fromJson(
        syntheticGrant(),
        session.defaultAgendaServer,
      );
      manager.state = session.ConnectionState.connected;
      await tester.pumpWidget(
        AgentAgendaApp(
          manager: manager,
          connectedBuilder: (context) => Scaffold(
            body: Builder(
              builder: (context) => TextButton(
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => const Scaffold(
                      body: Text('Contenido privado sintético'),
                    ),
                  ),
                ),
                child: const Text('Abrir documento'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Abrir documento'));
      await tester.pumpAndSettle();
      expect(find.text('Contenido privado sintético'), findsOneWidget);
      await manager.disconnect();
      await tester.pumpAndSettle();
      expect(find.text('Contenido privado sintético'), findsNothing);
      expect(find.text('Conecta tu espacio'), findsOneWidget);
    },
  );
}
