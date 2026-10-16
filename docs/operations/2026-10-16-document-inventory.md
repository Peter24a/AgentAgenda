# Conteo por título y comparación documental

Cambio de servidor solicitado el 15 de octubre de 2026 (America/Mexico_City).
No modifica Android, su APK ni los contratos obligatorios del chat.

## Comportamiento

- Las preguntas de conteo y búsqueda consultan todos los títulos disponibles del
  propietario. Se normalizan acentos, mayúsculas y plurales comunes; los términos
  se buscan como palabras completas. No se confunden alias o nombres de archivo
  con títulos. Cada documento cuenta una vez y enlaza su revisión más reciente.
- Se muestran hasta 20 resultados, indicando el total completo. Los eliminados,
  documentos de otro propietario y los marcados NEVER_UPLOAD quedan excluidos.
- Un conteo explícito de documentos por título sólo consulta metadatos. Preguntar
  cuántos reconocimientos se han obtenido o pedir comparar duplicados añade la
  inspección de las revisiones autorizadas para el dispositivo actual.
- La comparación usa hashes de archivo y texto extraído normalizado idéntico.
  Los textos parecidos se presentan como posibles duplicados, sin fusionarlos:
  cambiar destinatario, fecha o folio puede indicar otro reconocimiento.
- No se leen textos ni hashes de revisiones sin permiso. Se informa cuántos
  documentos están autorizados y cómo autorizar los restantes individualmente.
  Revocaciones y versiones nuevas conservan las barreras de permiso existentes.
- No se afirma que documentos, grupos de texto y reconocimientos obtenidos sean
  equivalentes. Un archivo puede contener varios reconocimientos o pertenecer
  a otra persona. No se borran ni fusionan documentos.
- Las copias exactas se comprueban en todos los autorizados; la búsqueda de
  similitudes se limita a 100 textos de hasta 20 000 caracteres y lo indica si
  hay exclusiones. Textos de menos de 80 caracteres no prueban copias de contenido.
- Las respuestas son deterministas, locales y compatibles con el SSE instalado;
  los originales y metadatos de esta operación no se envían al modelo.

## Verificación local

391 pruebas aprobadas, 2 omitidas por configuración opcional de PostgreSQL.
Las 21 pruebas nuevas cubren conteos completos, filtrado por propietario,
NEVER_UPLOAD/eliminados, últimas versiones, metadatos sin lectura de texto,
archivos idénticos, texto normalizado equivalente, plantillas parecidas de
personas distintas, hashes inválidos, permisos por dispositivo/revisión,
revocación, documentos sin versión y respuesta SSE de Android sin llamar al modelo.

La revisión final agregó dos casos (23 pruebas específicas aprobadas) para
buscar títulos que contienen «agenda» y formular la petición como «puedes
buscar…». El total de 391 corresponde a la ejecución completa anterior a esos
dos casos; no se suman ejecuciones solapadas.

## Producción

Release final `agentagenda-backend:document-inventory-20261016-r2`, código
`527d9c8`. Backend y worker actualizados en los seis espacios, con respaldo
cifrado, comprobación de hashes de fuentes, salud, autenticación SARA y
conservación de contenedores PostgreSQL/configuración/volúmenes.
Reversión privada:
`/srv/agentagenda/recovery/deploy-document-inventory-20261016-r2/rollback.py`.

**13/13 comprobaciones aprobadas en producción**, sobre el espacio sintético:
activación, aislamiento entre espacios, 12 documentos originales subidos y
extraídos, conteo completo a través del SSE de Android, ausencia de comparación
sin permiso, comparación con permiso parcial, aislamiento entre dispositivos,
revocación, agrupación de 11 copias equivalentes (10 adicionales), diferenciación
de otro destinatario/folio como parecido sin confirmar, descarga del original,
exclusión de eliminados y limpieza de fixtures/revocación de ambos dispositivos.
Informe privado:
`/srv/agentagenda/recovery/inventory-release-check-bd47e3bfc5.json`.

Los archivos sintéticos se eliminaron lógicamente; no se afirma purga física.
No se modificaron documentos personales, la app ni su instalación. El teléfono
estaba bloqueado durante esta verificación; la comprobación de compatibilidad
se realizó con el formato exacto del endpoint SSE de la aplicación instalada.
