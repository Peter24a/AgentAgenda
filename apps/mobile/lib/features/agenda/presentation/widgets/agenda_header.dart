import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../models/agenda_view.dart';
import 'beam_settings_sheet.dart';
import '../screens/notifications/notification_settings_screen.dart';

class AgendaHeader extends StatelessWidget {
  final DateTime selectedDate;
  final AgendaView view;
  final int totalActivities;
  final ValueChanged<AgendaView> onViewChanged;
  final VoidCallback onPrevious;
  final VoidCallback onNext;
  final VoidCallback onToday;
  final VoidCallback onAddActivity;

  const AgendaHeader({
    super.key,
    required this.selectedDate,
    required this.view,
    required this.totalActivities,
    required this.onViewChanged,
    required this.onPrevious,
    required this.onNext,
    required this.onToday,
    required this.onAddActivity,
  });

  String get _periodTitle {
    if (view == AgendaView.month) {
      return DateFormat('MMMM yyyy', 'es').format(selectedDate);
    }
    if (view == AgendaView.week) {
      final start = agendaWeekStart(selectedDate);
      final end = DateTime(start.year, start.month, start.day + 6);
      return '${DateFormat('d MMM', 'es').format(start)} – ${DateFormat('d MMM', 'es').format(end)}';
    }
    return DateFormat('EEEE d', 'es').format(selectedDate);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final title = _periodTitle;

    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 14, 20, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Row(
                  children: [
                    Container(
                      width: 10,
                      height: 10,
                      decoration: BoxDecoration(
                        color: theme.colorScheme.primary,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      'SARA Agenda',
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w700,
                        letterSpacing: 0.2,
                        color: theme.colorScheme.onSurface,
                      ),
                    ),
                  ],
                ),
              ),
              TextButton(onPressed: onToday, child: const Text('Hoy')),
              IconButton(
                tooltip: 'Avisos y recordatorios',
                icon: const Icon(Icons.notifications_outlined),
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => const NotificationSettingsScreen(),
                  ),
                ),
              ),
              IconButton.filledTonal(
                onPressed: onAddActivity,
                icon: const Icon(Icons.add_rounded),
                tooltip: 'Agregar actividad',
                style: IconButton.styleFrom(
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8),
                  ),
                ),
              ),
              const SizedBox(width: 4),
              IconButton(
                onPressed: () => showModalBottomSheet<void>(
                  context: context,
                  isScrollControlled: true,
                  builder: (_) => const BeamSettingsSheet(),
                ),
                icon: const Icon(Icons.tune_rounded),
                tooltip: 'Ajustes de SARA',
              ),
            ],
          ),
          const SizedBox(height: 14),
          SizedBox(
            width: double.infinity,
            child: SegmentedButton<AgendaView>(
              showSelectedIcon: false,
              segments: const [
                ButtonSegment(value: AgendaView.day, label: Text('Día')),
                ButtonSegment(value: AgendaView.week, label: Text('Semana')),
                ButtonSegment(value: AgendaView.month, label: Text('Mes')),
              ],
              selected: {view},
              onSelectionChanged: (selection) => onViewChanged(selection.first),
              style: SegmentedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 12),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8),
                ),
                selectedBackgroundColor: theme.colorScheme.primaryContainer,
                selectedForegroundColor: theme.colorScheme.onPrimaryContainer,
                side: BorderSide(
                  color: theme.colorScheme.outlineVariant,
                  width: 1.0,
                ),
              ),
            ),
          ),
          const SizedBox(height: 22),
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${title[0].toUpperCase()}${title.substring(1)}',
                      style: theme.textTheme.headlineSmall?.copyWith(
                        fontWeight: FontWeight.w800,
                        letterSpacing: -0.7,
                      ),
                    ),
                    const SizedBox(height: 5),
                    Text(
                      view == AgendaView.day
                          ? DateFormat('MMMM yyyy', 'es').format(selectedDate)
                          : view == AgendaView.week
                          ? 'Toca un día para ver sus actividades'
                          : 'Elige una semana o un día',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),
              IconButton(
                onPressed: onPrevious,
                icon: const Icon(Icons.chevron_left_rounded),
                tooltip: 'Periodo anterior',
              ),
              IconButton(
                onPressed: onNext,
                icon: const Icon(Icons.chevron_right_rounded),
                tooltip: 'Periodo siguiente',
              ),
            ],
          ),
          const SizedBox(height: 18),
          Row(
            children: [
              Expanded(
                child: Text(
                  '$totalActivities ${totalActivities == 1 ? 'actividad' : 'actividades'}',
                  style: theme.textTheme.labelMedium?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
