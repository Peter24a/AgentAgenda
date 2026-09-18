import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:timezone/timezone.dart' as tz;

import '../../../../../core/notifications/follow_up_plan.dart';
import '../../../../../core/notifications/follow_up_service.dart';
import '../../../../../core/notifications/system_clock.dart';

class NotificationSettingsScreen extends StatefulWidget {
  final FollowUpService? service;
  const NotificationSettingsScreen({super.key, this.service});
  @override
  State<NotificationSettingsScreen> createState() =>
      _NotificationSettingsScreenState();
}

class _NotificationSettingsScreenState extends State<NotificationSettingsScreen>
    with WidgetsBindingObserver {
  late final FollowUpService service =
      widget.service ?? FollowUpService.instance;
  bool _clockBusy = false;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    service.init();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) service.refreshPermissions();
  }

  String _time(int hour, int minute) =>
      '${hour.toString().padLeft(2, '0')}:${minute.toString().padLeft(2, '0')}';
  void _message(String text) {
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
    }
  }

  Future<void> _pickTime({required bool alarm}) async {
    final settings = service.settings;
    final selected = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(
        hour: alarm ? settings.alarmHour : settings.quietHour,
        minute: alarm ? settings.alarmMinute : settings.quietMinute,
      ),
    );
    if (selected == null) return;
    final next = alarm
        ? service.settings.copyWith(
            alarmHour: selected.hour,
            alarmMinute: selected.minute,
          )
        : service.settings.copyWith(
            quietHour: selected.hour,
            quietMinute: selected.minute,
          );
    if (next.alarmHour * 60 + next.alarmMinute >=
        next.quietHour * 60 + next.quietMinute) {
      _message(
        'El inicio del descanso debe ser posterior a la hora de despertar.',
      );
      return;
    }
    await service.saveSettings(next);
  }

  Future<void> _openClock() async {
    setState(() => _clockBusy = true);
    final settings = service.settings;
    final opened = await SystemClock.openAlarm(
      hour: settings.alarmHour,
      minute: settings.alarmMinute,
      weekdays: settings.alarmWeekdays,
    );
    if (!mounted) return;
    setState(() => _clockBusy = false);
    _message(
      opened
          ? 'Se abrió el Reloj. Revisa allí que la alarma esté guardada y activa.'
          : 'No se pudo abrir un Reloj compatible. Configura esta alarma en la app Reloj de tu teléfono.',
    );
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Avisos y despertador')),
    body: ListenableBuilder(
      listenable: service,
      builder: (context, _) {
        final settings = service.settings;
        final alarmTime = _time(settings.alarmHour, settings.alarmMinute);
        final quietTime = _time(settings.quietHour, settings.quietMinute);
        final disabled =
            service.busy || !service.supported || !service.initialized;
        return SafeArea(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
            children: [
              if (!service.supported)
                const _Notice(
                  'Estos ajustes requieren Android. No se programarán avisos desde esta plataforma.',
                ),
              if (service.busy) const LinearProgressIndicator(),
              _Section(
                title: 'Seguimientos variables',
                icon: Icons.notifications_active_outlined,
                children: [
                  const Text(
                    'Una pregunta breve al finalizar bloques de 20 a 89 minutos, o 15 minutos antes del final de bloques más largos. No son avisos a intervalos fijos.',
                  ),
                  SwitchListTile.adaptive(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Activar seguimientos'),
                    subtitle: Text(
                      settings.enabled
                          ? (service.permissionGranted
                                ? 'Activados en esta app'
                                : 'Activados aquí; Android no permite mostrarlos')
                          : 'Desactivados',
                    ),
                    value: settings.enabled,
                    onChanged: disabled
                        ? null
                        : (enabled) async {
                            if (enabled) {
                              await service.enableFromUserAction();
                            } else {
                              await service.saveSettings(
                                settings.copyWith(enabled: false),
                              );
                            }
                          },
                  ),
                  Text(
                    service.permissionGranted
                        ? 'Permiso de notificaciones: concedido. El canal puede silenciarse en Android.'
                        : 'Permiso de notificaciones: no concedido o desactivado.',
                  ),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      OutlinedButton.icon(
                        onPressed: disabled
                            ? null
                            : () async {
                                if (!await service.openPermissionSettings()) {
                                  _message(
                                    'No se pudieron abrir los ajustes de notificaciones.',
                                  );
                                }
                              },
                        icon: const Icon(Icons.settings_outlined),
                        label: const Text('Permisos en Android'),
                      ),
                      OutlinedButton.icon(
                        onPressed: disabled
                            ? null
                            : () async {
                                final sent = await service
                                    .showTestFromUserAction();
                                _message(
                                  sent
                                      ? 'Prueba enviada ahora. Revisa el panel de notificaciones.'
                                      : 'No se pudo mostrar la prueba. Revisa los permisos.',
                                );
                              },
                        icon: const Icon(Icons.notification_add_outlined),
                        label: const Text('Enviar prueba ahora'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 14),
                  DropdownButtonFormField<int>(
                    initialValue: settings.dailyLimit,
                    decoration: const InputDecoration(
                      labelText: 'Máximo de avisos planificados por día',
                      border: OutlineInputBorder(),
                    ),
                    items: [2, 4, 6, 8]
                        .map(
                          (number) => DropdownMenuItem(
                            value: number,
                            child: Text('$number avisos'),
                          ),
                        )
                        .toList(),
                    onChanged: disabled
                        ? null
                        : (number) {
                            if (number != null) {
                              service.saveSettings(
                                settings.copyWith(dailyLimit: number),
                              );
                            }
                          },
                  ),
                  const SizedBox(height: 14),
                  const Text(
                    'Se separan al menos 75 minutos. Se omiten actividades completadas, de sueño y propuestas o bloques provisionales/condicionales sin aceptar.',
                  ),
                  const SizedBox(height: 8),
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Inicio del descanso'),
                    subtitle: Text(
                      'Silencio planificado diario: $quietTime–$alarmTime',
                    ),
                    trailing: TextButton(
                      onPressed: disabled
                          ? null
                          : () => _pickTime(alarm: false),
                      child: Text(quietTime),
                    ),
                  ),
                  Text(
                    'No se programan seguimientos antes de $alarmTime, incluso en días sin despertador. Se dejan márgenes antes del descanso y de los bloques de sueño de tu agenda.',
                  ),
                ],
              ),
              _Section(
                title: 'Horario sincronizado',
                icon: Icons.sync_rounded,
                children: [
                  Text(
                    service.lastSynced == null
                        ? 'Todavía no hay un horario sincronizado para los avisos.'
                        : 'Última sincronización: ${DateFormat("d MMM, HH:mm", 'es').format(tz.TZDateTime.from(service.lastSynced!, tz.getLocation(agendaTimezone)))} (Ciudad de México).',
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '${service.planned.length} avisos pendientes para los próximos siete días.',
                  ),
                  if (service.error != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 10),
                      child: _Notice(service.error!),
                    ),
                  const SizedBox(height: 10),
                  const Text(
                    'Los avisos ya programados permanecen en el teléfono sin conexión. Los cambios realizados fuera de la app llegan al volver a abrirla o sincronizar; no hay notificaciones push del servidor.',
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Android puede retrasar avisos aproximados o restringirlos por batería. Forzar la detención de la app puede impedirlos. Para despertar, utiliza el Reloj.',
                  ),
                  const SizedBox(height: 8),
                  FilledButton.tonalIcon(
                    onPressed: disabled || !settings.enabled
                        ? null
                        : service.synchronize,
                    icon: const Icon(Icons.sync),
                    label: const Text('Sincronizar avisos ahora'),
                  ),
                  if (service.planned.isNotEmpty)
                    ExpansionTile(
                      tilePadding: EdgeInsets.zero,
                      title: const Text('Próximos avisos'),
                      children: service.planned
                          .take(12)
                          .map(
                            (notice) => ListTile(
                              dense: true,
                              leading: const Icon(Icons.schedule),
                              title: Text(
                                DateFormat('EEE d MMM · HH:mm', 'es').format(
                                  tz.TZDateTime.from(
                                    notice.at,
                                    tz.getLocation(agendaTimezone),
                                  ),
                                ),
                              ),
                              subtitle: const Text(
                                'Seguimiento de una actividad · hora aproximada',
                              ),
                            ),
                          )
                          .toList(),
                    ),
                ],
              ),
              _Section(
                title: 'Despertador del teléfono',
                icon: Icons.alarm_rounded,
                children: [
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(
                      alarmTime,
                      style: Theme.of(context).textTheme.displaySmall,
                    ),
                    subtitle: const Text('Hora local del teléfono'),
                    trailing: TextButton(
                      onPressed: disabled ? null : () => _pickTime(alarm: true),
                      child: const Text('Cambiar hora'),
                    ),
                  ),
                  const Text('Días del despertador'),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 7,
                    runSpacing: 7,
                    children: List.generate(7, (index) {
                      final day = index + 1;
                      return FilterChip(
                        label: Text(
                          const [
                            'Lun',
                            'Mar',
                            'Mié',
                            'Jue',
                            'Vie',
                            'Sáb',
                            'Dom',
                          ][index],
                        ),
                        selected: settings.alarmWeekdays.contains(day),
                        onSelected: disabled
                            ? null
                            : (selected) {
                                final days = {...settings.alarmWeekdays};
                                if (selected) {
                                  days.add(day);
                                } else {
                                  days.remove(day);
                                }
                                service.saveSettings(
                                  settings.copyWith(
                                    alarmWeekdays: days.toList()..sort(),
                                  ),
                                );
                              },
                      );
                    }),
                  ),
                  const SizedBox(height: 12),
                  const Text(
                    'Lunes a viernes están seleccionados inicialmente. Para el sábado revisa si necesitas una hora distinta.',
                  ),
                  const SizedBox(height: 14),
                  FilledButton.icon(
                    onPressed:
                        disabled || _clockBusy || settings.alarmWeekdays.isEmpty
                        ? null
                        : _openClock,
                    icon: const Icon(Icons.open_in_new),
                    label: Text('Configurar $alarmTime en Reloj'),
                  ),
                  const SizedBox(height: 10),
                  const Text(
                    'Este botón solicita la alarma y abre el Reloj de Android. Revisa allí los días, el sonido y que esté activa. Cambiar estos ajustes no modifica alarmas ya creadas en Reloj.',
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'SARA Agenda no puede comprobar si la alarma quedó activada. La alarma del Reloj funciona por separado de la conexión con el servidor.',
                  ),
                ],
              ),
            ],
          ),
        );
      },
    ),
  );
}

class _Section extends StatelessWidget {
  final String title;
  final IconData icon;
  final List<Widget> children;
  const _Section({
    required this.title,
    required this.icon,
    required this.children,
  });
  @override
  Widget build(BuildContext context) => Card(
    margin: const EdgeInsets.only(bottom: 18),
    child: Padding(
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  title,
                  style: Theme.of(context).textTheme.titleLarge,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          ...children,
        ],
      ),
    ),
  );
}

class _Notice extends StatelessWidget {
  final String text;
  const _Notice(this.text);
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(
      color: Theme.of(context).colorScheme.secondaryContainer,
      borderRadius: BorderRadius.circular(12),
    ),
    child: Text(
      text,
      style: TextStyle(
        color: Theme.of(context).colorScheme.onSecondaryContainer,
      ),
    ),
  );
}
