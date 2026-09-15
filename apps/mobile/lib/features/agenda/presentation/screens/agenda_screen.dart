import 'dart:async';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../../../core/network/api_client.dart';
import '../../models/agenda_item.dart';
import '../../models/agenda_view.dart';
import '../../models/agent_proposal.dart';
import '../widgets/agenda_header.dart';
import '../widgets/agenda_calendar_views.dart';
import '../widgets/day_activity_carousel.dart';
import '../widgets/agent_proposal_card.dart';
import '../widgets/agent_screen_border.dart';
import '../widgets/new_activity_sheet.dart';
import '../widgets/premium_agent_button.dart';
import '../../../chat/presentation/screens/chat_screen.dart';

class AgendaScreen extends StatefulWidget {
  const AgendaScreen({super.key});

  @override
  State<AgendaScreen> createState() => _AgendaScreenState();
}

class _AgendaScreenState extends State<AgendaScreen>
    with WidgetsBindingObserver {
  DateTime _selectedDate = agendaDay(DateTime.now());
  DateTime _now = DateTime.now();
  AgendaView _view = AgendaView.day;
  AgentProposal? _activeProposal;
  bool _isLoading = false;
  bool _followingToday = true;
  String? _loadError;
  int _requestGeneration = 0;
  List<AgendaItem> _items = [];
  final Set<String> _pendingChanges = {};
  Timer? _clock;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _clock = Timer.periodic(const Duration(seconds: 30), (_) => _updateClock());
    _fetchData();
  }

  @override
  void dispose() {
    _clock?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _updateClock();
      _fetchData();
    }
  }

  void _updateClock() {
    if (!mounted) return;
    final now = DateTime.now();
    final changeDay = _followingToday && !agendaSameDay(_selectedDate, now);
    setState(() {
      _now = now;
      if (changeDay) _selectedDate = agendaDay(now);
    });
    if (changeDay) _fetchData();
  }

  (DateTime, DateTime) get _range {
    if (_view == AgendaView.day) {
      return (
        _selectedDate,
        DateTime(
          _selectedDate.year,
          _selectedDate.month,
          _selectedDate.day + 1,
        ),
      );
    }
    if (_view == AgendaView.week) {
      final start = agendaWeekStart(_selectedDate);
      return (start, DateTime(start.year, start.month, start.day + 7));
    }
    final first = DateTime(_selectedDate.year, _selectedDate.month);
    final last = DateTime(first.year, first.month + 1, 0);
    return (
      agendaWeekStart(first),
      DateTime(last.year, last.month, last.day + 8 - last.weekday),
    );
  }

  Future<void> _fetchData() async {
    if (!mounted) return;
    final request = ++_requestGeneration;
    final (start, end) = _range;
    setState(() {
      _isLoading = true;
      _loadError = null;
    });
    try {
      final proposalFuture = ApiClient.instance.getPendingProposal();
      final events = await ApiClient.instance.getAgendaRange(
        start: start,
        end: end,
      );
      final proposal = await proposalFuture;
      if (!mounted || request != _requestGeneration) return;
      setState(() {
        _items = events..sort((a, b) => a.startTime.compareTo(b.startTime));
        _activeProposal = proposal;
        _isLoading = false;
      });
    } catch (_) {
      if (!mounted || request != _requestGeneration) return;
      setState(() {
        _isLoading = false;
        _loadError = 'No pudimos actualizar tu agenda. Revisa la conexión e inténtalo de nuevo.';
      });
    }
  }

  void _select(DateTime date, AgendaView view, {bool followToday = false}) {
    setState(() {
      _selectedDate = agendaDay(date);
      _view = view;
      _followingToday = followToday;
      _items = [];
    });
    _fetchData();
  }

  void _movePeriod(int direction) {
    final date = _selectedDate;
    final next = _view == AgendaView.month
        ? DateTime(date.year, date.month + direction)
        : DateTime(
            date.year,
            date.month,
            date.day + direction * (_view == AgendaView.week ? 7 : 1),
          );
    _select(next, _view);
  }

  void _showMessage(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), behavior: SnackBarBehavior.floating),
    );
  }

  Future<void> _toggleItem(AgendaItem item) async {
    if (!_pendingChanges.add(item.id)) return;
    setState(
      () => _items = _items
          .map(
            (it) => it.id == item.id
                ? it.copyWith(isCompleted: !it.isCompleted)
                : it,
          )
          .toList(),
    );
    final success = await ApiClient.instance.toggleEvent(
      item.id,
      date: item.startTime,
    );
    _pendingChanges.remove(item.id);
    if (!mounted) return;
    if (!success) {
      setState(
        () =>
            _items = _items.map((it) => it.id == item.id ? item : it).toList(),
      );
      _showMessage('No se pudo guardar el cambio de actividad.');
    }
  }

  Future<void> _deleteItem(AgendaItem item) async {
    if (!_pendingChanges.add(item.id)) return;
    final success = await ApiClient.instance.deleteEvent(item.id);
    _pendingChanges.remove(item.id);
    if (!mounted) return;
    if (success) {
      setState(() => _items.removeWhere((it) => it.id == item.id));
      _showMessage('Actividad eliminada.');
    } else {
      _showMessage('No se pudo eliminar la actividad.');
    }
  }

  void _openNewActivityModal() {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      builder: (_) => NewActivitySheet(
        targetDate: _selectedDate,
        onAdd: (newItem) async {
          final created = await ApiClient.instance.createOrUpdateEvent(newItem);
          if (!mounted) return;
          if (created != null) {
            await _fetchData();
            _showMessage('Actividad agregada a tu agenda.');
          } else {
            _showMessage(
              'No se pudo agregar la actividad. Inténtalo de nuevo.',
            );
          }
        },
      ),
    );
  }

  void _showItemOptions(AgendaItem item) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) => SafeArea(
        child: SingleChildScrollView(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(22, 24, 22, 20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item.title,
                  style: Theme.of(ctx).textTheme.titleLarge
                      ?.copyWith(fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 8),
                Text(
                  '${DateFormat("EEEE d 'de' MMMM", 'es').format(item.startTime)} · ${item.timeRange}',
                ),
                if (item.description?.isNotEmpty == true) ...[
                  const SizedBox(height: 16),
                  Text(item.description!),
                ],
                const SizedBox(height: 18),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: Icon(
                    item.isCompleted
                        ? Icons.remove_done_rounded
                        : Icons.check_circle_outline_rounded,
                  ),
                  title: Text(
                    item.isCompleted
                        ? 'Marcar como pendiente'
                        : 'Marcar como completada',
                  ),
                  onTap: () {
                    Navigator.pop(ctx);
                    _toggleItem(item);
                  },
                ),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: Icon(
                    Icons.delete_outline_rounded,
                    color: Theme.of(ctx).colorScheme.error,
                  ),
                  title: Text(
                    'Eliminar actividad',
                    style: TextStyle(color: Theme.of(ctx).colorScheme.error),
                  ),
                  onTap: () {
                    Navigator.pop(ctx);
                    _deleteItem(item);
                  },
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _acceptProposal() async {
    final proposal = _activeProposal;
    if (proposal == null) return;
    final success = await ApiClient.instance.confirmProposal(proposal.id);
    if (!mounted) return;
    if (success) {
      await _fetchData();
      _showMessage('Propuesta aplicada a tu agenda.');
    } else {
      _showMessage('No se pudo confirmar la propuesta en el servidor.');
    }
  }

  Future<void> _dismissProposal() async {
    final proposal = _activeProposal;
    if (proposal == null) return;
    final success = await ApiClient.instance.rejectProposal(proposal.id);
    if (!mounted) return;
    if (success) {
      setState(() => _activeProposal = null);
    } else {
      _showMessage('No se pudo descartar la propuesta.');
    }
  }

  Future<void> _openAgentChat({bool checkIn = false}) async {
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => ChatScreen(
          agendaDate: _selectedDate,
          checkIn: checkIn,
          initialPrompt: checkIn
              ? '¿Qué estás haciendo ahora? Cuéntame cómo vas y elegimos el siguiente paso.'
              : null,
        ),
      ),
    );
    if (mounted) _fetchData();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final dayItems = agendaItemsForDay(_items, _selectedDate);
    final showCheckIn =
        !_isLoading &&
        _loadError == null &&
        agendaSameDay(_selectedDate, _now) &&
        !dayItems.any(
          (item) =>
              !item.isCompleted &&
              !item.startTime.isAfter(_now) &&
              agendaEventEnd(item).isAfter(_now),
        );
    final displayedItems = _view == AgendaView.day
        ? dayItems
        : _view == AgendaView.month
        ? _items
              .where(
                (item) =>
                    item.startTime.year == _selectedDate.year &&
                    item.startTime.month == _selectedDate.month,
              )
              .toList()
        : _items;
    return Scaffold(
      body: AgentScreenBorder(
        child: SafeArea(
          child: RefreshIndicator(
            onRefresh: _fetchData,
            child: CustomScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              slivers: [
                SliverToBoxAdapter(
                  child: AgendaHeader(
                    selectedDate: _selectedDate,
                    view: _view,
                    totalActivities: displayedItems.length,
                    completedActivities: displayedItems
                        .where((item) => item.isCompleted)
                        .length,
                    onViewChanged: (view) => _select(
                      _selectedDate,
                      view,
                      followToday: _followingToday,
                    ),
                    onPrevious: () => _movePeriod(-1),
                    onNext: () => _movePeriod(1),
                    onToday: () => _select(
                      DateTime.now(),
                      AgendaView.day,
                      followToday: true,
                    ),
                    onAddActivity: _openNewActivityModal,
                  ),
                ),
                if (_isLoading)
                  const SliverToBoxAdapter(
                    child: Padding(
                      padding: EdgeInsets.symmetric(vertical: 8),
                      child: LinearProgressIndicator(minHeight: 2),
                    ),
                  ),
                if (_loadError != null)
                  SliverToBoxAdapter(
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(20, 14, 20, 4),
                      child: Material(
                        color: theme.colorScheme.errorContainer.withValues(
                          alpha: 0.5,
                        ),
                        borderRadius: BorderRadius.circular(20),
                        child: Padding(
                          padding: const EdgeInsets.all(16),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                _loadError!,
                                style: theme.textTheme.bodyMedium,
                              ),
                              TextButton.icon(
                                onPressed: _fetchData,
                                icon: const Icon(Icons.refresh_rounded),
                                label: const Text('Reintentar'),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                if (_activeProposal != null)
                  SliverToBoxAdapter(
                    child: AgentProposalCard(
                      proposal: _activeProposal!,
                      onAccept: _acceptProposal,
                      onDismiss: _dismissProposal,
                    ),
                  ),
                const SliverToBoxAdapter(child: SizedBox(height: 10)),
                if (_view == AgendaView.day &&
                    (dayItems.isNotEmpty || showCheckIn))
                  SliverToBoxAdapter(
                    child: DayActivityCarousel(
                      key: ValueKey(_selectedDate),
                      selectedDate: _selectedDate,
                      now: _now,
                      items: dayItems,
                      showCheckIn: showCheckIn,
                      onCheckIn: () => _openAgentChat(checkIn: true),
                      onOpenItem: _showItemOptions,
                      onToggleItem: _toggleItem,
                    ),
                  ),
                if (_view == AgendaView.day &&
                    !_isLoading &&
                    _loadError == null &&
                    dayItems.isEmpty &&
                    !showCheckIn)
                  SliverToBoxAdapter(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 32,
                        vertical: 40,
                      ),
                      child: Column(
                        children: [
                          Icon(
                            Icons.event_available_rounded,
                            size: 48,
                            color: theme.colorScheme.primary,
                          ),
                          const SizedBox(height: 16),
                          Text(
                            'Sin actividades agendadas',
                            style: theme.textTheme.titleMedium?.copyWith(
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          const SizedBox(height: 8),
                          Text(
                            'Puedes planear este día con tu agente o agregar una actividad.',
                            textAlign: TextAlign.center,
                            style: theme.textTheme.bodyMedium?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                          const SizedBox(height: 18),
                          FilledButton.tonalIcon(
                            onPressed: _openNewActivityModal,
                            icon: const Icon(Icons.add_rounded),
                            label: const Text('Agregar actividad'),
                          ),
                        ],
                      ),
                    ),
                  ),
                if (_view == AgendaView.week)
                  SliverToBoxAdapter(
                    child: AgendaWeekView(
                      selectedDate: _selectedDate,
                      items: _items,
                      onDaySelected: (day) => _select(
                        day,
                        AgendaView.day,
                        followToday: agendaSameDay(day, DateTime.now()),
                      ),
                    ),
                  ),
                if (_view == AgendaView.month)
                  SliverToBoxAdapter(
                    child: AgendaMonthView(
                      selectedDate: _selectedDate,
                      items: _items,
                      onWeekSelected: (day) => _select(day, AgendaView.week),
                      onDaySelected: (day) => _select(
                        day,
                        AgendaView.day,
                        followToday: agendaSameDay(day, DateTime.now()),
                      ),
                    ),
                  ),
                const SliverToBoxAdapter(child: SizedBox(height: 110)),
              ],
            ),
          ),
        ),
      ),
      floatingActionButtonLocation: FloatingActionButtonLocation.centerFloat,
      floatingActionButton: PremiumAgentButton(onTap: () => _openAgentChat()),
    );
  }
}
