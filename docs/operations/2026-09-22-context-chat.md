# SARA: historial, conversaciones y contexto personal

Actualización: 21 de septiembre de 2026, noche de Ciudad de México (22 de septiembre UTC).
Fuente: petición explícita de Pedro, pruebas locales y comprobaciones en cite-server y su Pixel 10 Pro XL. Versión móvil 1.2.0+3.

## Resultado

- Chat: carga inicialmente las últimas 12 horas. Al llegar arriba solicita el bloque anterior; permite repetirlo, conserva lo visible y muestra desde qué fecha está cargado. Dentro de un bloque concurrido pagina por 60 mensajes, con cursor estable por fecha/id y pertenencia al usuario. No descarga todo el historial ni lo reenvía al modelo.
- Calendario: desaparecieron casillas, tachados, porcentajes y acciones para marcar completado. Los registros históricos siguen conservados. Se puede abrir «Platicar cómo me fue»; contar un resultado no marca automáticamente un evento.
- Conversaciones: seis invitaciones diarias a las 09:00, 11:30, 14:00, 16:30, 19:00 y 21:30, Ciudad de México. Respeta descanso y bloques de sueño. Recordatorios de actividades 10 minutos antes, programados separadamente. No exige reportar cada tarea.
- Al abrir un aviso, el servidor guarda una pregunta idempotente en el chat. Si hay una actividad reciente pertinente y permiso de agenda, pregunta cómo fue; si no, invita a contar el día. La respuesta al seguimiento se conserva como un episodio fechado mediante el servicio de memoria existente.
- Contexto: recupera recuerdos relevantes anteriores a las últimas 200 entradas y busca declaraciones históricas del usuario mediante búsqueda textual española indexada en PostgreSQL. Selecciona fragmentos con presupuesto de contexto; conserva fechas y da prioridad a correcciones recientes. No reentrena pesos ni promete memoria ilimitada.
- Se mantiene la subida y entrega bidireccional de fotos/documentos y el flujo de propuestas para crear, mover y cancelar. La validación real de esos recorridos está en `2026-09-21-files-calendar.md`.

## Importación personal

55 documentos seleccionados de PersonalLLM: inicialmente 30 SAFE y 25 OPT_IN. El primer lote importó 31 revisiones nuevas y reconoció 24 sin cambios. Se actualizaron después HOY y su clasificación a OPT_IN, porque ya contenía información financiera/familiar. Total final seleccionado: 29 SAFE y 26 OPT_IN, con 54 originales indexables y uno guardado cuya extracción requiere revisión.

Las 26 revisiones privadas tienen autorización explícita para el dispositivo emparejado de Pedro. El permiso está ligado al documento, revisión y destinatario: no habilita otras revisiones futuras ni otros clientes automáticamente. NEVER_UPLOAD permanece excluido incluso con permiso. Fuentes privadas derivadas no se convierten en memorias globales por esta importación.

No se leyeron ni copiaron la bóveda prohibida ni INBOX. Se omitieron originales oficiales sensibles, credenciales, formatos no soportados, instrucciones, paquetes y archivos derivados/históricos excluidos por el importador. «Subir la carpeta» se implementó como sincronizar sus documentos admisibles, no como copiar indiscriminadamente cada archivo. No se modificaron los originales documentales. HOY conserva copia previa verificada en el archivo local y deja constancia de la reanudación; las prioridades antiguas no se dieron por cumplidas ni se importaron como citas nuevas.

## Evidencia

- Backend: 189 pruebas pasan, 1 omitida; después del ajuste final de búsqueda, las 11 pruebas pertinentes de historial, permisos, recuerdos antiguos y chat durable vuelven a pasar.
- Flutter: 22 pruebas pasan; análisis sin incidencias. Prueba de presentación del chat repetida tras añadir el indicador de fechas.
- PostgreSQL desplegado: migración `a21b12c01`, permisos por revisión, índice de historial y búsqueda textual. Una frase sintética de 2020 se recuperó con una pregunta que contenía palabras adicionales; la transacción de prueba se revirtió.
- API autenticada del teléfono: `/v1/chat/history` y el bloque anterior devolvieron HTTP 200. Recuperación documental real: cinco fragmentos pertinentes sin imprimir contenido privado.
- Pixel real: APK instalado conservando sesión, seguimiento abierto y pregunta durable visible. Desplazamiento hacia mensajes anteriores disparó cargas de bloques de 12 horas; se verificó HTTP 200 para una ventana anterior del 19 de septiembre.
- Permiso Android concedido, seguimiento activado y seis notificaciones recurrentes registradas en el plugin, con zona America/Mexico_City. La prueba inmediata apareció como notificación de la app en Android. No se simuló que ya hubieran transcurrido las horas de mañana.

## Despliegue y recuperación

Backend y worker reconstruidos y saludables en cite-server. Base y código previos conservados en `/home/cite/AgentAgenda/99_ARCHIVO/2026-09-22-context-chat/`: `database.dump`, `backend-before.tar.gz` y manifiestos de importación. Imagen previa: `agentagenda-backend:before-20260922-context`.

La migración es aditiva. Para volver al código anterior, restaurar el código y la imagen previos, etiquetar esta imagen como `agentagenda-backend:local` y recrear los servicios `agent-backend` y `document-worker`. Conservar tablas nuevas e información importada evita perder datos; una restauración total de base sólo debe hacerse conscientemente, porque reemplaza escrituras posteriores. No eliminar volúmenes.

## Límites actuales

Los avisos son locales y continúan con la app cerrada; no hay push del servidor. Las modificaciones hechas fuera del teléfono llegan al abrir o sincronizar la app. Android puede retrasar los avisos aproximados y una detención forzada puede bloquearlos. Las preguntas notificadas son invitaciones programadas: la personalización según el calendario ocurre al abrirlas.

La memoria mejora la continuidad mediante recuperación de datos y episodios; no equivale a aprendizaje automático del modelo, comprensión perfecta de todas las fechas ni contexto infinito. La sincronización de PersonalLLM es la realizada en esta sesión: cambios futuros en esa carpeta requieren una nueva importación. Los límites restantes de archivos y distribución figuran en el informe anterior.

APK final instalado: SHA-256 `f07764ee7cb5db6749462ade482b508189ddcff5c2d03c5c687bc0d1d68f0934`. Tras reinstalar conservó sesión, permiso y seis avisos. El catálogo contiene además documentos importados antes de esta sesión; el recuento de 55 corresponde a la selección sincronizada ahora.
