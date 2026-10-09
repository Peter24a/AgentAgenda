import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'core/network/api_client.dart';
import 'core/network/space_session.dart' as session;
import 'core/notifications/follow_up_service.dart';
import 'core/theme/app_theme.dart';
import 'features/agenda/presentation/screens/agenda_screen.dart';
import 'features/activation/activation_screen.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeDateFormatting('es', null);
  await ApiClient.instance.init();
  await FollowUpService.instance.init();
  final sessions = session.SpaceSessionManager.instance;
  final apiCleanup = sessions.onDisconnect;
  sessions.onDisconnect = () async {
    await apiCleanup?.call();
    // A renewal can fail inside notification synchronization. Queue cleanup
    // without waiting on that same synchronization operation.
    unawaited(FollowUpService.instance.selectSpace('disconnected'));
  };
  await FollowUpService.instance.selectSpace(
    sessions.session == null
        ? 'disconnected'
        : '${sessions.session!.server}|${sessions.session!.spaceId}',
  );
  sessions.addListener(() {
    final current = sessions.session;
    if (current != null &&
        sessions.state == session.ConnectionState.connected) {
      unawaited(
        FollowUpService.instance.selectSpace(
          '${current.server}|${current.spaceId}',
        ),
      );
    }
  });

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
class AgentAgendaApp extends StatefulWidget {
  final session.SpaceSessionManager? manager;
  final Widget Function(BuildContext)? connectedBuilder;
  const AgentAgendaApp({super.key, this.manager, this.connectedBuilder});

  @override
  State<AgentAgendaApp> createState() => _AgentAgendaAppState();
}

class _AgentAgendaAppState extends State<AgentAgendaApp> {
  final _navigator = GlobalKey<NavigatorState>();
  late final session.SpaceSessionManager manager =
      widget.manager ?? session.SpaceSessionManager.instance;

  @override
  void initState() {
    super.initState();
    manager.addListener(_changed);
  }

  void _changed() {
    if (!mounted) return;
    if (manager.state != session.ConnectionState.connected) {
      _navigator.currentState?.popUntil((route) => route.isFirst);
    }
    setState(() {});
  }

  @override
  void dispose() {
    manager.removeListener(_changed);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AgentAgenda',
      navigatorKey: _navigator,
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: ThemeMode.system,
      home: manager.session == null
          ? ActivationScreen(manager: manager)
          : manager.state == session.ConnectionState.connected
          ? KeyedSubtree(
              key: ValueKey(
                '${manager.session!.server}|${manager.session!.spaceId}|${manager.generation}',
              ),
              child:
                  widget.connectedBuilder?.call(context) ??
                  const AgendaScreen(),
            )
          : ConnectionRecoveryScreen(manager: manager),
    );
  }
}
