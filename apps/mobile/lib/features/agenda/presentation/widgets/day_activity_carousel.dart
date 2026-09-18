import 'package:flutter/material.dart';

import '../../models/agenda_item.dart';
import '../../models/agenda_view.dart';

/// Keeps the present activity in focus while preserving deliberate browsing.
class DayActivityCarousel extends StatefulWidget {
  final DateTime selectedDate;
  final DateTime now;
  final List<AgendaItem> items;
  final bool showCheckIn;
  final VoidCallback onCheckIn;
  final ValueChanged<AgendaItem> onOpenItem;
  final ValueChanged<AgendaItem> onToggleItem;

  const DayActivityCarousel({
    super.key,
    required this.selectedDate,
    required this.now,
    required this.items,
    required this.showCheckIn,
    required this.onCheckIn,
    required this.onOpenItem,
    required this.onToggleItem,
  });

  @override
  State<DayActivityCarousel> createState() => _DayActivityCarouselState();
}

class _DayActivityCarouselState extends State<DayActivityCarousel> {
  late PageController _controller;
  late List<AgendaItem?> _entries;
  late String _anchorKey;
  int _visibleIndex = 0;
  bool _dragging = false;
  bool _pointerDown = false;
  bool _pendingFocus = false;
  DateTime? _lastManualScroll;

  List<AgendaItem?> _makeEntries() {
    final entries = <AgendaItem?>[...widget.items];
    if (widget.showCheckIn) {
      final next = entries.indexWhere(
        (item) => !item!.isCompleted && item.startTime.isAfter(widget.now),
      );
      entries.insert(next < 0 ? entries.length : next, null);
    }
    return entries;
  }

  String _keyAt(int index) => _entries[index]?.id ?? 'check-in';

  int get _currentIndex {
    if (!agendaSameDay(widget.selectedDate, widget.now)) return 0;
    if (widget.showCheckIn) return _entries.indexOf(null);
    final active = _entries.indexWhere(
      (item) =>
          item != null &&
          !item.isCompleted &&
          !item.startTime.isAfter(widget.now) &&
          agendaEventEnd(item).isAfter(widget.now),
    );
    if (active >= 0) return active;
    final next = _entries.indexWhere(
      (item) =>
          item != null &&
          !item.isCompleted &&
          item.startTime.isAfter(widget.now),
    );
    return next >= 0 ? next : (_entries.length - 1).clamp(0, _entries.length);
  }

  @override
  void initState() {
    super.initState();
    _entries = _makeEntries();
    _visibleIndex = _currentIndex;
    _anchorKey = _entries.isEmpty ? '' : _keyAt(_visibleIndex);
    _controller = PageController(
      viewportFraction: 0.9,
      initialPage: _visibleIndex,
    );
  }

  @override
  void didUpdateWidget(covariant DayActivityCarousel oldWidget) {
    super.didUpdateWidget(oldWidget);
    final visibleKey = _entries.isEmpty
        ? ''
        : _keyAt(_visibleIndex.clamp(0, _entries.length - 1));
    _entries = _makeEntries();
    if (_entries.isEmpty) return;
    final newAnchor = _keyAt(_currentIndex);
    if (_anchorKey != newAnchor) {
      _anchorKey = newAnchor;
      _pendingFocus = true;
    }
    final retainedIndex = _entries.indexWhere(
      (item) => (item?.id ?? 'check-in') == visibleKey,
    );
    if (retainedIndex >= 0) _visibleIndex = retainedIndex;
    _visibleIndex = _visibleIndex.clamp(0, _entries.length - 1);
    final recentlyBrowsed =
        _lastManualScroll != null &&
        DateTime.now().difference(_lastManualScroll!) <
            const Duration(seconds: 30);
    if (_pendingFocus && !_dragging && !_pointerDown && !recentlyBrowsed) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _focusCurrent());
    }
  }

  void _focusCurrent() {
    if (!mounted ||
        !_controller.hasClients ||
        _entries.isEmpty ||
        _dragging ||
        _pointerDown) {
      return;
    }
    _pendingFocus = false;
    final index = _currentIndex;
    if (MediaQuery.disableAnimationsOf(context)) {
      _controller.jumpToPage(index);
    } else {
      _controller.animateToPage(
        index,
        duration: const Duration(milliseconds: 450),
        curve: Curves.easeOutCubic,
      );
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_entries.isEmpty) return const SizedBox.shrink();
    final theme = Theme.of(context);
    final today = agendaSameDay(widget.selectedDate, widget.now);
    final scale = MediaQuery.textScalerOf(context).scale(14) / 14;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(22, 6, 18, 0),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  'Tu día, paso a paso',
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              if (today && _visibleIndex != _currentIndex)
                TextButton.icon(
                  onPressed: _focusCurrent,
                  icon: const Icon(Icons.my_location_rounded, size: 16),
                  label: const Text('Ahora'),
                ),
            ],
          ),
        ),
        const SizedBox(height: 4),
        SizedBox(
          height: 300 + 80 * scale,
          child: Listener(
            onPointerDown: (_) => _pointerDown = true,
            onPointerUp: (_) => _pointerDown = false,
            onPointerCancel: (_) => _pointerDown = false,
            child: NotificationListener<ScrollNotification>(
              onNotification: (notification) {
                if (notification is ScrollStartNotification &&
                    notification.dragDetails != null) {
                  _dragging = true;
                  _lastManualScroll = DateTime.now();
                }
                if (notification is ScrollEndNotification && _dragging) {
                  _dragging = false;
                  _lastManualScroll = DateTime.now();
                }
                return false;
              },
              child: PageView.builder(
                controller: _controller,
                itemCount: _entries.length,
                onPageChanged: (index) => setState(() => _visibleIndex = index),
                itemBuilder: (context, index) {
                  final item = _entries[index];
                  return Padding(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 5,
                      vertical: 8,
                    ),
                    child: item == null
                        ? _CheckInCard(onTap: widget.onCheckIn)
                        : _ActivityCard(
                            item: item,
                            now: widget.now,
                            onTap: () => widget.onOpenItem(item),
                            onToggle: () => widget.onToggleItem(item),
                          ),
                  );
                },
              ),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 6),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  'Desliza para recorrer tus actividades',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ),
              Text(
                '${_visibleIndex + 1} / ${_entries.length}',
                style: theme.textTheme.labelMedium,
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _ActivityCard extends StatelessWidget {
  final AgendaItem item;
  final DateTime now;
  final VoidCallback onTap;
  final VoidCallback onToggle;

  const _ActivityCard({
    required this.item,
    required this.now,
    required this.onTap,
    required this.onToggle,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final active =
        !item.isCompleted &&
        !item.startTime.isAfter(now) &&
        agendaEventEnd(item).isAfter(now);
    final label = item.isCompleted
        ? 'Completada'
        : active
        ? 'Ahora · En curso'
        : agendaEventEnd(item).isBefore(now)
        ? 'Anterior'
        : 'Próxima';
    final provisional =
        item.description?.toLowerCase().contains('horario provisional') ??
        false;

    return Material(
      color: colorScheme.surfaceContainerLow,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(
          color: colorScheme.outlineVariant,
          width: 1.0,
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: Stack(
        children: [
          // Indicador visual lateral de estado activo (SARA ciruela, WCAG 1.4.1)
          Positioned(
            left: 0,
            top: 0,
            bottom: 0,
            width: 4,
            child: ColoredBox(
              color: item.isCompleted
                  ? colorScheme.outlineVariant
                  : (active ? colorScheme.primary : colorScheme.primary.withValues(alpha: 0.5)),
            ),
          ),

          Padding(
            padding: const EdgeInsets.fromLTRB(18, 16, 16, 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: SingleChildScrollView(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: Text(
                                label,
                                style: theme.textTheme.labelMedium?.copyWith(
                                  color: active
                                      ? colorScheme.primary
                                      : colorScheme.onSurfaceVariant,
                                  fontWeight: FontWeight.w700,
                                  letterSpacing: 0.2,
                                ),
                              ),
                            ),
                            IconButton(
                              onPressed: onTap,
                              icon: const Icon(Icons.more_horiz_rounded),
                              tooltip: 'Detalles y opciones de actividad',
                              style: IconButton.styleFrom(
                                minimumSize: const Size(44, 44),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 4),
                        Wrap(
                          spacing: 8,
                          runSpacing: 6,
                          children: [
                            _Pill(
                              text: item.timeRange,
                              icon: Icons.schedule_rounded,
                            ),
                            _Pill(
                              text: item.category.label,
                              icon: Icons.label_outline_rounded,
                            ),
                            if (provisional)
                              const _Pill(
                                text: 'Horario provisional',
                                icon: Icons.edit_calendar_outlined,
                              ),
                          ],
                        ),
                        const SizedBox(height: 14),
                        Text(
                          item.title,
                          maxLines: 3,
                          overflow: TextOverflow.ellipsis,
                          style: theme.textTheme.titleLarge?.copyWith(
                            fontWeight: FontWeight.w700,
                            letterSpacing: -0.3,
                            decoration: item.isCompleted
                                ? TextDecoration.lineThrough
                                : null,
                            color: item.isCompleted
                                ? colorScheme.onSurface.withValues(alpha: 0.45)
                                : colorScheme.onSurface,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          item.description?.isNotEmpty == true
                              ? item.description!
                              : 'Actividad programada en SARA Agenda.',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: colorScheme.onSurfaceVariant.withValues(
                              alpha: item.isCompleted ? 0.45 : 0.85,
                            ),
                            height: 1.4,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton.icon(
                    onPressed: onToggle,
                    style: TextButton.styleFrom(
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                    icon: Icon(
                      item.isCompleted
                          ? Icons.check_circle_rounded
                          : Icons.radio_button_unchecked_rounded,
                      size: 20,
                      color: item.isCompleted
                          ? colorScheme.primary
                          : colorScheme.outline,
                    ),
                    label: Text(
                      item.isCompleted ? 'Completada' : 'Marcar como realizada',
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

class _Pill extends StatelessWidget {
  final String text;
  final IconData icon;
  const _Pill({required this.text, required this.icon});
  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: colorScheme.secondaryContainer,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: colorScheme.outlineVariant,
          width: 0.8,
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 13, color: colorScheme.onSurfaceVariant),
          const SizedBox(width: 5),
          Flexible(
            child: Text(
              text,
              style: theme.textTheme.labelSmall?.copyWith(
                fontWeight: FontWeight.w600,
                color: colorScheme.onSurface,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _CheckInCard extends StatelessWidget {
  final VoidCallback onTap;
  const _CheckInCard({required this.onTap});
  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    return Material(
      color: colorScheme.surfaceContainerLow,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(
          color: colorScheme.outlineVariant,
          width: 1.0,
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Stack(
          children: [
            Positioned(
              left: 0,
              top: 0,
              bottom: 0,
              width: 4,
              child: ColoredBox(color: colorScheme.primary),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 20, 20, 20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: SingleChildScrollView(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Icon(
                            Icons.auto_awesome_rounded,
                            size: 26,
                            color: colorScheme.primary,
                          ),
                          const SizedBox(height: 14),
                          Text(
                            'Espacio de reflexión',
                            style: theme.textTheme.labelMedium?.copyWith(
                              color: colorScheme.primary,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          const SizedBox(height: 8),
                          Text(
                            '¿Qué estás haciendo ahora?',
                            style: theme.textTheme.titleLarge?.copyWith(
                              fontWeight: FontWeight.w700,
                              letterSpacing: -0.4,
                              color: colorScheme.onSurface,
                            ),
                          ),
                          const SizedBox(height: 10),
                          Text(
                            'Cuéntale a tu asistente SARA para registrar este momento y organizar los siguientes pasos de tu jornada.',
                            style: theme.textTheme.bodyMedium?.copyWith(
                              color: colorScheme.onSurfaceVariant,
                              height: 1.4,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  FilledButton.icon(
                    onPressed: onTap,
                    icon: const Icon(Icons.forum_rounded, size: 18),
                    label: const Text('Conversar con SARA'),
                    style: FilledButton.styleFrom(
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
