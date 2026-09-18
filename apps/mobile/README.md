# AgentAgenda para Android

Actualizado: 15 de septiembre de 2026. Cliente Flutter de la agenda, con seguimientos locales voluntarios y acceso al despertador de Android.

## Compilar y verificar

Desde `apps/mobile`, con Flutter y el SDK de Android configurados:

```sh
flutter pub get
flutter analyze
flutter test
flutter build apk --debug --dart-define=BACKEND_URL=https://agenda-api.pedroibarra.dev
```

El APK queda en `build/app/outputs/flutter-apk/app-debug.apk`. La URL no contiene credenciales; la sesión se configura en la aplicación. Compilar no instala el APK ni activa avisos o alarmas. El manifiesto principal incluye `INTERNET`, por lo que también se aplica a las compilaciones release.

## Seguimientos locales

En **Tu agenda → campana (Avisos y despertador)**:

- **Activar seguimientos** solicita el permiso de notificaciones y permite programar avisos. El interruptor está apagado inicialmente. El permiso de Android se muestra por separado.
- **Enviar prueba ahora** muestra una notificación solo al pulsarlo; no activa el interruptor ni programa un despertador.
- **Sincronizar avisos ahora** reconcilia los próximos siete días con el servidor. La pantalla muestra la fecha de la última sincronización y los avisos planificados.

Los avisos se calculan a partir de actividades aceptadas: al final de bloques de 20–89 minutos, o 15 minutos antes del final de bloques de al menos 90 minutos. Se separan al menos 75 minutos y se limita el número planificado por día (cuatro inicialmente). Se excluyen actividades completadas, sueño, propuestas pendientes y marcadores `[PROVISIONAL]` o `[CONDICIONAL]`. No se planifican dentro del descanso ni antes de la hora configurada para despertar; además se deja un margen antes del descanso. El cálculo usa `America/Mexico_City` y la configuración inicial de descanso es 22:30–06:45, todos los días.

Al abrir o reanudar la agenda, crear o cambiar actividades, aceptar propuestas, completar o borrar eventos, se reconcilian los avisos. Completar y borrar también cancela los avisos locales correspondientes. Tocar un seguimiento abre el registro de cómo vas; el contenido visible de la notificación es genérico y no expone títulos de actividades.

El teléfono conserva únicamente ajustes, identificadores, horas, categoría y estado necesarios para reconciliar, la fecha de sincronización y los identificadores de notificaciones. No se guardan títulos ni descripciones de actividades en esta caché. Los avisos ya programados pueden funcionar con la app cerrada y sin red; el receptor de arranque del plugin vuelve a programarlos después de un reinicio. No se consultan cambios externos mientras la app está cerrada: deben sincronizarse al volver a abrirla o con el botón. No hay FCM ni push del servidor. Una caché de más de siete días deja de utilizarse al reconciliar.

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
