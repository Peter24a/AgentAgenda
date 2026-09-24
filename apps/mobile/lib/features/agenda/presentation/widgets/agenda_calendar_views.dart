import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../models/agenda_item.dart';
import '../../models/agenda_view.dart';

class AgendaWeekView extends StatelessWidget {
  final DateTime selectedDate;
  final List<AgendaItem> items;
  final ValueChanged<DateTime> onDaySelected;

  const AgendaWeekView({
    super.key,
    required this.selectedDate,
    required this.items,
    required this.onDaySelected,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final start = agendaWeekStart(selectedDate);
    return Column(
      children: List.generate(7, (index) {
        final day = DateTime(start.year, start.month, start.day + index);
        final activities = agendaItemsForDay(items, day);
        final today = agendaSameDay(day, DateTime.now());
        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 6),
          child: Material(
            color: today
                ? theme.colorScheme.primaryContainer
                : theme.colorScheme.surfaceContainerLow,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
              side: BorderSide(
                color: today
                    ? theme.colorScheme.primary
                    : theme.colorScheme.outlineVariant,
                width: 1.0,
              ),
            ),
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              onTap: () => onDaySelected(day),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(
                      width: 46,
                      child: Column(
                        children: [
                          Text(
                            DateFormat('E', 'es').format(day).toUpperCase(),
                            style: theme.textTheme.labelSmall,
                          ),
                          const SizedBox(height: 4),
                          Text(
                            '${day.day}',
                            style: theme.textTheme.headlineSmall?.copyWith(
                              fontWeight: FontWeight.w800,
                              color: today ? theme.colorScheme.primary : null,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            today
                                ? 'Hoy · ${activities.length} actividades'
                                : '${activities.length} ${activities.length == 1 ? 'actividad' : 'actividades'}',
                            style: theme.textTheme.titleSmall?.copyWith(
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          const SizedBox(height: 7),
                          if (activities.isEmpty)
                            Text(
                              'Espacio disponible',
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                          for (final item in activities.take(3))
                            Padding(
                              padding: const EdgeInsets.only(bottom: 5),
                              child: Text(
                                '${item.formattedTime}  ${item.title}',
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: theme.textTheme.bodySmall?.copyWith(
                                  color: theme.colorScheme.onSurfaceVariant,
                                  decoration: null,
                                ),
                              ),
                            ),
                          if (activities.length > 3)
                            Text(
                              '+ ${activities.length - 3} más',
                              style: theme.textTheme.labelSmall?.copyWith(
                                color: theme.colorScheme.primary,
                              ),
                            ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 4),
                    const Icon(Icons.chevron_right_rounded, size: 20),
                  ],
                ),
              ),
            ),
          ),
        );
      }),
    );
  }
}

class AgendaMonthView extends StatelessWidget {
  final DateTime selectedDate;
  final List<AgendaItem> items;
  final ValueChanged<DateTime> onWeekSelected;
  final ValueChanged<DateTime> onDaySelected;

  const AgendaMonthView({
    super.key,
    required this.selectedDate,
    required this.items,
    required this.onWeekSelected,
    required this.onDaySelected,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final first = DateTime(selectedDate.year, selectedDate.month);
    final start = agendaWeekStart(first);
    final monthEnd = DateTime(first.year, first.month + 1, 0);
    final rows = ((monthEnd.day + first.weekday - 1) / 7).ceil();
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: Row(
              children: [
                for (final name in ['L', 'M', 'M', 'J', 'V', 'S', 'D'])
                  Expanded(
                    child: Center(
                      child: Text(
                        name,
                        style: theme.textTheme.labelSmall?.copyWith(
                          fontWeight: FontWeight.w700,
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 8),
          for (var row = 0; row < rows; row++) _weekRow(context, start, row),
          const SizedBox(height: 14),
          Text(
            'Los puntos indican días con actividades.',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }

  Widget _weekRow(BuildContext context, DateTime start, int row) {
    final theme = Theme.of(context);
    final weekStart = DateTime(start.year, start.month, start.day + row * 7);
    final weekEnd = DateTime(
      weekStart.year,
      weekStart.month,
      weekStart.day + 6,
    );
    final nextWeek = DateTime(
      weekStart.year,
      weekStart.month,
      weekStart.day + 7,
    );
    final weekCount = items
        .where(
          (item) =>
              item.startTime.isBefore(nextWeek) &&
              agendaEventEnd(item).isAfter(weekStart),
        )
        .length;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Material(
        color: theme.colorScheme.surfaceContainerLow,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: theme.colorScheme.outlineVariant, width: 1.0),
        ),
        clipBehavior: Clip.antiAlias,
        child: Column(
          children: [
            Row(
              children: List.generate(7, (index) {
                final day = DateTime(
                  weekStart.year,
                  weekStart.month,
                  weekStart.day + index,
                );
                final inMonth = day.month == selectedDate.month;
                final today = agendaSameDay(day, DateTime.now());
                final selected = agendaSameDay(day, selectedDate);
                final count = agendaItemsForDay(items, day).length;
                return Expanded(
                  child: Semantics(
                    label:
                        '${DateFormat("EEEE d 'de' MMMM", 'es').format(day)}, $count actividades',
                    button: true,
                    selected: selected,
                    child: ExcludeSemantics(
                      child: InkWell(
                        onTap: () => onDaySelected(day),
                        child: Padding(
                          padding: const EdgeInsets.symmetric(vertical: 10),
                          child: Column(
                            children: [
                              Container(
                                width: 34,
                                height: 34,
                                alignment: Alignment.center,
                                decoration: BoxDecoration(
                                  color: today
                                      ? theme.colorScheme.primary
                                      : selected
                                      ? theme.colorScheme.primaryContainer
                                      : Colors.transparent,
                                  shape: BoxShape.circle,
                                ),
                                child: Text(
                                  '${day.day}',
                                  style: theme.textTheme.bodyMedium?.copyWith(
                                    fontWeight: today || selected
                                        ? FontWeight.w800
                                        : FontWeight.w500,
                                    color: today
                                        ? theme.colorScheme.onPrimary
                                        : inMonth
                                        ? theme.colorScheme.onSurface
                                        : theme.colorScheme.outline,
                                  ),
                                ),
                              ),
                              const SizedBox(height: 5),
                              Container(
                                width: 5,
                                height: 5,
                                decoration: BoxDecoration(
                                  color: count > 0
                                      ? theme.colorScheme.primary
                                      : Colors.transparent,
                                  shape: BoxShape.circle,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                );
              }),
            ),
            InkWell(
              onTap: () => onWeekSelected(weekStart),
              child: ConstrainedBox(
                constraints: const BoxConstraints(minHeight: 48),
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 14,
                    vertical: 8,
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          'Semana ${DateFormat('d MMM', 'es').format(weekStart)} – ${DateFormat('d MMM', 'es').format(weekEnd)}',
                          style: theme.textTheme.labelMedium?.copyWith(
                            color: theme.colorScheme.primary,
                          ),
                        ),
                      ),
                      Text('$weekCount', style: theme.textTheme.labelSmall),
                      const SizedBox(width: 4),
                      Icon(
                        Icons.arrow_forward_rounded,
                        size: 16,
                        color: theme.colorScheme.primary,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
