# Operación de AgentAgenda por espacios

Despliegue del 8 de octubre de 2026, en `cite-server`. Este documento describe la plataforma implementada; el [plan de migración](MULTITENANCY_MIGRATION_PLAN.md) conserva las decisiones y el diseño previo. Las credenciales, códigos de activación, manifiestos privados y contenidos de clientes permanecen fuera de Git.

## Entrada y recursos desplegados

La dirección pública es `https://agenda-api.pedroibarra.dev`. El túnel existente de Cloudflare continúa llegando a `127.0.0.1:8001`, donde ahora escucha la plataforma. No se crea DNS ni otro túnel al dar de alta un cliente.

| Componente | Ubicación o función |
| --- | --- |
| Panel administrativo | `/` y `/admin`; acceso directo con cuenta administrativa independiente de la agenda de Pedro |
| Activación del navegador | `/activar` |
| Dashboard del propietario | `/app`: agenda, conversación, documentos y dispositivos |
| Administración por API | `/control/v1/*` |
| Activación y sesión del propietario | `/platform/v1/*` |
| API de cada espacio | `/s/<UUID>/v1/*` |
| Compatibilidad personal | `/v1/*`, vinculada explícitamente al espacio existente de Pedro |
| APK común firmado | `/download/agentagenda.apk` |
| Servicio de entrada | `agentagenda-platform.service`, proceso nativo en `127.0.0.1:8001` |
| Backend adoptado de Pedro | `127.0.0.1:8201` |
| Backend adoptado de Walter | `127.0.0.1:8202` |
| Nuevos backends | Puertos privados persistidos desde 8400; disponibles entre 8400 y 9399 |
| Mapeo privado de espacios existentes | `/etc/agentagenda/spaces.json` |

Cada espacio conserva su propia base PostgreSQL, bóveda documental, backend y worker. La imagen de backend y el motor de IA se comparten. El identificador UUID permanece estable al suspender, reabrir, reinstalar una app o cambiar el nombre del propietario.

Una ruta desconocida devuelve rechazo y nunca utiliza la agenda personal como destino. El gateway exige identidad del backend seleccionado, elimina las cabeceras de inscripción y secretos de aplicación, bloquea `/internal/*` y transmite chat SSE y descargas sin redirigir a hostnames anteriores. La suspensión también bloquea `/v1/*` cuando corresponde al espacio personal.

## Almacenamiento y claves

El almacenamiento de la plataforma reside en un contenedor LUKS de 64 GiB, archivo disperso `/home/cite/AgentAgenda-platform/spaces.luks`, montado en `/srv/agentagenda`. El servicio `agentagenda-storage.service` monta el almacenamiento antes de Docker. La dependencia se configura en `docker.service.d/agentagenda-storage.conf`; el aprovisionador y los respaldos rechazan trabajar si el montaje no está disponible.

```text
/srv/agentagenda/
├── control/
│   ├── platform.sqlite3       Registro, invitaciones, sesiones y operaciones
│   └── operations/            Logs privados de aprovisionamiento
├── runtime/
│   ├── ports.json            Asignación persistente de puertos nuevos
│   ├── ports.lock            Exclusión para el asignador
│   └── <UUID>/
│       ├── compose.json       Servicios y configuración privada
│       ├── resources.json     Recursos registrados del espacio
│       └── lifecycle.lock     Coordinación de operaciones y respaldos
├── spaces/<UUID>/
│   ├── postgres/             Datos de PostgreSQL
│   └── vault/                Originales documentales y temporales
└── recovery/                 Área temporal de respaldos y restauraciones
```

La configuración y las claves viven en `/etc/agentagenda`, con permisos restrictivos. `platform.env` configura el servicio; `platform.key` cifra las credenciales guardadas en el registro; `admin-password.hash` contiene el hash de la contraseña administrativa; `backend-shared.json` configura la inferencia compartida; `backup.agekey` permite recuperar los respaldos. Las claves no se incorporan a los archivos de respaldo.

Existe una copia privada de recuperación en `/home/peterpad/.local/share/agentagenda/recovery`. Mantener otra copia fuera del servidor y del equipo de trabajo sigue siendo una tarea operativa manual. Perder la clave LUKS impide abrir el almacenamiento; perder `platform.key` impide recuperar secretos y sesiones del registro; perder la clave de `age` impide descifrar las copias archivadas. Respaldar también la firma Android fuera de Git para conservar futuras actualizaciones del paquete general.

## Crear y reconectar un cliente

1. Abrir `/admin` e iniciar la sesión administrativa.
2. Crear el espacio con nombre, propietario y cuota documental. La preparación se muestra como operación en curso; el espacio sólo queda disponible después de que su backend arranca y supera la comprobación de salud.
3. Generar el código de activación y entregarlo al propietario por un canal privado. Los códigos predeterminados vencen a las 24 horas y se consumen una vez.
4. El propietario instala el mismo APK que los demás clientes e introduce el código, o abre `/activar` para autorizar su navegador.
5. Comprobar que aparece el espacio correcto y que puede consultar su agenda y sus documentos. Cada dispositivo recibe credenciales propias, revocables.

Al reinstalar la aplicación de Pedro, generar una **reconexión al espacio existente**, conservando su UUID y propietario de datos. El contenido sincronizado se consulta desde la misma base; no se vuelve a importar ni a sembrar. Si hay cambios exclusivamente locales en el teléfono anterior, sincronizarlos o exportarlos antes de desinstalarlo. Los permisos Android y los avisos locales requieren configuración nueva.

El dashboard del propietario permite autorizar otro dispositivo y revocar sus sesiones. El administrador sólo dispone de metadatos y acciones de servicio: su sesión no abre el contenido del cliente. Para una reconexión que traslade permisos documentales del teléfono anterior, el operador puede indicar `--replace-device-id`: sólo copia autorizaciones vigentes del mismo titular y de las revisiones originales permitidas; excluye documentos `NEVER_UPLOAD`, eliminados, desconocidos o de otro titular, y no autoriza futuras revisiones. El teléfono anterior se revoca después de verificar la sesión nueva.

La CLI se ejecuta con el entorno privado del servicio, desde `/home/cite/AgentAgenda-platform/code/services/platform`, utilizando `/opt/agentagenda-platform/venv/bin/python`. Consultar el UUID en el panel o en el mapeo privado antes de utilizarla:

```sh
python -m app.cli list-spaces
python -m app.cli create-invite UUID --purpose reconnect
python -m app.cli create-invite UUID --purpose reconnect --replace-device-id ID_ANTERIOR
```

Los comandos de invitación imprimen una credencial temporal. Ejecutarlos en una terminal privada y no copiar el resultado a documentación pública, logs compartidos o tickets.

La app y la web conservan un `request_id` aleatorio al activar. Si se pierde la respuesta, reintentar con la misma solicitud recupera el mismo resultado; otra solicitud no puede reutilizar el código. El registro y el backend conservan recibos cifrados para reconciliar esa emisión sin duplicar dispositivos.

## Suspender, cerrar y reabrir

| Acción | Resultado |
| --- | --- |
| Suspender | Bloquea la entrada inmediatamente y solicita detener los recursos del espacio; conserva sus datos y la sesión web para una reactivación posterior. |
| Reactivar | Arranca los mismos recursos y habilita el acceso cuando vuelve a estar saludable. |
| Cerrar | Bloquea la entrada, invalida las sesiones web y detiene los recursos; conserva base, archivos y respaldos. |
| Reabrir | Arranca el mismo espacio conservado, sin crear otra base ni otro propietario. |
| Reintentar alta fallida | Reutiliza los identificadores y recursos de la operación incompleta. |

Las operaciones se observan en el panel y en `/control/v1/operations`. El helper sólo acepta acciones fijas y UUID; ninguna petición pública elige comandos, rutas, destinos de red o nombres de contenedores. Sus archivos de configuración y asignaciones se escriben mediante reemplazo atómico, con sincronización a disco. Las operaciones de cada espacio y sus respaldos comparten un bloqueo de ciclo de vida.

**No hay una operación pública de purga definitiva.** Cerrar conserva el espacio; una solicitud de eliminación se tramita mediante el procedimiento manual siguiente. La retención de treinta días se aplica a archivos de respaldo regulares y no borra automáticamente el espacio cerrado. Una operación fallida mantiene el acceso bloqueado cuando corresponde y permite revisar el diagnóstico privado antes de reintentar.

## Solicitud de eliminación y control de restauraciones

La vía pública es `https://agenda-api.pedroibarra.dev/soporte#eliminacion`, enlazada desde la app, con correo `pibarrafacio@gmail.com`. El operador tramita la solicitud; este documento no ejecuta purgas ni convierte cierre o borrado lógico en eliminación definitiva. Google admite un flujo de soporte para solicitar eliminación y requiere explicar cualquier retención excepcional. [Requisitos oficiales de eliminación](https://support.google.com/googleplay/android-developer/answer/13327111?hl=en).

1. **Verificar solicitud y titular.** Asignar una referencia aleatoria, confirmar el UUID y el alcance —espacio completo o datos concretos— mediante el canal previamente conocido o una prueba con un dispositivo autorizado. Nombre del espacio o UUID públicos por sí solos no acreditan titularidad. No solicitar contraseñas, códigos de recuperación ni conversaciones/documentos como prueba. Si el usuario perdió el dispositivo, usar la relación de alta y contacto previamente verificados.
2. **Registrar la eliminación fuera de las copias que podrían revertirla.** Mantener un registro privado independiente, propuesto en `/etc/agentagenda/deletion-ledger.jsonl`, con permisos 0600 y copia cifrada separada fuera del host. Para un espacio completo basta UUID, referencia de solicitud, alcance, fechas de verificación/bloqueo/eliminación, estado y fecha límite de retirada de copias. No incluir nombre, email, archivos ni conversación en este registro mínimo. Para eliminación selectiva, guardar sólo los identificadores afectados y sus revisiones. Registrar primero la marca de exclusión o *tombstone*; actualizar el resultado al terminar. El registro no forma parte del respaldo operativo restaurable ni se reemplaza por una versión antigua incluida en él.
3. **Bloquear y coordinar el espacio correcto.** Usar el UUID canónico y el bloqueo `lifecycle.lock`, coordinando el timer de copias para impedir que capture un estado parcial. Cerrar detiene acceso y sesiones web mientras se prepara la purga; comprobar backend, worker y base detenidos. Inhabilitar invitaciones y credenciales reutilizables de ese espacio, si existen, y cualquier trabajo pendiente que pudiera regenerar datos. Estos pasos son parte de una solicitud verificada, no una tarea rutinaria sobre clientes activos.
4. **Eliminar el ámbito activo.** Para un espacio completo, retirar únicamente sus contenedores, base PostgreSQL, bóveda con originales/revisiones/temporales, runtime y asignación de puerto, y eliminar de SQLite sus sesiones, invitaciones, operaciones, recibos de revisión y registro de espacio en el orden que respeten las claves foráneas. Al modificar `ports.json`, adquirir también `ports.lock` y reemplazar el archivo atómicamente para no perder asignaciones concurrentes de otros clientes. Revisar logs privados de sus operaciones y exportaciones temporales. Validar rutas reales bajo los directorios esperados antes de cualquier retirada; el volumen LUKS es compartido y no se elimina para purgar un solo cliente. Para datos selectivos, borrar físicamente originales/revisiones y referencias, recuerdos derivados, índices y reportes afectados; marcar `is_deleted` o revocar un permiso sólo bloquea usos, no retira las copias físicas.
5. **Inventariar todas las copias.** Revisar respaldos regulares, dumps/ensayos de restauración en `recovery`, archivos previos a la migración, copias extraordinarias, exportaciones manuales, snapshots y copias fuera del host. Los archivos fuera de `backups/agentagenda-*.tar.age` no expiran con el timer de treinta días. Registrar destino, responsable y fecha de retiro o excepción justificada; las claves de descifrado disponibles hacen que una copia cifrada siga siendo una copia de datos.
6. **Retirar datos también de las copias.** Si un archivo contiene otros espacios, reconstruirlo en almacenamiento cifrado excluyendo los datos del titular y limpiando también sus filas del SQLite respaldado, verificar a los otros espacios y sustituir el archivo cifrado. Si se conserva una copia antigua sólo para recuperación durante la ventana publicada, fijar una fecha límite explícita y mantenerla inaccesible al servicio y excluida de restauración hasta su retiro. No conservar indefinidamente un respaldo manual porque el timer no lo alcance. Cualquier excepción adicional por seguridad o obligación legal necesita motivo, alcance, plazo y comunicación al titular.
7. **Comprobar y confirmar.** Verificar sin abrir contenidos de otros clientes que la entrada ya rechaza ese espacio, sus recursos/datos activos no existen, los siguientes respaldos lo excluyen y las copias inventariadas se retiraron o tienen una fecha comunicada. Registrar la comprobación en el ledger y enviar al titular el resultado, la fecha de retirada de las copias pendientes y cualquier retención excepcional. No afirmar eliminación completa mientras sigan existiendo copias recuperables pendientes.

**Barrera manual obligatoria antes de restaurar:** consultar la copia más reciente del ledger independiente antes de arrancar Docker, backend, worker o plataforma con un respaldo anterior. Restaurar en un destino aislado con las entradas públicas y trabajos deshabilitados; excluir espacios eliminados y aplicar las marcas de eliminación selectiva tanto a los dumps/bóvedas como al registro, invitaciones, sesiones, runtime y asignaciones. Comprobar que sus antiguos tokens, códigos y tareas no vuelven a funcionar y que no se generan nuevos respaldos de esos datos. Sólo entonces adoptar la recuperación y habilitar los espacios restantes.

Esta barrera y la purga son manuales: `restart_spaces.py` y el aprovisionador todavía no aplican el ledger automáticamente. Un `state=closed` conservado en una copia histórica puede reabrirse; no sustituye la marca de eliminación independiente. Mantener el ledger mientras existan archivos o snapshots que puedan contener datos anteriores, y aplicar a ese metadato mínimo su propia política de retención. No guardar una copia de contenido borrado como evidencia de haberlo eliminado.

## Comprobaciones y diagnóstico

En `cite-server`, usar `sudo` para las unidades y archivos privados:

```sh
sudo systemctl status agentagenda-storage.service agentagenda-platform.service
sudo systemctl cat agentagenda-platform.service
sudo journalctl -u agentagenda-platform.service --since '30 minutes ago' --no-pager
sudo findmnt /srv/agentagenda
df -h /srv/agentagenda
df -h /home/cite/AgentAgenda-platform
curl --fail http://127.0.0.1:8001/health
sudo systemctl list-timers agentagenda-backup.timer
```

El servicio utiliza `app.server:app`, una sola instancia y cabeceras de proxy aceptadas únicamente desde `127.0.0.1`. `ExecStartPre` ejecuta `restart_spaces.py` para respetar el estado registrado al arrancar. El log de acceso HTTP de plataforma está desactivado, evitando registrar enlaces de activación. El Dockerfile actualizado también desactiva access logs de los backends y SQLAlchemy oculta sus parámetros; los errores de drivers y workers pueden conservar otros detalles técnicos. Los diagnósticos del helper se guardan en `/srv/agentagenda/control/operations/<operation_id>.log`, con modo 0600 dentro de un directorio 0700, y no se sirven por HTTP.

El aprovisionador configura logs Docker `json-file` de base/backend/worker con `max-size=10m` y `max-file=3`. La comprobación del despliegue `r2`, el 8 de octubre a las 22:02 de Ciudad de México, confirmó esa configuración en los nueve contenedores de los tres espacios activos, access logs desactivados en sus backends y `hide_parameters=True` en sus motores SQLAlchemy. El ajuste se aplicó también a sus composiciones existentes: futuros cambios no se heredan automáticamente. La rotación limita tamaño por contenedor, no días, y no aplica por sí sola al journal de systemd, archivos del helper, exportaciones o logs de Cloudflare. La revisión previa detectó access logs habilitados y sin rotación; no ejecutó una purga manual de esos registros ni de contenidos de clientes. Consultar [Data Safety](../distribution/google-play/DATA_SAFETY_DRAFT.md) para la evidencia y los límites.

Una respuesta correcta de `/health` sólo confirma la entrada. Verificar además la operación del espacio, su salud y su sesión autorizada; no declarar que una agenda vacía confirma autenticación. El detalle administrativo expone consumo documental y cuota efectiva mediante métricas internas protegidas, sin documentos ni conversaciones.

Las cuotas iniciales limitan documentos almacenados y reservas de subidas. Las cargas incompletas expiran después de 24 horas; los temporales huérfanos consumen capacidad hasta que se depuran. La cuota por cliente no reserva físicamente ese tamaño: vigilar espacio libre tanto en el filesystem LUKS como en el filesystem que contiene su archivo disperso. La capacidad de 64 GiB no se amplía automáticamente.

El detalle de cada espacio muestra bytes almacenados, límite efectivo y porcentaje consumido. Esta medición corresponde a los originales finalizados; el control de subidas también cuenta reservas y temporales. La lista general muestra el límite asignado. La cuota todavía no se edita desde el panel: una ampliación requiere actualizar la configuración persistida y aplicada del backend, coordinada con el ciclo de vida del espacio. Cambiar sólo el registro administrativo no modifica el límite efectivo.

Si una operación de reactivación falla, revisar su log y la salud de los servicios definidos en su `resources.json`. No cambiar el puerto a mano ni ejecutar otro stack con la misma base. El asignador registra el puerto una sola vez y mantiene la asignación durante suspensiones y reinicios.

## Respaldos

`agentagenda-backup.timer` ejecuta `agentagenda-backup.service` diariamente a las **04:00 de America/Mexico_City**. Para lanzar una copia manual y consultar el resultado:

```sh
sudo systemctl start agentagenda-backup.service
sudo journalctl -u agentagenda-backup.service --since '30 minutes ago' --no-pager
sudo systemctl status agentagenda-backup.timer
```

`services/platform/backup.py` realiza estas operaciones dentro del montaje cifrado:

1. Adquiere el bloqueo del espacio y registra qué contenedores estaban activos.
2. Detiene brevemente backend y worker, manteniendo una base disponible para generar `pg_dump -Fc`.
3. Copia la bóveda y el runtime del espacio junto al dump; restaura el estado de ejecución anterior al terminar.
4. Obtiene una copia consistente del registro SQLite mediante su API de respaldo y conserva la asignación global `ports.json`.
5. Empaqueta las copias y cifra el archivo con `age` antes de escribirlo fuera del montaje.
6. Descifra en memoria para comprobar la integridad del archivo y retira archivos de respaldo con más de treinta días.

Los archivos terminados se guardan en `/home/cite/AgentAgenda-platform/backups/agentagenda-<fecha UTC>.tar.age`, con permisos 0600. Puede existir una interrupción breve de acceso durante la copia de cada espacio. Una copia cifrada verificada sigue necesitando transferencia manual fuera de `cite-server`: las copias locales no protegen frente a la pérdida completa del host.

El respaldo conserva consistencia entre base y archivos de cada espacio. La restauración debe comprobar que cada espacio registrado dispone de su dump, bóveda y recursos; no habilitar un registro cuyo respaldo no contenga todos esos componentes. Conservar los archivos de la ventana de recuperación necesaria antes de cambiar retención o retirar recursos.

## Restauración y vuelta atrás

La recuperación es una operación de mantenimiento realizada por el operador. No sobrescribir la instalación activa ni mezclar su base con una copia anterior mientras acepta escrituras.

1. Confirmar que se dispone de la copia `.tar.age`, la identidad `age`, la clave LUKS y `platform.key` correspondientes, y de la versión vigente del ledger independiente de eliminación. Consultar sus exclusiones antes de restaurar; una copia histórica no puede revivir datos cuyo borrado se verificó después.
2. Descifrar y extraer la copia en un directorio privado bajo `/srv/agentagenda/recovery`; no escribir dumps ni bóvedas descifradas en `/tmp` o fuera del almacenamiento cifrado.
3. Restaurar los dumps permitidos en PostgreSQL temporal, con recursos y destinos separados de producción, sin acceso público ni workers. Aplicar las exclusiones del ledger a datos y registro. Comparar conteos, referencias y hashes documentales con su manifiesto privado; comprobar consultas autorizadas y descargas sintéticas.
4. Coordinar un corte de escrituras para adoptar la copia seleccionada. Restaurar base, bóveda, runtime y registro compatibles, con puertos disponibles y claves correspondientes.
5. Comprobar estados de suspensión/cierre antes de iniciar backends y workers. Habilitar la entrada sólo después de verificar identidad, contenido esperado, documentos y chat.
6. Registrar qué copia quedó como fuente de datos y conservar la anterior hasta terminar las pruebas. No mantener dos copias del mismo espacio recibiendo escrituras.

Antes de incorporar otros clientes, la ruta personal puede volver a su backend verificado. Con varios clientes activos, la recuperación debe conservar la entrada común y todas sus asignaciones. No apuntar Cloudflare directamente a un backend si eso evita los bloqueos de suspensión o deja inaccesibles los demás espacios.

## Evidencia del corte y límites actuales

En el corte inicial de la versión `2.0.0+5` se verificaron respaldos previos y restauraciones de prueba de ambas bases. Este inventario es evidencia histórica de la transición, no un contador actual del servicio; incluye registros históricos y borrados lógicos donde corresponde:

| Datos preservados | Pedro | Walter |
| --- | ---: | ---: |
| Eventos | 715 | 7 |
| Documentos | 97 | 0 |
| Revisiones | 127 | 0 |
| Mensajes | 50 | 0 |
| Permisos documentales | 34 | — |

La copia simultánea con suspensión y reactivación se verificó contra el servicio público; el mismo dispositivo volvió a autenticarse después del respaldo. Se retiraron los tres espacios sintéticos usados en aquella validación inicial. El túnel propio de Walter está detenido y su reinicio automático deshabilitado; eliminar su registro DNS requiere la confirmación final en el navegador. Posteriormente se creó el espacio de revisión de Google Play descrito abajo, separado de esos ensayos y de los clientes reales.

La validación histórica del corte completó 204 pruebas del backend, 11 de plataforma, 36 de Flutter y 5 de utilidades web. La preparación actual `2.0.1+6` completó 238 pruebas backend, con dos pruebas PostgreSQL opcionales omitidas en esa suite, 31 de plataforma, 51 de Flutter y 5 web. Por separado, una integración contra PostgreSQL real aprobó 16 pruebas. La API real comprobó reportes de IA (201 inicial, 200 al reintentar), aislamiento y operaciones de chat, documentos y tareas. La prueba inicial de servicio con espacios sintéticos comprobó activación, identidad, aislamiento, descargas, chat SSE, creación, suspensión, reactivación y reapertura, incluyendo asignación de puertos nuevos. El estado definitivo del retiro del hostname anterior de Walter se registra en el resultado del corte; su base y bóveda no se eliminan por retirar DNS.

La aplicación Android común usa `com.agentagenda.agent_agenda`. El emulador con páginas de 16 KB ya arrancó la app, activó el espacio de revisión y completó una conversación contra el servicio real. Un Pixel recibió una compilación anterior de `2.0.1+6`, pero se desconectó antes de completar la activación; la prueba física de la compilación final y sus capturas siguen pendientes. Las comprobaciones del emulador y HTTP no sustituyen ese paso.

El almacenamiento y los respaldos están cifrados, y las sesiones web contienen credenciales cifradas en servidor. La IA y el OCR procesan texto descifrado en la infraestructura del operador. **Este servicio no ofrece cifrado de extremo a extremo frente al administrador del servidor.** El panel evita mostrar contenido ajeno, pero los privilegios técnicos del dueño de la infraestructura siguen existiendo, conforme al modelo acordado.

## Estado de publicación Android

La preparación actual es `2.0.1+6` del paquete general `com.agentagenda.agent_agenda`, con firma de producción. El APK y el [AAB para Google Play](https://support.google.com/googleplay/android-developer/answer/9844679?hl=en) finales están compilados y verificados tras los ajustes de fechas; sus hashes y manifiestos se registran en `distribution/google-play/verification/release-validation.json`. El APK está disponible en `/download/agentagenda.apk`. La ficha de Google Play aún no se ha creado ni se ha presentado una versión: falta completar las declaraciones legales y la configuración de Console. Este estado no equivale a una publicación aprobada.

Se retiraron los permisos amplios de lectura de galería, vídeo, audio y almacenamiento heredados de `open_filex`; la app utiliza selección puntual del usuario y apertura de archivos. La app y la web comparten la paleta SARA, con modos claro y oscuro. La política está publicada en `https://privacy.ici-labs.com/agentagenda/`, el soporte y la solicitud de eliminación en `https://agenda-api.pedroibarra.dev/soporte`, y el contacto es `pibarrafacio@gmail.com`. El público previsto es de 13 años o más; no hay anuncios, pagos ni un SDK móvil de analítica. Consultar el [borrador Data Safety](../distribution/google-play/DATA_SAFETY_DRAFT.md) antes de presentar las respuestas.

El [reporte de respuestas de IA](https://support.google.com/googleplay/android-developer/answer/13985936?hl=en) ya está implementado dentro del chat. Envía el identificador del mensaje, motivo y comentario opcional al backend del propietario; guarda un recibo durable sin copiar automáticamente el chat completo, reenviarlo por correo ni mostrarlo en el panel administrativo. El detalle del espacio expone sólo el contador de reportes pendientes. Las instrucciones del asistente incluyen contenido apropiado para adolescentes, sin prometer un filtro infalible.

Existe un espacio sintético exclusivo para [revisión de Google Play](https://support.google.com/googleplay/android-developer/answer/15748846?hl=en): `efc01f41-1384-4a76-ac1c-19de65ce6209`, con cuota de 1 GiB. Sus ejemplos de agenda, documentos y conversación son simulados y no proceden de clientes reales. El operador fija ese UUID en `PLATFORM_REVIEW_SPACE_ID` y emite una credencial reutilizable mediante `create-review-code`; los códigos ordinarios de clientes siguen siendo de un uso y 24 horas. Mantener el código y su exportación privada fuera de Git y de esta documentación. La creación, rotación y revocación se describen en [services/platform/README.md](../services/platform/README.md).

Se comprobaron alineación ZIP y segmentos LOAD de 64 bits, y la app ejecutó activación y chat real en un emulador con páginas de 16 KB. Quedan la instalación/activación de la compilación final en el teléfono físico y las capturas definitivas de ficha. Cerrar conserva datos: el flujo público de soporte y el procedimiento manual de eliminación y restauración de este documento describen cómo se tramita su borrado.
