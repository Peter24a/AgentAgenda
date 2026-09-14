from datetime import datetime
from typing import List, Dict, Any
from app.models.agenda import AgendaItemModel
from app.models.chat import ChatMessageModel

SYSTEM_PROMPT = """Eres el Agente Inteligente de AgentAgenda, una agenda personal donde el usuario interactúa exclusivamente a través de ti (no hay formularios manuales).
Tu misión es organizar su tiempo, resolver dudas y proponer ajustes estructurados a su itinerario.

REGLAS ESTRICTAS:
1. Respeta los descansos y comidas ya existentes.
2. Si el usuario pide agendar, mover o cancelar algo, responde amablemente y genera SIEMPRE un bloque de propuesta en formato ```proposal ... ```:
```proposal
{
  "summary": "Título conciso del cambio propuesto",
  "reason": "Justificación breve del ajuste",
  "items": [
    {
      "id": "id-unico-o-existente",
      "title": "Nombre de la actividad",
      "category": "work|food|sleep|exercise|study|leisure|general",
      "start_time": "YYYY-MM-DDTHH:MM:SS",
      "end_time": "YYYY-MM-DDTHH:MM:SS",
      "description": "Detalle opcional"
    }
  ]
}
```
3. La aplicación móvil requiere confirmación explícita del usuario para aplicar la propuesta.
4. Si el usuario solo charla o pregunta algo sin modificar la agenda, responde de manera concisa y empática sin bloque de propuesta.
"""

def build_llm_messages(
    current_date: str,
    events: List[AgendaItemModel],
    user_message: str,
    history: List[ChatMessageModel]
) -> List[Dict[str, str]]:
    # Create compact context representation (~50-100 tokens)
    events_str = "\n".join([
        f"- [{e.start_time.strftime('%H:%M')} a {e.end_time.strftime('%H:%M') if e.end_time else '?'}] {e.title} ({e.category.value})"
        for e in events
    ]) or "No hay actividades registradas aún para esta fecha."

    context_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"--- CONTEXTO ACTUAL ---\n"
        f"Fecha actual: {current_date}\n"
        f"Actividades agendadas hoy:\n{events_str}\n"
        f"----------------------"
    )

    messages = [{"role": "system", "content": context_prompt}]

    # Include recent history (limit to last 6 messages to save context)
    recent_history = history[-6:] if len(history) > 6 else history
    for msg in recent_history:
        messages.append({
            "role": "user" if msg.is_user else "assistant",
            "content": msg.text
        })

    # Add current user message
    messages.append({"role": "user", "content": user_message})
    return messages
