# Data Safety — respuestas guardadas para AgentAgenda

Revisado el 8 de octubre de 2026 para Android `com.agentagenda.agent_agenda`, versión `2.0.1+8`. Las respuestas de Seguridad de los datos ya se guardaron en Play Console, con confirmación «Cambio guardado», y se auditaron contra su exportación real. Están pendientes de envío y revisión; no se afirma aprobación ni publicación. Se conserva el nombre de este archivo para mantener sus referencias. Las respuestas deben revisarse cuando cambien versiones distribuidas bajo el mismo paquete.

Se declararon **17 tipos de datos recogidos, todos no efímeros: 5 obligatorios y 12 opcionales**. **Cuatro tipos se declararon también compartidos:** Device or other IDs (incluye IP), Approximate location, Diagnostics y App interactions. Las finalidades de compartición de los cuatro son Analytics y Fraud prevention, security, and compliance, sin publicidad.

## Respuestas generales guardadas

| Pregunta | Respuesta guardada | Evidencia y límite |
|---|---|---|
| ¿La app recoge datos? | Sí | La activación, agenda, chat, archivos y reportes usan la API remota. No declarar «no recoge datos». |
| ¿Todos los datos recogidos por la app viajan cifrados? | Sí, para el servicio configurado | Sesiones sólo HTTPS; el manifiesto bloquea tráfico sin cifrar. Correo y apertura de archivos se realizan mediante apps externas elegidas por el usuario. |
| ¿Existe un mecanismo para solicitar eliminación? | Sí | Enlaces visibles en activación/ajustes y https://privacy.ici-labs.com/agentagenda/eliminacion/. Solicitud manual con verificación del titular; desinstalar, desconectar o cerrar el espacio no lo purga. |
| URL de eliminación | https://privacy.ici-labs.com/agentagenda/eliminacion/ | Funciona sin iniciar sesión. |
| ¿Verificación independiente de seguridad? | No | Las pruebas internas no equivalen a validación independiente MASVS. |
| ¿Se comparte con terceros? | Sí: IDs/IP, ubicación aproximada, diagnóstico e interacciones | Cloudflare actúa como processor para contenido en tránsito y Customer Logs, y como controller para cierto Network Data operacional propio. Sin prueba de anonimización irreversible de esos metadatos, se guardaron esas cuatro categorías recogidas y compartidas para seguridad/análisis con criterio conservador. El contenido, archivos y consultas de búsqueda quedan recogidos bajo la excepción de proveedor, sin evidencia de uso controller de su texto. |
| ¿Tiene anuncios? | No | No hay SDK ni interfaz publicitaria en el paquete. |
| ¿Creación de cuenta en la app? | La app no permite crear una cuenta; admite cuentas creadas fuera de ella, método «Otro» | El administrador crea el espacio personal y entrega un código de activación; la app conecta ese espacio existente y registra el dispositivo. No admite registro público. Esta descripción quedó guardada en el formulario. |

## Tipos y usos observados en el código

Los nombres ingleses ayudan a ubicar categorías de Play Console. «Opcional» significa que el usuario decide introducir o subir ese contenido y puede usar otras funciones sin hacerlo. Ningún tipo se guardó como procesamiento efímero.

| Tipo de Play | Respuesta guardada | Obligatorio / opcional | Finalidad de recogida guardada | Evidencia |
|---|---|---|---|---|
| Personal info → User IDs | Recogido | Obligatorio para conectar | App functionality; Account management; Fraud prevention, security, and compliance | Identificador del espacio/propietario, código, credenciales y sesiones en `space_session.dart`, `/platform/v1/activate` y autenticación del backend. |
| Device or other IDs | Recogido y compartido (incluye IP) | Obligatorio para conectar | App functionality; Account management; Fraud prevention, security, and compliance; Analytics | ID de registro del dispositivo, ID del intento de activación, tokens, fechas de uso y metadatos de red. No es un identificador publicitario ni se lee IMEI. |
| Calendar → Calendar events | Recogido | Opcional | App functionality; Personalization | Actividades, horarios, notas, categorías, estados y contexto de agenda sincronizados en `api_client.dart` y `api/agenda.py`. No se solicita permiso para leer el calendario completo del sistema. |
| Messages → Other in-app messages | Recogido | Opcional | App functionality; Personalization | Chat durable: mensajes, respuestas, contexto y propuestas. Reportar guarda una referencia al mensaje seleccionado, el motivo y el comentario opcional; no copia la respuesta ni toda la conversación a una cola externa. |
| Files and docs → Files and docs | Recogido | Opcional | App functionality; Personalization | Originales elegidos, título, tipo, tamaño, revisiones, metadatos y texto extraído mediante `uploadDocument()` y `document_storage.py`. |
| Photos and videos → Photos | Recogido | Opcional | App functionality; Personalization | Selector de fotos y subida del original. No se accede automáticamente a toda la galería. |
| Photos and videos → Videos | Recogido si se sube un vídeo | Opcional | App functionality | El selector genérico `FileType.any` y la bóveda aceptan originales sin restringirlos a formatos con extractor. No hay función de grabación de vídeo. |
| Audio files → Voice or sound recordings / Music files / Other audio files | Recogido si se sube ese tipo de archivo | Opcional | App functionality | Son tres tipos seleccionados por separado en Console. El mismo selector genérico permite guardar originales de audio aunque no haya transcripción ni reproductor; el servicio no almacena sólo PDF/fotos. |
| App activity → Other user-generated content | Recogido | Opcional | App functionality; Personalization | Tareas, registros voluntarios de actividad, anotaciones y comentarios de reportes que no queden cubiertos por agenda/chat/archivos. |
| Personal info → Name | Recogido cuando se proporciona, con criterio conservador | Opcional | Account management; App functionality | El nombre editable del dispositivo y las solicitudes de soporte pueden contener el nombre o apodo de la persona; se puede usar una etiqueta genérica. La app no exige un nombre legal. El nombre del cliente usado al crear el espacio procede del alta administrativa. |
| Personal info → Email address | Recogido en soporte, con criterio conservador | Opcional | App functionality; Account management | Al solicitar soporte o eliminación por correo, el operador recibe dirección de remitente y lo que el usuario envía. La app abre una aplicación externa: no lee las cuentas de correo del teléfono ni transmite mensajes de agenda silenciosamente. |

## Datos de infraestructura y respuestas guardadas

| Dato / categoría | Respuesta y finalidad de recogida guardadas | Evidencia y límite |
|---|---|---|
| IP → Device or other IDs | Recogido y compartido; obligatorio para conexión; App functionality; Account management; Fraud prevention, security, and compliance; Analytics | La IP se incluye en la categoría consolidada Device or other IDs, con las cuatro finalidades guardadas. Cloudflare procesa la IP del visitante. El rate limiter de plataforma usa `request.client.host` y marcas de intento en RAM. La ventana es de 300 segundos, pero las claves IP pueden permanecer hasta limpieza por volumen o reinicio del proceso: no prometer procesamiento estrictamente efímero. Los access logs internos observados mostraron IP privadas de Docker, no IP públicas del visitante. |
| Location → Approximate location | Recogido y compartido conservador; obligatorio; Analytics; Fraud prevention, security, and compliance | El panel de Cloudflare, filtrado por `agenda-api.pedroibarra.dev`, conserva recuentos por país junto con IP y rutas de solicitudes. No se usa GPS ni se personaliza la agenda con ubicación. La retención efectiva de cada producto sigue sin confirmarse; no marcar ausencia de ubicación únicamente por no pedir permiso Android. |
| App info and performance → Diagnostics | Recogido y compartido conservador; obligatorio para la operación; App functionality; Analytics | Estados y errores del backend, worker, operaciones, gateway IA y borde Cloudflare. Pueden relacionarse con IDs de operación o espacio. No hay Crashlytics/Sentry/Firebase Analytics ni envío de trazas de crashes Android; no seleccionar Crash logs sólo por existir excepciones del servidor. |
| App activity → App interactions | Recogido y compartido conservador; obligatorio para la operación; App functionality; Analytics; Fraud prevention, security, and compliance | Rutas, métodos, estados y recuentos de peticiones permiten observar acciones de servicio. No hay SDK de seguimiento de pulsaciones. El panel administrativo conserva operaciones de creación/suspensión/cierre y no muestra contenido del cliente. |
| App activity → In-app search history | Recogido al buscar; opcional; App functionality | Las consultas `q` salen del teléfono al buscar documentos. No existe tabla propia de historial de búsquedas; los access logs anteriores podían conservar el query string y la infraestructura ve la URL. No marcar efímero sin comprobar también el borde y los logs históricos. |

La recogida de país, IP y metadatos se comprobó también en la cuenta Cloudflare. El DPA y los términos self-serve respaldan la excepción de proveedor para contenido y Customer Logs; la política y FAQ oficiales distinguen Network Data propio. La compartición de ubicación, diagnóstico e interacciones es una inferencia conservadora: no se demostró anonimización irreversible de esos metadatos. Los plazos efectivos siguen sin confirmarse; la observación de métricas no prueba retención limitada. Google exige declarar ubicación derivada de IP y diferencia los datos realmente efímeros de los registrados. [Guía oficial de Data Safety](https://support.google.com/googleplay/android-developer/answer/10787469?hl=en).

## Evidencia operativa del 8 de octubre de 2026

Revisión de lectura entre las 21:52 y las 22:02, hora de Ciudad de México, incluyendo la comprobación posterior al despliegue `r2`. Se analizaron configuración y contadores de logs dentro del servidor; no se exportaron líneas, IP, búsquedas, credenciales ni contenido de clientes.

- **Entrada de plataforma:** `agentagenda-platform.service` usa `--no-access-log` y sólo confía en proxy de loopback. La muestra de su journal tenía cero líneas de acceso HTTP y cero excepciones.
- **Backends de espacios, estado observado antes del ajuste final:** Uvicorn conservaba access logs en Docker `json-file`; no había `max-size`/`max-file` por contenedor ni una política global en `daemon.json`. Esto admite rutas, parámetros de URL, código HTTP, IP del origen interno y marcas de tiempo. La muestra de contenedores recién recreados no contenía query strings; no demuestra que la configuración previa nunca los haya registrado.
- **Minimización aplicada y comprobada en `r2`:** los backends de los tres espacios activos ejecutan `--no-access-log` y sus motores SQLAlchemy informan `hide_parameters=True`. Los nueve contenedores —backend, worker y PostgreSQL de cada espacio— están activos con `json-file`, `max-size=10m`, `max-file=3`; el aprovisionador aplica lo mismo a altas futuras. Los límites son por tamaño y no equivalen a treinta días. Los errores del driver pueden incorporar detalles propios incluso cuando SQLAlchemy oculta parámetros. No se ejecutó una purga manual de logs ni contenidos de clientes. [Rotación oficial de Docker](https://docs.docker.com/engine/logging/drivers/json-file/).
- **IA del servicio:** las tres configuraciones consultadas apuntaban a `llm-gateway`, alias Docker del gateway compartido; no a una API externa de modelos. Ese gateway ya tenía access logs desactivados y rotación 10m × 3. Una muestra agregada de 10 000 líneas no encontró marcadores de prompts/mensajes; esto es evidencia de esa muestra, no una garantía universal sobre todos los diagnósticos.
- **Web pública:** respuestas HTTP con cabeceras de navegador muestran el script de Web Analytics de Cloudflare inyectado en soporte y privacidad. El CSP del panel puede impedir ejecutar el beacon, mientras que el portal de privacidad no presentó CSP en la muestra. Esto corresponde a páginas web y no demuestra un SDK móvil en el APK. [Recogida del beacon](https://developers.cloudflare.com/web-analytics/data-metrics/data-origin-and-collection/) y [dimensiones disponibles](https://developers.cloudflare.com/web-analytics/data-metrics/dimensions/).
- **Borde Cloudflare:** a las 22:17, la vista Requests de la zona Free, filtrada por `Host equals agenda-api.pedroibarra.dev`, mostró rutas, país, IP de cliente, agente de usuario, estado HTTP y recuentos de solicitudes. Se confirmó el rango visible de las últimas 24 horas y opciones de consulta hasta 30 días; estas opciones no prueban eliminación al día 30. No se exportaron valores de IP ni contenidos a esta documentación. Los plazos efectivos y productos de seguridad todavía requieren comprobación. [Zone Analytics](https://developers.cloudflare.com/analytics/account-and-zone-analytics/zone-analytics/).
- **Exportación de borde:** la vista Logpush de la cuenta mostró `Subscribe to Logpush`, sin una lista de destinos o trabajos configurados. No se contrató ni activó ese producto. Esta observación no demuestra la ausencia de registros internos de Cloudflare ni sustituye revisar otros productos de seguridad.

No usar la ausencia de errores en una muestra ni el cierre de un espacio para afirmar que no se recogen diagnósticos o que ya se borraron sus datos. El procedimiento manual y la barrera de restauración se describen en [MULTITENANCY_OPERATIONS.md](../../docs/MULTITENANCY_OPERATIONS.md).

La app no solicita contactos, ubicación precisa, SMS, micrófono ni cámara y no lee identificadores de publicidad. No hay SDK de publicidad ni telemetría móvil. Inter/Manrope están incluidas y su descarga externa está desactivada. Esto no reemplaza la revisión de los logs y servicios del servidor.

## Proveedores y compartición

- **Cloudflare:** intermediación HTTPS, túnel, seguridad y métricas web/HTTP. Puede ver IP, metadatos y tráfico en el punto de terminación TLS. El almacenamiento cifrado y los espacios separados no impiden el acceso técnico del operador. Su DPA (§2.3/3.1), incorporado a los términos self-serve (§6.1), describe procesamiento por cuenta del cliente para contenido en tránsito y Customer Logs. La política (§2/6) y FAQ distinguen Network Data que trata por cuenta propia para seguridad y funcionamiento de su red. [DPA de Cloudflare](https://www.cloudflare.com/cloudflare-customer-dpa/), [términos](https://www.cloudflare.com/terms/), [privacidad](https://www.cloudflare.com/privacypolicy/) y [FAQ de límites de metadatos](https://developers.cloudflare.com/data-localization/metadata-boundary/faq/).
- **IA local del servicio:** procesamiento de mensajes, agenda y fragmentos autorizados dentro de la infraestructura operada; no se incorpora un proveedor externo de modelos en el cliente móvil.
- **Gmail para soporte:** el usuario inicia el correo y decide qué envía. La app no transmite silenciosamente conversaciones o documentos por email.
- **Android / apps externas:** selector de archivos, notificaciones locales, Reloj y apertura de un original por FileProvider, por acciones del usuario.

Google distingue recogida de datos, compartición y transferencias a proveedores que sólo actúan por cuenta del desarrollador. La excepción de proveedor depende de cómo se presta el servicio, no del nombre de la empresa. No hay venta ni publicidad según la política publicada. [Guía oficial de Data Safety](https://support.google.com/googleplay/android-developer/answer/10787469?hl=en).

## Referencias de implementación

- `apps/mobile/lib/core/network/space_session.dart`: alta del dispositivo, sesiones, URL HTTPS y renovación.
- `apps/mobile/lib/core/network/api_client.dart`: payloads reales de agenda, chat, archivos y reportes.
- `apps/mobile/lib/features/documents/document_library.dart`: selector de fotos y archivos genéricos.
- `apps/mobile/lib/core/notifications/`: seguimientos y caché local; no FCM.
- `apps/mobile/android/app/src/main/AndroidManifest.xml`: permisos fusionados que deben verificarse en el AAB final.
- `services/backend/app/api/chat.py`: recepción autorizada e idempotente de reportes.
- `services/backend/app/services/document_storage.py`: originales, cuotas y revisiones.
- `services/platform/app/registry.py`: datos administrativos y sesiones.
- [Política publicada](https://privacy.ici-labs.com/agentagenda/).

## Evidencia de las respuestas guardadas

La exportación real de Console se conserva sin modificaciones en [verification/data-safety-console-export.csv](verification/data-safety-console-export.csv): **211 752 bytes, 783 filas (cabecera y 782 registros)**, SHA-256 `727356bef12412cec98206b1c4ced498d8d5707063c43ba7c2c0e02aee5ec005`. La auditoría comprobó los 17 tipos, obligatoriedad, finalidades de recogida y compartición y ausencia de procesamiento efímero, sin discrepancias con las tablas de este documento. También comprobó cifrado en tránsito, mecanismo y URL de eliminación y el acceso mediante cuentas creadas fuera de la app. No se declaró verificación independiente de seguridad.

El CSV documenta las respuestas exportadas; la confirmación «Cambio guardado» en Console acredita que se guardaron. Ninguna de esas evidencias equivale al envío, aprobación o publicación. Antes de presentar la app, conservar esta exportación junto con el AAB final y comprobar que no hayan cambiado el servicio ni las respuestas. Para futuras actualizaciones, usar el esquema real de Console.

## Aplicación en Console

Las respuestas guardadas declaran los 17 tipos no efímeros. Los cinco obligatorios son User IDs, Device or other IDs, Approximate location, Diagnostics y App interactions. Los doce opcionales son Name, Email address, Calendar events, Other in-app messages, Files and docs, Photos, Videos, Voice or sound recordings, Music files, Other audio files, Other user-generated content e In-app search history. La recogida de Device or other IDs tiene las cuatro finalidades App functionality, Account management, Fraud prevention, security, and compliance y Analytics. Para las cuatro categorías compartidas se guardaron Analytics y Fraud prevention, security, and compliance, sin publicidad. No se atribuye compartición controller al contenido privado sin evidencia.

El validador de Console devolvió 403 para el enlace original de soporte pese a GET200 en navegador y curl. Se publicó un enlace estático dedicado de eliminación con barra final en el portal de privacidad y se añadió HEAD a las rutas públicas de soporte/privacidad; esto no desactiva protecciones de Cloudflare. El resultado de su validación efectiva se registra en `verification/console-progress.json`.
