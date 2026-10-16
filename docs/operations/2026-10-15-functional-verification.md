# Comprobación funcional de documentos, chat y agenda

Revisión del 15 de octubre de 2026 (America/Mexico_City), ejecutada contra el
servicio publicado y su espacio sintético de revisión. No se abrieron documentos
ni conversaciones de clientes. El inventario final tenía cinco espacios activos.

## Resultados reales

| Recorrido | Resultado |
| --- | --- |
| Activación sintética y revocación de su dispositivo | Correcto |
| Rechazo de credenciales de otro espacio | HTTP 401 |
| PDF de dos páginas: subida, extracción y descarga idéntica al original | Correcto |
| DOCX: subida, extracción y descarga idéntica al original | Correcto |
| Imagen PNG con texto impreso: OCR y descarga idéntica al original | Correcto |
| Catálogo y entrega del archivo mediante enlace del chat | Correcto |
| Descarga sin sesión | HTTP 401 |
| Búsqueda y análisis conversacional de un archivo recién subido sin clasificación | No disponible; falta el flujo de autorización |
| Búsqueda y respuesta con hechos y citas tras autorizar exclusivamente el PDF sintético | Correcto |
| Propuesta generada por el modelo, pendiente hasta confirmar | Correcto tras la corrección |
| Recuperación de propuesta y confirmación; reintento sin duplicar | Correcto tras la corrección |
| Hora local, movimiento, rechazo y cancelación | Correcto |

La repetición posterior al despliegue aprobó 22 de 24 comprobaciones. Las dos
negativas son manifestaciones del mismo pendiente: búsqueda y análisis de una
subida nueva sin autorización. No se contabilizan como fallos de extracción ni
como autorización implícita del propietario.

Los originales de prueba se marcaron eliminados del catálogo y el dispositivo
se revocó; la comprobación posterior rechazó sus credenciales. Son archivos y
conversaciones sintéticos; no se afirma purga física de registros de prueba.
Los informes privados permanecen en
`/srv/agentagenda/recovery/functional-check-39dfc4dd2b.json` y
`/srv/agentagenda/recovery/functional-check-a067e519d1.json`.

## Corrección de confirmaciones

Antes de la corrección, `get_turn_response` analizaba de nuevo el bloque del
asistente y generaba otro ID, distinto del de la propuesta persistida. Recuperar
el turno o reproducir su SSE podía entregar una propuesta que no existía al
confirmar.

El commit `94820ee` vincula la propuesta al turno y al propietario con un ID
estable. La respuesta recupera de la base los mismos items, zona horaria y
estado. Las propuestas antiguas sólo se recuperan si hay una coincidencia única
de contenido y ventana de generación; no se inventa una propuesta ante ausencia
o ambigüedad. No se requiere migración de esquema ni actualización del APK.

La batería completa del backend terminó con **243 pruebas aprobadas y 2 omitidas**
por falta de configuración PostgreSQL opcional. Las verificaciones de producción
anteriores sí ejecutaron el recorrido sobre las bases PostgreSQL reales del
espacio sintético; no sustituyen todas las pruebas opcionales de concurrencia.
También se actualizó la expectativa de una prueba de métricas para conservar su
restricción de metadatos tras añadir los conteos de dispositivos.

Release aplicado a backend y worker de los cinco espacios:
`agentagenda-backend:chat-proposal-recovery-20261015`.
Se verificaron salud, identidad de contenedores PostgreSQL, configuración de los
recursos y hashes de las fuentes dentro de las imágenes. Se comprobó ausencia de
generaciones recientes antes del corte. El respaldo cifrado previo y la reversión
privada están en
`/srv/agentagenda/recovery/deploy-chat-proposal-recovery-20261015/`.

## Pendiente documental

`document_storage.complete_upload` crea el original, su revisión y el trabajo de
extracción, pero no clasifica el documento para contexto del modelo.
`context_visibility` excluye deliberadamente originales no clasificados. Existen
clasificaciones y grants por revisión y destinatario en el modelo, pero falta un
recorrido de API/interfaz para que el propietario los autorice y revoque.

El siguiente cambio debe ofrecer autorización explícita de análisis por documento
/revisión y destinatario, mostrar su estado y permitir revocarla. No debe marcar
como SAFE toda la biblioteca ni ampliar permisos de documentos personales por el
mero hecho de haberlos subido. La autorización manual utilizada en la prueba se
aplicó sólo al PDF sintético conocido; no está disponible actualmente como
experiencia de usuario.

## Alcance

Se probaron API, extracción, modelo real, recuperación y persistencia en servidor.
No se comprobó en un teléfono físico la apertura con otras apps, notificaciones,
restricciones de batería, todas las variantes de escaneo ni cada pantalla de la
versión distribuida por Play. No se presenta esta revisión como garantía de
funcionamiento universal.
