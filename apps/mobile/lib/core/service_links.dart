import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

const privacyPolicyUrl = 'https://privacy.ici-labs.com/agentagenda/';
const supportUrl = 'https://agenda-api.pedroibarra.dev/soporte';
const aiProcessingNotice =
    'El asistente procesa tus mensajes y el contenido que autorices en el servidor '
    'de AgentAgenda. La IA puede equivocarse; revisa sus respuestas y propuestas.';

class ServiceLinks extends StatelessWidget {
  final bool showAiNotice;
  const ServiceLinks({super.key, this.showAiNotice = true});

  static const _channel = MethodChannel('agent_agenda/service_links');

  Future<void> _open(BuildContext context, String url) async {
    var opened = false;
    try {
      opened =
          await _channel.invokeMethod<bool>('openHttps', {'url': url}) ?? false;
    } on PlatformException {
      // Show a copyable address if the device has no browser available.
    } on MissingPluginException {
      // Desktop test/preview hosts may not have the Android channel.
    }
    if (opened || !context.mounted) return;
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Abrir en tu navegador'),
        content: SelectableText(url),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cerrar'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      if (showAiNotice) ...[
        Text(aiProcessingNotice, style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: 8),
      ],
      Wrap(
        spacing: 4,
        children: [
          TextButton.icon(
            onPressed: () => _open(context, privacyPolicyUrl),
            icon: const Icon(Icons.privacy_tip_outlined, size: 18),
            label: const Text('Privacidad'),
          ),
          TextButton.icon(
            onPressed: () => _open(context, supportUrl),
            icon: const Icon(Icons.help_outline_rounded, size: 18),
            label: const Text('Soporte'),
          ),
          TextButton.icon(
            onPressed: () => _open(context, '$supportUrl#eliminacion'),
            icon: const Icon(Icons.delete_outline_rounded, size: 18),
            label: const Text('Solicitar eliminación de datos'),
          ),
        ],
      ),
    ],
  );
}
