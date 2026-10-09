import 'package:flutter/material.dart';

import '../../core/branding/sara_brand_mark.dart';
import '../../core/network/space_session.dart' as session;
import '../../core/service_links.dart';

class ActivationScreen extends StatefulWidget {
  final session.SpaceSessionManager manager;
  const ActivationScreen({super.key, required this.manager});
  @override
  State<ActivationScreen> createState() => _ActivationScreenState();
}

class _ActivationScreenState extends State<ActivationScreen> {
  final _code = TextEditingController();
  final _server = TextEditingController(text: session.defaultAgendaServer);
  final _name = TextEditingController(text: 'Mi teléfono Android');
  final _form = GlobalKey<FormState>();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _code.dispose();
    _server.dispose();
    _name.dispose();
    super.dispose();
  }

  Future<void> _activate() async {
    if (!_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.manager.activate(
        _code.text,
        server: _server.text,
        deviceName: _name.text,
      );
    } catch (_) {
      if (mounted) setState(() => _error = widget.manager.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(28),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: Form(
                key: _form,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Center(
                      child: SaraBrandMark(
                        size: 64,
                        color: theme.colorScheme.primary,
                      ),
                    ),
                    const SizedBox(height: 24),
                    Text(
                      'AgentAgenda',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.headlineLarge,
                    ),
                    const SizedBox(height: 12),
                    Text(
                      'Conecta tu espacio',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.titleLarge,
                    ),
                    const SizedBox(height: 12),
                    const Text(
                      'Introduce el código o enlace que te entregó el administrador. Si reinstalaste la app, tu contenido sigue en tu espacio.',
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 28),
                    TextFormField(
                      controller: _code,
                      enabled: !_busy,
                      autocorrect: false,
                      enableSuggestions: false,
                      decoration: const InputDecoration(
                        labelText: 'Código o enlace de activación',
                        border: OutlineInputBorder(),
                      ),
                      validator: (value) {
                        try {
                          session.ActivationInput.parse(
                            value ?? '',
                            _server.text,
                          );
                          return null;
                        } on session.ConnectionException catch (error) {
                          return error.message;
                        }
                      },
                    ),
                    const SizedBox(height: 16),
                    TextFormField(
                      controller: _name,
                      enabled: !_busy,
                      maxLength: 128,
                      decoration: const InputDecoration(
                        labelText: 'Nombre de este dispositivo',
                        border: OutlineInputBorder(),
                      ),
                    ),
                    ExpansionTile(
                      title: const Text('Dirección del servicio'),
                      tilePadding: EdgeInsets.zero,
                      children: [
                        TextFormField(
                          controller: _server,
                          enabled: !_busy,
                          keyboardType: TextInputType.url,
                          autocorrect: false,
                          enableSuggestions: false,
                          decoration: const InputDecoration(
                            labelText: 'Servidor HTTPS',
                            border: OutlineInputBorder(),
                          ),
                        ),
                        const SizedBox(height: 16),
                      ],
                    ),
                    if (_error ?? widget.manager.message
                        case final String error) ...[
                      const SizedBox(height: 12),
                      Text(
                        error,
                        style: TextStyle(color: theme.colorScheme.error),
                      ),
                    ],
                    const SizedBox(height: 20),
                    FilledButton.icon(
                      onPressed: _busy ? null : _activate,
                      icon: _busy
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.key_rounded),
                      label: Text(
                        _busy ? 'Conectando…' : 'Conectar mi espacio',
                      ),
                    ),
                    const SizedBox(height: 24),
                    const ServiceLinks(),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class ConnectionRecoveryScreen extends StatelessWidget {
  final session.SpaceSessionManager manager;
  const ConnectionRecoveryScreen({super.key, required this.manager});
  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.cloud_off_rounded, size: 52),
              const SizedBox(height: 20),
              Text(
                manager.session?.spaceName ?? 'Tu espacio',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: 12),
              Text(
                manager.message ?? 'Verificando tu conexión…',
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              if (manager.state == session.ConnectionState.checking)
                const CircularProgressIndicator()
              else ...[
                FilledButton(
                  onPressed: manager.verify,
                  child: const Text('Reintentar conexión'),
                ),
                TextButton(
                  onPressed: manager.logout,
                  child: const Text('Desconectar este dispositivo'),
                ),
              ],
            ],
          ),
        ),
      ),
    ),
  );
}
