import 'package:flutter/material.dart';

import '../../../../core/network/api_client.dart';

class AiResponseReportDialog extends StatefulWidget {
  final String messageId;
  final String responseText;
  const AiResponseReportDialog({
    super.key,
    required this.messageId,
    required this.responseText,
  });

  @override
  State<AiResponseReportDialog> createState() => _AiResponseReportDialogState();
}

class _AiResponseReportDialogState extends State<AiResponseReportDialog> {
  final _details = TextEditingController();
  AiReportReason _reason = AiReportReason.harmful;
  bool _sending = false;
  String? _error;

  @override
  void dispose() {
    _details.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    setState(() {
      _sending = true;
      _error = null;
    });
    try {
      await ApiClient.instance.reportAiResponse(
        messageId: widget.messageId,
        reason: _reason,
        details: _details.text,
      );
      if (mounted) Navigator.pop(context, true);
    } catch (_) {
      if (mounted) {
        setState(() {
          _sending = false;
          _error = 'No se pudo enviar el reporte. Conservamos tu comentario; intenta de nuevo.';
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !_sending,
    child: AlertDialog(
      title: const Text('Reportar respuesta de IA'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Compartirás esta respuesta con soporte para revisión, junto con '
              'el motivo y tu comentario. Tu conversación completa no se envía.',
            ),
            const SizedBox(height: 16),
            Text(
              'Respuesta elegida',
              style: Theme.of(context).textTheme.labelLarge,
            ),
            const SizedBox(height: 6),
            Container(
              padding: const EdgeInsets.all(12),
              constraints: const BoxConstraints(maxHeight: 160),
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.surfaceContainerLow,
                borderRadius: BorderRadius.circular(8),
              ),
              child: SingleChildScrollView(
                child: SelectableText(widget.responseText),
              ),
            ),
            const SizedBox(height: 18),
            DropdownButtonFormField<AiReportReason>(
              initialValue: _reason,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Motivo'),
              items: AiReportReason.values
                  .map(
                    (reason) => DropdownMenuItem(
                      value: reason,
                      child: Text(reason.label, maxLines: 2),
                    ),
                  )
                  .toList(),
              onChanged: _sending
                  ? null
                  : (reason) {
                      if (reason != null) setState(() => _reason = reason);
                    },
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _details,
              enabled: !_sending,
              maxLength: 2000,
              maxLines: 4,
              decoration: const InputDecoration(
                labelText: 'Comentario (opcional)',
                hintText: 'Describe el problema sin añadir datos personales innecesarios.',
                border: OutlineInputBorder(),
              ),
            ),
            if (_error != null)
              Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: _sending ? null : () => Navigator.pop(context, false),
          child: const Text('Cancelar'),
        ),
        FilledButton.icon(
          onPressed: _sending ? null : _send,
          icon: _sending
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.flag_outlined),
          label: Text(_sending ? 'Enviando…' : 'Enviar reporte'),
        ),
      ],
    ),
  );
}
