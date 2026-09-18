import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'core/network/api_client.dart';
import 'core/notifications/follow_up_service.dart';
import 'core/theme/app_theme.dart';
import 'features/agenda/presentation/screens/agenda_screen.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeDateFormatting('es', null);
  await ApiClient.instance.init();
  await FollowUpService.instance.init();

  // Configurar barra de estado transparente estilo Pixel edge-to-edge
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      systemNavigationBarColor: Colors.transparent,
    ),
  );

  runApp(const AgentAgendaApp());
}

/// Aplicación principal de AgentAgenda.
class AgentAgendaApp extends StatelessWidget {
  const AgentAgendaApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SARA Agenda',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: ThemeMode.system,
      home: const AgendaScreen(),
    );
  }
}
