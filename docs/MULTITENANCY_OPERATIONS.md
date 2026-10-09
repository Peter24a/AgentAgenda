# Operación de AgentAgenda por espacios

Despliegue del 8 de octubre de 2026, en `cite-server`. Este documento describe la plataforma implementada; el [plan de migración](MULTITENANCY_MIGRATION_PLAN.md) conserva las decisiones y el diseño previo. Las credenciales, códigos de activación, manifiestos privados y contenidos de clientes permanecen fuera de Git.

## Entrada y recursos desplegados

La dirección pública es `https://agenda-api.pedroibarra.dev`. El túnel existente de Cloudflare continúa llegando a `127.0.0.1:8001`, donde ahora escucha la plataforma. No se crea DNS ni otro túnel al dar de alta un cliente.

| Componente | Ubicación o función |
| --- | --- |
| Página pública | `/`, con descarga del APK general |
| Panel administrativo | `/admin`; cuenta administrativa independiente de la agenda de Pedro |
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

**No hay una operación pública de purga definitiva.** Los espacios cerrados permanecen conservados hasta una política posterior de eliminación. La retención de treinta días se aplica a archivos de respaldo y no borra automáticamente el espacio cerrado. Una operación fallida mantiene el acceso bloqueado cuando corresponde y permite revisar el diagnóstico privado antes de reintentar.

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

El servicio utiliza `app.server:app`, una sola instancia y cabeceras de proxy aceptadas únicamente desde `127.0.0.1`. `ExecStartPre` ejecuta `restart_spaces.py` para respetar el estado registrado al arrancar. El log de acceso HTTP está desactivado, evitando registrar enlaces de activación. Los diagnósticos del helper se guardan en `/srv/agentagenda/control/operations/<operation_id>.log`, con modo 0600 dentro de un directorio 0700, y no se sirven por HTTP.

Una respuesta correcta de `/health` sólo confirma la entrada. Verificar además la operación del espacio, su salud y su sesión autorizada; no declarar que una agenda vacía confirma autenticación. El detalle administrativo expone consumo documental y cuota efectiva mediante métricas internas protegidas, sin documentos ni conversaciones.

Las cuotas iniciales limitan documentos almacenados y reservas de subidas. Las cargas incompletas expiran después de 24 horas; los temporales huérfanos consumen capacidad hasta que se depuran. La cuota por cliente no reserva físicamente ese tamaño: vigilar espacio libre tanto en el filesystem LUKS como en el filesystem que contiene su archivo disperso. La capacidad de 64 GiB no se amplía automáticamente.

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
4. Obtiene una copia consistente del registro SQLite mediante su API de respaldo.
5. Empaqueta las copias y cifra el archivo con `age` antes de escribirlo fuera del montaje.
6. Descifra en memoria para comprobar la integridad del archivo y retira archivos de respaldo con más de treinta días.

Los archivos terminados se guardan en `/home/cite/AgentAgenda-platform/backups/agentagenda-<fecha UTC>.tar.age`, con permisos 0600. Puede existir una interrupción breve de acceso durante la copia de cada espacio. Una copia cifrada verificada sigue necesitando transferencia manual fuera de `cite-server`: las copias locales no protegen frente a la pérdida completa del host.

El respaldo conserva consistencia entre base y archivos de cada espacio. La restauración debe comprobar que cada espacio registrado dispone de su dump, bóveda y recursos; no habilitar un registro cuyo respaldo no contenga todos esos componentes. Conservar los archivos de la ventana de recuperación necesaria antes de cambiar retención o retirar recursos.

## Restauración y vuelta atrás

La recuperación es una operación de mantenimiento realizada por el operador. No sobrescribir la instalación activa ni mezclar su base con una copia anterior mientras acepta escrituras.

1. Confirmar que se dispone de la copia `.tar.age`, la identidad `age`, la clave LUKS y `platform.key` correspondientes.
2. Descifrar y extraer la copia en un directorio privado bajo `/srv/agentagenda/recovery`; no escribir dumps ni bóvedas descifradas en `/tmp` o fuera del almacenamiento cifrado.
3. Restaurar cada dump en PostgreSQL temporal, con recursos y destinos separados de producción. Comparar conteos, referencias y hashes documentales con su manifiesto privado; comprobar consultas autorizadas y descargas sintéticas.
4. Coordinar un corte de escrituras para adoptar la copia seleccionada. Restaurar base, bóveda, runtime y registro compatibles, con puertos disponibles y claves correspondientes.
5. Comprobar estados de suspensión/cierre antes de iniciar backends y workers. Habilitar la entrada sólo después de verificar identidad, contenido esperado, documentos y chat.
6. Registrar qué copia quedó como fuente de datos y conservar la anterior hasta terminar las pruebas. No mantener dos copias del mismo espacio recibiendo escrituras.

Antes de incorporar otros clientes, la ruta personal puede volver a su backend verificado. Con varios clientes activos, la recuperación debe conservar la entrada común y todas sus asignaciones. No apuntar Cloudflare directamente a un backend si eso evita los bloqueos de suspensión o deja inaccesibles los demás espacios.

## Evidencia del corte y límites actuales

Se verificaron respaldos previos y restauraciones de prueba de ambas bases. El inventario de la transición conservó estos conteos, incluyendo registros históricos y borrados lógicos donde corresponde:

| Datos preservados | Pedro | Walter |
| --- | ---: | ---: |
| Eventos | 715 | 7 |
| Documentos | 97 | 0 |
| Revisiones | 127 | 0 |
| Mensajes | 50 | 0 |
| Permisos documentales | 34 | — |

La validación de código completó 204 pruebas del backend, 11 de plataforma, 36 de Flutter y 5 de utilidades web. La prueba pública con espacios sintéticos comprobó activación, identidad, aislamiento, descargas, chat SSE, creación, suspensión, reactivación y reapertura, incluyendo asignación de puertos nuevos. El estado definitivo del retiro del hostname anterior de Walter se registra en el resultado del corte; su base y bóveda no se eliminan por retirar DNS.

La aplicación Android común está compilada y firmada para `com.agentagenda.agent_agenda`. La instalación y reconexión en un teléfono Android físico requieren la comprobación del propietario; las pruebas automatizadas y HTTP no sustituyen esa verificación.

El almacenamiento y los respaldos están cifrados, y las sesiones web contienen credenciales cifradas en servidor. La IA y el OCR procesan texto descifrado en la infraestructura del operador. **Este servicio no ofrece cifrado de extremo a extremo frente al administrador del servidor.** El panel evita mostrar contenido ajeno, pero los privilegios técnicos del dueño de la infraestructura siguen existiendo, conforme al modelo acordado.
