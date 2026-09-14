/// Contrato de datos ultracompacto para el Agente LLM.
/// Diseñado específicamente para no saturar el contexto de un modelo local de ~30B.
library;

class CompactEventContext {
  final String id;
  final String time;
  final String title;
  final String cat;

  const CompactEventContext({
    required this.id,
    required this.time,
    required this.title,
    required this.cat,
  });

  Map<String, dynamic> toJson() => {
        'i': id,
        't': time,
        's': title,
        'c': cat,
      };
}

/// Snapshot mínimo que se le envía al LLM en cada turno (aprox ~60-120 tokens).
class CompactAgendaSnapshot {
  final String date;
  final String timezone;
  final List<CompactEventContext> events;

  const CompactAgendaSnapshot({
    required this.date,
    this.timezone = 'America/Mexico_City',
    required this.events,
  });

  Map<String, dynamic> toJson() => {
        'd': date,
        'tz': timezone,
        'e': events.map((e) => e.toJson()).toList(),
      };
}

/// Definición de herramientas sencillas y deterministas para el LLM.
class AgentToolDefinitions {
  AgentToolDefinitions._();

  static const String systemPrompt = '''
Eres el organizador de agenda del usuario.
Tu tarea es analizar peticiones sencillas y responder EXCLUSIVAMENTE con una propuesta estructurada.
Reglas:
1. No confirmes cambios por tu cuenta; la app requiere aprobación del usuario.
2. Si falta información decisiva (como la hora exacta), solicita aclaración brevemente.
3. Respeta siempre las horas de descanso y comida ya establecidas.
''';
}
