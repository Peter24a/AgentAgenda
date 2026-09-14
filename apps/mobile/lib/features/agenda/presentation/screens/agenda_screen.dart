import 'package:flutter/material.dart';
import '../../../../core/network/api_client.dart';
import '../../models/agenda_item.dart';
import '../../models/agent_proposal.dart';
import '../widgets/agenda_header.dart';
import '../widgets/atmospheric_card.dart';
import '../widgets/agent_proposal_card.dart';
import '../widgets/agent_screen_border.dart';
import '../widgets/premium_agent_button.dart';
import '../../../chat/presentation/screens/chat_screen.dart';

/// Pantalla visualizadora de la agenda gestionada por el Agente.
/// Presenta la agenda, las propuestas pendientes del LLM y el botón flotante inferior.
class AgendaScreen extends StatefulWidget {
  const AgendaScreen({super.key});

  @override
  State<AgendaScreen> createState() => _AgendaScreenState();
}

class _AgendaScreenState extends State<AgendaScreen> {
  DateTime _selectedDate = DateTime.now();
  AgentProposal? _activeProposal;
  bool _isLoading = false;

  // Lista de actividades confirmadas (con fallback inicial por si no hay red)
  List<AgendaItem> _items = [
    AgendaItem(
      id: '1',
      title: 'Desayuno nutritivo y café',
      description: 'Avena con fruta y espresso doble',
      startTime: DateTime(2026, 9, 14, 8, 0),
      endTime: DateTime(2026, 9, 14, 8, 45),
      category: ActivityCategory.food,
      isCompleted: true,
    ),
    AgendaItem(
      id: '2',
      title: 'Bloque de código: AgentAgenda',
      description: 'Implementar interfaz Pixel y backend FastAPI',
      startTime: DateTime(2026, 9, 14, 9, 30),
      endTime: DateTime(2026, 9, 14, 12, 30),
      category: ActivityCategory.work,
    ),
    AgendaItem(
      id: '3',
      title: 'Comida y descanso ligero',
      description: 'Pausa para despejar y caminar un poco',
      startTime: DateTime(2026, 9, 14, 14, 0),
      endTime: DateTime(2026, 9, 14, 15, 0),
      category: ActivityCategory.food,
    ),
    AgendaItem(
      id: '4',
      title: 'Entrenamiento de fuerza y cardio',
      description: 'Rutina de 45 minutos en el gimnasio',
      startTime: DateTime(2026, 9, 14, 18, 30),
      endTime: DateTime(2026, 9, 14, 19, 30),
      category: ActivityCategory.exercise,
    ),
    AgendaItem(
      id: '5',
      title: 'Dormir y descanso profundo',
      description: 'Dejar el teléfono en no molestar y descansar 8 horas',
      startTime: DateTime(2026, 9, 14, 22, 30),
      endTime: DateTime(2026, 9, 15, 6, 30),
      category: ActivityCategory.sleep,
    ),
  ];

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
          if (remoteEvents.isNotEmpty) {
            _items = remoteEvents;
          }
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

  void _acceptProposal() async {
    if (_activeProposal == null) return;
    final propId = _activeProposal!.id;
    final success = await ApiClient.instance.confirmProposal(propId);

    if (success) {
      await _fetchData();
    } else {
      setState(() {
        _items.addAll(_activeProposal!.resultingItems);
        _items.sort((a, b) => a.startTime.compareTo(b.startTime));
        _activeProposal = null;
      });
    }

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('¡Propuesta del Agente aplicada a tu agenda!'),
          behavior: SnackBarBehavior.floating,
        ),
      );
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

                // Línea de tiempo visualizadora
                SliverList(
                  delegate: SliverChildBuilderDelegate(
                    (context, index) {
                      final item = sortedItems[index];
                      return AtmosphericCard(
                        key: ValueKey(item.id),
                        item: item,
                        onToggleComplete: () => _toggleItem(item.id),
                        onTap: () {},
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
