import 'package:flutter/material.dart';
import '../../../../core/network/api_client.dart';
import '../../models/agenda_item.dart';
import '../../models/agent_proposal.dart';
import '../widgets/agenda_header.dart';
import '../widgets/atmospheric_card.dart';
import '../widgets/agent_proposal_card.dart';
import '../widgets/agent_screen_border.dart';
import '../widgets/new_activity_sheet.dart';
import '../widgets/premium_agent_button.dart';
import '../../../chat/presentation/screens/chat_screen.dart';

/// Pantalla visualizadora de la agenda gestionada por el Agente.
/// Presenta la agenda real conectada al backend, las propuestas del LLM y controles Pixel.
class AgendaScreen extends StatefulWidget {
  const AgendaScreen({super.key});

  @override
  State<AgendaScreen> createState() => _AgendaScreenState();
}

class _AgendaScreenState extends State<AgendaScreen> {
  DateTime _selectedDate = DateTime.now();
  AgentProposal? _activeProposal;
  bool _isLoading = false;

  // Lista de actividades sincronizadas en vivo desde el backend (sin datos mock)
  List<AgendaItem> _items = [];

  @override
  void initState() {
    super.initState();
    _fetchData();
  }

  Future<void> _fetchData() async {
    if (!mounted) return;
    setState(() => _isLoading = true);

    try {
      final remoteEvents =
          await ApiClient.instance.getEvents(date: _selectedDate);
      final proposal = await ApiClient.instance.getPendingProposal();

      if (mounted) {
        setState(() {
          _items = remoteEvents;
          _activeProposal = proposal;
          _isLoading = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _toggleItem(String id) async {
    setState(() {
      _items = _items.map((it) {
        if (it.id == id) {
          return it.copyWith(isCompleted: !it.isCompleted);
        }
        return it;
      }).toList();
    });

    await ApiClient.instance.toggleEvent(id, date: _selectedDate);
  }

  void _deleteItem(String id) async {
    final previousItems = [..._items];
    setState(() {
      _items.removeWhere((it) => it.id == id);
    });

    final success = await ApiClient.instance.deleteEvent(id);
    if (!success && mounted) {
      setState(() => _items = previousItems);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('No se pudo eliminar la actividad.'),
          behavior: SnackBarBehavior.floating,
        ),
      );
    } else if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Actividad eliminada.'),
          behavior: SnackBarBehavior.floating,
        ),
      );
    }
  }

  void _openNewActivityModal() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      builder: (ctx) => NewActivitySheet(
        targetDate: _selectedDate,
        onAdd: (newItem) async {
          final created = await ApiClient.instance.createOrUpdateEvent(newItem);
          if (created != null && mounted) {
            await _fetchData();
            if (!mounted) return;
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(
                content: Text('¡Actividad agregada a la agenda!'),
                behavior: SnackBarBehavior.floating,
              ),
            );
          }
        },
      ),
    );
  }

  void _showItemOptions(AgendaItem item) {
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) {
        final theme = Theme.of(ctx);
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 16.0),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                ListTile(
                  leading: Icon(
                    item.isCompleted
                        ? Icons.remove_done_rounded
                        : Icons.check_circle_outline_rounded,
                    color: theme.colorScheme.primary,
                  ),
                  title: Text(
                    item.isCompleted
                        ? 'Marcar como pendiente'
                        : 'Marcar como completada',
                  ),
                  onTap: () {
                    Navigator.pop(ctx);
                    _toggleItem(item.id);
                  },
                ),
                ListTile(
                  leading: const Icon(Icons.delete_outline_rounded, color: Colors.redAccent),
                  title: const Text(
                    'Eliminar actividad',
                    style: TextStyle(color: Colors.redAccent),
                  ),
                  onTap: () {
                    Navigator.pop(ctx);
                    _deleteItem(item.id);
                  },
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  void _acceptProposal() async {
    if (_activeProposal == null) return;
    final propId = _activeProposal!.id;
    final success = await ApiClient.instance.confirmProposal(propId);

    if (mounted) {
      if (success) {
        await _fetchData();
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('¡Propuesta del Agente aplicada a tu agenda!'),
            behavior: SnackBarBehavior.floating,
          ),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('No se pudo confirmar la propuesta en el servidor.'),
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    }
  }

  void _dismissProposal() async {
    if (_activeProposal == null) return;
    final propId = _activeProposal!.id;
    setState(() => _activeProposal = null);
    await ApiClient.instance.rejectProposal(propId);
  }

  void _openAgentChat() async {
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const ChatScreen()),
    );
    _fetchData();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final completedCount = _items.where((i) => i.isCompleted).length;
    final sortedItems = [..._items]
      ..sort((a, b) => a.startTime.compareTo(b.startTime));

    return Scaffold(
      body: AgentScreenBorder(
        child: SafeArea(
          child: RefreshIndicator(
            onRefresh: _fetchData,
            child: CustomScrollView(
              slivers: [
                SliverToBoxAdapter(
                  child: AgendaHeader(
                    selectedDate: _selectedDate,
                    totalActivities: _items.length,
                    completedActivities: completedCount,
                    onDateChanged: (date) {
                      setState(() => _selectedDate = date);
                      _fetchData();
                    },
                    onAddActivity: _openNewActivityModal,
                  ),
                ),

                if (_isLoading)
                  const SliverToBoxAdapter(
                    child: LinearProgressIndicator(minHeight: 2),
                  ),

                // Propuesta pendiente del Agente (si existe)
                if (_activeProposal != null)
                  SliverToBoxAdapter(
                    child: AgentProposalCard(
                      proposal: _activeProposal!,
                      onAccept: _acceptProposal,
                      onDismiss: _dismissProposal,
                    ),
                  ),

                const SliverToBoxAdapter(child: SizedBox(height: 8)),

                // Estado vacío amigable cuando no hay eventos para la fecha
                if (!_isLoading && sortedItems.isEmpty)
                  SliverFillRemaining(
                    hasScrollBody: false,
                    child: Center(
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 32.0, vertical: 24.0),
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Container(
                              width: 64,
                              height: 64,
                              decoration: BoxDecoration(
                                color: theme.colorScheme.primaryContainer.withValues(alpha: 0.4),
                                shape: BoxShape.circle,
                              ),
                              child: Icon(
                                Icons.event_available_rounded,
                                size: 32,
                                color: theme.colorScheme.primary,
                              ),
                            ),
                            const SizedBox(height: 16),
                            Text(
                              'Sin actividades agendadas',
                              style: theme.textTheme.titleMedium?.copyWith(
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                            const SizedBox(height: 6),
                            Text(
                              'Pide al Agente que organice tu itinerario o agrega una actividad manualmente.',
                              textAlign: TextAlign.center,
                              style: theme.textTheme.bodyMedium?.copyWith(
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                            const SizedBox(height: 18),
                            FilledButton.tonalIcon(
                              onPressed: _openNewActivityModal,
                              icon: const Icon(Icons.add_rounded, size: 20),
                              label: const Text('Agregar actividad'),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),

                // Línea de tiempo visualizadora
                if (sortedItems.isNotEmpty)
                  SliverList(
                    delegate: SliverChildBuilderDelegate(
                      (context, index) {
                        final item = sortedItems[index];
                        return Dismissible(
                          key: ValueKey('dismiss_${item.id}'),
                          direction: DismissDirection.endToStart,
                          background: Container(
                            alignment: Alignment.centerRight,
                            padding: const EdgeInsets.only(right: 28),
                            margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                            decoration: BoxDecoration(
                              color: Colors.redAccent.withValues(alpha: 0.85),
                              borderRadius: BorderRadius.circular(28),
                            ),
                            child: const Icon(Icons.delete_rounded, color: Colors.white, size: 28),
                          ),
                          onDismissed: (_) => _deleteItem(item.id),
                          child: AtmosphericCard(
                            key: ValueKey(item.id),
                            item: item,
                            onToggleComplete: () => _toggleItem(item.id),
                            onTap: () => _showItemOptions(item),
                          ),
                        );
                      },
                      childCount: sortedItems.length,
                    ),
                  ),

                const SliverToBoxAdapter(child: SizedBox(height: 96)),
              ],
            ),
          ),
        ),
      ),
      floatingActionButtonLocation: FloatingActionButtonLocation.centerFloat,
      floatingActionButton: PremiumAgentButton(
        onTap: _openAgentChat,
      ),
    );
  }
}
