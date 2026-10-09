import 'package:flutter/material.dart';
import '../../../../core/network/api_client.dart';
import '../../../../core/theme/beam_color_notifier.dart';
import '../../../../core/theme/color_schemes.dart';

/// Modal de ajustes y configuración del servidor backend para SARA Agenda.
/// Cumple con la Identidad Visual SARA v0.4.0 (radio modal 16px, controles 8px, cero degradados).
class BeamSettingsSheet extends StatefulWidget {
  const BeamSettingsSheet({super.key});

  @override
  State<BeamSettingsSheet> createState() => _BeamSettingsSheetState();
}

class _BeamSettingsSheetState extends State<BeamSettingsSheet> {
  late final TextEditingController _serverController;
  bool _testingConnection = false;
  String? _connectionStatus;
  bool? _connectionSuccess;

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
      _connectionSuccess = null;
    });

    await ApiClient.instance.setBaseUrl(url);
    final isHealthy = await ApiClient.instance.checkHealth();
    final events = await ApiClient.instance.getEvents();

    if (mounted) {
      setState(() {
        _testingConnection = false;
        _connectionSuccess = isHealthy;
        _connectionStatus = isHealthy
            ? '✓ Conexión establecida (${events.length} actividades disponibles)'
            : '✗ No se pudo alcanzar el servidor en esta dirección';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final isDark = theme.brightness == Brightness.dark;

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
                color: colorScheme.outlineVariant,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 18),

          Row(
            children: [
              Icon(Icons.tune_rounded, size: 22, color: colorScheme.primary),
              const SizedBox(width: 10),
              Text(
                'Ajustes de SARA Agenda',
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w700,
                  color: colorScheme.onSurface,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            'Identidad Visual Unificada SARA v0.4.0 · Comunidad FIME',
            style: theme.textTheme.bodySmall?.copyWith(
              color: colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 16),

          // Tarjeta de información de la identidad
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: colorScheme.secondaryContainer,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                color: colorScheme.outlineVariant,
                width: 1.0,
              ),
            ),
            child: Row(
              children: [
                Container(
                  width: 16,
                  height: 16,
                  decoration: BoxDecoration(
                    color: colorScheme.primary,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Firma de Marca: Ciruela SARA',
                        style: theme.textTheme.labelMedium?.copyWith(
                          fontWeight: FontWeight.w700,
                          color: colorScheme.onSurface,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        isDark ? '#C5AED0 en modo oscuro' : '#6B4F73 en modo claro',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: colorScheme.onSurfaceVariant,
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),

          const SizedBox(height: 20),
          const Divider(height: 1),
          const SizedBox(height: 18),

          Row(
            children: [
              Icon(Icons.all_inclusive_rounded, size: 20, color: colorScheme.primary),
              const SizedBox(width: 10),
              Text(
                'Lazo Perimetral (Analogía al Isotipo)',
                style: theme.textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            'Lazo de luz que recorre el borde del dispositivo, simbolizando el flujo continuo y la identidad de SARA.',
            style: theme.textTheme.bodySmall?.copyWith(
              color: colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 10),

          ValueListenableBuilder<bool>(
            valueListenable: BeamColorConfig.isEnabled,
            builder: (context, enabled, _) {
              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SwitchListTile.adaptive(
                    value: enabled,
                    onChanged: (val) => BeamColorConfig.isEnabled.value = val,
                    title: const Text('Activar lazo perimetral'),
                    contentPadding: EdgeInsets.zero,
                  ),
                  if (enabled) ...[
                    const SizedBox(height: 12),
                    Text(
                      'Trayectoria del lazo:',
                      style: theme.textTheme.labelMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 8),
                    ValueListenableBuilder<BeamPathStyle>(
                      valueListenable: BeamColorConfig.currentPathStyle,
                      builder: (context, currentStyle, _) {
                        return Column(
                          children: BeamPathStyle.values.map((style) {
                            final isSelected = style == currentStyle;
                            return Container(
                              margin: const EdgeInsets.only(bottom: 8),
                              decoration: BoxDecoration(
                                color: isSelected
                                    ? colorScheme.secondaryContainer
                                    : colorScheme.surfaceContainerLow,
                                borderRadius: BorderRadius.circular(8),
                                border: Border.all(
                                  color: isSelected
                                      ? colorScheme.primary
                                      : colorScheme.outlineVariant,
                                  width: isSelected ? 1.5 : 1.0,
                                ),
                              ),
                              child: ListTile(
                                dense: true,
                                contentPadding: const EdgeInsets.symmetric(
                                  horizontal: 12,
                                  vertical: 2,
                                ),
                                leading: Icon(
                                  style == BeamPathStyle.saraAssistantLoop
                                      ? Icons.all_inclusive_rounded
                                      : Icons.crop_square_rounded,
                                  color: isSelected
                                      ? colorScheme.primary
                                      : colorScheme.onSurfaceVariant,
                                ),
                                title: Text(
                                  style.label,
                                  style: theme.textTheme.labelMedium?.copyWith(
                                    fontWeight: isSelected
                                        ? FontWeight.w700
                                        : FontWeight.w500,
                                    color: isSelected
                                        ? colorScheme.onSecondaryContainer
                                        : colorScheme.onSurface,
                                  ),
                                ),
                                subtitle: Text(
                                  style.description,
                                  style: theme.textTheme.bodySmall?.copyWith(
                                    color: colorScheme.onSurfaceVariant,
                                    fontSize: 11,
                                  ),
                                ),
                                trailing: Icon(
                                  isSelected
                                      ? Icons.radio_button_checked_rounded
                                      : Icons.radio_button_unchecked_rounded,
                                  color: isSelected
                                      ? colorScheme.primary
                                      : colorScheme.outline,
                                  size: 20,
                                ),
                                onTap: () =>
                                    BeamColorConfig.currentPathStyle.value = style,
                              ),
                            );
                          }).toList(),
                        );
                      },
                    ),
                    const SizedBox(height: 12),
                    Text(
                      'Paleta cromática:',
                      style: theme.textTheme.labelMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 8),
                    ValueListenableBuilder<BeamThemeOption>(
                      valueListenable: BeamColorConfig.currentOption,
                      builder: (context, current, _) {
                        return Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: BeamColorConfig.options.map((opt) {
                            final isSelected = opt.name == current.name;
                            return ChoiceChip(
                              label: Text(opt.name),
                              selected: isSelected,
                              onSelected: (_) => BeamColorConfig.currentOption.value = opt,
                              avatar: Container(
                                width: 12,
                                height: 12,
                                decoration: BoxDecoration(
                                  color: opt.primaryColor,
                                  shape: BoxShape.circle,
                                ),
                              ),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(8),
                              ),
                            );
                          }).toList(),
                        );
                      },
                    ),
                  ],
                ],
              );
            },
          ),

          const SizedBox(height: 22),
          const Divider(height: 1),
          const SizedBox(height: 18),

          Row(
            children: [
              const Icon(Icons.dns_rounded, size: 20),
              const SizedBox(width: 10),
              Text(
                'Servidor Backend & API',
                style: theme.textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            'Dirección de la API en vivo o del entorno de desarrollo.',
            style: theme.textTheme.bodySmall?.copyWith(
              color: colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 12),

          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _serverController,
                  decoration: InputDecoration(
                    hintText: 'https://walteragenda.pedroibarra.dev',
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: 14,
                      vertical: 12,
                    ),
                    filled: true,
                    fillColor: colorScheme.surfaceContainerLow,
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8),
                      borderSide: BorderSide(color: colorScheme.outline),
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8),
                      borderSide: BorderSide(color: colorScheme.outlineVariant),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8),
                      borderSide: BorderSide(color: colorScheme.primary, width: 2),
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
                    borderRadius: BorderRadius.circular(8),
                  ),
                  minimumSize: const Size(80, 48),
                ),
                child: _testingConnection
                    ? SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: colorScheme.onPrimary,
                        ),
                      )
                    : const Text('Guardar'),
              ),
            ],
          ),
          const SizedBox(height: 8),

          // Acceso rápido para restaurar servidor oficial en cite-server
          Wrap(
            spacing: 8,
            runSpacing: 6,
            children: [
              ActionChip(
                label: const Text('Servidor Walter (cite-server)'),
                onPressed: () {
                  _serverController.text = 'https://walteragenda.pedroibarra.dev';
                  _testAndSaveServer();
                },
              ),
              ActionChip(
                label: const Text('Local (127.0.0.1:8001)'),
                onPressed: () {
                  _serverController.text = 'http://127.0.0.1:8001';
                  _testAndSaveServer();
                },
              ),
            ],
          ),

          if (_connectionStatus != null) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: _connectionSuccess == true
                    ? (isDark ? SaraColors.darkSuccessSoft : SaraColors.lightSuccessSoft)
                    : (isDark ? SaraColors.darkErrorSoft : SaraColors.lightErrorSoft),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                children: [
                  Icon(
                    _connectionSuccess == true
                        ? Icons.check_circle_rounded
                        : Icons.error_outline_rounded,
                    size: 16,
                    color: _connectionSuccess == true
                        ? (isDark ? SaraColors.darkSuccess : SaraColors.lightSuccess)
                        : (isDark ? SaraColors.darkError : SaraColors.lightError),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      _connectionStatus!,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: _connectionSuccess == true
                            ? (isDark ? SaraColors.darkSuccess : SaraColors.lightSuccess)
                            : (isDark ? SaraColors.darkError : SaraColors.lightError),
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}
