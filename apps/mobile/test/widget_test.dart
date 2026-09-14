import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:agent_agenda/main.dart';

void main() {
  setUpAll(() async {
    await initializeDateFormatting('es', null);
  });

  testWidgets('App smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(const AgentAgendaApp());
    expect(find.text('AgentAgenda'), findsNothing);
  });
}
