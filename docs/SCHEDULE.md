# Horario personal y registro de actividades

## Navegación

La vista inicial es Día. El carrusel enfoca la actividad actual y permite recorrer
las anteriores y siguientes. Avanza cuando cambia el bloque, respetando un gesto
o una consulta manual reciente. El botón Ahora vuelve al momento actual.

Semana resume las actividades por día. Mes muestra semanas navegables: seleccionar
una semana abre Semana y seleccionar un día abre Día. También se puede abrir un
día directamente desde el calendario mensual. El chat usa la fecha seleccionada.

Los intervalos se conservan en UTC y se muestran en la hora local del dispositivo.
Las consultas del horario usan America/Mexico_City e incluyen actividades que
cruzan medianoche. Las propuestas del chat conservan la zona horaria al confirmarse.

## Precarga desde el plan autorizado

El archivo original describe días, objetivos, etapas y duraciones. El propietario
autorizó asignar horas provisionales. Esas horas se identifican en las tarjetas y
pueden ajustarse; no representan horarios fijos de clases, trabajo o sueño.

El plan privado conserva las fuentes y distingue información original de decisiones
de colocación. No se incorpora a Git. La importación continúa desde la fecha de
activación, sin recrear sesiones pasadas ni convertir vencimientos condicionales
antiguos en compromisos actuales.

Desde el backend, montando el plan privado en modo de sólo lectura:

```sh
python -m app.importing.schedule preview /import/schedule-plan.json \
  --user-id default_user --not-before 2026-09-15
python -m app.importing.schedule apply /import/schedule-plan.json \
  --user-id default_user --not-before 2026-09-15
```

`preview` informa lo que se crearía. `apply` crea los eventos y sus cambios de
sincronización en una transacción. Los IDs son estables: repetir el lote no duplica
eventos ni restaura los eliminados. Se conservan ediciones manuales y compromisos
existentes; las colisiones se informan sin sobreescribirlos.

## Huecos y memoria

Durante un hueco de hoy aparece «¿Qué estás haciendo ahora?». Al tocar esa tarjeta,
el chat pregunta por la actividad. La primera respuesta se guarda mediante
`POST /v1/agenda/check-ins` con fecha, hora y una clave que evita duplicados al
reintentar. Requiere `memory:write`; un error mantiene el texto para volver a enviar.

El chat recupera registros recientes sólo con `memory:read`. Los trata como
observaciones fechadas, no como hábitos permanentes ni como instrucciones. Las
memorias se pueden retirar mediante la API de memoria existente.

La invitación aparece dentro de la app; no es una notificación en segundo plano.
Completar, modificar o borrar una actividad no altera los documentos originales.
