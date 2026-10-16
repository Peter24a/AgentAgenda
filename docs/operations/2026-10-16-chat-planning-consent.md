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
modelo. No se afirma cobertura de toda formulación posible; ante fechas o
acciones no resueltas se solicita precisión.

## Producción

Publicado en backend y worker de los **seis espacios activos**, conservando sus
contenedores PostgreSQL, volúmenes, puertos y configuración. Se verificaron los
hashes de todas las fuentes dentro de cada imagen, salud y autenticación SARA.
Release final: `agentagenda-backend:chat-planning-consent-20261016-r2`.

La primera prueba publicada detectó que «14:30 hora de Ciudad de México» podía
interpretarse como una duración. Se corrigió en `0eee8c1`, se añadieron tres
regresiones y pasaron **101 pruebas específicas** de fechas y compatibilidad.
El respaldo cifrado y reversión del release final están en
`/srv/agentagenda/recovery/deploy-chat-planning-consent-20261016-r2/`.

La repetición final completó **31/31 comprobaciones en producción**, incluyendo
subida/extracción/descarga de PDF, DOCX y OCR, permiso por chat sin clasificación
manual, hechos y citas reales, revocación, creación pendiente, confirmación y
reintento, hora local, movimiento, rechazo, cancelación, viernes siguiente y
rutina semanal confirmada sobre PostgreSQL. Informe privado:
`/srv/agentagenda/recovery/planning-release-check-ab5e6437d8.json`.
Se pausaron las rutinas sintéticas, se eliminaron lógicamente los archivos y
eventos de comprobación y se revocó el dispositivo. No se afirma purga física.

Una comprobación adicional del endpoint heredado `/v1/chat/stream`, con el
cuerpo exacto de Android (`message`, `date`, `history`), pasó **4/4** controles:
activación sintética, aislamiento entre espacios, respuesta SSE de aclaración
sin propuesta y revocación del dispositivo. Informe privado:
`/srv/agentagenda/recovery/planning-release-check-dd03c7c1e5.json`.

## Teléfono físico con la aplicación oficial

Se verificó por ADB el Pixel 10 Pro XL conectado por el propietario, con
**AgentAgenda 2.0.3, versionCode 10**, instalada previamente. No se instaló,
actualizó ni recompiló la aplicación.

- «Agenda Prueba de compatibilidad del telefono» preguntó fecha, hora y duración.
- «El 18 de abril de 2030 de 14:00 a 14:15» recuperó la aclaración y presentó la
  tarjeta con fecha y horario correctos, pendiente de aprobación.
- Se pulsó **Descartar**. Una consulta de solo lectura limitada a esa prueba
  confirmó estado `rejected` y **cero eventos creados** con ese título.

Esta prueba física cubre aclaración, continuidad del chat, presentación y rechazo
de propuestas en la versión instalada. Las comprobaciones documentales y de
rutinas descritas arriba se ejecutaron por API contra el espacio sintético.
