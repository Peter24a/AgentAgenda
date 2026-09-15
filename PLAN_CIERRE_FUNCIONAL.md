# AgentAgenda: plan para cerrar el funcionamiento completo

Actualizado: **15 de septiembre de 2026**. Estado: **trabajo pausado por petición de Pedro**. Fuente: revisión del código local, comprobaciones acotadas de `cite-server`, pruebas automatizadas y aclaraciones de Pedro en esta conversación. Los pasos sin marcar son trabajo pendiente, no acciones realizadas.

## Resultado que buscamos

Una agenda Android que conserve el horario real, ayude a reorganizar el día, guarde y recupere recuerdos verificables, haga seguimientos variables y permita configurar el despertador de las **06:45**. El servidor debe poder convertirse en la fuente de contexto para otros asistentes mediante MCP, con permisos y respaldo recuperable. Los detalles visuales menores quedan al final.

**El código de esta revisión está guardado localmente, pero no se desplegó ni se instaló en el teléfono. No se aplicó la corrección del calendario ni se configuró MCP en Codex. No se activaron avisos ni una alarma. PersonalLLM se conserva.** La app y los datos que estaban en producción continúan con su estado anterior.

## 1. Lo encontrado y lo preparado

| Área | Hallazgo | Estado al pausar |
| --- | --- | --- |
| Horario | La precarga se construyó con el plan del 31 de agosto: 70 bloques hasta noviembre, 50 a las 19:00 y 20 a las 09:00. No representa la semana que revisamos el 13 de septiembre. | Preparados un candidato de semana y una reconciliación que conserva historia y cambios manuales. **Sin aplicar.** |
| Agenda y permisos | Algunas rutas de agenda/propuestas aceptaban peticiones sin sesión y usaban el usuario predeterminado. Se comprobó una consulta sin autenticación con HTTP 200. | Corregidos autenticación y alcances en el código local. **La corrección aún no protege el servidor publicado.** |
| Sincronización | Varias operaciones REST no emitían cambios para otros clientes. Había inconsistencias de zona horaria y tipos de cambio en propuestas. | Corregidas las rutas revisadas, con pruebas. Falta verificar PostgreSQL y clientes reales. |
| Memoria | El chat incorporaba check-ins, pero no recuperaba de forma adecuada recuerdos semánticos generales. | Mejoradas recuperación, vigencia, revocación y límites de contexto. **Pedir «recuerda X» aún no crea por sí solo una memoria.** |
| Privacidad | No había una frontera suficiente entre documentos autorizados y contexto automático; la memoria carece de clasificación propia completa. | El código nuevo admite documentos explícitamente SAFE para contexto automático y excluye OPT_IN, no clasificados y borrados. Faltan clasificación de memorias y autorizaciones granulares. |
| MCP | Había errores de protocolo, autenticación y permisos; AgentAgenda no figuraba como conexión de Codex. | Corregido MCP HTTP y preparado transporte STDIO de lectura por SSH. **Sin desplegar, registrar ni probar desde una nueva sesión.** |
| Seguimientos | La invitación «¿cómo vas?» solo aparecía dentro de la app. | Implementados avisos Android locales, optativos y persistidos. Falta comprobar entrega en teléfono. |
| Despertador | No existía una alarma real de mañana. | Añadido acceso al Reloj del teléfono con 06:45 y días editables. Abrir Reloj no certifica que una alarma haya quedado activa. |
| Continuidad | Las exportaciones de contexto no equivalen a un respaldo restaurable del sistema. | Existe copia preventiva de base y código, pero falta respaldo completo y ensayo de restauración. **No retirar PersonalLLM todavía.** |

### Evidencia de pruebas

- Backend, estado local final: **178 pruebas pasan, 1 omitida**. Se ejecutó con SQLite en memoria, desde `/tmp`, sin usar la base personal. La prueba omitida de PostgreSQL no cuenta como validación de producción. Quedan advertencias de dependencias/APIs obsoletas.
- Móvil: **24 pruebas pasaron antes del último ajuste menor**; `flutter analyze` terminó sin incidencias después. Hay que repetir las pruebas sobre la versión final.
- `git diff --check` sin errores al cierre de código.
- APK debug inicial compilado, pero **sin la URL de producción** y anterior al cierre final. No instalarlo como entrega terminada. Se debe recompilar.
- No se realizaron pruebas físicas de los nuevos avisos ni del despertador.

## 2. Orden de trabajo al retomar

1. Revisar este documento y el diff local; preservar los cambios existentes en servidor y repositorio.
2. Verificar copia recuperable y desplegar primero las correcciones de acceso, memoria y sincronización.
3. Revalidar el horario para la fecha real de reanudación; previsualizar y aplicar su reconciliación.
4. Compilar e instalar la app conservando la sesión; probar calendario, avisos y Reloj en el teléfono.
5. Terminar escritura de recuerdos, privacidad y sincronización de memoria.
6. Conectar MCP y comprobar continuidad desde una sesión nueva, sin leer PersonalLLM automáticamente.
7. Completar operación, respaldo/restauración y una semana de uso real. Solo entonces evaluar retirar la carpeta activa.

No cambiar modelo, gateway, web personal ni servicios ajenos para resolver esta tarea. No borrar historia ni subir la carpeta personal completa a Git. No interpretar el paso de los días como confirmación de pendientes personales.

## 3. Despliegue y datos: prioridad inmediata

- [ ] Congelar una versión identificable del código final, con diff revisado y pruebas. Los cambios de esta revisión siguen en el árbol de trabajo; no se creó commit ni se hizo push.
- [ ] Verificar de nuevo el estado remoto. El servidor tenía cambios previos sin commit: **no ejecutar `git reset --hard`, no sustituir todo el repositorio y no hacer un pull que los pierda**. Antes de esta revisión, los archivos de ejecución comparados coincidían con el contenido local original; comprobarlo otra vez antes de copiar.
- [ ] Crear una copia nueva si producción cambió desde la pausa. Conservar base PostgreSQL, originales documentales/volúmenes, manifiesto de hashes, código, versión del esquema y configuración necesaria para recuperar el servicio. Los secretos requieren almacenamiento separado y protegido; nunca imprimirlos ni incluirlos en este Markdown o Git.
- [ ] Guardar la imagen anterior y preparar vuelta atrás de código. Una restauración de base requiere una decisión específica y comprobar cambios posteriores; no ejecutar un dump antiguo sobre datos nuevos por rutina.
- [ ] Construir y recrear únicamente `agent-backend` y `document-worker`. Conservar las restricciones de red y autenticación vigentes; no restaurar un Compose antiguo que reabra acceso anónimo.
- [ ] Verificar HTTPS, salud, conexión PostgreSQL, worker y una operación autenticada. Comprobar agenda/propuestas/MCP sin sesión → 401; alcances insuficientes → 403; aislamiento entre usuarios y dispositivos.
- [ ] Verificar escritura REST → lectura por sincronización, UTC ↔ America/Mexico_City, concurrencia, reintentos y confirmación de propuestas en PostgreSQL real.

Servidor: `ssh cite-server`; repositorio remoto: `~/AgentAgenda`; endpoint: `https://agenda-api.pedroibarra.dev`.

Copia preventiva creada durante esta revisión, **sin ensayo de restauración**:

```text
~/AgentAgenda-backups/20260915-review/before-review.dump
~/AgentAgenda-backups/20260915-review/backend-code.tgz
```

Esta copia no acredita por sí sola respaldo de originales documentales ni recuperación completa. El informe anterior [de inferencia y despliegue](docs/operations/2026-09-15-inference-deployment.md) conserva la instalación previa; sus afirmaciones de funcionamiento no sustituyen las pruebas pendientes de esta revisión.

El host tuvo un fallo de BuildKit. La alternativa ya documentada es construir desde la raíz remota con `DOCKER_BUILDKIT=0 docker build -t agentagenda-backend:local services/backend` y usar después Compose con `--no-build`. Revisar primero la configuración actual; no reiniciar Docker ni el motor compartido de inferencia para aplicar esta alternativa.

## 4. Horario fiel a lo hablado

La fuente de la semana actual sigue siendo [SEMANA_ACTUAL.md](/home/peterpad/Documents/PersonalLLM/SEMANA_ACTUAL.md), con las aclaraciones posteriores de Pedro por encima de propuestas anteriores. **06:45 es la hora solicitada para despertar; los días no quedaron confirmados.** Lunes a viernes es un valor inicial editable del móvil, no una decisión atribuible a Pedro.

El objetivo 2 h matemáticas + 2 h programación a mano + 2 h EGEL se conserva como aspiración. Las horas libres dentro de prácticas dependen de trabajo real; no sumarlas como disponibilidad garantizada, no duplicar clases dentro y fuera de prácticas y no recuperar automáticamente faltantes recortando el descanso. La hora matutina de matemáticas sigue siendo una propuesta por validar. No se prometen horas óptimas universales ni ciclos rígidos de aprendizaje.

Archivos preparados **fuera de Git**, con acceso local restringido:

- [Horario candidato para revisar](/home/peterpad/.local/share/AgentAgenda/reviews/2026-09-15/HORARIO_REVISADO.md).
- [Lote candidato](/home/peterpad/.local/share/AgentAgenda/reviews/2026-09-15/schedule-corrected.json): colección `operational-week-2026-09-15-v1`, 69 eventos entre el 15 y el 19 de septiembre, sin solapamientos internos detectados. Su revisión vence el 20; no es una recurrencia permanente.
- Origen remoto de la precarga anterior: `~/AgentAgenda-imports/20260915/schedule-plan.json`. No editar ese original.

### Antes de aplicar

- [ ] Si se retoma después de esta semana, producir un candidato vigente en lugar de cargar fechas pasadas. Conservar el candidato del día 15 como evidencia histórica.
- [ ] Validar margen entre despertar, matemáticas, desayuno y salida. El candidato 07:00–08:00 de matemáticas / 08:00–08:30 de preparación es **provisional**, no una rutina confirmada.
- [ ] Resolver los días del despertador y la excepción del sábado: el trabajo empieza a las 07:00 y el traslado puede requerir salir a las 06:30. No asignar 06:45 a ese día sin revisar la logística.
- [ ] Mantener viernes y domingo condicionados a viaje/trabajo reales; HTI fuera de asistencia. Revisar la excepción del 16 de septiembre únicamente si aún es pertinente.
- [ ] Representar explícitamente disponibilidad, aceptación y vigencia de bloques. Los marcadores `[PROVISIONAL]` / `[CONDICIONAL]` sirven como protección inicial; añadir estado estructurado para que editar un título no active accidentalmente avisos.
- [ ] Usar una colección diferente para el nuevo lote y ejecutar `reconcile-preview`. Eliminar del calendario solo los eventos futuros de la precarga antigua que sigan exactamente intactos; preservar completados, editados, borrados e historia.
- [ ] Revisar conflictos con actividades conservadas antes de `reconcile-apply`. Si hay conflictos, ajustar el candidato; no sobrescribir la edición del usuario.
- [ ] Verificar en Día/Semana/Mes y en MCP horas, zona, sueño que cruza medianoche y ausencia de duplicados. Repetir el lote debe ser idempotente.
- [ ] Mostrar al usuario qué días están realmente planificados. Retirar las sesiones antiguas hasta noviembre y cargar solo una semana deja semanas siguientes sin plan: no rellenarlas silenciosamente con la rutina vieja.
- [ ] Implementar revisión semanal y ajustes del día como propuestas con vista previa, confirmación y registro de cambios. No mover compromisos fijos ni tratar lo programado como realizado.

CLI disponible en el código nuevo, desde el backend desplegado con acceso a ambos lotes privados:

```sh
python -m app.importing.schedule reconcile-preview OLD.json NEW.json --user-id default_user --cutoff AAAA-MM-DD
python -m app.importing.schedule reconcile-apply OLD.json NEW.json --user-id default_user --cutoff AAAA-MM-DD
```

Sustituir rutas y fecha por valores revisados. Los archivos del host no aparecen automáticamente en el contenedor. El corte debe corresponder al periodo que se decida migrar, sin eliminar historia de días ya transcurridos.

**Criterio de cierre:** el calendario refleja obligaciones reales, explica qué es tentativo y permite adaptar un día ocupado sin perder tareas ni inventar disponibilidad. El temario se desarrolla aparte, después de validar el horario.

## 5. Avisos variables y despertador

### Lo implementado localmente

En **Tu agenda → campana «Avisos y despertador»** hay activación voluntaria, permiso de Android, prueba manual, sincronización y próximos avisos. El cálculo coloca un seguimiento al terminar bloques de 20–89 min y 15 min antes del final de bloques de al menos 90 min; separa avisos 75 min y limita a cuatro por día inicialmente. Excluye completados, sueño y bloques provisionales/condicionales.

Se conservan ajustes y datos mínimos para los avisos ya programados, sin títulos/descripciones en la caché de planificación ni en el texto visible de la notificación. La entrega es aproximada. La app todavía **no recibe cambios externos mediante push mientras permanece cerrada**.

El botón **Configurar 06:45 en Reloj** abre el Reloj Android con hora y días seleccionados. Cambiar los ajustes de AgentAgenda no cambia ni elimina alarmas ya guardadas en Reloj. La app no verifica si el usuario la dejó activa. Documentación y fuentes oficiales: [README móvil](apps/mobile/README.md).

### Trabajo pendiente

- [ ] Repetir `flutter test`, `flutter analyze` y compilar con `--dart-define=BACKEND_URL=https://agenda-api.pedroibarra.dev`. El APK existente no es la entrega válida.
- [ ] Instalar con conservación de datos y firma compatible, sin desinstalar ni perder emparejamiento. Comprobar URL y sesión usando la propia app, sin extraer sus credenciales privadas.
- [ ] Activar seguimientos y conceder permiso; verificar que denegarlo no rompa la agenda y que se vea claramente si no habrá avisos.
- [ ] Probar aviso real con app abierta, cerrada normalmente, sin red y tras reiniciar el teléfono. Comprobar toque → evento/check-in correcto, envío y recuperación del registro posterior.
- [ ] Verificar que completar, mover o borrar un evento cancele/reprograme su aviso, también tras cambios desde otro cliente.
- [ ] Revisar selección/prioridad: el límite diario no debe quedar consumido por pausas, trayectos o comidas si Pedro busca seguimiento de estudio. Permitir elegir categorías y evitar insistencia por falta de respuesta.
- [ ] Incorporar entrega de cambios externos al teléfono: decidir e implementar push (p. ej. FCM como señal sin contexto privado) y sincronización autenticada; mantener reconciliación al abrir. Si se usa trabajo periódico como alternativa, documentar y medir su demora. No presentarlo como entrega instantánea.
- [ ] Revalidar quiet hours y eventos cancelados **al entregar**, o suprimir avisos vencidos. Actualmente se filtra al programar: Android podría retrasar un aviso hasta el descanso.
- [ ] Ajustar zona del calendario, zona del dispositivo y viajes; probar que la alarma suene a la hora local que Pedro espera y no confundirla con avisos de estudio.
- [ ] Guardar la alarma en Reloj, verificar días, activación, sonido y volumen, y hacer una prueba cercana. No declarar «te despertará» por haber abierto el intent.
- [ ] Documentar límites observados: detención forzada, ahorro de batería, permisos revocados y ajustes del sistema. No prometer entrega exacta de notificaciones comunes.

**Criterio de cierre:** Pedro recibe un seguimiento útil, lo responde y ese dato aparece posteriormente; el cambio de una actividad no produce un aviso viejo; el Reloj tiene una alarma activa comprobada. No hace falta construir un despertador nativo propio si el del sistema cumple esta función.

## 6. Memorias y contexto que sí sobreviven

- [ ] Crear un flujo de **propuesta de memoria → confirmación → operación persistida → recibo visible** para «recuerda», «corrige» y «olvida». El modelo no debe afirmar que guardó algo sin un resultado de escritura real.
- [ ] Guardar fuente, fecha observada, vigencia, certeza y versión. Diferenciar hechos, preferencias, intenciones, observaciones de un día e inferencias. Un check-in no se convierte automáticamente en hábito permanente.
- [ ] Dar a cada memoria clasificación propia SAFE / OPT_IN y autorizaciones con finalidad, destinatario y duración. El nivel derivado debe heredar el más sensible de sus fuentes. NEVER_UPLOAD no ingresa en almacenamiento o contexto del modelo.
- [ ] Implementar confirmación puntual para usar OPT_IN en una tarea concreta; denegar por defecto desde otros clientes. No resolverlo con un interruptor global que exponga toda la biblioteca.
- [ ] Añadir una vista funcional para consultar, corregir, revocar y entender qué recuerda la app. Conservar versiones e historia sin reintroducir información corregida por resúmenes o mensajes antiguos.
- [ ] Emitir altas/cambios/revocaciones de memoria en sincronización y bootstrap. Resolver reintentos y conflictos sin duplicar hechos ni revivir versiones retiradas.
- [ ] Actualizar manualmente el mínimo contexto operativo SAFE necesario para el horario vigente, con fuente y fecha. No volver a importar todo PersonalLLM para actualizar una preferencia.
- [ ] Probar la cadena completa: «recuerda» confirmado → reiniciar → nueva conversación → recuperación correcta → corrección → respuesta nueva → revocación → ausencia del contexto revocado.
- [ ] Probar negación de permisos, fuentes borradas, documentos sin clasificación, recuerdos vencidos y usuarios distintos. Contenido documental aporta datos, nunca órdenes para cambiar permisos o ejecutar acciones.
- [ ] Construir contexto por capas: perfil vigente pequeño, estado del día/semana, recuerdos relevantes y fragmentos de fuentes con citas. Medir presupuesto de tokens y respuestas del modelo real; no truncar arbitrariamente lo que cambia una decisión.
- [ ] Generar una propuesta de resumen semanal revisable con hechos realizados, cambios, pendientes y dudas. Guardar procedencia y permitir corrección; no convertir el resumen en una segunda fuente canónica mantenida a mano.
- [ ] Para revisión con un modelo grande, exportar un paquete mínimo SAFE por defecto, con permiso explícito para material adicional. No enviar automáticamente archivos personales a terceros ni inferir que usar MCP autoriza toda la biblioteca.

El código de esta revisión ya mejora la lectura de memoria y el filtrado documental, pero no completa los pasos anteriores. Detalle del importador y límites: [PERSONAL_IMPORT.md](docs/PERSONAL_IMPORT.md).

**Criterio de cierre:** el asistente distingue conversación de memoria persistida, muestra evidencia de lo guardado y conserva correcciones/permisos entre dispositivos y sesiones.

## 7. MCP como acceso al contexto del servidor

- [ ] Desplegar `services/backend/app/mcp/stdio.py` y verificar JSON-RPC: initialize, tools/list, llamada de lectura autorizada, notificaciones sin respuesta, errores y límites de entrada. Mantener stdout reservado para protocolo.
- [ ] Registrar la conexión local usando SSH existente, sin tokens incrustados:

  ```sh
  codex mcp add agentagenda -- ssh -o BatchMode=yes -o ConnectTimeout=10 cite-server docker exec -i agent-backend python -m app.mcp.stdio
  ```

- [ ] Confirmar primero que el contenedor y el usuario objetivo corresponden a esta instalación. El adaptador preparado usa `default_user` y permisos de lectura: no es una solución multiusuario general. La autoridad de este transporte es la cuenta SSH.
- [ ] Verificar en una sesión nueva que Codex ve las herramientas y puede consultar solo el contexto autorizado. Una entrada en configuración no demuestra que las herramientas ya estén cargadas en la sesión actual.
- [ ] Probar una consulta del horario vigente y recuerdos de prueba mínimos; no usar una lectura masiva de documentos personales como prueba de conectividad.
- [ ] Si se habilita HTTP MCP para otros clientes, exigir identidad, alcances por herramienta, validación de origen/protocolo y pruebas de rechazo. No publicar acceso genérico sin permisos.
- [ ] Definir la fuente canónica para cada tipo de dato. El calendario y las memorias confirmadas deben tener una sola autoridad; archivos antiguos se conservan como fuentes, no como instrucciones vigentes por defecto.
- [ ] Preparar un archivo de arranque local mínimo con instrucciones, dirección del servicio, límites de privacidad y modo de recuperación. No asumir que cualquier conversación nueva recordará automáticamente cómo conectarse.
- [ ] Comprobar un arranque sin leer PersonalLLM: obtener estado vigente, fuentes y pendientes desde MCP; si el servidor está caído, declarar indisponibilidad sin inventar ni usar silenciosamente un resumen viejo.

El transporte inicialmente de lectura es suficiente para consultar contexto. Cualquier escritura futura por MCP debe pasar por permisos, confirmación de cambios cuando corresponda, control de versiones e idempotencia; no abrir escritura arbitraria de archivos.

## 8. Operación fiable y retirada de PersonalLLM

- [ ] Probar renovación de sesión durante uso activo, expiración/revocación, desconexión SSE y reintentos. Una conversación o escritura fallida no debe aparentar éxito ni duplicarse al reintentar.
- [ ] Verificar experiencia sin red y recuperación: qué se puede consultar, qué queda pendiente de envío, qué nunca debe mostrarse como guardado hasta llegar al servidor.
- [ ] Definir una entrega Android estable, con versión y firma conservada, copia segura de la clave y procedimiento de actualización. No exigir firma de producción para el primer ensayo, pero resolverla antes de depender diariamente del sistema.
- [ ] Añadir comprobaciones de salud/alertas operativas y registro de fallos sin cuerpos privados ni secretos. Medir disponibilidad, errores de sincronización, worker atrasado y antigüedad del último respaldo.
- [ ] Automatizar respaldo de PostgreSQL, originales y metadatos de versiones/permisos, más configuración de recuperación protegida. Definir retención y una copia fuera de la misma máquina.
- [ ] Restaurar en un entorno aislado y comparar integridad, archivos, tareas, eventos, memorias, permisos, historia y sincronización. Probar pérdida/reinstalación del teléfono y recuperación de acceso sin exponer tokens.
- [ ] Hacer una prueba de uso real durante una semana: día completo, día con prácticas ocupadas, viaje, rancho y disponibilidad dominical variable. Registrar fallos concretos y corregirlos antes de declarar cierre.
- [ ] Verificar que documentos históricos importados tengan fuente y clasificación correctas sin abrir fuentes privadas innecesariamente. Los conteos de una importación anterior no certifican la calidad de las memorias ni su accesibilidad adecuada.
- [ ] Demostrar continuidad desde otra sesión/dispositivo y recuperación desde respaldo. Un export con hash no demuestra que pueda reconstruirse la aplicación.
- [ ] Una vez cumplido lo anterior, acordar retirar PersonalLLM como carpeta activa: conservar archivo recuperable y dejar un punto de entrada mínimo. **Eliminarla definitivamente es una acción posterior explícita de Pedro.**

## 9. Comprobación final y decisiones pendientes

Se considera cerrado el alcance funcional cuando pasan estos recorridos completos:

| Recorrido | Evidencia necesaria |
| --- | --- |
| Planificar y adaptar | Jornada realista sin solapamientos; propuesta revisable; cambios conservados tras reinicio y sincronización. |
| Recordar | Alta/corrección/revocación confirmadas, con fuente y permisos, recuperables en otra conversación. |
| Acompañar | Seguimiento entregado en teléfono, respuesta guardada, no repetición tras completar y ningún aviso obsoleto tras sincronizar. |
| Despertar | Alarma activa en Reloj con hora/días correctos y prueba sonora. |
| Conectar | Sesión nueva consulta contexto autorizado mediante MCP sin depender de leer toda la carpeta. |
| Recuperar | Restauración completa probada; actualización de app/backend sin perder sesión, archivos o historia. |

Pendientes de preferencia que se resuelven al probar, sin bloquear hoy el cierre documental: días del despertador y hora del sábado; aceptación del bloque matutino; categorías/frecuencia de seguimientos; disponibilidad de domingo. **«Variable y a las 6:45» no confirma por sí solo todas esas opciones.**

Después de estos recorridos: ajustes menores de apariencia, animaciones y refinamientos visuales. Antes, únicamente cambios de interfaz necesarios para entender permisos, guardar/corregir recuerdos, aceptar horarios y saber si algo falló.

## 10. Puntos de entrada para continuar el código

| Parte | Archivos principales |
| --- | --- |
| Reconciliación de horario | `services/backend/app/importing/schedule.py`, `tests/test_schedule_import.py` dentro del backend |
| Agenda y propuestas | `app/api/agenda.py`, `app/api/proposals.py`, `app/services/agenda_service.py`, `app/services/proposal_service.py` dentro del backend |
| Contexto y memoria | `app/services/context_engine.py`, `context_visibility.py`, `memory_service.py`, `chat_orchestrator.py`, `app/api/memory.py` dentro del backend |
| MCP | `services/backend/app/api/mcp.py`, `app/mcp/server.py`, `app/mcp/stdio.py` dentro del backend |
| Pruebas nuevas del backend | `services/backend/tests/test_agenda_access_sync.py`, `test_context_access_regressions.py` en el mismo directorio |
| Avisos Android | `apps/mobile/lib/core/notifications/`, pantalla `apps/mobile/lib/features/agenda/presentation/screens/notifications/`, `apps/mobile/test/notifications/` |

Para pruebas locales de backend, usar explícitamente la base sintética y ejecutar desde `/tmp`, evitando cargar configuración personal por el directorio actual:

```sh
cd /tmp
PYTHONPATH=/home/peterpad/Documents/AgentAgenda/services/backend DATABASE_URL=sqlite+aiosqlite:///:memory: /home/peterpad/Documents/AgentAgenda/services/backend/.venv/bin/pytest -q --tb=short --disable-warnings /home/peterpad/Documents/AgentAgenda/services/backend/tests
```

La documentación histórica describe estados anteriores. Este archivo es el punto de continuación de **esta revisión**, y debe actualizarse con resultados observados al completar cada fase, sin marcar realizado lo que solo se preparó localmente.
