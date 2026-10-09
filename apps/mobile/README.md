# AgentAgenda para Android

Actualizado: 8 de octubre de 2026. App única para todos los espacios: paquete `com.agentagenda.agent_agenda`, versión 2.0.1+6. Conserva seguimientos locales voluntarios y acceso al despertador de Android.

## Compilar y verificar

Desde `apps/mobile`, con Flutter y el SDK de Android configurados:

```sh
flutter pub get
flutter analyze
flutter test
flutter build apk --debug
flutter build apk --release
flutter build appbundle --release
```

Los APK quedan en `build/app/outputs/flutter-apk/`. Una compilación release requiere `android/key.properties` con `storeFile`, `storePassword`, `keyAlias` y `keyPassword` del keystore de producción. El archivo y el keystore están excluidos de Git; no se permite firmar release con la clave debug. El mismo APK sirve para todos: no contiene tokens, invitaciones ni nombres de clientes. Compilar no instala el APK ni activa avisos o alarmas.

## Activación y reconexión

En una instalación limpia se muestra **Conecta tu espacio**, con un código/enlace temporal y nombre del teléfono. La dirección común es `https://agenda-api.pedroibarra.dev`; puede configurarse otro origen HTTPS explícitamente antes de activar. Los enlaces de activación deben pertenecer al origen seleccionado. Las credenciales se guardan usando `flutter_secure_storage` 10.3.4 (Android Keystore + AES-GCM), con copias automáticas de Android deshabilitadas.

`POST /platform/v1/activate` registra el dispositivo y devuelve la sesión de `/s/<space_id>`. El ID del intento de activación se conserva cifrado para reintentar una respuesta perdida con el mismo código. Una vez recibida la sesión se guarda antes de verificar `/v1/auth/me`, de modo que una pérdida de red posterior conserve la posibilidad de reconectar. Cada arranque verifica identidad; falta de red muestra reintentar conexión, y credenciales revocadas/vencidas o un espacio suspendido muestran reconexión. Las llamadas API y descargas mantienen el prefijo del espacio, rechazan otros orígenes/espacios y no siguen redirecciones con credenciales. La renovación de sesión es compartida entre solicitudes y cada petición rechazada con 401 se reintenta una vez cuando es reproducible.

En **Ajustes → Tu espacio** se muestra el nombre del espacio y la conexión real, y se puede desconectar/cambiar de espacio. Desconectar intenta revocar el teléfono en el servidor y siempre elimina su sesión local, cierra solicitudes y rutas privadas, cancela avisos y borra archivos temporales descargados por AgentAgenda. Los ajustes de avisos quedan separados por servidor/espacio; caché y horarios previos se descartan al cambiar. Las alarmas ya guardadas en Reloj siguen siendo administradas por Android.

Reinstalar elimina el acceso local. Un nuevo código para **el mismo espacio existente** recupera agenda, chat y documentos del servidor; nunca se crea otra agenda automáticamente. Los antiguos tokens en preferencias se eliminan al actualizar. Las instalaciones anteriores firmadas con una clave debug o con el paquete de Walter deben desinstalarse antes de instalar el APK general; el contenido del servidor permanece.

Las pruebas `space_session_test.dart`, `widget_test.dart` y `notifications/follow_up_service_test.dart` cubren activación, pérdida de respuesta, persistencia, identidad, códigos vencidos, límites de URL, renovación, cierre de pantallas privadas, cambio de espacio y sincronizaciones antiguas en vuelo. La activación y entrega de avisos en un teléfono real siguen requiriendo verificación física.

## Privacidad, soporte y reportes de IA

Activación y **Ajustes** ofrecen enlaces a [privacidad](https://privacy.ici-labs.com/agentagenda/), [soporte](https://agenda-api.pedroibarra.dev/soporte) y [solicitud de eliminación de datos](https://agenda-api.pedroibarra.dev/soporte#eliminacion), que se abren en el navegador del teléfono. Se informa que la IA procesa los mensajes y los documentos autorizados en el servidor; las respuestas y propuestas requieren revisión del usuario.

Cada respuesta de asistente guardada ofrece **Reportar respuesta**. Un diálogo muestra la respuesta exacta, permite elegir motivo y comentario opcional de hasta 2000 caracteres, y explica qué se comparte con soporte. Únicamente al pulsar **Enviar reporte** se llama a `POST /s/<space_id>/v1/chat/reports` con `message_id`, `reason` y `details` opcional. La app no envía el historial completo. El servidor verifica propiedad y utiliza la respuesta guardada; al terminar el stream devuelve `assistant_message_id` para permitir el reporte inmediatamente. Los fallos conservan el comentario para reintentar. `ai_report_test.dart` verifica el destino aislado, credenciales, campos, límites y errores.

Fotos y documentos se eligen mediante el selector de Android. Las descargas se abren desde almacenamiento privado con FileProvider. El manifiesto elimina los permisos amplios de almacenamiento y `READ_MEDIA_*` que agregan algunas dependencias; no se requiere acceso completo a la galería.

Inter y Manrope se incluyen en `assets/fonts/`, con variantes verificadas contra los hashes SHA-256 del paquete `google_fonts` 8.2.1 y sus licencias SIL Open Font License. Se desactiva la descarga de fuentes en ejecución para evitar depender de conexión o contactar a Google para obtenerlas. **Ajustes → Licencias de código abierto** incluye estas licencias.

## Seguimientos locales

En **Tu agenda → campana (Avisos y despertador)**:

- **Activar seguimientos** solicita el permiso de notificaciones y permite programar avisos. El interruptor está apagado inicialmente. El permiso de Android se muestra por separado.
- **Enviar prueba ahora** muestra una notificación solo al pulsarlo; no activa el interruptor ni programa un despertador.
- **Sincronizar avisos ahora** reconcilia los próximos siete días con el servidor. La pantalla muestra la fecha de la última sincronización y los avisos planificados.

Los avisos se calculan a partir de actividades aceptadas: al final de bloques de 20–89 minutos, o 15 minutos antes del final de bloques de al menos 90 minutos. Se separan al menos 75 minutos y se limita el número planificado por día (cuatro inicialmente). Se excluyen actividades completadas, sueño, propuestas pendientes y marcadores `[PROVISIONAL]` o `[CONDICIONAL]`. No se planifican dentro del descanso ni antes de la hora configurada para despertar; además se deja un margen antes del descanso. El cálculo usa `America/Mexico_City` y la configuración inicial de descanso es 22:30–06:45, todos los días.

Al abrir o reanudar la agenda, crear o cambiar actividades, aceptar propuestas, completar o borrar eventos, se reconcilian los avisos. Completar y borrar también cancela los avisos locales correspondientes. Tocar un seguimiento abre el registro de cómo vas; el contenido visible de la notificación es genérico y no expone títulos de actividades.

El teléfono conserva ajustes separados por espacio, identificadores, títulos, horas, categoría y estado necesarios para reconciliar, la fecha de sincronización y los identificadores de notificaciones. No guarda descripciones completas en esta caché. Al desconectar o cambiar de espacio elimina la caché y todos sus avisos. Los avisos ya programados pueden funcionar con la app cerrada y sin red; el receptor de arranque del plugin vuelve a programarlos después de un reinicio. No se consultan cambios externos mientras la app está cerrada: deben sincronizarse al volver a abrirla o con el botón. No hay FCM ni push del servidor. Una caché de más de siete días deja de utilizarse al reconciliar.

La entrega es **aproximada** (`inexactAllowWhileIdle`): Android, el ahorro de batería y los ajustes del fabricante pueden retrasarla o impedirla; forzar la detención puede impedir avisos hasta volver a abrir la app. El filtro de descanso se aplica a la hora planificada y no garantiza la hora real si Android la retrasa. Estos seguimientos no sustituyen un despertador.

## Despertador del sistema

En la misma pantalla, la sección **Despertador del teléfono** ofrece **06:45**, **Cambiar hora**, días editables (lunes a viernes inicialmente) y **Configurar 06:45 en Reloj**. Ninguna alarma se abre o activa al iniciar la app ni al cambiar estos ajustes.

El botón envía `ACTION_SET_ALARM` al Reloj de Android con la hora y los días seleccionados, y con `EXTRA_SKIP_UI=false`. Hay que revisar en Reloj que la alarma quede activa, su sonido y su volumen. La app confirma únicamente que pudo abrir Reloj; no puede verificar que se haya guardado la alarma. Las alarmas guardadas las administra Reloj, incluso sin red. Cambiar ajustes en AgentAgenda no modifica ni elimina alarmas que ya se hayan guardado en Reloj. El despertador usa la zona horaria del teléfono; los seguimientos usan Ciudad de México.

## Implementación y pruebas

`lib/core/notifications/` contiene el planificador puro, la reconciliación persistida, el adaptador del plugin y el canal hacia Reloj. `test/notifications/` verifica horarios, sueño, provisionales, recurrencias, cancelación, persistencia, falta de red, permisos y despacho explícito de alarmas con datos sintéticos. Las pruebas locales no sustituyen la comprobación de permisos, entrega y Reloj en un teléfono.

Fuentes oficiales de implementación:

- [flutter_local_notifications 22.3.1](https://pub.dev/packages/flutter_local_notifications/versions/22.3.1): configuración Android, permisos y receptores persistidos.
- [Android AlarmClock](https://developer.android.com/reference/android/provider/AlarmClock): `ACTION_SET_ALARM` y sus parámetros.
- [Alarmas de Android](https://developer.android.com/develop/background-work/services/alarms): comportamiento de alarmas aproximadas y restricciones del sistema.

- [flutter_secure_storage 10.3.4](https://pub.dev/packages/flutter_secure_storage/versions/10.3.4): almacenamiento cifrado y configuración Android.
