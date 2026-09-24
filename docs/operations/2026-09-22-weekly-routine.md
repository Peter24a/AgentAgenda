# Recuperación del horario como rutina semanal

Actualizado el 21 de septiembre de 2026, noche de Ciudad de México (22 de septiembre UTC).
Fuente: Pedro informó que su horario ya no aparecía y confirmó expresamente «Como rutina semanal».

## Causa y corrección

El servidor conservaba 69 bloques del horario corregido del 15–19 de septiembre. Eran ocurrencias con fecha, sin repetición. Por eso la semana del 21 aparecía vacía. La documentación de pausa del día 15 decía que ese candidato no se había aplicado, pero los eventos reales demostraron un estado posterior; se registró la discrepancia en PersonalLLM, sin inventar cuándo se había aplicado.

Se creó una rutina persistente con 90 bloques semanales, basada en el horario anterior y SEMANA_ACTUAL.md. Se añadió el lunes con sus clases ordinarias y se repuso la clase normal del miércoles; no se repite la excepción festiva del 16. Se conservaron descripciones provisionales/condicionales y no se inventó disponibilidad dominical. KHS tiene límite inclusivo 2026-10-05 y preparación EGEL 2026-12-03 según el plan; esas horas no se reasignan automáticamente a otros objetivos.

Primera materialización: 351 bloques del 21 de septiembre al 18 de octubre, sin conflictos. Los 140 registros previos del propietario, incluidos borrados históricos y pruebas anteriores, conservaron título, fechas, estado de borrado y versión. El horario no certifica actividades realizadas ni restablece casillas de completado.

## Continuidad y control

`weekly_routines` conserva la plantilla, propietario, zona horaria y estado. El worker revisa cada cinco minutos si hace falta completar el horizonte móvil de 28 días. Las ocurrencias tienen identidad estable por rutina/bloque/fecha. Repetir el mantenimiento no duplica eventos; cambios manuales, cancelaciones y citas que ocupan un hueco se preservan. El mantenimiento sigue sin abrir la app; la visualización y avisos locales se actualizan al sincronizar el teléfono.

SARA 1.2.1+4 incluye en Avisos → Rutina semanal un interruptor para agregar automáticamente próximas semanas. Desactivarlo detiene las nuevas incorporaciones y conserva las actividades ya cargadas; no se presenta como una cancelación de todas las citas. Reactivarlo respeta las ocurrencias borradas o editadas. Cambiar una actividad individual no modifica el patrón de toda la serie.

La plantilla y previsualización privadas se guardan en `/home/peterpad/.local/share/AgentAgenda/reviews/2026-09-21-weekly/`. No están en git. Los documentos operativos de PersonalLLM se actualizaron con versiones previas verificadas en `99_ARCHIVO/2026-09-21_rutina_semanal_recuperada/`; sus cuatro nuevas revisiones se sincronizaron con SARA, conservando el permiso por destinatario para las dos OPT_IN.

## Verificación

- Backend: 193 pruebas aprobadas y una omitida. Incluyen renovación a la semana siguiente, zona horaria, cruce de medianoche, idempotencia, conservación de cambios/borrados, suspensión/reactivación de generación, aislamiento de propietario, conflictos y fechas límite.
- Flutter: 22 pruebas aprobadas; análisis sin incidencias y APK compilado.
- PostgreSQL real: previsualización 351 altas, cero conflictos; aplicación 351 altas. Comprobación de registros anteriores sin modificaciones. Nueva previsualización posterior comprueba idempotencia.
- Pixel real: versión instalada conservando sesión. La app muestra 18 actividades del lunes 21 y 90 en la semana 21–27, con las clases y el descanso nocturno recuperados.
- Migración `b22c01` aplicada; backend saludable y worker activo.

## Recuperación

Antes del cambio se conservaron base y código en `/home/cite/AgentAgenda/99_ARCHIVO/2026-09-22-weekly/` (`database.dump`, `backend-before.tar.gz`). Imagen previa `agentagenda-backend:before-20260922-weekly`. Restaurar sólo la imagen anterior detiene el nuevo mantenimiento, pero conserva los eventos ya creados; no vaciar volúmenes ni restaurar la base completa sin considerar las escrituras posteriores. La rutina se puede desactivar mediante su control autenticado sin borrar historia.

Comprobaciones finales: segunda previsualización con cero altas y 351 sin cambios. En el Pixel, Avisos → Rutina semanal muestra «Mi horario de estudio y prácticas — Repetición semanal activa». Las cuatro revisiones actualizadas del contexto terminaron en estado `ready`.
