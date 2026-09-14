import 'agenda_item.dart';

/// Estado de una propuesta del Agente.
enum ProposalStatus { pending, accepted, rejected }

/// Propuesta estructurada generada por el Agente en el backend.
/// Diseñada para ser mínima y comprensible por un LLM local sin gastar contexto.
class AgentProposal {
  final String id;
  final String summary;
  final String reason;
  final List<AgendaItem> resultingItems;
  final ProposalStatus status;
  final DateTime createdAt;

  const AgentProposal({
    required this.id,
    required this.summary,
    required this.reason,
    required this.resultingItems,
    this.status = ProposalStatus.pending,
    required this.createdAt,
  });

  AgentProposal copyWith({
    String? id,
    String? summary,
    String? reason,
    List<AgendaItem>? resultingItems,
    ProposalStatus? status,
    DateTime? createdAt,
  }) {
    return AgentProposal(
      id: id ?? this.id,
      summary: summary ?? this.summary,
      reason: reason ?? this.reason,
      resultingItems: resultingItems ?? this.resultingItems,
      status: status ?? this.status,
      createdAt: createdAt ?? this.createdAt,
    );
  }
}
