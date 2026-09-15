import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:agent_agenda/features/chat/presentation/screens/chat_screen.dart';

void main() {
  testWidgets('ChatScreen renders markdown elements properly', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: ChatScreen(),
      ),
    );
    await tester.pumpAndSettle();

    // Verify MarkdownBody is used for the assistant message
    expect(find.byType(MarkdownBody), findsWidgets);

    // Verify the initial welcome text is present
    expect(find.textContaining('asistente de agenda'), findsOneWidget);
  });
}
