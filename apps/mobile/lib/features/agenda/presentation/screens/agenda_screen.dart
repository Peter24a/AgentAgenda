import 'package:flutter/material.dart';
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

  // Propuesta activa del Agente para demostrar el flujo de aprobación
  AgentProposal? _activeProposal = AgentProposal(
    id: 'prop_01',
    summary: 'Optimización de tarde: pausa para despejar',
    reason:
        'Detecté 3 horas seguidas de desarrollo. Sugiero insertar 30 min de descanso antes del entrenamiento para mantener la energía.',
    createdAt: DateTime.now(),
    resultingItems: [
      AgendaItem(
        id: 'prop_item_1',
        title: 'Caminata y desconexión',
        description: 'Sugerido por el Agente para evitar fatiga',
        startTime: DateTime(2026, 9, 14, 17, 30),
        endTime: DateTime(2026, 9, 14, 18, 0),
        category: ActivityCategory.leisure,
      ),
    ],
  );

  // Lista de actividades confirmadas
  late List<AgendaItem> _items = [
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

  void _toggleItem(String id) {
    setState(() {
      _items = _items.map((it) {
        if (it.id == id) {
          return it.copyWith(isCompleted: !it.isCompleted);
        }
        return it;
      }).toList();
    });
  }

  void _acceptProposal() {
    if (_activeProposal == null) return;
    setState(() {
      _items.addAll(_activeProposal!.resultingItems);
      _items.sort((a, b) => a.startTime.compareTo(b.startTime));
      _activeProposal = null;
    });
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('¡Propuesta del Agente aplicada a tu agenda!'),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  void _dismissProposal() {
    setState(() => _activeProposal = null);
  }

  void _openAgentChat() {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const ChatScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    final completedCount = _items.where((i) => i.isCompleted).length;
    final sortedItems = [..._items]..sort((a, b) => a.startTime.compareTo(b.startTime));

    return Scaffold(
      body: AgentScreenBorder(
        child: SafeArea(
          child: CustomScrollView(
            slivers: [
              SliverToBoxAdapter(
                child: AgendaHeader(
                  selectedDate: _selectedDate,
                  totalActivities: _items.length,
                  completedActivities: completedCount,
                  onDateChanged: (date) {
                    setState(() => _selectedDate = date);
                  },
                ),
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

              // Espacio inferior para no tapar contenido con el botón flotante
              const SliverToBoxAdapter(child: SizedBox(height: 96)),
            ],
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
