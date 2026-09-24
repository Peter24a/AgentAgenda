# Archivos bidireccionales y calendario — 21 de septiembre de 2026

Actualizado: 2026-09-21, America/Mexico_City. Fuente: inspección del código y contenedores por SSH, consultas agregadas a PostgreSQL y pruebas sintéticas. Reanudado por petición explícita de Pedro; prioridad: utilidad, calidad de respuesta y calendario fiable, sin mostrar referencias técnicas al usuario.

## Estado comprobado

- `cite-server`: backend, worker y PostgreSQL activos; `/health` y disponibilidad autenticada del motor de IA responden HTTP 200.
- Inventario anterior a pruebas: 77 documentos activos, 78 revisiones (77 `ready`, 1 `needs_review`), 78 trabajos completados y ninguno pendiente. Se verificaron conteos, no se abrieron originales privados ni se comparó exhaustivamente contra la carpeta local.
- Agenda activa: 70 eventos reales, con el último inicio el 19 de septiembre en hora local. El 21 de septiembre aparece vacío; no se crearon compromisos por inferencia.
- El despliegue estaba en el mismo commit base que el proyecto local (`b6accfc`).

## Cambios

- App Android 1.1.0+2: clip en el chat para elegir foto o documento con el selector del sistema. Transferencia en streaming, progreso, límite de 50 MB y confirmación de guardado sólo después de completar la publicación en el servidor.
- «Mis archivos»: búsqueda por nombre, paginación de 30 elementos, errores y reintento. El catálogo omite los cuerpos extraídos y evita cargarlos por la relación de revisiones.
- Descarga autenticada, sin tokens en enlaces y sin redirecciones. Imágenes visibles con zoom; documentos se abren con una app compatible del teléfono. Los archivos descargados se almacenan en caché temporal privada; abrir en otra app permite conservar o compartir según esa app.
- Chat: «Dame mi CV», «Dame la foto …» y `/archivo nombre` devuelven enlaces reales del catálogo. Búsqueda por título/alias, no reconocimiento del contenido visual. Esta entrega se resuelve sin inferencia y respeta propietario y alcance de lectura; excluye orígenes NEVER_UPLOAD. No modifica la clasificación ni hace los originales privados accesibles al contexto del modelo.
- Fuentes técnicas siguen ocultas. Los enlaces visibles aparecen al pedir un archivo; las respuestas ordinarias no muestran índices de referencias ni listas de adjuntos no solicitadas. Se conserva procedencia interna. Un mensaje que sólo contiene una propuesta se muestra como un resumen legible, sin una burbuja vacía.
- El teléfono usa el historial durable del servidor; evita reenviar toda la conversación. Recupera la propuesta pendiente al volver a abrir el chat y oculta el bloque JSON de propuestas.
- Propuestas: acción `delete` para cancelar realmente, conservando borrado lógico y sincronización. Mover conserva el id. Fecha/hora inicial y final visibles antes de aprobar, incluso al cruzar medianoche. La tarjeta se retira al aceptar o rechazar.
- Instrucciones del modelo: distinguir fecha visualizada de hoy/mañana, conservar ids al mover y pedir precisión cuando falta información. Temperatura 0.3, salida máxima 2048 tokens; una salida truncada o propuesta inválida falla explícitamente.
- Suscripción SSE registrada antes de consultar el estado: una respuesta rápida de archivos no puede terminar en el hueco entre consulta y suscripción.

## Verificación

- Backend: **185 pruebas pasan, 1 omitida** (PostgreSQL live no configurado en la suite local). Base SQLite sintética, ejecución desde `/tmp`.
- Flutter: **25 pruebas pasan** y `flutter analyze` sin incidencias. Incluye visualización de las fechas y la cancelación antes de aprobar.
- Pixel 10 Pro XL real, backend desplegado, HTTPS y modelo local real: prueba de integración completada en 43 s. Subió PNG y TXT sintéticos, descargó bytes idénticos, encontró dos entradas y recuperó ambos enlaces por chat.
- En esa misma prueba: modelo generó una propuesta para crear un evento de enero de 2030, moverlo de día a 23:30–00:30 y cancelarlo. Se aprobaron las tres propuestas sintéticas y se verificaron id, fecha y hora UTC guardados y desaparición de la fecha anterior. Las pruebas retiran sólo sus documentos/eventos sintéticos mediante borrado lógico; los mensajes de prueba quedan como historial.
- Una repetición posterior del test encontró la sesión vacía: Flutter desinstala el APK de integración al terminar. Se restauraron las preferencias respaldadas, se renovó el emparejamiento del mismo dispositivo y se instaló el APK normal 1.1.0+2. La app normal volvió a renovar credenciales y consultar agenda con HTTP 200. La segunda ejecución no cuenta como una prueba aprobada.
- Los casos anteriores prueban recorridos concretos; no certifican comprensión perfecta de todas las expresiones temporales, resolución general de solapamientos, recurrencias o edición de toda una semana.

## Despliegue y recuperación

Backend y worker se reconstruyeron desde el código y se reiniciaron sin migraciones ni reemplazar volúmenes. Copia previa de código en el servidor:
`/home/cite/AgentAgenda/99_ARCHIVO/2026-09-21-bidirectional/backend-before.tar.gz`.
Imagen previa: `agentagenda-backend:before-20260921-files`.

Para volver al backend anterior, restaurar el código de esa copia, etiquetar la imagen anterior como `agentagenda-backend:local` y recrear backend/worker con Compose. No ejecutar `down -v`.

## Límites que siguen pendientes

- Guardar y devolver fotos funciona; la extracción disponible es OCR local. No se añadió interpretación visual multimodal de escenas ni búsqueda semántica de fotos.
- Subir un archivo no concede al modelo permiso permanente para analizarlo. Los originales sin clasificación siguen fuera del contexto automático. El aviso local de subida no es un mensaje durable de chat; el archivo sí persiste en la biblioteca.
- La búsqueda conversacional de archivos reconoce intenciones acotadas y nombres. `/archivo nombre` y la biblioteca son las rutas explícitas cuando una frase no se reconoce.
- Las sesiones de subida siguen en memoria del backend: reiniciar durante una carga requiere empezar de nuevo; no se implementó reanudación después de reiniciar.
- Renovación de credenciales durante una sesión larga, acceso offline completo, restauración integral desde respaldo, firma de distribución y evaluación más amplia de calidad siguen pendientes del plan general.
- El selector nativo se abrió en el Pixel desde «Subir documento». La prueba automatizada de transferencia usa archivos sintéticos mediante el mismo cliente; no se seleccionaron fotos personales ni se completó manualmente la elección de un archivo desde el selector.

Dependencias de la interfaz verificadas en documentación primaria: [file_picker](https://pub.dev/packages/file_picker/versions/10.3.10), [open_filex](https://pub.dev/packages/open_filex), [path_provider](https://pub.dev/packages/path_provider).
