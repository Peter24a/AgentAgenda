# Agenda conversacional y autorización documental sin actualizar Android

Cambio de servidor solicitado el 15 de octubre de 2026 (America/Mexico_City).
No modifica `apps/mobile`, el APK, la versión de Play ni los contratos obligatorios
que consume la aplicación instalada. Conserva `/v1/chat/stream`, los mensajes SSE
y la confirmación de propuestas mediante su ID.

## Comportamiento

- El servidor resuelve las fechas relativas, semanas, días y horarios; el modelo
  aporta la actividad, pero no decide el cálculo de sus ocurrencias. Las fechas
  de la tarjeta y del texto se reconstruyen con los valores verificados.
- El contexto consulta el período solicitado y, al mover, las fechas de origen
  y destino. El contexto semanal presenta filas completas y conteos diarios;
  si el presupuesto obliga a omitir detalles, lo indica explícitamente.
- Fecha, hora, duración o alcance ambiguos producen una pregunta sin propuesta.
  El estado de aclaración dura 30 minutos, pertenece a usuario/dispositivo y
  mantiene su fecha de referencia. Una respuesta posterior puede corregir fecha
  u hora. No se crean eventos antes de confirmar.
- Dos propuestas con IDs distintos y el mismo título normalizado e intervalo
  no duplican la entrada. Se revisan cruces contra la agenda vigente antes de
  presentar y al confirmar, bajo el bloqueo transaccional del propietario.
- Las rutinas semanales requieren inicio y fin o una petición explícita de
  continuidad indefinida. La confirmación crea la rutina y sus próximas cuatro
  semanas; el worker mantiene el horizonte. Se respetan las ocurrencias editadas
  o canceladas. Una cancelación de fechas concretas usa los datos canónicos;
  las peticiones ambiguas de cancelar toda una serie piden precisar su alcance.
- Al pedir analizar un archivo nuevo, se identifica por catálogo y se pregunta
  si autoriza esa revisión para el asistente de ese dispositivo. «Sí, autorizo»
  continúa el análisis. También admite `/autorizar nombre` y `/revocar nombre`.
  Las nuevas revisiones requieren un permiso nuevo; no se marca toda la
  biblioteca como SAFE. La revocación también invalida el contexto histórico
  anterior y las memorias derivadas de fuentes sin permiso.

## Persistencia y compatibilidad

Dos tablas aditivas: `chat_pending_actions` y `proposal_contexts` (migración
`e25c01`, creación compatible con el arranque actual). El campo opcional
`routine` no cambia los campos que interpreta Android. Los originales existentes,
eventos y dispositivos no se migran ni se sustituyen. La reversión de código e
imagen puede conservar estas tablas aditivas.

## Verificación previa al despliegue

- **367 pruebas aprobadas, 2 omitidas** por configuración PostgreSQL opcional.
- Pruebas de integración con el formato exacto del cliente Android existente:
  aclaraciones, fecha calculada, conflictos, duplicados, rutina, documento y
  revocación. También se comprobó el contexto de 70 eventos semanales y el
  presupuesto de entradas grandes.
- Once comprobaciones con el modelo real y una base SQLite sintética aislada
  en el contenedor de revisión: viernes siguiente correcto pese a otra fecha
  seleccionada, respuesta a aclaración, confirmación, repetición de solicitud
  sin duplicados, conflicto, seis fechas de rutina y persistencia, permiso de
  documento, respuesta con folio/monto correctos, revocación y nueva solicitud
  de permiso. Todas correctas.
- No se abrieron conversaciones ni documentos de clientes durante la prueba.
  La ejecución de producción utiliza exclusivamente el espacio sintético de
  revisión y elimina lógicamente sus fixtures/revoca el dispositivo al terminar.

La interpretación de títulos y respuestas generales sigue dependiendo del
modelo. No se afirma cobertura de toda formulación posible ni verificación en
un teléfono físico; ante fechas o acciones no resueltas se solicita precisión.
