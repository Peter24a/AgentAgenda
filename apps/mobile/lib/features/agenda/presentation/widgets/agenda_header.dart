import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';
import 'beam_settings_sheet.dart';
import 'week_strip_selector.dart';

/// Encabezado estilo At a Glance con despliegue animado y fluido del calendario.
/// Optimizado con AnimatedSize y curvas nativas M3 sin costo de GPU.
class AgendaHeader extends StatefulWidget {
  final DateTime selectedDate;
  final int totalActivities;
  final int completedActivities;
  final Function(DateTime) onDateChanged;
  final VoidCallback? onAddActivity;

  const AgendaHeader({
    super.key,
    required this.selectedDate,
    required this.totalActivities,
    required this.completedActivities,
    required this.onDateChanged,
    this.onAddActivity,
  });

  @override
  State<AgendaHeader> createState() => _AgendaHeaderState();
}

class _AgendaHeaderState extends State<AgendaHeader> {
  bool _isCalendarExpanded = false;

  void _toggleCalendar() {
    HapticFeedback.selectionClick();
    setState(() => _isCalendarExpanded = !_isCalendarExpanded);
  }

  void _openSettings(BuildContext context) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => const BeamSettingsSheet(),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final dayName = DateFormat('EEEE', 'es').format(widget.selectedDate);
    final formattedDate = DateFormat("d 'de' MMMM", 'es').format(widget.selectedDate);
    final capitalizedDay = dayName[0].toUpperCase() + dayName.substring(1);

    final progress = widget.totalActivities > 0
        ? widget.completedActivities / widget.totalActivities
        : 0.0;

    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 26, 20, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Barra superior: Píldora de Fecha + Estado 30B + Tuerca de Ajustes
          Row(
            children: [
              // Botón desplegable del calendario con efecto táctil
              InkWell(
                onTap: _toggleCalendar,
                borderRadius: BorderRadius.circular(20),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 240),
                  curve: Curves.easeOutCubic,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 14,
                    vertical: 8,
                  ),
                  decoration: BoxDecoration(
                    color: _isCalendarExpanded
                        ? theme.colorScheme.primaryContainer
                        : theme.colorScheme.surfaceContainerHigh,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        Icons.calendar_today_rounded,
                        size: 15,
                        color: _isCalendarExpanded
                            ? theme.colorScheme.onPrimaryContainer
                            : theme.colorScheme.primary,
                      ),
                      const SizedBox(width: 8),
                      Text(
                        'Hoy',
                        style: theme.textTheme.labelLarge?.copyWith(
                          fontWeight: FontWeight.w700,
                          color: _isCalendarExpanded
                              ? theme.colorScheme.onPrimaryContainer
                              : theme.colorScheme.primary,
                        ),
                      ),
                      const SizedBox(width: 4),
                      // Rotación animada de la flecha indicadora
                      AnimatedRotation(
                        turns: _isCalendarExpanded ? 0.5 : 0.0,
                        duration: const Duration(milliseconds: 260),
                        curve: Curves.easeInOutCubicEmphasized,
                        child: Icon(
                          Icons.keyboard_arrow_down_rounded,
                          size: 18,
                          color: _isCalendarExpanded
                              ? theme.colorScheme.onPrimaryContainer
                              : theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const Spacer(),

              // Estado del Agente local
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: isDark
                      ? const Color(0xFF1E2A38)
                      : const Color(0xFFE8F0FE),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(
                    color: const Color(0xFF4285F4).withValues(alpha: 0.3),
                  ),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.circle,
                      size: 8,
                      color: Color(0xFF34A853),
                    ),
                    SizedBox(width: 6),
                    Text(
                      '30B Local',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF4285F4),
                      ),
                    ),
                  ],
                ),
              ),
              if (widget.onAddActivity != null) ...[
                IconButton.filledTonal(
                  onPressed: widget.onAddActivity,
                  icon: const Icon(Icons.add_rounded, size: 20),
                  tooltip: 'Nueva actividad',
                  style: IconButton.styleFrom(
                    backgroundColor: theme.colorScheme.surfaceContainerHigh,
                    minimumSize: const Size(38, 38),
                    padding: EdgeInsets.zero,
                  ),
                ),
                const SizedBox(width: 8),
              ],

              // Tuerca de configuración
              IconButton.filledTonal(
                onPressed: () => _openSettings(context),
                icon: const Icon(Icons.tune_rounded, size: 20),
                tooltip: 'Personalizar lazo luminoso',
                style: IconButton.styleFrom(
                  backgroundColor: theme.colorScheme.surfaceContainerHigh,
                  minimumSize: const Size(38, 38),
                  padding: EdgeInsets.zero,
                ),
              ),
            ],
          ),

          // Despliegue animado fluido de la tira semanal del calendario
          AnimatedSize(
            duration: const Duration(milliseconds: 300),
            curve: Curves.easeInOutCubicEmphasized,
            child: _isCalendarExpanded
                ? Padding(
                    padding: const EdgeInsets.only(top: 14),
                    child: WeekStripSelector(
                      selectedDate: widget.selectedDate,
                      onDateSelected: (date) {
                        HapticFeedback.lightImpact();
                        widget.onDateChanged(date);
                      },
                    ),
                  )
                : const SizedBox.shrink(),
          ),

          const SizedBox(height: 18),

          // Título del día y fecha
          Text(
            capitalizedDay,
            style: theme.textTheme.headlineMedium?.copyWith(
              fontWeight: FontWeight.w900,
              letterSpacing: -0.5,
              color: theme.colorScheme.onSurface,
            ),
          ),
          Text(
            formattedDate,
            style: theme.textTheme.titleMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
              fontWeight: FontWeight.w500,
            ),
          ),
          const SizedBox(height: 14),

          // Píldora de progreso
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: BoxDecoration(
              color: isDark
                  ? theme.colorScheme.surfaceContainer
                  : theme.colorScheme.surfaceContainerLow,
              borderRadius: BorderRadius.circular(22),
            ),
            child: Row(
              children: [
                SizedBox(
                  width: 28,
                  height: 28,
                  child: CircularProgressIndicator(
                    value: progress,
                    strokeWidth: 3.5,
                    backgroundColor: theme.colorScheme.surfaceContainerHighest,
                    valueColor: AlwaysStoppedAnimation<Color>(
                      theme.colorScheme.primary,
                    ),
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Text(
                    widget.totalActivities == 0
                        ? 'Esperando planificación del Agente'
                        : widget.completedActivities == widget.totalActivities
                            ? '¡Todo listo por hoy! 🎉'
                            : '${widget.completedActivities} de ${widget.totalActivities} completadas',
                    style: theme.textTheme.bodyMedium?.copyWith(
                      fontWeight: FontWeight.w600,
                      color: theme.colorScheme.onSurface,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
