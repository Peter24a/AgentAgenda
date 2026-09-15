import 'package:flutter/material.dart';
import '../../../../core/network/api_client.dart';
import '../../../../core/theme/beam_color_notifier.dart';

/// Modal para personalizar el color del lazo luminoso ("gusanito")
/// y configurar la dirección del servidor backend con LLM.
class BeamSettingsSheet extends StatefulWidget {
  const BeamSettingsSheet({super.key});

  @override
  State<BeamSettingsSheet> createState() => _BeamSettingsSheetState();
}

class _BeamSettingsSheetState extends State<BeamSettingsSheet> {
  late final TextEditingController _serverController;
  bool _testingConnection = false;
  String? _connectionStatus;

  @override
  void initState() {
    super.initState();
    _serverController = TextEditingController(text: ApiClient.instance.baseUrl);
  }

  @override
  void dispose() {
    _serverController.dispose();
    super.dispose();
  }

  Future<void> _testAndSaveServer() async {
    final url = _serverController.text.trim();
    if (url.isEmpty) return;

    setState(() {
      _testingConnection = true;
      _connectionStatus = null;
    });

    await ApiClient.instance.setBaseUrl(url);
    final isHealthy = await ApiClient.instance.checkHealth();
    final events = await ApiClient.instance.getEvents();

    if (mounted) {
      setState(() {
        _testingConnection = false;
        _connectionStatus = isHealthy
            ? '✓ Conectado exitosamente (${events.length} actividades)'
            : '✗ No se pudo alcanzar el backend en esa dirección';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Center(
            child: Container(
              width: 36,
              height: 4,
              decoration: BoxDecoration(
                color: theme.colorScheme.outlineVariant,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 18),

          Row(
            children: [
              const Icon(Icons.palette_outlined, size: 22),
              const SizedBox(width: 10),
              Text(
                'Color del destello luminoso',
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            'Elige entre el espectro multicolor dinámico o un tono sólido.',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 16),

          ValueListenableBuilder<BeamThemeOption>(
            valueListenable: BeamColorConfig.currentOption,
            builder: (context, activeOption, _) {
              return Wrap(
                spacing: 10,
                runSpacing: 10,
                children: BeamColorConfig.options.map((option) {
                  final isSelected = activeOption.name == option.name;

                  return InkWell(
                    onTap: () {
                      BeamColorConfig.currentOption.value = option;
                    },
                    borderRadius: BorderRadius.circular(24),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 14,
                        vertical: 9,
                      ),
                      decoration: BoxDecoration(
                        color: isSelected
                            ? option.primaryColor.withValues(alpha: 0.18)
                            : theme.colorScheme.surfaceContainerHigh,
                        borderRadius: BorderRadius.circular(24),
                        border: Border.all(
                          color: isSelected
                              ? option.primaryColor
                              : Colors.transparent,
                          width: 1.8,
                        ),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Container(
                            width: 20,
                            height: 20,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              gradient: option.isMulticolor
                                  ? const SweepGradient(
                                      colors: [
                                        Color(0xFF4285F4),
                                        Color(0xFF9C27B0),
                                        Color(0xFFEA4335),
                                        Color(0xFFFBBC05),
                                        Color(0xFF34A853),
                                        Color(0xFF26C6DA),
                                        Color(0xFF4285F4),
                                      ],
                                    )
                                  : null,
                              color: option.isMulticolor
                                  ? null
                                  : option.primaryColor,
                              boxShadow: [
                                BoxShadow(
                                  color: option.primaryColor.withValues(alpha: 0.35),
                                  blurRadius: 6,
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(width: 8),
                          Text(
                            option.name,
                            style: theme.textTheme.labelMedium?.copyWith(
                              fontWeight: isSelected
                                  ? FontWeight.w800
                                  : FontWeight.w500,
                              color: isSelected
                                  ? theme.colorScheme.onSurface
                                  : theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                }).toList(),
              );
            },
          ),

          const SizedBox(height: 24),
          const Divider(height: 1),
          const SizedBox(height: 18),

          Row(
            children: [
              const Icon(Icons.dns_rounded, size: 22),
              const SizedBox(width: 10),
              Text(
                'Servidor Backend & LLM',
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            'URL del servicio FastAPI conectado al Qwen 27B local.',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 12),

          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _serverController,
                  decoration: InputDecoration(
                    hintText: 'https://agenda.ici-labs.com o IP:8001',
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: 16,
                      vertical: 12,
                    ),
                    filled: true,
                    fillColor: theme.colorScheme.surfaceContainerHigh,
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(16),
                      borderSide: BorderSide.none,
                    ),
                  ),
                  style: theme.textTheme.bodyMedium,
                ),
              ),
              const SizedBox(width: 8),
              FilledButton(
                onPressed: _testingConnection ? null : _testAndSaveServer,
                style: FilledButton.styleFrom(
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(16),
                  ),
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                ),
                child: _testingConnection
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Guardar'),
              ),
            ],
          ),
          if (_connectionStatus != null) ...[
            const SizedBox(height: 8),
            Text(
              _connectionStatus!,
              style: theme.textTheme.labelMedium?.copyWith(
                color: theme.colorScheme.primary,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
