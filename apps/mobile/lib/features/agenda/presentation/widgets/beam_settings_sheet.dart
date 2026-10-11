import 'package:flutter/material.dart';

import '../../../../core/network/api_client.dart';
import '../../../../core/network/space_session.dart' as session;
import '../../../../core/service_links.dart';
import '../../../../core/theme/beam_color_notifier.dart';
import '../../../../core/theme/color_schemes.dart';

/// Ajustes de apariencia y conexión del espacio.
class BeamSettingsSheet extends StatefulWidget {
  const BeamSettingsSheet({super.key});

  @override
  State<BeamSettingsSheet> createState() => _BeamSettingsSheetState();
}

class _BeamSettingsSheetState extends State<BeamSettingsSheet> {
  bool _testingConnection = false;
  String? _connectionStatus;
  bool? _connectionSuccess;

  Future<void> _testConnection() async {
    setState(() {
      _testingConnection = true;
      _connectionStatus = null;
    });
    await ApiClient.instance.sessions.verify();
    if (!mounted) return;
    final connected =
        ApiClient.instance.sessions.state == session.ConnectionState.connected;
    setState(() {
      _testingConnection = false;
      _connectionSuccess = connected;
      _connectionStatus = connected
          ? 'Tu espacio está conectado.'
          : ApiClient.instance.sessions.message ??
                'Conecta tu espacio para continuar.';
    });
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
              Expanded(
                child: Text(
                  'Ajustes',
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                    color: colorScheme.onSurface,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            'Personaliza tu agenda y administra tu espacio.',
            style: theme.textTheme.bodySmall?.copyWith(
              color: colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 24),
          const Divider(height: 1),
          const SizedBox(height: 18),

          Row(
            children: [
              Icon(
                Icons.auto_awesome_outlined,
                size: 20,
                color: colorScheme.primary,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Lazo de luz',
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            'Elige cómo se ilumina el borde de tu pantalla.',
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
                    title: const Text('Mostrar lazo de luz'),
                    contentPadding: EdgeInsets.zero,
                  ),
                  if (enabled) ...[
                    const SizedBox(height: 12),
                    Text(
                      'Recorrido',
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
                            return Padding(
                              padding: const EdgeInsets.only(bottom: 8),
                              child: Material(
                                color: isSelected
                                    ? colorScheme.secondaryContainer
                                    : colorScheme.surfaceContainerLow,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(8),
                                  side: BorderSide(
                                    color: isSelected
                                        ? colorScheme.primary
                                        : colorScheme.outlineVariant,
                                    width: isSelected ? 1.5 : 1.0,
                                  ),
                                ),
                                clipBehavior: Clip.antiAlias,
                                child: ListTile(
                                  selected: isSelected,
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
                                    style: theme.textTheme.labelMedium
                                        ?.copyWith(
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
                                      BeamColorConfig.currentPathStyle.value =
                                          style,
                                ),
                              ),
                            );
                          }).toList(),
                        );
                      },
                    ),
                    const SizedBox(height: 12),
                    Text(
                      'Color',
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
                              onSelected: (_) =>
                                  BeamColorConfig.currentOption.value = opt,
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

          Text('Tu espacio', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          ListenableBuilder(
            listenable: ApiClient.instance.sessions,
            builder: (context, _) {
              final sessions = ApiClient.instance.sessions;
              final (icon, status) = switch (sessions.state) {
                session.ConnectionState.connected => (
                  Icons.cloud_done_outlined,
                  'Conectado',
                ),
                session.ConnectionState.checking => (
                  Icons.sync_rounded,
                  'Verificando conexión…',
                ),
                session.ConnectionState.unavailable => (
                  Icons.cloud_off_outlined,
                  'Sin conexión por el momento',
                ),
                session.ConnectionState.disconnected => (
                  Icons.link_off_rounded,
                  'Sin conectar',
                ),
              };
              return Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: colorScheme.surfaceContainerLow,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: colorScheme.outlineVariant),
                ),
                child: Row(
                  children: [
                    Icon(icon, color: colorScheme.primary, size: 22),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            sessions.session?.spaceName ??
                                'Tu espacio personal',
                            style: theme.textTheme.titleSmall,
                          ),
                          const SizedBox(height: 2),
                          Text(
                            status,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: colorScheme.onSurfaceVariant,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              );
            },
          ),
          const SizedBox(height: 16),
          OutlinedButton.icon(
            onPressed: _testingConnection ? null : _testConnection,
            icon: _testingConnection
                ? const SizedBox.square(
                    dimension: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.refresh_rounded),
            label: Text(
              _testingConnection ? 'Verificando…' : 'Comprobar conexión',
            ),
          ),
          TextButton.icon(
            onPressed: () async {
              final confirmed = await showDialog<bool>(
                context: context,
                builder: (context) => AlertDialog(
                  title: const Text('¿Desconectar este teléfono?'),
                  content: const Text(
                    'Tu contenido seguirá guardado en tu espacio. Necesitarás un código nuevo para volver a conectar este teléfono o cambiar de espacio.',
                  ),
                  actions: [
                    TextButton(
                      onPressed: () => Navigator.pop(context, false),
                      child: const Text('Cancelar'),
                    ),
                    FilledButton(
                      onPressed: () => Navigator.pop(context, true),
                      child: const Text('Desconectar'),
                    ),
                  ],
                ),
              );
              if (confirmed == true) await ApiClient.instance.sessions.logout();
            },
            icon: const Icon(Icons.logout_rounded),
            label: const Text('Desconectar o cambiar de espacio'),
          ),
          const SizedBox(height: 16),
          const Divider(),
          const ServiceLinks(),
          TextButton.icon(
            onPressed: () => showLicensePage(
              context: context,
              applicationName: 'AgentAgenda',
              applicationVersion: '2.0.3',
            ),
            icon: const Icon(Icons.description_outlined, size: 18),
            label: const Text('Licencias de código abierto'),
          ),

          if (_connectionStatus != null) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: _connectionSuccess == true
                    ? (isDark
                          ? SaraColors.darkSuccessSoft
                          : SaraColors.lightSuccessSoft)
                    : (isDark
                          ? SaraColors.darkErrorSoft
                          : SaraColors.lightErrorSoft),
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
                        ? (isDark
                              ? SaraColors.darkSuccess
                              : SaraColors.lightSuccess)
                        : (isDark
                              ? SaraColors.darkError
                              : SaraColors.lightError),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      _connectionStatus!,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: _connectionSuccess == true
                            ? (isDark
                                  ? SaraColors.darkSuccess
                                  : SaraColors.lightSuccess)
                            : (isDark
                                  ? SaraColors.darkError
                                  : SaraColors.lightError),
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
